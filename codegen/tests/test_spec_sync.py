"""The spec sync's commit type, breaking-change detection and release notes
(docs/DESIGN.md sections 3.1 and 13). They never touch the network.

The fixtures are ``openapi/verification.json`` as this repository committed it at the
commit in each file name: public, pinned copies, so that all seven SDKs test the same
upstream changes and report the same results.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import pathlib
import re
import shutil
import sys
from typing import Any

import pytest

CODEGEN = pathlib.Path(__file__).resolve().parents[1]
REPO = CODEGEN.parent
FIXTURES = CODEGEN / "tests" / "fixtures"
sys.path.insert(0, str(CODEGEN))

import spec_sync  # noqa: E402

NOW = dt.datetime(2026, 11, 6, 6, 0, tzinfo=dt.timezone.utc)
# Commit -> the start of the SHA-256 of its openapi/verification.json.
PINNED = {
    "9fe57fc69299601e59cc7a64c1db370fea5c7461": "12b2fdb05572755d",  # v1.0.1
    "e002a815773bbd1599256e2774046ee76520c6c8": "d1783bd862848198",
    "fe9f57a1dfb6374bfd391750d2044fc7a206e4ea": "9f8cdf8be8157588",
    "ccc799410f82eee1c25c7ce5abc6caa53846be6b": "1b0c7bdd8d7957bd",
}
NULL = "can now be null"
OBJECT = "type changed from string to object"
# The API change of 2026-11-04: the list sdk-python PR #14 printed for the same pair.
BREAKING_2026_11_04 = [
    ("GET /v3/session/{sessionId}/decision/", "registry_checks[].company.registry_data", NULL),
    ("GET /v3/session/{sessionId}/decision/", "registry_checks[].ownership_structure", NULL),
    ("GET /v3/session/{sessionId}/decision/", "signatures[].confirmation.channel", NULL),
    ("POST /v3/email/risk/", "email.email_intelligence.reason_codes[]", OBJECT),
    ("POST /v3/email/risk/", "email.enrichment.reason_codes[]", OBJECT),
    ("POST /v3/kyb/select/", "kyb_registry.registry_data", NULL),
    ("POST /v3/kyb/shareholders/", "kyb_registry.registry_data", NULL),
    ("POST /v3/kyb/ubo/", "kyb_registry.registry_data", NULL),
    ("POST /v3/phone/risk/", "phone.enrichment.reason_codes[]", OBJECT),
    ("POST /v3/phone/risk/", "phone.phone_intelligence.reason_codes[]", OBJECT),
    ("POST /v3/session/import-shared/", "registry_checks[].company.registry_data", NULL),
    ("POST /v3/session/import-shared/", "registry_checks[].ownership_structure", NULL),
    ("POST /v3/session/import-shared/", "signatures[].confirmation.channel", NULL),
    ("POST /v3/session/{sessionId}/signatures/{nodeId}/validate/", "signatures[].confirmation.channel", NULL),
]  # fmt: skip
API_SECTION = "API changes that can break typed code"


@pytest.fixture
def openapi(tmp_path: pathlib.Path) -> pathlib.Path:
    target = tmp_path / "openapi"
    shutil.copytree(REPO / "openapi", target)
    return target


def _fixture(commit: str) -> bytes:
    return (FIXTURES / f"verification-{commit}.json").read_bytes()


def _sync(openapi: pathlib.Path, downloads: dict[str, bytes]) -> spec_sync.SyncResult:
    return spec_sync.sync(openapi, downloads, today=NOW.date(), now=NOW, version="1.1.0")


def _sync_pair(openapi: pathlib.Path, before: str, after: str) -> spec_sync.SyncResult:
    (openapi / "verification.json").write_bytes(_fixture(before))
    return _sync(openapi, {"verification.json": _fixture(after)})


def _section(summary: str, title: str) -> str:
    return summary.split(f"## {title}\n", 1)[1].split("\n## ", 1)[0]


def _nested(message: str) -> list[str]:
    return re.findall(r"BEGIN_NESTED_COMMIT\n(.*?)\nEND_NESTED_COMMIT", message, re.S)


# The pinned upstream changes ------------------------------------------------------------


def test_fixtures_are_the_pinned_upstream_documents() -> None:
    for commit, digest in PINNED.items():
        assert hashlib.sha256(_fixture(commit)).hexdigest().startswith(digest), commit


def test_api_change_of_2026_11_04_is_a_minor_release_listing_every_breaking_change(
    openapi: pathlib.Path,
) -> None:
    result = _sync_pair(
        openapi, "9fe57fc69299601e59cc7a64c1db370fea5c7461", "e002a815773bbd1599256e2774046ee76520c6c8"
    )  # fmt: skip
    assert result.commit_type == "feat"
    assert [(b.operation, b.path, b.kind) for b in result.breaking] == BREAKING_2026_11_04
    assert {b.where for b in result.breaking} == {"response"}

    # The pull request body opens with them, one line each.
    lines = result.summary.splitlines()
    assert lines[0] == "## Breaking changes"
    assert lines[1 : 1 + len(BREAKING_2026_11_04)] == [f"- {b.describe()}" for b in result.breaking]
    assert lines[1] == (
        "- `GET /v3/session/{sessionId}/decision/` response "
        "`registry_checks[].company.registry_data`: can now be null"
    )
    assert "a minor version, never a major one" in _section(result.summary, "Release")

    # The release notes repeat them; never "!" or a BREAKING CHANGE footer (a major).
    message = result.commit_message()
    assert message.splitlines()[0] == "feat(spec): sync API spec 2026-11-06"
    assert "BREAKING" not in message
    assert _nested(message) == [f"api(spec): {b.describe()}" for b in result.breaking]
    assert not any(c in line for line in _nested(message) for c in "<>")


def test_documentation_only_change_of_2026_11_06_releases_nothing(openapi: pathlib.Path) -> None:
    result = _sync_pair(
        openapi, "fe9f57a1dfb6374bfd391750d2044fc7a206e4ea", "ccc799410f82eee1c25c7ce5abc6caa53846be6b"
    )  # fmt: skip
    assert result.changed
    assert result.commit_type == "chore"
    assert result.breaking == []
    assert _section(result.summary, "Breaking changes").strip() == "None detected."
    assert "releases nothing on its own" in _section(result.summary, "Release")
    assert "`POST /v3/poa/`" in _section(result.summary, "Changed operations")
    assert result.commit_message() == "chore(spec): sync API spec 2026-11-06\n"


# Release notes ----------------------------------------------------------------------------


def _release(message: str) -> tuple[str | None, dict[str, list[str]]]:
    """What release-please makes of a squash-merged sync whose BEGIN_COMMIT_OVERRIDE block
    holds ``message``, read with release-please-config.json: the version bump and the
    release notes by section. The first line and each nested block are one commit; only
    types with a visible section reach the notes, and without one nothing is released."""
    config = json.loads((REPO / "release-please-config.json").read_text("utf-8"))
    sections = {s["type"]: s for s in config["packages"]["."]["changelog-sections"]}
    commits = [message.splitlines()[0], *_nested(message)]
    notes: dict[str, list[str]] = {}
    bump = "patch"
    for commit in commits:
        match = re.fullmatch(r"(\w+)(?:\((\w+)\))?(!?): (.+)", commit)
        assert match, commit
        kind, _, bang, text = match.groups()
        if bang or "BREAKING CHANGE" in message:
            bump = "major"
        elif kind == "feat" and bump != "major":
            bump = "minor"
        section = sections.get(kind)
        if section and not section.get("hidden"):
            notes.setdefault(section["section"], []).append(text)
    return (bump if notes else None), notes


def test_release_notes_have_a_section_for_api_changes_that_can_break_typed_code(
    openapi: pathlib.Path,
) -> None:
    result = _sync_pair(
        openapi, "9fe57fc69299601e59cc7a64c1db370fea5c7461", "e002a815773bbd1599256e2774046ee76520c6c8"
    )  # fmt: skip
    bump, notes = _release(result.commit_message())
    assert bump == "minor"
    assert notes == {
        "Features": ["sync API spec 2026-11-06"],
        API_SECTION: [b.describe() for b in result.breaking],
    }
    # A documentation-only sync (chore, a hidden section) proposes no release on its own.
    assert _release("chore(spec): sync API spec 2026-11-06\n") == (None, {})


def test_release_please_config_keeps_chores_ci_and_tests_hidden() -> None:
    config = json.loads((REPO / "release-please-config.json").read_text("utf-8"))
    sections = {s["type"]: s for s in config["packages"]["."]["changelog-sections"]}
    assert sections["api"] == {"type": "api", "section": API_SECTION}
    assert not sections["feat"].get("hidden")
    for kind in ("chore", "ci", "test", "build", "refactor", "style"):
        assert sections[kind]["hidden"] is True, kind


def test_release_notes_are_capped(openapi: pathlib.Path) -> None:
    many = [
        spec_sync.BreakingChange(f"GET /v3/thing-{i}/", "response", "a", "removed")
        for i in range(spec_sync.MAX_RELEASE_NOTES + 3)
    ]
    message = spec_sync.SyncResult(True, "", "2026-11-06", "feat", many).commit_message()
    nested = _nested(message)
    assert len(nested) == spec_sync.MAX_RELEASE_NOTES + 1
    assert nested[-1] == "api(spec): 3 more, listed in the spec sync pull request"


# Detection rules (DESIGN 3.1) -------------------------------------------------------------

OBJ = {"type": "object", "properties": {"a": {"type": "string"}}, "required": ["a"]}
STATUS = {"type": "string", "enum": ["a", "b"]}


def _diff(old: Any, new: Any, *, request: bool = False) -> list[tuple[str, str, bool]]:
    out: list[spec_sync.Change] = []
    spec_sync.diff_schema(old, new, "body", request=request, out=out)
    return [(c.path, c.kind, c.breaking) for c in out]


@pytest.mark.parametrize("request_side", [True, False], ids=["request", "response"])
def test_counted_in_requests_and_responses(request_side: bool) -> None:
    def diff(old: Any, new: Any) -> list[tuple[str, str, bool]]:
        return _diff(old, new, request=request_side)

    # A type change, in either direction.
    assert diff({"type": "integer"}, {"type": "number"}) == [
        ("", "type changed from integer to number", True)
    ]
    assert diff({"type": "number"}, {"type": "integer"}) == [
        ("", "type changed from number to integer", True)
    ]
    assert diff({"type": "string"}, {"type": "object", "properties": {}}) == [("", OBJECT, True)]
    # A value that can now be null, however the document says it.
    for nullable in (
        {"type": "string", "nullable": True},
        {"type": ["string", "null"]},
        {"anyOf": [{"type": "string"}, {"type": "null"}]},
        {"oneOf": [{"type": "string"}, {"enum": [None]}]},
        {"allOf": [{"type": "string"}], "nullable": True},
    ):
        assert diff({"type": "string"}, nullable) == [("", NULL, True)], nullable
    assert diff(STATUS, {**STATUS, "enum": ["a", "b", None]}) == [("", NULL, True)]
    # A removed field or enum value, nested in objects and array items.
    assert diff(OBJ, {"type": "object", "properties": {}}) == [("a", "removed", True)]
    assert diff(STATUS, {**STATUS, "enum": ["a"]}) == [("", 'enum value "b" removed', True)]
    nested = {"type": "array", "items": {"type": "object", "properties": {"s": STATUS}}}
    narrowed = {
        "type": "array",
        "items": {"type": "object", "properties": {"s": {**STATUS, "enum": ["b"]}}},
    }
    assert diff(nested, narrowed) == [("[].s", 'enum value "a" removed', True)]  # fmt: skip
    # A union that loses a variant.
    two = {"oneOf": [OBJ, {**OBJ, "properties": {"b": {"type": "string"}}}]}
    assert diff(two, {"oneOf": [OBJ]}) == [("", "type changed: 1 oneOf variant(s) removed", True)]
    assert diff(two, OBJ) == [("", "type changed: 1 oneOf variant(s) removed", True)]
    assert diff({"oneOf": [{"type": "string"}, {"type": "integer"}]}, {"type": "string"}) == [
        ("", "type changed from integer or string to string", True)
    ]


def test_newly_required_request_fields_count_and_response_requiredness_does_not() -> None:
    optional = {**OBJ, "required": []}
    assert _diff(optional, OBJ, request=True) == [("a", "now required", True)]
    added = {"type": "object", "properties": {**OBJ["properties"], "b": {"type": "string"}}}
    assert _diff(optional, {**added, "required": ["b"]}, request=True) == [
        ("b", "added (required)", True)
    ]
    assert _diff(optional, added, request=True) == [("b", "added", False)]
    assert _diff(optional, OBJ) == [("a", "now always present", False)]
    assert _diff(OBJ, optional) == [("a", "no longer always present", False)]
    assert _diff(OBJ, optional, request=True) == [("a", "no longer required", False)]


def test_listed_but_not_counted() -> None:
    assert _diff(STATUS, {**STATUS, "enum": ["a", "b", "c"]}) == [
        ("", 'enum values added ["c"]', False)
    ]
    assert _diff({"type": "string"}, STATUS) == [("", 'now limited to ["a", "b"]', False)]
    assert _diff(STATUS, {"type": "string"}) == [("", "no longer limited to fixed values", False)]
    assert _diff({"type": "string", "nullable": True}, {"type": "string"}, request=True) == [
        ("", "no longer accepts null", False)
    ]
    assert _diff({"type": "string"}, {"type": "string", "format": "date-time"}) == [
        ("", "other constraints changed (format, pattern, limits or default)", False)
    ]
    assert _diff({"oneOf": [OBJ]}, {"oneOf": [OBJ, {**OBJ, "title": "B", "properties": {}}]}) == [
        ("", "1 oneOf variant(s) added", False)
    ]


def test_an_optional_value_reads_as_nullable_not_as_its_fields_removed() -> None:
    assert _diff(OBJ, {"anyOf": [OBJ, {"type": "null"}]}) == [("", NULL, True)]
    assert _diff(OBJ, {"oneOf": [OBJ, {"enum": [None]}], "description": "or null"}) == [
        ("", NULL, True)
    ]
    assert _diff({"anyOf": [OBJ, {"type": "null"}]}, OBJ) == [("", "can no longer be null", False)]


def test_an_enum_behind_all_of_is_compared() -> None:
    assert _diff({"allOf": [STATUS]}, {"allOf": [{**STATUS, "enum": ["a"]}]}) == [
        ("", 'enum value "b" removed', True)
    ]


def test_documentation_never_counts_but_a_field_named_like_it_does() -> None:
    documented = {
        **OBJ,
        "description": "now documented",
        "title": "Thing",
        "example": {"a": "z"},
        "x-codeSamples": [],
    }
    assert _diff(OBJ, documented) == []
    fields = {"type": "object", "properties": {"description": {"type": "string"}, "tags": {}}}
    assert _diff(fields, {"type": "object", "properties": {"tags": {}}}) == [
        ("description", "removed", True)
    ]
    assert _diff(
        {"type": "object", "properties": {"title": {"type": "string"}}},
        {"type": "object", "properties": {"title": {"type": "integer"}}},
    ) == [("title", "type changed from string to integer", True)]


def _op(*parameters: Any, responses: Any = None, body: Any = None) -> dict[str, Any]:
    op: dict[str, Any] = {"parameters": list(parameters), "responses": responses or {}}
    if body is not None:
        op["requestBody"] = {"content": {"application/json": {"schema": body}}}
    return op


def _json(schema: Any) -> dict[str, Any]:
    return {"description": "ok", "content": {"application/json": {"schema": schema}}}


def test_parameters() -> None:
    limit = {"name": "limit", "in": "query", "schema": {"type": "integer"}}
    where = "parameter `limit` (query)"

    def changes(old: Any, new: Any) -> list[tuple[str, str, bool]]:
        found = spec_sync.describe_change({}, old, {}, new)
        return [(c.where, c.kind, c.breaking) for c in found]

    required_null = {**limit, "required": True, "schema": {"type": "integer", "nullable": True}}
    assert changes(_op(limit), _op(required_null)) == [
        (where, "now required", True),
        (where, NULL, True),
    ]
    assert changes(_op(limit), _op({**limit, "schema": {"type": "string"}})) == [
        (where, "type changed from integer to string", True)
    ]
    assert changes(_op(limit), _op({**limit, "name": "page"})) == [
        (where, "removed", False),
        ("parameter `page` (query)", "added", False),
    ]
    assert changes(_op(), _op({**limit, "required": True})) == [(where, "added (required)", True)]


def test_every_success_response_is_compared_and_reported_once() -> None:
    gone = {"type": "object", "properties": {}}
    old = _op(responses={"200": _json(OBJ), "202": _json(OBJ), "400": _json(OBJ)})
    both = _op(responses={"200": _json(gone), "202": _json(gone), "400": _json(gone)})
    found = spec_sync.describe_change({}, old, {}, both)
    assert [(c.where, c.path, c.kind) for c in found] == [("response", "a", "removed")]
    only_202 = _op(responses={"200": _json(OBJ), "202": _json(gone)})
    found = spec_sync.describe_change({}, old, {}, only_202)
    assert [(c.path, c.kind) for c in found] == [("a", "removed")]


def test_references_are_followed() -> None:
    doc = {"components": {"schemas": {"Obj": OBJ}}}
    new_doc = {"components": {"schemas": {"Obj": {**OBJ, "properties": {}}}}}
    ref = {"$ref": "#/components/schemas/Obj"}
    op = _op(responses={"200": _json({"type": "array", "items": ref})}, body=ref)
    found = spec_sync.describe_change(doc, op, new_doc, op)
    assert [(c.where, c.path, c.kind, c.breaking) for c in found] == [
        ("request body", "a", "removed", True),
        ("response", "[].a", "removed", True),
    ]


# Commit type ------------------------------------------------------------------------------

OP = "/programmatic/resend-otp/"


def _account_sync(openapi: pathlib.Path, change: Any) -> spec_sync.SyncResult:
    spec = json.loads((openapi / "account.json").read_text("utf-8"))
    change(spec)
    return _sync(openapi, {"account.json": json.dumps(spec).encode()})


def _response(spec: Any) -> Any:
    return spec["paths"][OP]["post"]["responses"]["200"]["content"]["application/json"]["schema"]


@pytest.mark.parametrize(
    ("change", "commit_type"),
    [
        (lambda s: s["paths"][OP]["post"].update(description="Reworded."), "chore"),
        (lambda s: s["paths"][OP]["post"].update({"x-codeSamples": []}), "chore"),
        (lambda s: s["info"].update(version="9.9.9"), "chore"),
        (lambda s: s["tags"].append({"name": "New tag"}), "chore"),
        (lambda s: _response(s).update(description="Reworded."), "chore"),
        (lambda s: _response(s)["properties"].update(description={"type": "string"}), "feat"),
        (lambda s: _response(s)["properties"].update(extra={"type": "string"}), "feat"),
        (lambda s: s["paths"][OP]["post"].update(deprecated=True), "feat"),
        (lambda s: s["paths"][OP]["post"]["x-didit-sdk"].update(method="resend"), "feat"),
    ],
    ids=[
        "description",
        "code samples",
        "info",
        "tags",
        "schema description",
        "field named description",
        "new field",
        "deprecated",
        "rename",
    ],
)
def test_feat_when_a_caller_can_observe_it_and_chore_for_documentation(
    openapi: pathlib.Path, change: Any, commit_type: str
) -> None:
    result = _account_sync(openapi, change)
    assert result.changed
    assert result.commit_type == commit_type
    assert result.breaking == []
    assert result.commit_message() == f"{commit_type}(spec): sync API spec 2026-11-06\n"


def test_a_new_webhook_event_is_feat(openapi: pathlib.Path) -> None:
    spec = json.loads((openapi / "verification.json").read_text("utf-8"))
    spec["x-webhooks"]["synthetic.event"] = spec["x-webhooks"]["status.updated"]
    result = _sync(openapi, {"verification.json": json.dumps(spec).encode()})
    assert result.commit_type == "feat"


def test_upstream_adopting_an_overlay_entry_unchanged_is_chore(openapi: pathlib.Path) -> None:
    key = f"account POST {OP}"
    spec = json.loads((openapi / "account.json").read_text("utf-8"))
    naming = spec["paths"][OP]["post"].pop("x-didit-sdk")
    (openapi / "account.json").write_text(json.dumps(spec), "utf-8")
    overlay = json.loads((openapi / "overlay.json").read_text("utf-8"))
    overlay["operations"][key] = naming
    (openapi / "overlay.json").write_text(json.dumps(overlay, indent=1), "utf-8")
    spec["paths"][OP]["post"]["x-didit-sdk"] = naming
    result = _sync(openapi, {"account.json": json.dumps(spec).encode()})
    assert result.commit_type == "chore"
    assert key not in json.loads((openapi / "overlay.json").read_text("utf-8"))["operations"]


# The Authentication document ---------------------------------------------------------------


def _authentication(openapi: pathlib.Path) -> Any:
    return json.loads((openapi / "authentication.json").read_text("utf-8"))


def test_a_removed_authentication_operation_is_breaking_and_never_deprecated(
    openapi: pathlib.Path,
) -> None:
    before = (openapi / "deprecated-operations.json").read_bytes()
    spec = _authentication(openapi)
    del spec["paths"]["/session/"]["delete"]
    result = _sync(openapi, {"authentication.json": json.dumps(spec).encode()})
    assert result.commit_type == "feat"
    assert [b.describe() for b in result.breaking] == [
        "`authentication DELETE /session/`: operation removed (`authentication.revoke_session`)"
    ]
    assert "- `authentication.revoke_session` was removed: remove it" in _section(
        result.summary, "Authentication module"
    )
    # The module is hand-written: nothing is generated or kept as deprecated for it.
    assert (openapi / "deprecated-operations.json").read_bytes() == before


def test_a_renamed_authentication_method_names_the_module_change(openapi: pathlib.Path) -> None:
    spec = _authentication(openapi)
    naming = spec["paths"]["/token/"]["post"]["x-didit-sdk"]
    naming["variants"][1]["method"] = "refresh_tokens"
    result = _sync(openapi, {"authentication.json": json.dumps(spec).encode()})
    assert result.commit_type == "feat"
    assert result.breaking == []
    module = _section(result.summary, "Authentication module")
    assert "- `authentication.refresh_tokens` is new: add it" in module
    assert "- `authentication.refresh` was removed: remove it" in module
    assert "## Renamed methods (0)" in result.summary


def test_authentication_documentation_change_is_chore(openapi: pathlib.Path) -> None:
    spec = _authentication(openapi)
    spec["paths"]["/session/"]["get"]["description"] = "Reworded."
    result = _sync(openapi, {"authentication.json": json.dumps(spec).encode()})
    assert result.commit_type == "chore"
    assert "## Authentication module" not in result.summary


def test_the_sync_downloads_the_authentication_document() -> None:
    assert spec_sync.UPSTREAM["authentication.json"] == (
        "https://docs.didit.me/openapi-authentication.json"
    )
    source = json.loads((REPO / "openapi" / "SOURCE.json").read_text("utf-8"))
    data = (REPO / "openapi" / "authentication.json").read_bytes()
    assert source["authentication.json"]["url"] == spec_sync.UPSTREAM["authentication.json"]
    assert source["authentication.json"]["sha256"] == hashlib.sha256(data).hexdigest()


# Command line ----------------------------------------------------------------------------------


def test_cli_writes_the_type_and_the_commit_message(
    monkeypatch: pytest.MonkeyPatch, openapi: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    upstream = tmp_path / "upstream"
    shutil.copytree(openapi, upstream)
    spec = json.loads((upstream / "verification.json").read_text("utf-8"))
    del spec["paths"]["/v3/billing/balance/"]
    (upstream / "verification.json").write_text(json.dumps(spec), "utf-8")
    output, message = tmp_path / "github_output", tmp_path / "message.txt"
    monkeypatch.setattr(spec_sync, "REPO", openapi.parent)
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    args = ["--from-dir", str(upstream), "--commit-message", str(message)]
    assert spec_sync.main(args) == 0
    outputs = dict(line.split("=", 1) for line in output.read_text("utf-8").splitlines())
    assert outputs["changed"] == "true"
    assert outputs["type"] == "feat"
    assert message.read_text("utf-8") == (
        f"feat(spec): sync API spec {outputs['date']}\n\nBEGIN_NESTED_COMMIT\n"
        "api(spec): `GET /v3/billing/balance/`: operation removed; `billing.retrieve_balance` "
        f"stays as a deprecated method until version {spec_sync.next_minor(spec_sync._version())}\n"
        "END_NESTED_COMMIT\n"
    )
