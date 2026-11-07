#!/usr/bin/env python3
"""Generate ``openapi/breaking-vectors.json``: the breaking-change rules of DESIGN.md 3.1 as cases.

    uv run python codegen/breaking_vectors.py          # write the file
    uv run python codegen/breaking_vectors.py --check  # fail when the file is not current

The file is the contract of the spec sync's breaking-change detector in all seven server
SDKs. It is generated here and copied byte for byte into the other six repositories,
whose tests run every case through their own detector; a rule change lands here first.

Every case below is written by hand: two minimal OpenAPI documents, ``before`` and
``after``, whose operations carry ``x-didit-sdk`` (``server`` true or false), and the
expected result, checked against DESIGN.md 3.1 rather than copied from the detector. The
generator runs ``spec_sync.classify`` on each case and refuses to write the file while the
detector disagrees, so the file and this repository's detector never differ.

The file is ``{"version": 1, "rules": "docs/DESIGN.md section 3.1", "generator":
"codegen/breaking_vectors.py", "cases": [...]}``. Each case has:

- ``name``: unique, kebab-case.
- ``rule``: the DESIGN.md 3.1 bullet it covers, by its opening words: ``Responses``,
  ``Requests``, ``Operations``, ``Unions``, ``Success statuses`` or ``Release notes``
  (the bullet "Every counted change reaches the release notes").
- ``before`` and ``after``: the upstream ``verification.json`` before and after the change.
- ``expect.type``: ``feat(spec)`` or ``chore(spec)``.
- ``expect.breaking``: the counted changes, distinct and sorted by code point (all ASCII);
  empty when the change is only listed.

A counted change is one line, ``<METHOD> <path> <where> <field>: <kind>``:

- ``<where>``: ``response`` (any 2xx body), ``request body``, ``query``, ``path`` or
  ``header``.
- ``<field>``: a dotted path; ``[]`` is an array's items, ``{}`` a map's values, and
  ``(oneOf N)`` or ``(anyOf N)`` the Nth variant (from 1) of the union after the change.
  A parameter's field starts with its name (``ids[]``). A whole body has no ``<field>``
  (``GET /things/ response: can now be null``).
- ``<kind>``: ``removed``, ``type <old> -> <new>``, ``can now be null``, ``no longer
  required``, ``now required`` (also a new required parameter or field), or ``enum value
  <value> removed`` with the value as JSON (``enum value "closed" removed``).
- Two kinds belong to the operation and have no ``<where> <field>``: ``<METHOD> <path>:
  body now required`` and ``<METHOD> <path>: operation removed``.
- A type is a JSON type name, ``string (date)``, ``string (date-time)`` or ``string
  (binary)`` for the typed formats, or ``any`` for a schema without a type. Several types
  are joined with ``|`` in sorted order. A union's variants, or a method's 2xx bodies,
  give one type each, so ``type object|object -> object`` is an object variant (or the only
  body of a removed status) that went away.
"""

from __future__ import annotations

import argparse
import copy
import json
import pathlib
import re
import sys
from typing import Any

import spec_sync

REPO = pathlib.Path(__file__).resolve().parents[1]
OUTPUT = REPO / "openapi" / "breaking-vectors.json"
GENERATOR = "codegen/breaking_vectors.py"
# The rule of each case -> how its bullet opens in DESIGN.md 3.1.
RULES = {
    "Responses": "- Responses (",
    "Requests": "- Requests (",
    "Operations": "- Operations:",
    "Unions": "- Unions (",
    "Success statuses": "- Success statuses:",
    "Release notes": "- Every counted change reaches the release notes",
}
NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
# A field: names, ".", "[]", "{}" and "(oneOf N)" / "(anyOf N)".
FIELD = r"(?:[^\s:()]+|\((?:oneOf|anyOf) [1-9][0-9]*\))+"
KIND = (
    r"(?:removed|type \S.* -> \S.*|can now be null|no longer required|now required"
    r"|enum value .+ removed)"
)
BREAKING = re.compile(
    r"(?:GET|PUT|POST|DELETE|PATCH|HEAD|OPTIONS) /\S*"
    r"(?:: (?:body now required|operation removed)"
    rf"|(?: response| request body)(?: {FIELD})?: {KIND}"
    rf"| (?:query|path|header) {FIELD}: {KIND})"
)
Json = Any

# Building blocks ----------------------------------------------------------------------------

STRING: Json = {"type": "string"}
INTEGER: Json = {"type": "integer"}


def document(paths: Json, schemas: Json = None) -> Json:
    doc: Json = {
        "openapi": "3.1.0",
        "info": {"title": "Breaking-change vectors", "version": "1.0.0"},
        "paths": paths,
    }
    if schemas:
        doc["components"] = {"schemas": schemas}
    return doc


def naming(method: str, resource: str = "things", *, server: bool = True) -> Json:
    auth = "api_key" if server else "device_token"
    return {"resource": resource, "method": method, "auth": auth, "server": server}


def ok(schema: Json, description: str = "OK") -> Json:
    return {"description": description, "content": {"application/json": {"schema": schema}}}


def operation(
    method: str,
    *,
    resource: str = "things",
    server: bool = True,
    parameters: Json = None,
    body: Json = None,
    body_required: bool = False,
    response: Json = None,
    responses: Json = None,
) -> Json:
    """One operation named ``resource.method``; a 200 JSON ``response`` unless ``responses``."""
    op: Json = {"x-didit-sdk": naming(method, resource, server=server)}
    if parameters:
        op["parameters"] = parameters
    if body is not None:
        op["requestBody"] = {"content": {"application/json": {"schema": body}}}
        if body_required:
            op["requestBody"]["required"] = True
    op["responses"] = responses if responses is not None else {"200": ok(response or THING)}
    return op


def obj(properties: Json, required: tuple[str, ...] = ()) -> Json:
    out: Json = {"type": "object", "properties": properties}
    if required:
        out["required"] = list(required)
    return out


def param(name: str, where: str = "query", schema: Json = None, *, required: bool = False) -> Json:
    out: Json = {"name": name, "in": where, "schema": schema or STRING}
    if required or where == "path":
        out["required"] = True
    return out


def enum(*values: str) -> Json:
    return {"type": "string", "enum": list(values)}


def ref(name: str) -> Json:
    return {"$ref": f"#/components/schemas/{name}"}


def edit(schema: Json, **properties: Json) -> Json:
    """``schema`` with these properties replaced (None removes one, from ``required`` too)."""
    out = copy.deepcopy(schema)
    for name, value in properties.items():
        if value is None:
            del out["properties"][name]
            if name in out.get("required", []):
                out["required"].remove(name)
        else:
            out["properties"][name] = value
    return out


def requiring(schema: Json, *names: str) -> Json:
    return {**copy.deepcopy(schema), "required": list(names)}


ID = param("id", "path")
THING = obj(
    {"id": STRING, "name": STRING, "status": enum("active", "closed")},
    required=("id", "name", "status"),
)
JOB = obj({"job_id": STRING}, required=("job_id",))
NEW_THING = obj({"name": STRING, "note": STRING, "amount": INTEGER}, required=("name",))
CARD = obj({"kind": enum("card"), "last4": STRING}, required=("kind", "last4"))
BANK = obj({"kind": enum("bank"), "iban": STRING}, required=("kind", "iban"))
WALLET = obj({"kind": enum("wallet"), "address": STRING}, required=("kind", "address"))


def get_thing(response: Json = None, **options: Json) -> Json:
    """``GET /things/{id}/``, method ``things.retrieve``, returning ``response``."""
    parameters = [ID, *options.pop("parameters", [])]
    return document(
        {
            "/things/{id}/": {
                "get": operation("retrieve", parameters=parameters, response=response, **options)
            }
        }
    )


def list_things(*parameters: Json) -> Json:
    """``GET /things/``, method ``things.list``, with these query parameters."""
    response = obj({"results": {"type": "array", "items": THING}})
    return document(
        {"/things/": {"get": operation("list", parameters=list(parameters), response=response)}}
    )


def create_thing(body: Json = None, *, body_required: bool = False, **options: Json) -> Json:
    """``POST /things/``, method ``things.create``, sending ``body``."""
    op = operation(
        "create", body=NEW_THING if body is None else body, body_required=body_required, **options
    )
    return document({"/things/": {"post": op}})


def get_payment(response: Json) -> Json:
    """``GET /payments/{id}/``, method ``payments.retrieve``, returning ``response``."""
    op = operation("retrieve", resource="payments", parameters=[ID], response=response)
    return document({"/payments/{id}/": {"get": op}})


def create_with_statuses(responses: Json) -> Json:
    """``POST /things/`` with these responses (a status without a body is ``None``)."""
    full = {
        status: ok(schema) if schema is not None else {"description": "No content"}
        for status, schema in responses.items()
    }
    return create_thing(responses=full)


def case(
    name: str,
    rule: str,
    before: Json,
    after: Json,
    breaking: list[str] | tuple[str, ...] = (),
    *,
    commit_type: str = "feat(spec)",
) -> Json:
    return {
        "name": name,
        "rule": rule,
        "before": before,
        "after": after,
        "expect": {"type": commit_type, "breaking": sorted(breaking)},
    }


# The cases ----------------------------------------------------------------------------------


def _responses() -> list[Json]:
    rule = "Responses"
    thing = "GET /things/{id}/ response"
    dated = edit(THING, created_at=STRING, born_on={"type": "string", "format": "date"})
    owned = edit(THING, owner=obj({"email": STRING}))
    nullable_email = {"anyOf": [STRING, {"type": "null"}]}
    scored = edit(THING, score={"type": "number"}, metadata={})
    files = edit(THING, file={"type": "string", "format": "binary"})
    counted = edit(THING, counts={"type": "object", "additionalProperties": INTEGER})
    listed = obj({"results": {"type": "array", "items": ref("Thing")}})
    extended = {"allOf": [ref("Base"), obj({"label": STRING})]}
    base = obj({"id": STRING, "created_at": STRING}, required=("id",))
    documented = copy.deepcopy(get_thing())
    get = documented["paths"]["/things/{id}/"]["get"]
    get["summary"] = "Retrieve a thing"
    get["description"] = "Returns one thing."
    get["responses"]["200"] = ok(
        {
            **edit(THING, name={**STRING, "description": "The name.", "example": "Box"}),
            "title": "Thing",
        },
        description="The thing",
    )
    return [
        case(
            "response-field-removed",
            rule,
            get_thing(),
            get_thing(edit(THING, name=None)),
            [f"{thing} name: removed"],
        ),
        case(
            "response-field-type-changed",
            rule,
            get_thing(),
            get_thing(edit(THING, id=INTEGER)),
            [f"{thing} id: type string -> integer"],
        ),
        case(
            "response-field-can-now-be-null",
            rule,
            get_thing(),
            get_thing(edit(THING, name={"type": ["string", "null"]})),
            [f"{thing} name: can now be null"],
        ),
        case(
            "response-nested-field-can-now-be-null",
            rule,
            get_thing(owned),
            get_thing(edit(owned, owner=obj({"email": nullable_email}))),
            [f"{thing} owner.email: can now be null"],
        ),
        case(
            "response-field-no-longer-required",
            rule,
            get_thing(),
            get_thing(requiring(THING, "id", "status")),
            [f"{thing} name: no longer required"],
        ),
        case(
            "response-enum-value-removed",
            rule,
            get_thing(),
            get_thing(edit(THING, status=enum("active"))),
            [f'{thing} status: enum value "closed" removed'],
        ),
        case(
            "response-typed-format-gained-and-changed",
            rule,
            get_thing(dated),
            get_thing(
                edit(
                    dated,
                    created_at={"type": "string", "format": "date-time"},
                    born_on={"type": "string", "format": "date-time"},
                )
            ),
            [
                f"{thing} born_on: type string (date) -> string (date-time)",
                f"{thing} created_at: type string -> string (date-time)",
            ],
        ),
        case(
            "response-typed-format-lost",
            rule,
            get_thing(files),
            get_thing(edit(files, file=STRING)),
            [f"{thing} file: type string (binary) -> string"],
        ),
        case(
            "response-value-becomes-untyped-or-typed",
            rule,
            get_thing(scored),
            get_thing(
                edit(scored, score={"description": "Any score."}, metadata=obj({"source": STRING}))
            ),
            [f"{thing} metadata: type any -> object", f"{thing} score: type number -> any"],
        ),
        case(
            "response-map-value-type-changed",
            rule,
            get_thing(counted),
            get_thing(edit(counted, counts={"type": "object", "additionalProperties": STRING})),
            [f"{thing} counts{{}}: type integer -> string"],
        ),
        case(
            "response-ref-and-array-items",
            rule,
            document({"/things/": {"get": operation("list", response=listed)}}, {"Thing": THING}),
            document(
                {"/things/": {"get": operation("list", response=listed)}},
                {"Thing": edit(THING, name=None)},
            ),
            ["GET /things/ response results[].name: removed"],
        ),
        case(
            "response-all-of",
            rule,
            document(
                {
                    "/things/{id}/": {
                        "get": operation("retrieve", parameters=[ID], response=extended)
                    }
                },
                {"Base": base},
            ),
            document(
                {
                    "/things/{id}/": {
                        "get": operation("retrieve", parameters=[ID], response=extended)
                    }
                },
                {"Base": edit(base, id=INTEGER, created_at=None)},
            ),
            [f"{thing} created_at: removed", f"{thing} id: type string -> integer"],
        ),
        case(
            "response-field-added-is-listed",
            rule,
            get_thing(),
            get_thing(edit(THING, color=STRING)),
        ),
        case(
            "response-enum-value-added-is-listed",
            rule,
            get_thing(),
            get_thing(edit(THING, status=enum("active", "closed", "archived"))),
        ),
        case(
            "response-field-now-always-present-is-listed",
            rule,
            get_thing(requiring(THING, "id", "status")),
            get_thing(),
        ),
        case(
            "response-value-no-longer-null-is-listed",
            rule,
            get_thing(edit(THING, name={"type": ["string", "null"]})),
            get_thing(),
        ),
        case(
            "response-documentation-only", rule, get_thing(), documented, commit_type="chore(spec)"
        ),
    ]


def _requests() -> list[Json]:
    rule = "Requests"
    things, create = "GET /things/", "POST /things/"
    limit = param("limit", schema=INTEGER)
    status = param("status", schema=enum("active", "closed"))
    key = param("Idempotency-Key", "header")
    tags = {"type": "array", "items": enum("a", "b")}
    tagged = edit(NEW_THING, tags=tags)
    archive = operation("archive", parameters=[ID], response=JOB)
    reason = obj({"reason": STRING}, required=("reason",))
    archive_with_body = operation(
        "archive", parameters=[ID], response=JOB, body=reason, body_required=True
    )
    documented = copy.deepcopy(list_things(limit))
    documented["paths"]["/things/"]["get"]["parameters"][0].update(
        description="How many things to return.", example=10
    )
    return [
        case(
            "query-parameter-removed",
            rule,
            list_things(limit),
            list_things(),
            [f"{things} query limit: removed"],
        ),
        case(
            "header-parameter-removed",
            rule,
            create_thing(parameters=[key]),
            create_thing(),
            [f"{create} header Idempotency-Key: removed"],
        ),
        case(
            "request-body-field-removed",
            rule,
            create_thing(),
            create_thing(edit(NEW_THING, note=None)),
            [f"{create} request body note: removed"],
        ),
        case(
            "query-parameter-type-changed",
            rule,
            list_things(limit),
            list_things(param("limit", schema=STRING)),
            [f"{things} query limit: type integer -> string"],
        ),
        case(
            "path-parameter-type-changed",
            rule,
            get_thing(),
            document(
                {
                    "/things/{id}/": {
                        "get": operation("retrieve", parameters=[param("id", "path", INTEGER)])
                    }
                }
            ),
            ["GET /things/{id}/ path id: type string -> integer"],
        ),
        case(
            "request-body-field-type-changed",
            rule,
            create_thing(),
            create_thing(
                edit(
                    NEW_THING, amount={"type": "number"}, note={"type": "string", "format": "date"}
                )
            ),
            [
                f"{create} request body amount: type integer -> number",
                f"{create} request body note: type string -> string (date)",
            ],
        ),
        case(
            "new-required-parameter",
            rule,
            list_things(),
            list_things(param("cursor", required=True)),
            [f"{things} query cursor: now required"],
        ),
        case(
            "new-required-body-field",
            rule,
            create_thing(),
            create_thing(requiring(edit(NEW_THING, currency=STRING), "name", "currency")),
            [f"{create} request body currency: now required"],
        ),
        case(
            "optional-parameter-becomes-required",
            rule,
            list_things(limit),
            list_things(param("limit", schema=INTEGER, required=True)),
            [f"{things} query limit: now required"],
        ),
        case(
            "optional-body-field-becomes-required",
            rule,
            create_thing(),
            create_thing(requiring(NEW_THING, "name", "note")),
            [f"{create} request body note: now required"],
        ),
        case(
            "body-becomes-required",
            rule,
            create_thing(),
            create_thing(body_required=True),
            [f"{create}: body now required"],
        ),
        case(
            "new-required-body",
            rule,
            document({"/things/{id}/archive/": {"post": archive}}),
            document({"/things/{id}/archive/": {"post": archive_with_body}}),
            [
                "POST /things/{id}/archive/ request body reason: now required",
                "POST /things/{id}/archive/: body now required",
            ],
        ),
        case(
            "query-enum-value-removed",
            rule,
            list_things(status),
            list_things(param("status", schema=enum("active"))),
            [f'{things} query status: enum value "closed" removed'],
        ),
        case(
            "request-body-array-item-enum-value-removed",
            rule,
            create_thing(tagged),
            create_thing(edit(tagged, tags={"type": "array", "items": enum("a")})),
            [f'{create} request body tags[]: enum value "b" removed'],
        ),
        case(
            "request-body-ref-field-removed",
            rule,
            document(
                {"/things/": {"post": operation("create", body=ref("NewThing"))}},
                {"NewThing": NEW_THING},
            ),
            document(
                {"/things/": {"post": operation("create", body=ref("NewThing"))}},
                {"NewThing": edit(NEW_THING, note=None)},
            ),
            [f"{create} request body note: removed"],
        ),
        case(
            "parameter-can-now-be-null-is-listed",
            rule,
            list_things(limit),
            list_things(param("limit", schema={"type": ["integer", "null"]})),
        ),
        case(
            "body-field-can-now-be-null-is-listed",
            rule,
            create_thing(),
            create_thing(edit(NEW_THING, note={"anyOf": [STRING, {"type": "null"}]})),
        ),
        case(
            "parameter-no-longer-required-is-listed",
            rule,
            list_things(param("limit", schema=INTEGER, required=True)),
            list_things(limit),
        ),
        case(
            "body-field-no-longer-required-is-listed",
            rule,
            create_thing(),
            create_thing(requiring(NEW_THING)),
        ),
        case(
            "body-no-longer-required-is-listed",
            rule,
            create_thing(body_required=True),
            create_thing(),
        ),
        case("optional-parameter-added-is-listed", rule, list_things(), list_things(limit)),
        case(
            "optional-body-field-added-is-listed",
            rule,
            create_thing(),
            create_thing(edit(NEW_THING, color=STRING)),
        ),
        case(
            "request-enum-value-added-is-listed",
            rule,
            list_things(status),
            list_things(param("status", schema=enum("active", "closed", "archived"))),
        ),
        case(
            "request-documentation-only",
            rule,
            list_things(limit),
            documented,
            commit_type="chore(spec)",
        ),
    ]


def _operations() -> list[Json]:
    rule = "Operations"
    retrieve = operation("retrieve", parameters=[ID])
    delete = operation("delete", parameters=[ID], response=JOB)
    device = operation(
        "retrieve", resource="devices", server=False, parameters=[ID, param("fields")]
    )
    device_after = operation(
        "retrieve",
        resource="devices",
        server=False,
        parameters=[ID],
        response=edit(THING, name=None),
    )
    renamed = copy.deepcopy(retrieve)
    renamed["x-didit-sdk"]["method"] = "get"
    gone = operation("retrieve", parameters=[ID], response=edit(THING, name=None))
    return [
        case(
            "operation-removed",
            rule,
            document({"/things/{id}/": {"get": retrieve, "delete": delete}}),
            document({"/things/{id}/": {"get": retrieve}}),
            ["DELETE /things/{id}/: operation removed"],
        ),
        case(
            "operation-no-longer-on-server-sdks",
            rule,
            document({"/things/{id}/": {"get": retrieve}}),
            document(
                {
                    "/things/{id}/": {
                        "get": {**retrieve, "x-didit-sdk": naming("retrieve", server=False)}
                    }
                }
            ),
            ["GET /things/{id}/: operation removed"],
        ),
        case(
            "server-false-operation-removed-is-listed",
            rule,
            document({"/things/{id}/": {"get": retrieve}, "/device/things/{id}/": {"get": device}}),
            document({"/things/{id}/": {"get": retrieve}}),
        ),
        case(
            "server-false-operation-changes-are-listed",
            rule,
            document({"/device/things/{id}/": {"get": device}}),
            document({"/device/things/{id}/": {"get": device_after}}),
        ),
        case(
            "operation-added-is-listed",
            rule,
            document({"/things/{id}/": {"get": retrieve}}),
            document({"/things/{id}/": {"get": retrieve, "delete": delete}}),
        ),
        case(
            "moved-operation-changes-count-under-its-new-path",
            rule,
            document({"/things/{id}/": {"get": retrieve}}),
            document({"/items/{id}/": {"get": gone}}),
            ["GET /items/{id}/ response name: removed"],
        ),
        case(
            "moved-operation-unchanged-is-listed",
            rule,
            document({"/things/{id}/": {"get": retrieve}}),
            document({"/items/{id}/": {"get": retrieve}}),
        ),
        case(
            "renamed-method-is-listed",
            rule,
            document({"/things/{id}/": {"get": retrieve}}),
            document({"/things/{id}/": {"get": renamed}}),
        ),
    ]


def _unions() -> list[Json]:
    rule = "Unions"
    payment = "GET /payments/{id}/ response"
    bank = edit(BANK, iban=INTEGER)
    titled = {**CARD, "title": "Card payment"}
    by_email = obj({"email": STRING}, required=("email",))
    by_phone = obj({"phone": STRING, "country_code": STRING}, required=("phone",))
    contact = document(
        {
            "/contacts/": {
                "post": operation(
                    "create", resource="contacts", body={"anyOf": [by_email, by_phone]}
                )
            }
        }
    )
    contact_after = document(
        {
            "/contacts/": {
                "post": operation(
                    "create",
                    resource="contacts",
                    body={"anyOf": [by_email, edit(by_phone, country_code=None)]},
                )
            }
        }
    )
    return [
        case(
            "union-variant-added-and-paired-variant-changed",
            rule,
            get_payment({"oneOf": [CARD, BANK]}),
            get_payment({"oneOf": [CARD, bank, WALLET]}),
            [f"{payment} (oneOf 2).iban: type string -> integer"],
        ),
        case(
            "union-variants-reordered-and-paired-variant-changed",
            rule,
            get_payment({"oneOf": [CARD, BANK]}),
            get_payment({"oneOf": [bank, CARD]}),
            [f"{payment} (oneOf 1).iban: type string -> integer"],
        ),
        case(
            "union-variant-removed",
            rule,
            get_payment({"oneOf": [CARD, BANK]}),
            get_payment({"oneOf": [CARD]}),
            [f"{payment}: type object|object -> object"],
        ),
        case(
            "schema-becomes-union-compared-with-its-variant",
            rule,
            get_payment(CARD),
            get_payment({"oneOf": [edit(CARD, last4=INTEGER), BANK]}),
            [f"{payment} (oneOf 1).last4: type string -> integer"],
        ),
        case(
            "request-union-variant-field-removed",
            rule,
            contact,
            contact_after,
            ["POST /contacts/ request body (anyOf 2).country_code: removed"],
        ),
        case(
            "union-variant-added-is-listed",
            rule,
            get_payment({"oneOf": [CARD, BANK]}),
            get_payment({"oneOf": [CARD, BANK, WALLET]}),
        ),
        case(
            "union-variants-reordered-is-listed",
            rule,
            get_payment({"oneOf": [CARD, BANK]}),
            get_payment({"oneOf": [BANK, CARD]}),
        ),
        case(
            "union-variant-title-renamed-is-listed",
            rule,
            get_payment({"oneOf": [titled, BANK]}),
            get_payment({"oneOf": [{**titled, "title": "Card charge"}, BANK]}),
        ),
    ]


def _statuses() -> list[Json]:
    rule = "Success statuses"
    create = "POST /things/ response"
    return [
        case(
            "added-status-without-body",
            rule,
            create_with_statuses({"200": THING}),
            create_with_statuses({"200": THING, "204": None}),
            [f"{create}: can now be null"],
        ),
        case(
            "removed-status-whose-body-no-other-returns",
            rule,
            create_with_statuses({"200": THING, "202": JOB}),
            create_with_statuses({"200": THING}),
            [f"{create}: type object|object -> object"],
        ),
        case(
            "removed-status-whose-body-has-another-type",
            rule,
            create_with_statuses({"200": STRING, "202": INTEGER}),
            create_with_statuses({"200": STRING}),
            [f"{create}: type integer|string -> string"],
        ),
        case(
            "only-success-status-changed-compares-the-bodies",
            rule,
            create_with_statuses({"200": THING}),
            create_with_statuses({"201": edit(THING, name=None)}),
            [f"{create} name: removed"],
        ),
        case(
            "added-status-with-another-body-is-listed",
            rule,
            create_with_statuses({"200": THING}),
            create_with_statuses({"200": THING, "202": JOB}),
        ),
        case(
            "added-status-with-the-same-body-is-listed",
            rule,
            create_with_statuses({"200": THING}),
            create_with_statuses({"200": THING, "201": THING}),
        ),
        case(
            "removed-status-whose-body-another-returns-is-listed",
            rule,
            create_with_statuses({"200": THING, "201": THING}),
            create_with_statuses({"200": THING}),
        ),
        case(
            "removed-status-without-body-is-listed",
            rule,
            create_with_statuses({"200": THING, "204": None}),
            create_with_statuses({"200": THING}),
        ),
        case(
            "only-success-status-changed-is-listed",
            rule,
            create_with_statuses({"200": THING}),
            create_with_statuses({"201": THING}),
        ),
    ]


def _release_notes() -> list[Json]:
    rule = "Release notes"
    wide = obj({f"field_{i:02d}": STRING for i in range(30)})
    retrieve = operation("retrieve", parameters=[ID, param("expand")])
    delete = operation("delete", parameters=[ID], response=JOB)
    create = operation("create", body=NEW_THING)
    after_retrieve = operation(
        "retrieve", parameters=[ID], response=edit(THING, id=INTEGER, color=STRING)
    )
    after_create = operation(
        "create", body=edit(NEW_THING, note={"type": ["string", "null"]}, amount=None)
    )
    return [
        case(
            "every-counted-change-is-listed",
            rule,
            get_thing(wide),
            get_thing(obj({})),
            [f"GET /things/{{id}}/ response field_{i:02d}: removed" for i in range(30)],
        ),
        case(
            "counted-changes-of-every-operation-are-listed",
            rule,
            document(
                {"/things/": {"post": create}, "/things/{id}/": {"get": retrieve, "delete": delete}}
            ),
            document(
                {"/things/": {"post": after_create}, "/things/{id}/": {"get": after_retrieve}}
            ),
            [
                "DELETE /things/{id}/: operation removed",
                "GET /things/{id}/ query expand: removed",
                "GET /things/{id}/ response id: type string -> integer",
                "POST /things/ request body amount: removed",
            ],
        ),
    ]


def cases() -> list[Json]:
    return [
        *_responses(),
        *_requests(),
        *_operations(),
        *_unions(),
        *_statuses(),
        *_release_notes(),
    ]


# The file -----------------------------------------------------------------------------------


def _check(found: list[Json]) -> list[str]:
    """Every problem with the cases: their form, and each result the detector disagrees with."""
    problems: list[str] = []
    names = [c["name"] for c in found]
    problems += [
        f"{n}: the name is used twice" for n in sorted({n for n in names if names.count(n) > 1})
    ]
    for rule in RULES:
        if sum(c["rule"] == rule for c in found) < 2:
            problems.append(f"rule {rule!r} has fewer than two cases")
    for c in found:
        expect = c["expect"]
        if not NAME.fullmatch(c["name"]):
            problems.append(f"{c['name']}: the name is not kebab-case")
        if c["rule"] not in RULES:
            problems.append(f"{c['name']}: unknown rule {c['rule']!r}")
        for line in expect["breaking"]:
            if not line.isascii() or not BREAKING.fullmatch(line):
                problems.append(f"{c['name']}: {line!r} is not a normalized breaking change")
        if expect["breaking"] and expect["type"] != "feat(spec)":
            problems.append(f"{c['name']}: a counted change is always feat(spec)")
        found_type, found_breaking = spec_sync.classify(c["before"], c["after"])
        if (found_type, found_breaking) != (expect["type"], expect["breaking"]):
            problems.append(
                f"{c['name']}: the detector gives {found_type} {json.dumps(found_breaking, indent=1)}, "
                f"the case expects {expect['type']} {json.dumps(expect['breaking'], indent=1)}"
            )
    return problems


def render() -> str:
    """The file's text; raises SystemExit when a case is malformed or the detector disagrees."""
    found = cases()
    problems = _check(found)
    if problems:
        raise SystemExit("breaking vectors not written:\n" + "\n".join(problems))
    data = {
        "version": 1,
        "rules": "docs/DESIGN.md section 3.1",
        "generator": GENERATOR,
        "cases": found,
    }
    return json.dumps(data, indent=2) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--check", action="store_true", help="fail when the committed file is not current"
    )
    args = parser.parse_args(argv)
    text = render()
    if args.check:
        current = OUTPUT.read_bytes() if OUTPUT.exists() else b""
        if current != text.encode():
            print(
                f"{OUTPUT.relative_to(REPO)} is not current: run uv run python {GENERATOR}",
                file=sys.stderr,
            )
            return 1
        return 0
    # LF on every platform: .gitattributes checks openapi/*.json out byte for byte.
    OUTPUT.write_text(text, "utf-8", newline="\n")
    print(f"wrote {OUTPUT.relative_to(REPO)} ({len(json.loads(text)['cases'])} cases)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
