"""Tests of the generator and the spec sync (they never touch the network)."""

from __future__ import annotations

import datetime as dt
import json
import pathlib
import shutil
import sys
from typing import Any

import pytest

CODEGEN = pathlib.Path(__file__).resolve().parents[1]
REPO = CODEGEN.parent
sys.path.insert(0, str(CODEGEN))

import spec_sync  # noqa: E402
from didit_codegen import naming  # noqa: E402
from didit_codegen.generate import GENERATED_ROOTS, build, generate  # noqa: E402
from didit_codegen.render import HEADER  # noqa: E402
from didit_codegen.spec import CodegenError, SdkNaming, load  # noqa: E402

NOW = dt.datetime(2026, 10, 18, 6, 0, tzinfo=dt.timezone.utc)


@pytest.fixture
def openapi(tmp_path: pathlib.Path) -> pathlib.Path:
    target = tmp_path / "openapi"
    shutil.copytree(REPO / "openapi", target)
    return target


def _read(path: pathlib.Path) -> Any:
    return json.loads(path.read_text("utf-8"))


def _write(path: pathlib.Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=1, ensure_ascii=False), "utf-8")


# Naming -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "pascal", "snake"),
    [
        ("key_people_checks", "KeyPeopleChecks", "key_people_checks"),
        ("sessionId", "SessionId", "session_id"),
        ("IDVerification", "IdVerification", "id_verification"),
        ("Idempotency-Key", "IdempotencyKey", "idempotency_key"),
        ("aml_v2", "AmlV2", "aml_v2"),
        ("2fa", "V2fa", "v_2fa"),
        ("", "Value", "value"),
    ],
)
def test_case_conversions(text: str, pascal: str, snake: str) -> None:
    assert naming.pascal(text) == pascal
    assert naming.snake(text) == snake


def test_identifiers() -> None:
    assert naming.identifier("from") == "from_"
    assert naming.identifier("_private") == "private"
    assert naming.identifier("first-name") == "first_name"
    assert naming.identifier("été") == "t"
    assert naming.identifier("json", taken=frozenset({"json"})) == "json_"
    assert naming.resource_class("cases.routing_rules") == "CasesRoutingRules"


def test_sdk_naming_validation() -> None:
    ok = SdkNaming.parse("k", {"resource": "a.b", "method": "list", "auth": "api_key", "server": True})
    assert ok.as_json() == {"auth": "api_key", "method": "list", "resource": "a.b", "server": True}
    bad: list[dict[str, Any]] = [
        {"resource": "A", "method": "list", "auth": "api_key", "server": True},
        {"resource": "a", "method": "List", "auth": "api_key", "server": True},
        {"resource": "a", "method": "list", "auth": "oauth", "server": True},
        {"resource": "a", "method": "list", "auth": "api_key", "server": "yes"},
        {"resource": "a", "method": "list", "auth": "api_key", "server": True, "scope": "org"},
        {"resource": "a", "method": "list", "auth": "api_key", "server": True, "extra": 1},
        {"resource": "a", "method": "list", "auth": "api_key"},
    ]
    for raw in bad:
        with pytest.raises(CodegenError):
            SdkNaming.parse("k", raw)
    with pytest.raises(CodegenError):
        SdkNaming.parse("k", ["not", "an", "object"])


# Loading ------------------------------------------------------------------------------


def test_repository_specs_load() -> None:
    model = load(REPO / "openapi")
    assert len(model.operations) == 266
    assert len(model.server_operations) == 257
    assert {op.api for op in model.server_operations} == {"verification", "account"}


def test_new_operation_without_naming_fails_with_its_name(openapi: pathlib.Path) -> None:
    spec = _read(openapi / "verification.json")
    spec["paths"]["/v3/brand-new/"] = {"get": {"operationId": "brand_new_list", "responses": {"200": {"description": "ok"}}}}
    _write(openapi / "verification.json", spec)
    with pytest.raises(CodegenError) as info:
        load(openapi)
    assert "GET /v3/brand-new/ (operationId brand_new_list)" in str(info.value)
    assert "openapi/overlay.json" in str(info.value)


def test_upstream_naming_wins_over_the_overlay(openapi: pathlib.Path) -> None:
    spec = _read(openapi / "verification.json")
    spec["paths"]["/v3/session/"]["post"]["x-didit-sdk"] = {
        "resource": "sessions",
        "method": "start",
        "auth": "api_key",
        "server": True,
    }
    _write(openapi / "verification.json", spec)
    op = next(o for o in load(openapi).operations if o.key == "POST /v3/session/")
    assert op.sdk.method == "start"


def test_stale_overlay_entry_fails(openapi: pathlib.Path) -> None:
    overlay = _read(openapi / "overlay.json")
    overlay["operations"]["GET /v3/gone/"] = {"resource": "gone", "method": "list", "auth": "api_key", "server": True}
    _write(openapi / "overlay.json", overlay)
    with pytest.raises(CodegenError, match="no longer exist upstream"):
        load(openapi)


def test_duplicate_method_names_fail(openapi: pathlib.Path) -> None:
    overlay = _read(openapi / "overlay.json")
    overlay["operations"]["GET /v3/sessions/"]["method"] = "create"
    _write(openapi / "overlay.json", overlay)
    with pytest.raises(CodegenError, match="both map to sessions.create"):
        load(openapi)


def test_method_clashing_with_a_nested_resource_fails(openapi: pathlib.Path) -> None:
    overlay = _read(openapi / "overlay.json")
    overlay["operations"]["GET /v3/sessions/"]["method"] = "imports"
    _write(openapi / "overlay.json", overlay)
    with pytest.raises(CodegenError, match="clashes with the nested resource"):
        load(openapi)


def test_application_scope_needs_the_prefix(openapi: pathlib.Path) -> None:
    overlay = _read(openapi / "overlay.json")
    overlay["operations"]["GET /v3/sessions/"]["scope"] = "application"
    _write(openapi / "overlay.json", overlay)
    with pytest.raises(CodegenError, match="scope application"):
        load(openapi)


# Generation ---------------------------------------------------------------------------


def test_generation_is_deterministic_and_marked() -> None:
    first = generate(REPO / "openapi")
    second = generate(REPO / "openapi")
    assert first == second
    assert all(path.startswith(GENERATED_ROOTS) for path in first)
    for path, text in first.items():
        assert text.startswith(HEADER), path


def test_every_server_operation_becomes_one_method() -> None:
    model, builder, methods = build(REPO / "openapi")
    assert len(methods) == len(model.server_operations) == 257
    kinds = {m.response.kind for m in methods}
    assert kinds == {"model", "page", "bytes", "none"}
    assert sum(1 for m in methods if m.response.kind == "page") == 27
    assert sum(1 for m in methods if m.body_mode in ("multipart", "auto")) == 11
    assert sum(1 for m in methods if m.op.sdk.scope == "application") == 106
    names = set(builder.registry.defs)
    assert "SessionsCreateParams" in names
    assert "SessionsCreateParamsContactDetails" in names
    assert "SessionsCreateResponse" in names
    assert "TransactionDetail" in names


def test_query_parameter_clashing_with_a_body_field_is_renamed() -> None:
    _, _, methods = build(REPO / "openapi")
    method = next(m for m in methods if m.resource == "sessions" and m.name == "update_aml_hit_status")
    by_py = {a.py: a for a in method.kwargs}
    assert by_py["node_id"].location == "body"
    assert by_py["node_id_query"].location == "query"
    assert by_py["node_id_query"].wire == "node_id"


def test_removed_operation_stays_as_a_deprecated_method(openapi: pathlib.Path) -> None:
    upstream = openapi.parent / "upstream"
    upstream.mkdir()
    spec = _read(openapi / "verification.json")
    del spec["paths"]["/v3/billing/balance/"]
    (upstream / "verification.json").write_text(json.dumps(spec), "utf-8")
    shutil.copy(openapi / "account.json", upstream / "account.json")

    downloads = {name: (upstream / name).read_bytes() for name in spec_sync.UPSTREAM}
    changed, summary = spec_sync.sync(openapi, downloads, today=NOW.date(), now=NOW)
    assert changed
    assert "billing.retrieve_balance" in summary
    assert "## Breaking changes" in summary
    deprecated = _read(openapi / "deprecated-operations.json")["operations"]
    assert "GET /v3/billing/balance/" in deprecated
    assert deprecated["GET /v3/billing/balance/"]["removed_on"] == "2026-10-18"
    assert "$ref" not in json.dumps(deprecated)
    assert "GET /v3/billing/balance/" not in _read(openapi / "overlay.json")["operations"]

    files = generate(openapi)
    billing = files["src/didit/resources/billing.py"]
    assert "@deprecated(" in billing
    assert "def retrieve_balance(" in billing


def test_moved_operation_is_not_deprecated(openapi: pathlib.Path) -> None:
    spec = _read(openapi / "verification.json")
    spec["paths"]["/v3/billing/balance-v2/"] = spec["paths"].pop("/v3/billing/balance/")
    overlay = _read(openapi / "overlay.json")
    entry = overlay["operations"]["GET /v3/billing/balance/"]
    spec["paths"]["/v3/billing/balance-v2/"]["get"]["x-didit-sdk"] = entry
    downloads = {
        "verification.json": json.dumps(spec).encode(),
        "account.json": (openapi / "account.json").read_bytes(),
    }
    changed, summary = spec_sync.sync(openapi, downloads, today=NOW.date(), now=NOW)
    assert changed
    assert "moved to `GET /v3/billing/balance-v2/`" in summary
    assert _read(openapi / "deprecated-operations.json")["operations"] == {}
    load(openapi)


def test_sync_reports_changes_and_drops_overlay_entries(openapi: pathlib.Path) -> None:
    spec = _read(openapi / "verification.json")
    op = spec["paths"]["/v3/session/"]["post"]
    op["x-didit-sdk"] = _read(openapi / "overlay.json")["operations"]["POST /v3/session/"]
    op["parameters"] = [{"name": "dry_run", "in": "query", "required": True, "schema": {"type": "boolean"}}]
    spec["paths"]["/v3/new-thing/"] = {"get": {"responses": {"200": {"description": "ok"}}}}
    downloads = {
        "verification.json": json.dumps(spec).encode(),
        "account.json": (openapi / "account.json").read_bytes(),
    }
    changed, summary = spec_sync.sync(openapi, downloads, today=NOW.date(), now=NOW)
    assert changed
    assert "`GET /v3/new-thing/`: **no SDK naming**" in summary
    assert "parameter added: dry_run (query, required)" in summary
    assert "**(breaking)**" in summary
    assert "Dropped 1 overlay entries" in summary
    assert "POST /v3/session/" not in _read(openapi / "overlay.json")["operations"]
    source = _read(openapi / "SOURCE.json")
    assert source["verification.json"]["fetched_at"] == "2026-10-18T06:00:00Z"
    assert len(source["verification.json"]["sha256"]) == 64
    assert source["webhook-vectors.json"]["generator"]


def test_sync_without_changes_touches_nothing(openapi: pathlib.Path) -> None:
    before = {p.name: p.read_bytes() for p in openapi.iterdir()}
    downloads = {name: (openapi / name).read_bytes() for name in spec_sync.UPSTREAM}
    changed, summary = spec_sync.sync(openapi, downloads, today=NOW.date(), now=NOW)
    assert not changed
    assert summary == "No upstream change.\n"
    assert {p.name: p.read_bytes() for p in openapi.iterdir()} == before


def test_seeded_json_layout_round_trips() -> None:
    for name in ("overlay.json", "SOURCE.json"):
        raw = (REPO / "openapi" / name).read_text("utf-8")
        assert json.dumps(json.loads(raw), indent=1, ensure_ascii=False) == raw


def test_cli_main_from_dir(monkeypatch: pytest.MonkeyPatch, openapi: pathlib.Path, tmp_path: pathlib.Path) -> None:
    output = tmp_path / "github_output"
    summary = tmp_path / "summary.md"
    monkeypatch.setattr(spec_sync, "REPO", openapi.parent)
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    assert spec_sync.main(["--from-dir", str(openapi), "--summary", str(summary)]) == 0
    assert "changed=false" in output.read_text("utf-8")
    assert summary.read_text("utf-8") == "No upstream change.\n"
