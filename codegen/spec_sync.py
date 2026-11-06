#!/usr/bin/env python3
"""Sync ``openapi/`` with the published API contract (docs/DESIGN.md section 3.1).

    uv run python codegen/spec_sync.py --summary spec-sync-summary.md

Downloads https://docs.didit.me/openapi-25.json, openapi-auth.json and
openapi-authentication.json, and when any of them changed:

- checks that each download is an OpenAPI 3 document with paths, and writes
  nothing otherwise;
- writes them byte for byte to ``openapi/verification.json`` / ``account.json`` /
  ``authentication.json`` and records URL, SHA-256 and fetch time in
  ``openapi/SOURCE.json``;
- drops ``overlay.json`` entries that upstream now carries as ``x-didit-sdk``;
- never deletes a public method silently: a server method whose operation was
  removed, or whose naming changed upstream (a rename), is recorded, fully
  dereferenced, in ``openapi/deprecated-operations.json``, so the SDK keeps it
  as a deprecated method until the next minor version (``remove_in``). An
  operation whose SDK name reappears on another path counts as moved, not removed.
  Nothing is generated or deprecated from ``authentication.json``: that module is
  hand-written (DESIGN section 10) and a contract test holds it to the document;
- picks the commit type (DESIGN sections 3.1 and 13): ``feat`` when anything a
  caller can observe changed, ``chore`` when only documentation did. Never ``!``
  or a ``BREAKING CHANGE:`` footer: a change that mirrors the API is a minor version;
- writes a Markdown summary that opens with "Breaking changes", every change that
  can break typed code (a field or parameter whose type changed or that can now be
  null, a removed operation, field or enum value, a newly required parameter or
  request field) in parameters, request bodies and 2xx responses, following
  ``$ref``s and array items, then lists added, removed, renamed and changed
  operations and schemas;
- writes the commit message release-please reads (``--commit-message``): the sync
  line, then one nested ``api(spec):`` commit per breaking change, which
  ``release-please-config.json`` lists under "API changes that can break typed code".

It prints ``changed``, ``date`` and ``type`` (feat or chore) to ``$GITHUB_OUTPUT``
when that is set. The generator, not this script, regenerates the code.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import sys
import urllib.request
from typing import Any

REPO = pathlib.Path(__file__).resolve().parents[1]
UPSTREAM = {
    "verification.json": "https://docs.didit.me/openapi-25.json",
    "account.json": "https://docs.didit.me/openapi-auth.json",
    "authentication.json": "https://docs.didit.me/openapi-authentication.json",
}
PREFIXES = {
    "verification.json": "",
    "account.json": "account ",
    "authentication.json": "authentication ",
}
# Documents the generator never reads: their module is hand-written (DESIGN section 10).
HAND_WRITTEN = frozenset({"authentication.json"})
METHODS = ("get", "put", "post", "delete", "patch", "head", "options")
# Keys that document without changing what is sent or received. In a map of names
# (NAME_MAPS) a key is a name: a property called "description" is a field.
DOC_KEYS = frozenset(
    {"description", "summary", "title", "example", "examples", "externalDocs", "tags"}
)
NAME_MAPS = frozenset(
    {
        "properties",
        "patternProperties",
        "paths",
        "schemas",
        "responses",
        "parameters",
        "requestBodies",
        "headers",
        "securitySchemes",
        "content",
        "encoding",
        "variables",
        "mapping",
        "x-webhooks",
    }
)
# The extension a caller can observe (the webhook events). Every other x- key documents;
# x-didit-sdk is compared as the effective naming, together with overlay.json.
OBSERVABLE_EXTENSIONS = frozenset({"x-webhooks"})
# String formats with their own type in the generated code (datetime, date, bytes or a
# file): adding, removing or changing one changes the field's type.
TYPED_FORMATS = frozenset({"date-time", "date", "binary"})
MAX_NOTES = 25
MAX_DEPTH = 32
NO_DIFFERENCE = "descriptions, examples or other details changed"
Json = Any


class SpecSyncError(Exception):
    """A download is not a document the SDK can be generated from."""


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "didit-sdk-python spec-sync"})  # noqa: S310
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310 - fixed https URLs
        data: bytes = response.read()
    return data


def check_openapi(name: str, data: bytes) -> Json:
    """Parse ``data`` and refuse anything that is not an OpenAPI 3 document with paths
    (an error page or a maintenance JSON must never replace the contract)."""
    try:
        doc = json.loads(data)
    except ValueError as exc:
        raise SpecSyncError(f"{name}: the download is not JSON ({exc}).") from exc
    if not isinstance(doc, dict):
        raise SpecSyncError(f"{name}: the download is not a JSON object.")
    version = doc.get("openapi")
    if not isinstance(version, str) or not version.startswith("3."):
        raise SpecSyncError(
            f"{name}: the download is not an OpenAPI 3 document (openapi={version!r})."
        )
    paths = doc.get("paths")
    if not isinstance(paths, dict) or not paths:
        raise SpecSyncError(f"{name}: the download has no paths.")
    return doc


def _pointer(doc: Json, ref: str) -> Json:
    cur = doc
    for part in ref[2:].split("/"):
        cur = cur[part.replace("~1", "/").replace("~0", "~")]
    return cur


def dereference(doc: Json, node: Json, depth: int = 0) -> Json:
    """``node`` with every local ``$ref`` inlined (self-contained for deprecated operations)."""
    if depth > 64:
        return {}
    if isinstance(node, dict):
        if "$ref" in node and isinstance(node["$ref"], str):
            try:
                found = _pointer(doc, node["$ref"])
            except (KeyError, IndexError, TypeError):
                # A dangling reference upstream: keep it visible; the generator reports it.
                return {"x-unresolved-ref": node["$ref"]}
            target = dereference(doc, found, depth + 1)
            extra = {k: v for k, v in node.items() if k != "$ref"}
            return {**target, **extra} if isinstance(target, dict) else target
        return {k: dereference(doc, v, depth + 1) for k, v in node.items()}
    if isinstance(node, list):
        return [dereference(doc, v, depth + 1) for v in node]
    return node


def operations(doc: Json, prefix: str) -> dict[str, Json]:
    out: dict[str, Json] = {}
    for path, item in doc.get("paths", {}).items():
        for method in METHODS:
            if method in item:
                op = dict(item[method])
                if item.get("parameters"):
                    op["parameters"] = [*item["parameters"], *op.get("parameters", [])]
                out[f"{prefix}{method.upper()} {path}"] = op
    return out


# What a caller can observe ----------------------------------------------------------------


def _shape(node: Json, names: bool = False) -> Json:
    """``node`` without documentation, so that only what is sent or received compares.

    ``names`` marks a map whose keys are names (properties, paths, status codes...),
    which all stay. ``required`` and ``type`` lists compare in any order.
    """
    if isinstance(node, dict):
        out: dict[str, Json] = {}
        for k, v in node.items():
            if not names and (
                k in DOC_KEYS or (str(k).startswith("x-") and k not in OBSERVABLE_EXTENSIONS)
            ):
                continue
            if not names and k in ("required", "type") and isinstance(v, list):
                out[k] = sorted(v, key=str)
            else:
                out[k] = _shape(v, not names and k in NAME_MAPS)
        return out
    if isinstance(node, list):
        return [_shape(v) for v in node]
    return node


def observable(doc: Json) -> Json:
    """What a caller can observe in a document: no documentation, no ``info`` and no
    ``x-didit-sdk`` (the sync compares the effective naming instead)."""
    return _shape({k: v for k, v in doc.items() if k != "info"})


# Schema comparison ----------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Change:
    """One difference of an operation; ``breaking`` when it is in the DESIGN 3.1 list."""

    where: str  # "response", "request body", "parameter `limit` (query)", "operation"
    path: str  # the field, for example "registry_checks[].company.registry_data"; "" for all
    kind: str  # "can now be null", "type changed from string to object", "removed", ...
    breaking: bool = False

    def text(self) -> str:
        target = f"{self.where} `{self.path}`" if self.path else self.where
        return f"{target}: {self.kind}"


@dataclasses.dataclass(frozen=True)
class BreakingChange:
    """A change that can break typed code, as the pull request and the release notes list it."""

    operation: str
    where: str
    path: str
    kind: str

    def describe(self) -> str:
        # No "<" or ">": release-please escapes them in the release notes.
        target = " ".join(p for p in (self.where, f"`{self.path}`" if self.path else "") if p)
        return f"`{self.operation}`{' ' + target if target else ''}: {self.kind}"


def _null_only(schema: Json) -> bool:
    return isinstance(schema, dict) and (
        schema.get("type") == "null" or schema.get("enum") == [None]
    )


def _variants(schema: Json, keyword: str | None = None) -> list[Json]:
    """The oneOf/anyOf variants other than null (of ``keyword``, or of both)."""
    keywords = (keyword,) if keyword else ("oneOf", "anyOf")
    return [v for k in keywords for v in schema.get(k) or [] if not _null_only(v)]


def _nullable(schema: Json, depth: int = 0) -> bool:
    """Whether ``schema`` accepts null: a null type, ``nullable``, null in its enum, or a
    null or nullable oneOf/anyOf variant."""
    if not isinstance(schema, dict) or depth > MAX_DEPTH:
        return False
    raw = schema.get("type")
    if raw == "null" or (isinstance(raw, list) and "null" in raw):
        return True
    if schema.get("nullable") is True:
        return True
    if isinstance(schema.get("enum"), list) and None in schema["enum"]:
        return True
    members = schema.get("allOf")
    if "type" not in schema and members and all(_nullable(m, depth + 1) for m in members):
        return True
    return any(_nullable(v, depth + 1) for k in ("oneOf", "anyOf") for v in schema.get(k) or [])


def _single(schema: Json, depth: int = 0) -> Json:
    """``schema`` read as one type: ``allOf`` members merged into it, and a oneOf/anyOf
    with a single non-null variant replaced by that variant, so that ``anyOf: [X, null]``
    reads as a nullable X rather than as X's fields removed."""
    if not isinstance(schema, dict) or depth > MAX_DEPTH:
        return schema
    members = schema.get("allOf")
    if isinstance(members, list) and all(isinstance(m, dict) for m in members):
        merged = {k: v for k, v in schema.items() if k != "allOf"}
        for member in members:
            for key, value in _single(member, depth + 1).items():
                if key == "properties" and isinstance(value, dict):
                    merged["properties"] = {**value, **(merged.get("properties") or {})}
                elif key == "required" and isinstance(value, list):
                    merged["required"] = sorted({*(merged.get("required") or []), *value})
                else:
                    merged.setdefault(key, value)
        schema = merged
    variants = _variants(schema)
    if len(variants) != 1 or not isinstance(variants[0], dict):
        return schema
    rest = {k: v for k, v in schema.items() if k not in ("oneOf", "anyOf")}
    return _single({**variants[0], **rest}, depth + 1)


def _json_type(value: Json) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    return "array" if isinstance(value, list) else "object"


def _kinds(schema: Json, depth: int = 0) -> frozenset[str]:
    """The JSON types ``schema`` allows besides null, inferred when it has no ``type``
    (a union allows its variants' types); empty when it does not say."""
    if not isinstance(schema, dict) or depth > MAX_DEPTH:
        return frozenset()
    raw = schema.get("type")
    kinds = set(raw) if isinstance(raw, list) else ({raw} if isinstance(raw, str) else set())
    kinds.discard("null")
    if kinds:
        return frozenset(kinds)
    if any(k in schema for k in ("properties", "additionalProperties", "patternProperties")):
        return frozenset({"object"})
    if "items" in schema:
        return frozenset({"array"})
    variants = _variants(schema)
    if variants:
        found = [_kinds(v, depth + 1) for v in variants]
        return frozenset().union(*found) if all(found) else frozenset()
    for member in schema.get("allOf") or []:
        kinds |= _kinds(member, depth + 1)
    if not kinds:
        values = schema["enum"] if isinstance(schema.get("enum"), list) else []
        if "const" in schema:
            values = [schema["const"]]
        kinds = {_json_type(v) for v in values if v is not None}
    return frozenset(kinds)


def _type_names(schema: Json, kinds: frozenset[str]) -> str:
    """``kinds`` as the summary names them; a string with a typed format is its own type."""
    fmt = schema.get("format")
    return " or ".join(
        f"string ({fmt})" if kind == "string" and fmt in TYPED_FORMATS else kind
        for kind in sorted(kinds)
    )


def _enum(schema: Json) -> list[Json] | None:
    values = schema.get("enum")
    return [v for v in values if v is not None] if isinstance(values, list) else None


def _object_props(schema: Json) -> tuple[dict[str, Json], set[str]]:
    props: dict[str, Json] = {}
    required: set[str] = set()
    stack = [schema]
    while stack:
        cur = stack.pop()
        if not isinstance(cur, dict):
            continue
        props.update(cur.get("properties") or {})
        required |= {name for name in cur.get("required") or [] if isinstance(name, str)}
        stack.extend(cur.get("allOf") or [])
    return props, required


def _join(path: str, name: str) -> str:
    return f"{path}.{name}" if path else name


def diff_schema(
    old: Json,
    new: Json,
    where: str,
    path: str = "",
    *,
    request: bool,
    out: list[Change],
    depth: int = 0,
) -> None:
    """Append a :class:`Change` for every difference between two dereferenced schemas.

    Breaking (DESIGN 3.1, the same in requests and responses): a type change in either
    direction, a value that can now be null, a removed field, enum value or union
    variant, and in a request (``request``) a field that is newly required. Everything
    else is listed, not counted.
    """
    if depth > MAX_DEPTH or _shape(old) == _shape(new):
        return
    start = len(out)

    def note(kind: str, breaking: bool = False, at: str = path) -> None:
        out.append(Change(where, at, kind, breaking))

    if not isinstance(old, dict) or not isinstance(new, dict):
        note("schema replaced", True)
        return
    if _nullable(new) and not _nullable(old):
        note("can now be null", True)
    elif _nullable(old) and not _nullable(new):
        note("no longer accepts null" if request else "can no longer be null")
    old, new = _single(old), _single(new)
    old_kinds, new_kinds = _kinds(old), _kinds(new)
    before, after = _type_names(old, old_kinds), _type_names(new, new_kinds)
    if old_kinds and new_kinds and before != after:
        note(f"type changed from {before} to {after}", True)
        # A union's variants can change too; the type change already covers those removed.
        _diff_variants(old, new, where, path, request=request, out=out, depth=depth, retyped=True)
        return

    old_enum, new_enum = _enum(old), _enum(new)
    if old_enum is not None and new_enum is not None:
        for value in old_enum:
            if value not in new_enum:
                note(f"enum value {json.dumps(value, ensure_ascii=False)} removed", True)
        added = [v for v in new_enum if v not in old_enum]
        if added:
            note(f"enum values added {json.dumps(added, ensure_ascii=False)}")
    elif new_enum is not None:
        note(f"now limited to {json.dumps(new_enum, ensure_ascii=False)}")
    elif old_enum is not None:
        note("no longer limited to fixed values")

    old_props, old_req = _object_props(old)
    new_props, new_req = _object_props(new)
    # A union's fields live in its variants, compared below.
    if (old_props and new_props) or not (_variants(old) or _variants(new)):
        for name in sorted(set(old_props) - set(new_props)):
            note("removed", True, _join(path, name))
        for name in sorted(set(new_props) - set(old_props)):
            required = request and name in new_req
            note("added (required)" if required else "added", required, _join(path, name))
        for name in sorted(set(old_props) & set(new_props)):
            at = _join(path, name)
            if name in new_req and name not in old_req:
                note("now required" if request else "now always present", request, at)
            elif name in old_req and name not in new_req:
                note("no longer required" if request else "no longer always present", False, at)
            diff_schema(
                old_props[name], new_props[name], where, at,
                request=request, out=out, depth=depth + 1,
            )  # fmt: skip
    for key, suffix in (("items", "[]"), ("additionalProperties", "{}")):
        old_sub, new_sub = old.get(key), new.get(key)
        if isinstance(old_sub, dict) or isinstance(new_sub, dict):
            diff_schema(
                old_sub if isinstance(old_sub, dict) else {},
                new_sub if isinstance(new_sub, dict) else {},
                where, path + suffix, request=request, out=out, depth=depth + 1,
            )  # fmt: skip
    _diff_variants(old, new, where, path, request=request, out=out, depth=depth, retyped=False)
    if len(out) == start:
        note("other constraints changed (format, pattern, limits or default)")


def _union_keyword(schema: Json) -> str | None:
    return next((k for k in ("oneOf", "anyOf") if _variants(schema, k)), None)


def _compatible(old: Json, new: Json) -> bool:
    old_kinds, new_kinds = _kinds(old), _kinds(new)
    return not old_kinds or not new_kinds or old_kinds == new_kinds


def _field_names(schema: Json) -> set[str]:
    return set(_object_props(_single(schema))[0]) if isinstance(schema, dict) else set()


def _pair_variants(
    old: list[Json], new: list[Json]
) -> tuple[list[tuple[int, int]], list[int], list[int]]:
    """Pair each old union variant with the new one it became: an unchanged one first,
    then one with the same title, then one of the same type with the most fields in common.
    Returns the pairs (old and new position) and the positions left over on each side
    (variants removed and added)."""
    left_old, left_new = list(range(len(old))), list(range(len(new)))
    pairs: list[tuple[int, int]] = []

    def pair(i: int, j: int) -> None:
        pairs.append((i, j))
        left_old.remove(i)
        left_new.remove(j)

    def title(schema: Json) -> Json:
        return schema.get("title") if isinstance(schema, dict) else None

    for same in (
        lambda a, b: _shape(a) == _shape(b),
        lambda a, b: title(a) is not None and title(a) == title(b),
    ):
        for i in list(left_old):
            j = next((j for j in left_new if same(old[i], new[j])), None)
            if j is not None:
                pair(i, j)
    candidates = sorted(
        (-len(_field_names(old[i]) & _field_names(new[j])), i, j)
        for i in left_old
        for j in left_new
        if _compatible(old[i], new[j])
    )
    for _, i, j in candidates:
        if i in left_old and j in left_new:
            pair(i, j)
    return sorted(pairs, key=lambda p: p[1]), left_old, left_new


def _diff_variants(
    old: Json,
    new: Json,
    where: str,
    path: str,
    *,
    request: bool,
    out: list[Change],
    depth: int,
    retyped: bool,
) -> None:
    """Compare two unions variant by variant; a plain schema is a union of one, so that
    ``[X, null]`` against X loses no variant and X against ``[X', Y]`` compares X with X'.
    A variant added or removed never hides a change inside the others."""
    old_vars, new_vars = _variants(old) or [old], _variants(new) or [new]
    if len(old_vars) == 1 and len(new_vars) == 1:
        return  # compared as the schema itself
    keyword = _union_keyword(new) or _union_keyword(old)
    pairs, removed, added = _pair_variants(old_vars, new_vars)
    for i, j in pairs:
        at = f"{path}({keyword} {j + 1})" if len(new_vars) > 1 else path
        diff_schema(
            old_vars[i], new_vars[j], where, at, request=request, out=out, depth=depth + 1
        )
    if removed and not retyped:
        kind = f"type changed: {len(removed)} {keyword} variant(s) removed"
        out.append(Change(where, path, kind, True))
    if added:
        out.append(Change(where, path, f"{len(added)} {keyword} variant(s) added"))


def _parameter_where(key: tuple[str, str]) -> str:
    return f"parameter `{key[1]}` ({key[0]})"


def _parameters(doc: Json, op: Json) -> dict[tuple[str, str], Json]:
    found: dict[tuple[str, str], Json] = {}
    for parameter in dereference(doc, op.get("parameters") or []):
        if isinstance(parameter, dict):
            found[(str(parameter.get("in", "")), str(parameter.get("name", "")))] = parameter
    return found


def _content(doc: Json, node: Json) -> dict[str, Json]:
    """The schema of each media type of a request body or response."""
    node = dereference(doc, node)
    content = node.get("content") if isinstance(node, dict) else None
    if not isinstance(content, dict):
        return {}
    return {
        media: entry.get("schema") or {}
        for media, entry in content.items()
        if isinstance(entry, dict)
    }


def _successes(doc: Json, op: Json) -> dict[str, dict[str, Json]]:
    responses = op.get("responses") or {}
    return {
        str(status): _content(doc, responses[status])
        for status in sorted(responses, key=str)
        if str(status).startswith("2")
    }


def _diff_content(
    old: dict[str, Json], new: dict[str, Json], where: str, *, request: bool, out: list[Change]
) -> None:
    """Compare a body per media type; when none is shared, the first against the first,
    so that a body that changes content type, appears or disappears is compared too."""
    if old and new and set(old) != set(new):
        out.append(
            Change(where, "", f"content type {', '.join(sorted(old))} -> {', '.join(sorted(new))}")
        )
    pairs = [(m, m) for m in sorted(set(old) & set(new))]
    if not pairs and (old or new):
        old = old or {"": {}}
        new = new or {"": {}}
        pairs = [(min(old), min(new))]
    for before, after in pairs:
        diff_schema(old[before], new[after], where, request=request, out=out)


def describe_change(old_doc: Json, old: Json, new_doc: Json, new: Json) -> list[Change]:
    """Every difference of one operation (or of a method that moved to another one)."""
    found: list[Change] = []
    old_params, new_params = _parameters(old_doc, old), _parameters(new_doc, new)
    for key in sorted(set(old_params) - set(new_params)):
        found.append(Change(_parameter_where(key), "", "removed"))
    for key in sorted(set(new_params) - set(old_params)):
        required = new_params[key].get("required") is True
        found.append(
            Change(_parameter_where(key), "", "added (required)" if required else "added", required)
        )
    for key in sorted(set(old_params) & set(new_params)):
        where = _parameter_where(key)
        if old_params[key].get("required") is not True and new_params[key].get("required") is True:
            found.append(Change(where, "", "now required", True))
        diff_schema(
            old_params[key].get("schema") or {}, new_params[key].get("schema") or {}, where,
            request=True, out=found,
        )  # fmt: skip

    old_body, new_body = old.get("requestBody") or {}, new.get("requestBody") or {}
    if dereference(old_doc, old_body).get("required") is not True and (
        dereference(new_doc, new_body).get("required") is True
    ):
        found.append(Change("request body", "", "now required"))
    _diff_content(
        _content(old_doc, old_body), _content(new_doc, new_body), "request body",
        request=True, out=found,
    )  # fmt: skip

    # Every 2xx response both have; when the only success status changed (200 to 201),
    # the old body against the new one.
    old_responses, new_responses = _successes(old_doc, old), _successes(new_doc, new)
    statuses = [(s, s) for s in old_responses if s in new_responses]
    if not statuses and len(old_responses) == 1 and len(new_responses) == 1:
        statuses = [(next(iter(old_responses)), next(iter(new_responses)))]
        found.append(Change("response", "", f"status {statuses[0][0]} -> {statuses[0][1]}"))
    for before, after in statuses:
        _diff_content(
            old_responses[before], new_responses[after], "response", request=False, out=found
        )

    if old.get("deprecated") is not True and new.get("deprecated") is True:
        found.append(Change("operation", "", "marked deprecated upstream"))
    if old.get("x-didit-sdk") != new.get("x-didit-sdk") and new.get("x-didit-sdk") is not None:
        naming = json.dumps(new["x-didit-sdk"], sort_keys=True)
        found.append(Change("x-didit-sdk", "", f"now {naming}"))
    # One entry per change, even when several responses or media types share it.
    return list(dict.fromkeys(found))


def notes(changes: list[Change]) -> list[str]:
    """The summary's notes for one operation: breaking first, capped to stay readable."""
    if not changes:
        return [NO_DIFFERENCE]
    ordered = [c for c in changes if c.breaking] + [c for c in changes if not c.breaking]
    out = [c.text() + (" (breaking)" if c.breaking else "") for c in ordered]
    if len(out) > MAX_NOTES:
        out = [*out[:MAX_NOTES], f"and {len(out) - MAX_NOTES} more differences"]
    return out


# Versions -------------------------------------------------------------------------------


def _version() -> str:
    text = (REPO / "src" / "didit" / "_version.py").read_text("utf-8")
    match = re.search(r'__version__ = "([^"]+)"', text)
    return match.group(1) if match else "0.0.0"


def next_minor(version: str) -> str:
    """The version in which a method deprecated in ``version`` is deleted."""
    match = re.match(r"(\d+)\.(\d+)", version)
    if not match:
        return "0.1.0"
    return f"{match.group(1)}.{int(match.group(2)) + 1}.0"


# The sync -------------------------------------------------------------------------------


@dataclasses.dataclass
class SyncResult:
    changed: bool
    summary: str
    date: str = ""
    commit_type: str = "chore"  # "feat" or "chore" (DESIGN 3.1)
    breaking: list[BreakingChange] = dataclasses.field(default_factory=list)

    def commit_message(self) -> str:
        """What release-please reads (the pull request's ``BEGIN_COMMIT_OVERRIDE`` block):
        the sync, then one nested ``api(spec):`` commit per breaking change, every one of
        them. A type outside release-please's own list only splits off in a nested block."""
        message = f"{self.commit_type}(spec): sync API spec {self.date}\n"
        if self.breaking:
            message += "\n" + "".join(
                f"BEGIN_NESTED_COMMIT\napi(spec): {c.describe()}\nEND_NESTED_COMMIT\n"
                for c in self.breaking
            )
        return message


def _name(naming: Json) -> str:
    return f"{naming['resource']}.{naming['method']}"


def _hand_written_methods(naming: Json) -> set[str]:
    """The methods a hand-written module has for one operation: its own and its variants'."""
    if not naming or not naming.get("server"):
        return set()
    variants = [v["method"] for v in naming.get("variants") or [] if isinstance(v, dict)]
    return {f"{naming['resource']}.{m}" for m in (naming["method"], *variants)}


def sync(
    openapi_dir: pathlib.Path,
    downloads: dict[str, bytes],
    *,
    today: dt.date,
    now: dt.datetime,
    version: str | None = None,
) -> SyncResult:
    """Apply ``downloads`` (file name -> bytes) to ``openapi_dir``."""
    old_docs: dict[str, Json] = {}
    new_docs: dict[str, Json] = {}
    changed_files: list[str] = []
    for name, data in downloads.items():
        new_docs[name] = check_openapi(name, data)
        path = openapi_dir / name
        old_bytes = path.read_bytes() if path.exists() else b"{}"
        old_docs[name] = json.loads(old_bytes)
        if old_bytes != data:
            changed_files.append(name)
    if not changed_files:
        return SyncResult(False, "No upstream change.\n", today.isoformat())

    version = version or _version()
    remove_in = next_minor(version)
    overlay_path = openapi_dir / "overlay.json"
    overlay = json.loads(overlay_path.read_text("utf-8"))
    old_overlay = dict(overlay["operations"])
    deprecated_path = openapi_dir / "deprecated-operations.json"
    deprecated: dict[str, Any] = (
        json.loads(deprecated_path.read_text("utf-8"))
        if deprecated_path.exists()
        else {"description": "", "methods": {}}
    )
    deprecated.setdefault("methods", {})
    old_ops: dict[str, tuple[str, Json]] = {}
    new_ops: dict[str, tuple[str, Json]] = {}
    for name in downloads:
        for key, op in operations(old_docs[name], PREFIXES[name]).items():
            old_ops[key] = (name, op)
        for key, op in operations(new_docs[name], PREFIXES[name]).items():
            new_ops[key] = (name, op)
    hand_written = {
        key for key, (name, _) in [*old_ops.items(), *new_ops.items()] if name in HAND_WRITTEN
    }

    def old_naming(key: str) -> Json:
        return old_ops[key][1].get("x-didit-sdk") or old_overlay.get(key)

    def new_naming(key: str) -> Json:
        return new_ops[key][1].get("x-didit-sdk") or old_overlay.get(key)

    added = sorted(set(new_ops) - set(old_ops))
    removed = sorted(set(old_ops) - set(new_ops))
    common = sorted(set(old_ops) & set(new_ops))
    # Generated server method name -> the operation that provides it after the sync.
    new_server_names = {
        _name(n): key
        for key in new_ops
        if key not in hand_written and (n := new_naming(key)) and n.get("server")
    }
    old_server_names = {
        _name(n): key
        for key in old_ops
        if key not in hand_written and (n := old_naming(key)) and n.get("server")
    }

    lines: list[str] = [
        f"Spec sync {today.isoformat()}. Upstream files changed: {', '.join(changed_files)}.",
        "",
    ]
    breaking: list[BreakingChange] = []
    kept: list[str] = []

    def keep(naming: Json, key: str, reason: str, replacement: str | None) -> None:
        """Record a method that would disappear as deprecated until ``remove_in``."""
        doc_name, op = old_ops[key]
        method = _name(naming)
        if replacement:
            note = (
                f"Renamed to {replacement} on {today.isoformat()}; "
                f"this name is removed in version {remove_in}."
            )
        else:
            note = (
                f"Removed from the API contract on {today.isoformat()}; "
                f"this method is removed in version {remove_in}."
            )
        entry: dict[str, Any] = {
            "reason": reason,
            "operation_key": key,
            "x-didit-sdk": naming,
            "operation": dereference(old_docs[doc_name], op),
            "since": today.isoformat(),
            "deprecated_since": version,
            "remove_in": remove_in,
            "note": note,
        }
        if replacement:
            entry["replacement"] = replacement
        deprecated["methods"][method] = entry
        kept.append(method)

    def removed_operation(key: str, detail: str) -> None:
        breaking.append(BreakingChange(key, "", "", f"operation removed{detail}"))

    lines.append(f"## Added operations ({len(added)})")
    for key in added:
        n = new_naming(key)
        if n is None:
            lines.append(
                f"- `{key}`: **no SDK naming**; add an entry to `openapi/overlay.json` (DESIGN section 4)"
            )
        elif n.get("server"):
            lines.append(f"- `{key}` -> `{_name(n)}`")
        else:
            lines.append(f"- `{key}` (not exposed by server SDKs: {n['auth']})")
    lines.append("")

    lines.append(f"## Removed operations ({len(removed)})")
    for key in removed:
        n = old_naming(key)
        if n is None:
            lines.append(f"- `{key}`")
        elif not n.get("server"):
            lines.append(f"- `{key}` (not exposed by server SDKs)")
        elif key in hand_written:
            lines.append(f"- `{key}` (`{_name(n)}`, hand-written; see Authentication module)")
            removed_operation(key, f" (`{_name(n)}`)")
        elif _name(n) in new_server_names:
            lines.append(
                f"- `{key}` moved to `{new_server_names[_name(n)]}`; `{_name(n)}` keeps its name"
            )
        else:
            lines.append(
                f"- `{key}` (`{_name(n)}`): kept as a deprecated method until version {remove_in}, "
                "recorded in `openapi/deprecated-operations.json`"
            )
            removed_operation(
                key, f"; `{_name(n)}` stays as a deprecated method until version {remove_in}"
            )
            keep(n, key, "removed", None)
        overlay["operations"].pop(key, None)
    lines.append("")

    renames: list[str] = []
    for key in common:
        before, after = old_naming(key), new_naming(key)
        if key in hand_written or not before or not before.get("server"):
            continue
        if after and after.get("server") and _name(after) == _name(before):
            continue
        if _name(before) in new_server_names:
            continue  # another operation now provides the name (swapped or moved)
        if after is None:
            # The generator fails until the operation is named again, so this cannot
            # ship silently; the overlay entry decides whether the name survives.
            renames.append(
                f"- `{key}` lost its SDK naming: add `{_name(before)}` back to "
                "`openapi/overlay.json` (the generator fails until it is named)"
            )
        elif not after.get("server"):
            # Server SDKs never expose device or end-user token operations (DESIGN 4),
            # and an API key could not call it any more, so the method goes now.
            renames.append(
                f"- `{key}` (`{_name(before)}`) is no longer a server operation "
                f"(auth {after.get('auth')}); the method is removed"
            )
            removed_operation(
                key,
                f" from server SDKs: it now needs {after.get('auth')}, "
                f"and `{_name(before)}` is removed",
            )
        else:
            renames.append(
                f"- `{key}`: `{_name(before)}` renamed to `{_name(after)}`; the old name stays "
                f"as a deprecated alias until version {remove_in}"
            )
            keep(before, key, "renamed", _name(after))
    lines.append(f"## Renamed methods ({len(renames)})")
    lines.extend(renames)
    lines.append("")

    # A name that stays but now belongs to another operation: moved to a new path,
    # or reassigned (swapped, or reused by another operation). Compare what the
    # method sends and receives before and after.
    moves: list[str] = []
    for method in sorted(set(old_server_names) & set(new_server_names)):
        old_key, new_key = old_server_names[method], new_server_names[method]
        if old_key == new_key:
            continue
        old_name, old = old_ops[old_key]
        new_name, new = new_ops[new_key]
        if old_key in new_ops:
            moves.append(
                f"- `{method}` **(review)** now calls `{new_key}` instead of `{old_key}` "
                "(which is still in the API): a different operation under the same name"
            )
            continue
        changes = describe_change(old_docs[old_name], old, new_docs[new_name], new)
        found = notes(changes) if changes else ["same parameters, body and response"]
        marker = " **(breaking)**" if any(c.breaking for c in changes) else ""
        moves.append(
            f"- `{method}`{marker} moved from `{old_key}` to `{new_key}`: " + "; ".join(found)
        )
        breaking.extend(
            BreakingChange(new_key, c.where, c.path, c.kind) for c in changes if c.breaking
        )
    lines.append(f"## Moved or reassigned methods ({len(moves)})")
    lines.extend(moves)
    lines.append("")

    for method in sorted(deprecated["methods"]):
        if method in new_server_names and method not in kept:
            del deprecated["methods"][method]
            lines.append(
                f"- `{method}` is provided again by `{new_server_names[method]}`; "
                "its deprecation entry was dropped."
            )

    changes_lines: list[str] = []
    documentation_only: list[str] = []
    for key in common:
        old_name, old = old_ops[key]
        new_name, new = new_ops[key]
        if old == new and old_docs[old_name].get("components") == new_docs[new_name].get(
            "components"
        ):
            continue
        changes = describe_change(old_docs[old_name], old, new_docs[new_name], new)
        if not changes:
            if old != new:
                documentation_only.append(key)
            continue
        marker = " **(breaking)**" if any(c.breaking for c in changes) else ""
        changes_lines.append(f"- `{key}`{marker}: " + "; ".join(notes(changes)))
        breaking.extend(BreakingChange(key, c.where, c.path, c.kind) for c in changes if c.breaking)
    lines.append(f"## Changed operations ({len(changes_lines) + len(documentation_only)})")
    lines.extend(changes_lines)
    if documentation_only:
        shown = ", ".join(f"`{key}`" for key in documentation_only[:MAX_NOTES])
        more = len(documentation_only) - MAX_NOTES
        lines.append(f"- {NO_DIFFERENCE}: {shown}" + (f" and {more} more" if more > 0 else ""))
    lines.append("")

    old_hand = set().union(
        *(_hand_written_methods(old_naming(k)) for k in old_ops if k in hand_written)
    )
    new_hand = set().union(
        *(_hand_written_methods(new_naming(k)) for k in new_ops if k in hand_written)
    )
    if old_hand != new_hand:
        lines.append("## Authentication module")
        lines.append(
            "The module is hand-written (DESIGN section 10); "
            "`tests/test_authentication_contract.py` fails until it follows the document."
        )
        lines.extend(f"- `{m}` is new: add it" for m in sorted(new_hand - old_hand))
        lines.extend(f"- `{m}` was removed: remove it" for m in sorted(old_hand - new_hand))
        lines.append("")

    lines.append("## Schemas")
    for name in downloads:
        old_schemas = old_docs[name].get("components", {}).get("schemas", {})
        new_schemas = new_docs[name].get("components", {}).get("schemas", {})
        for label, names in (
            ("added", sorted(set(new_schemas) - set(old_schemas))),
            ("removed", sorted(set(old_schemas) - set(new_schemas))),
            (
                "changed",
                sorted(
                    k
                    for k in set(old_schemas) & set(new_schemas)
                    if old_schemas[k] != new_schemas[k]
                ),
            ),
        ):
            if names:
                lines.append(f"- {name} {label}: " + ", ".join(f"`{n}`" for n in names))
    lines.append("")

    dropped: list[str] = []
    for key in list(overlay["operations"]):
        entry = new_ops.get(key)
        if entry is not None and entry[1].get("x-didit-sdk") is not None:
            if entry[1]["x-didit-sdk"] != overlay["operations"][key]:
                lines.append(
                    f"- `{key}`: upstream x-didit-sdk differs from the overlay; upstream wins."
                )
            dropped.append(key)
            del overlay["operations"][key]
    if dropped:
        lines.append(f"Dropped {len(dropped)} overlay entries that upstream now carries.")
        lines.append("")

    # feat when a caller can observe anything: the documents without documentation, or
    # the effective naming (upstream adopting an overlay entry unchanged is no change).
    breaking = list(dict.fromkeys(breaking))
    observable_change = (
        bool(breaking or added or removed)
        or any(old_naming(key) != new_naming(key) for key in common)
        or any(observable(old_docs[n]) != observable(new_docs[n]) for n in changed_files)
    )
    commit_type = "feat" if observable_change else "chore"
    if commit_type == "chore":
        release = (
            "`chore(spec)`: only descriptions, examples or other documentation changed, so this "
            "sync releases nothing on its own; it ships with the next release."
        )
    else:
        release = (
            "`feat(spec)`: this sync changes what a caller can observe, so merging it releases "
            "a minor version, never a major one (DESIGN.md section 13). "
            + (
                'The release notes repeat the breaking changes above under "API changes that '
                'can break typed code".'
                if breaking
                else "Nothing in it is on the list of changes that can break typed code."
            )
        )
    head = [
        "## Breaking changes",
        "\n".join(f"- {b.describe()}" for b in breaking) if breaking else "None detected.",
        "",
        "## Release",
        release,
        "",
    ]
    lines[0:0] = head

    for name, data in downloads.items():
        (openapi_dir / name).write_bytes(data)
    source_path = openapi_dir / "SOURCE.json"
    source = json.loads(source_path.read_text("utf-8")) if source_path.exists() else {}
    for name, data in downloads.items():
        source[name] = {
            "url": UPSTREAM.get(name, source.get(name, {}).get("url", "")),
            "sha256": hashlib.sha256(data).hexdigest(),
            "fetched_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
    # Same layout as the seeded files (one-space indent, no trailing newline), so diffs stay small.
    source_path.write_text(json.dumps(source, indent=1, ensure_ascii=False), "utf-8")
    overlay_path.write_text(json.dumps(overlay, indent=1, ensure_ascii=False), "utf-8")
    deprecated_path.write_text(json.dumps(deprecated, indent=1, ensure_ascii=False) + "\n", "utf-8")
    summary = "\n".join(lines).rstrip() + "\n"
    return SyncResult(True, summary, today.isoformat(), commit_type, breaking)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--summary", type=pathlib.Path, help="write the Markdown summary here")
    parser.add_argument(
        "--commit-message",
        type=pathlib.Path,
        help="write the commit message release-please reads here",
    )
    parser.add_argument(
        "--from-dir", type=pathlib.Path, help="read the upstream files from a directory instead"
    )
    args = parser.parse_args(argv)
    if args.from_dir:
        downloads = {name: (args.from_dir / name).read_bytes() for name in UPSTREAM}
    else:
        downloads = {name: fetch(url) for name, url in UPSTREAM.items()}
    now = dt.datetime.now(dt.timezone.utc)
    try:
        result = sync(REPO / "openapi", downloads, today=now.date(), now=now)
    except SpecSyncError as exc:
        print(f"spec sync refused the download, nothing was written: {exc}", file=sys.stderr)
        return 1
    if args.summary:
        args.summary.write_text(result.summary, "utf-8")
    if args.commit_message:
        args.commit_message.write_text(result.commit_message(), "utf-8")
    print(result.summary)
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as fh:
            fh.write(f"changed={'true' if result.changed else 'false'}\n")
            fh.write(f"date={result.date}\n")
            fh.write(f"type={result.commit_type}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
