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


def _spec_operation(openapi_dir: pathlib.Path, key: str) -> tuple[pathlib.Path, Any, Any]:
    """The spec file, its document and the operation behind an overlay key."""
    file = openapi_dir / ("account.json" if key.startswith("account ") else "verification.json")
    http_method, path = key.removeprefix("account ").split(" ", 1)
    doc = _read(file)
    return file, doc, doc["paths"][path][http_method.lower()]


def _naming(openapi_dir: pathlib.Path, key: str) -> Any:
    """An operation's naming: its own x-didit-sdk (upstream wins), else the overlay entry.

    Tests never assume where the naming lives: once upstream carries x-didit-sdk, the spec
    sync drops the overlay entries (DESIGN section 3).
    """
    _, _, op = _spec_operation(openapi_dir, key)
    return op.get("x-didit-sdk") or _read(openapi_dir / "overlay.json")["operations"][key]


def _change_naming(openapi_dir: pathlib.Path, key: str, **changes: Any) -> None:
    """Change an operation's naming where it lives (upstream x-didit-sdk, else the overlay)."""
    file, doc, op = _spec_operation(openapi_dir, key)
    if op.get("x-didit-sdk"):
        op["x-didit-sdk"].update(changes)
        _write(file, doc)
    else:
        overlay = _read(openapi_dir / "overlay.json")
        overlay["operations"][key].update(changes)
        _write(openapi_dir / "overlay.json", overlay)


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
    ok = SdkNaming.parse(
        "k", {"resource": "a.b", "method": "list", "auth": "api_key", "server": True}
    )
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


def _count_operations(openapi_dir: pathlib.Path) -> tuple[int, int]:
    """All operations and the server ones, counted straight from the JSON."""
    overlay = _read(openapi_dir / "overlay.json")["operations"]
    total = server = 0
    for name, prefix in (("verification.json", ""), ("account.json", "account ")):
        for path, item in _read(openapi_dir / name)["paths"].items():
            for method in ("get", "put", "post", "delete", "patch", "head", "options"):
                if method in item:
                    total += 1
                    naming = (
                        item[method].get("x-didit-sdk")
                        or overlay[f"{prefix}{method.upper()} {path}"]
                    )
                    server += bool(naming["server"])
    deprecated = len(_read(openapi_dir / "deprecated-operations.json")["methods"])
    return total + deprecated, server + deprecated


def test_repository_specs_load() -> None:
    model = load(REPO / "openapi")
    total, server = _count_operations(REPO / "openapi")
    assert len(model.operations) == total
    assert len(model.server_operations) == server
    assert {op.api for op in model.server_operations} == {"verification", "account"}


def test_new_operation_without_naming_fails_with_its_name(openapi: pathlib.Path) -> None:
    spec = _read(openapi / "verification.json")
    spec["paths"]["/v3/brand-new/"] = {
        "get": {"operationId": "brand_new_list", "responses": {"200": {"description": "ok"}}}
    }
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
    overlay["operations"]["GET /v3/gone/"] = {
        "resource": "gone",
        "method": "list",
        "auth": "api_key",
        "server": True,
    }
    _write(openapi / "overlay.json", overlay)
    with pytest.raises(CodegenError, match="no longer exist upstream"):
        load(openapi)


def test_duplicate_method_names_fail(openapi: pathlib.Path) -> None:
    _change_naming(openapi, "GET /v3/sessions/", method="create")
    with pytest.raises(CodegenError, match=r"both map to sessions\.create"):
        load(openapi)


def test_method_clashing_with_a_nested_resource_fails(openapi: pathlib.Path) -> None:
    _change_naming(openapi, "GET /v3/sessions/", method="imports")
    with pytest.raises(CodegenError, match="clashes with the nested resource"):
        load(openapi)


def test_application_scope_needs_the_prefix(openapi: pathlib.Path) -> None:
    _change_naming(openapi, "GET /v3/sessions/", scope="application")
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
    assert len(methods) == len(model.server_operations) == _count_operations(REPO / "openapi")[1]
    kinds = {m.response.kind for m in methods}
    assert kinds == {"model", "page", "bytes", "none"}
    # Counted from the JSON, independently of the generator.
    pages = multipart = scoped = 0

    def binary(schema: Any, spec: Any) -> set[str]:
        props = spec.resolve(schema).get("properties", {})
        out = set()
        for name, prop in props.items():
            prop = spec.resolve(prop)
            item = spec.resolve(prop.get("items", {}))
            if "binary" in (prop.get("format"), item.get("format")):
                out.add(name)
        return out

    for op in model.server_operations:
        props = (
            op.spec.resolve(
                ((op.op.get("responses") or {}).get("200") or {})
                .get("content", {})
                .get("application/json", {})
                .get("schema", {})
            )
            or {}
        ).get("properties", {})
        pages += {"count", "next", "previous", "results"} <= set(props)
        content = (op.op.get("requestBody") or {}).get("content", {})
        if "multipart/form-data" in content:
            files = binary(content["multipart/form-data"].get("schema", {}), op.spec)
            if "application/json" in content:
                json_schema = op.spec.resolve(content["application/json"].get("schema", {}))
                files -= set(json_schema.get("properties", {}))
            multipart += bool(files)
        scoped += op.sdk.scope == "application"
    assert sum(1 for m in methods if m.response.kind == "page") == pages
    assert sum(1 for m in methods if m.body_mode in ("multipart", "auto")) == multipart
    assert sum(1 for m in methods if m.op.sdk.scope == "application") == scoped
    assert pages
    assert multipart
    assert scoped
    names = set(builder.registry.defs)
    assert "SessionsCreateParams" in names
    assert "SessionsCreateParamsContactDetails" in names
    assert "SessionsCreateResponse" in names
    assert "TransactionDetail" in names


def test_query_parameter_clashing_with_a_body_field_is_renamed() -> None:
    _, _, methods = build(REPO / "openapi")
    method = next(
        m for m in methods if m.resource == "sessions" and m.name == "update_aml_hit_status"
    )
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
    shutil.copy(openapi / "authentication.json", upstream / "authentication.json")

    downloads = {name: (upstream / name).read_bytes() for name in spec_sync.UPSTREAM}
    result = spec_sync.sync(openapi, downloads, today=NOW.date(), now=NOW, version="0.4.2")
    assert result.changed
    assert result.commit_type == "feat"
    assert result.summary.startswith("## Breaking changes\n")
    assert _breaking(result.summary).strip() == (
        "- `GET /v3/billing/balance/`: operation removed; `billing.retrieve_balance` stays as "
        "a deprecated method until version 0.5.0"
    )
    deprecated = _read(openapi / "deprecated-operations.json")["methods"]
    entry = deprecated["billing.retrieve_balance"]
    assert entry["reason"] == "removed"
    assert entry["operation_key"] == "GET /v3/billing/balance/"
    assert entry["since"] == "2026-10-18"
    assert entry["deprecated_since"] == "0.4.2"
    assert entry["remove_in"] == "0.5.0"
    assert "$ref" not in json.dumps(deprecated)
    assert "GET /v3/billing/balance/" not in _read(openapi / "overlay.json")["operations"]

    files = generate(openapi)
    billing = files["src/didit/resources/billing.py"]
    assert "@deprecated(" in billing
    assert "def retrieve_balance(" in billing
    assert "removed in version 0.5.0" in billing


def test_renamed_method_stays_as_a_deprecated_alias(openapi: pathlib.Path) -> None:
    spec = _read(openapi / "verification.json")
    spec["paths"]["/v3/billing/balance/"]["get"]["x-didit-sdk"] = {
        **_naming(openapi, "GET /v3/billing/balance/"),
        "method": "get_balance",
    }
    downloads = {
        "verification.json": json.dumps(spec).encode(),
        "account.json": (openapi / "account.json").read_bytes(),
    }
    result = spec_sync.sync(openapi, downloads, today=NOW.date(), now=NOW, version="0.1.0")
    assert result.changed
    # A rename keeps the old name, so nothing breaks yet; the new name is a feature.
    assert result.commit_type == "feat"
    assert _breaking(result.summary).strip() == "None detected."
    renamed = _section(result.summary, "Renamed methods")
    assert "`billing.retrieve_balance` renamed to `billing.get_balance`" in renamed
    assert "until version 0.2.0" in renamed
    entry = _read(openapi / "deprecated-operations.json")["methods"]["billing.retrieve_balance"]
    assert entry["reason"] == "renamed"
    assert entry["replacement"] == "billing.get_balance"

    files = generate(openapi)
    billing = files["src/didit/resources/billing.py"]
    assert "def get_balance(" in billing
    assert "def retrieve_balance(" in billing
    assert "Renamed to billing.get_balance" in billing
    # The old response type stays importable next to the new one.
    types = "".join(t for p, t in files.items() if p.startswith("src/didit/types/"))
    assert "class BillingRetrieveBalanceResponse(" in types
    assert "class BillingGetBalanceResponse(" in types

    # Renamed back: the old name is live again (its alias is dropped), and the
    # interim name it shipped under becomes the deprecated alias in turn.
    spec["paths"]["/v3/billing/balance/"]["get"]["x-didit-sdk"]["method"] = "retrieve_balance"
    downloads["verification.json"] = json.dumps(spec).encode()
    summary = spec_sync.sync(openapi, downloads, today=NOW.date(), now=NOW, version="0.1.1").summary
    assert "`billing.retrieve_balance` is provided again" in summary
    methods = _read(openapi / "deprecated-operations.json")["methods"]
    assert list(methods) == ["billing.get_balance"]
    assert methods["billing.get_balance"]["replacement"] == "billing.retrieve_balance"
    load(openapi)


def _sync(openapi: pathlib.Path, spec: Any) -> str:
    downloads = {
        "verification.json": json.dumps(spec).encode(),
        "account.json": (openapi / "account.json").read_bytes(),
    }
    return spec_sync.sync(openapi, downloads, today=NOW.date(), now=NOW, version="0.1.0").summary


def _section(summary: str, title: str) -> str:
    return summary.split(f"## {title}", 1)[1].split("\n## ", 1)[0]


def _breaking(summary: str) -> str:
    return _section(summary, "Breaking changes")


def _name_op(openapi: pathlib.Path, spec: Any, path: str, http_method: str, **naming: Any) -> None:
    key = f"{http_method.upper()} {path}"
    spec["paths"][path][http_method]["x-didit-sdk"] = {**_naming(openapi, key), **naming}


def test_swapped_names_are_called_out_for_review(openapi: pathlib.Path) -> None:
    spec = _read(openapi / "verification.json")
    _name_op(openapi, spec, "/v3/billing/balance/", "get", method="top_up")
    _name_op(openapi, spec, "/v3/billing/top-up/", "post", method="retrieve_balance")
    moved = _section(_sync(openapi, spec), "Moved or reassigned methods")
    assert "`billing.top_up` **(review)** now calls `GET /v3/billing/balance/` instead of" in moved
    assert "`billing.retrieve_balance` **(review)** now calls `POST /v3/billing/top-up/`" in moved
    assert _read(openapi / "deprecated-operations.json")["methods"] == {}


def test_a_name_reused_by_another_operation_is_called_out(openapi: pathlib.Path) -> None:
    spec = _read(openapi / "verification.json")
    _name_op(openapi, spec, "/v3/billing/balance/", "get", method="current_balance")
    spec["paths"]["/v3/billing/balance-v2/"] = {
        "get": {
            "responses": {"200": {"description": "ok"}},
            "x-didit-sdk": {**_naming(openapi, "GET /v3/billing/balance/")},
        }
    }
    moved = _section(_sync(openapi, spec), "Moved or reassigned methods")
    assert (
        "`billing.retrieve_balance` **(review)** now calls `GET /v3/billing/balance-v2/` "
        "instead of `GET /v3/billing/balance/`" in moved
    )


def test_a_moved_operation_reports_what_changed(openapi: pathlib.Path) -> None:
    spec = _read(openapi / "verification.json")
    item = spec["paths"].pop("/v3/billing/balance/")
    item["get"]["x-didit-sdk"] = _naming(openapi, "GET /v3/billing/balance/")
    item["get"]["parameters"] = [
        {"name": "currency", "in": "query", "required": True, "schema": {"type": "string"}}
    ]
    item["get"]["responses"]["200"]["content"]["application/json"]["schema"] = {
        "type": "array",
        "items": {"type": "object"},
    }
    spec["paths"]["/v4/billing/balance/"] = item
    summary = _sync(openapi, spec)
    assert "`billing.retrieve_balance` **(breaking)** moved from `GET /v3/billing/balance/`" in (
        _section(summary, "Moved or reassigned methods")
    )
    assert _breaking(summary).strip().splitlines() == [
        "- `GET /v4/billing/balance/` query parameter `currency`: added (required)",
        "- `GET /v4/billing/balance/` response: type changed from object to array",
    ]
    assert _read(openapi / "deprecated-operations.json")["methods"] == {}


def test_an_operation_that_stops_being_a_server_operation_is_removed(
    openapi: pathlib.Path,
) -> None:
    spec = _read(openapi / "verification.json")
    _name_op(openapi, spec, "/v3/billing/balance/", "get", auth="device_token", server=False)
    breaking = _breaking(_sync(openapi, spec))
    assert breaking.strip() == (
        "- `GET /v3/billing/balance/`: operation removed from server SDKs: it now needs "
        "device_token, and `billing.retrieve_balance` is removed"
    )
    # Never kept: server SDKs do not expose device-token operations (DESIGN 4).
    assert _read(openapi / "deprecated-operations.json")["methods"] == {}
    files = generate(openapi)
    assert "def retrieve_balance(" not in files["src/didit/resources/billing.py"]


def test_an_operation_that_loses_its_naming_is_called_out(openapi: pathlib.Path) -> None:
    # Upstream named the operation (so the overlay no longer does), then drops it.
    naming = _naming(openapi, "GET /v3/billing/balance/")
    old = _read(openapi / "verification.json")
    overlay = _read(openapi / "overlay.json")
    overlay["operations"].pop("GET /v3/billing/balance/", None)
    old["paths"]["/v3/billing/balance/"]["get"]["x-didit-sdk"] = naming
    _write(openapi / "verification.json", old)
    _write(openapi / "overlay.json", overlay)
    spec = _read(openapi / "verification.json")
    del spec["paths"]["/v3/billing/balance/"]["get"]["x-didit-sdk"]
    summary = _sync(openapi, spec)
    # A sync failure for a person to fix, not an API change.
    assert "`GET /v3/billing/balance/` lost its SDK naming" in _section(summary, "Renamed methods")
    assert _breaking(summary).strip() == "None detected."
    assert _read(openapi / "deprecated-operations.json")["methods"] == {}
    with pytest.raises(CodegenError, match="no SDK naming"):
        load(openapi)


def test_nested_type_and_enum_changes_are_breaking(openapi: pathlib.Path) -> None:
    old = _read(openapi / "verification.json")
    old["components"]["schemas"]["LegacyUnusedThing"] = {"type": "object"}
    _write(openapi / "verification.json", old)
    spec = _read(openapi / "verification.json")
    del spec["components"]["schemas"]["LegacyUnusedThing"]
    schemas = spec["components"]["schemas"]
    # The reviewer's case: a nested component property changes type.
    schemas["DocumentAIDetectedCode"]["properties"]["type"] = {"type": "integer"}
    prop = "type"
    downloads = {
        "verification.json": json.dumps(spec).encode(),
        "account.json": (openapi / "account.json").read_bytes(),
    }
    summary = spec_sync.sync(openapi, downloads, today=NOW.date(), now=NOW, version="0.1.0").summary
    breaking = _breaking(summary)
    assert f".{prop}`: type changed from string to integer" in breaking
    assert "LegacyUnusedThing" not in breaking
    assert "verification.json removed: `LegacyUnusedThing`" in _section(summary, "Schemas")


@pytest.mark.parametrize(
    "body",
    [
        b"<html>maintenance</html>",
        b'{"message": "maintenance"}',
        b'{"openapi": "3.1.0", "paths": {}}',
        b"[]",
    ],
)
def test_sync_refuses_a_download_that_is_not_openapi(openapi: pathlib.Path, body: bytes) -> None:
    before = {p.name: p.read_bytes() for p in openapi.iterdir()}
    downloads = {
        "verification.json": (openapi / "verification.json").read_bytes(),
        "account.json": body,
    }
    with pytest.raises(spec_sync.SpecSyncError, match=r"account\.json"):
        spec_sync.sync(openapi, downloads, today=NOW.date(), now=NOW)
    assert {p.name: p.read_bytes() for p in openapi.iterdir()} == before


def test_deprecated_entry_that_is_provided_again_names_the_fix(openapi: pathlib.Path) -> None:
    deprecated = _read(openapi / "deprecated-operations.json")
    deprecated["methods"]["billing.retrieve_balance"] = {
        "reason": "removed",
        "operation_key": "GET /v3/billing/balance-old/",
        "x-didit-sdk": _naming(openapi, "GET /v3/billing/balance/"),
        "operation": {"responses": {"200": {"description": "ok"}}},
        "remove_in": "0.2.0",
    }
    _write(openapi / "deprecated-operations.json", deprecated)
    with pytest.raises(
        CodegenError, match=r"delete this entry from openapi/deprecated-operations\.json"
    ):
        load(openapi)


def test_next_minor() -> None:
    assert spec_sync.next_minor("0.1.0") == "0.2.0"
    assert spec_sync.next_minor("1.9.3") == "1.10.0"
    assert spec_sync.next_minor("garbage") == "0.1.0"


def test_moved_operation_is_not_deprecated(openapi: pathlib.Path) -> None:
    spec = _read(openapi / "verification.json")
    spec["paths"]["/v3/billing/balance-v2/"] = spec["paths"].pop("/v3/billing/balance/")
    entry = _naming(openapi, "GET /v3/billing/balance/")
    spec["paths"]["/v3/billing/balance-v2/"]["get"]["x-didit-sdk"] = entry
    downloads = {
        "verification.json": json.dumps(spec).encode(),
        "account.json": (openapi / "account.json").read_bytes(),
    }
    result = spec_sync.sync(openapi, downloads, today=NOW.date(), now=NOW)
    assert result.changed
    assert "moved to `GET /v3/billing/balance-v2/`" in result.summary
    assert _breaking(result.summary).strip() == "None detected."
    assert _read(openapi / "deprecated-operations.json")["methods"] == {}
    load(openapi)


def test_sync_reports_changes_and_drops_overlay_entries(openapi: pathlib.Path) -> None:
    # Before the sync only the overlay names the operation; upstream then carries it.
    naming = _naming(openapi, "POST /v3/session/")
    old = _read(openapi / "verification.json")
    old["paths"]["/v3/session/"]["post"].pop("x-didit-sdk", None)
    _write(openapi / "verification.json", old)
    overlay = _read(openapi / "overlay.json")
    overlay["operations"]["POST /v3/session/"] = naming
    _write(openapi / "overlay.json", overlay)
    spec = _read(openapi / "verification.json")
    op = spec["paths"]["/v3/session/"]["post"]
    op["x-didit-sdk"] = naming
    op["parameters"] = [
        {"name": "dry_run", "in": "query", "required": True, "schema": {"type": "boolean"}}
    ]
    spec["paths"]["/v3/new-thing/"] = {"get": {"responses": {"200": {"description": "ok"}}}}
    downloads = {
        "verification.json": json.dumps(spec).encode(),
        "account.json": (openapi / "account.json").read_bytes(),
    }
    result = spec_sync.sync(openapi, downloads, today=NOW.date(), now=NOW)
    summary = result.summary
    assert result.changed
    assert "`GET /v3/new-thing/`: **no SDK naming**" in summary
    assert "`POST /v3/session/` **(breaking)**: query parameter `dry_run`: added (required)" in (
        summary
    )
    assert _breaking(summary).strip() == (
        "- `POST /v3/session/` query parameter `dry_run`: added (required)"
    )
    assert "Dropped 1 overlay entries" in summary
    assert "POST /v3/session/" not in _read(openapi / "overlay.json")["operations"]
    source = _read(openapi / "SOURCE.json")
    assert source["verification.json"]["fetched_at"] == "2026-10-18T06:00:00Z"
    assert len(source["verification.json"]["sha256"]) == 64
    assert source["webhook-vectors.json"]["generator"]


def test_sync_without_changes_touches_nothing(openapi: pathlib.Path) -> None:
    before = {p.name: p.read_bytes() for p in openapi.iterdir()}
    downloads = {name: (openapi / name).read_bytes() for name in spec_sync.UPSTREAM}
    result = spec_sync.sync(openapi, downloads, today=NOW.date(), now=NOW)
    assert not result.changed
    assert result.summary == "No upstream change.\n"
    assert {p.name: p.read_bytes() for p in openapi.iterdir()} == before


def test_seeded_json_layout_round_trips() -> None:
    for name in ("overlay.json", "SOURCE.json"):
        raw = (REPO / "openapi" / name).read_text("utf-8")
        assert json.dumps(json.loads(raw), indent=1, ensure_ascii=False) == raw


def test_cli_main_from_dir(
    monkeypatch: pytest.MonkeyPatch, openapi: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    output = tmp_path / "github_output"
    summary = tmp_path / "summary.md"
    monkeypatch.setattr(spec_sync, "REPO", openapi.parent)
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    assert spec_sync.main(["--from-dir", str(openapi), "--summary", str(summary)]) == 0
    assert "changed=false" in output.read_text("utf-8")
    assert summary.read_text("utf-8") == "No upstream change.\n"


def test_scrub_keeps_timestamps_and_replaces_secrets() -> None:
    from didit_codegen.render_tests import scrub

    got = scrub(
        {
            "credentials_expires_at": "2026-10-27T10:00:00Z",
            "api_key": "abc",
            "password": "2026-10-27-secret",
            "token_date": "2026-10-27",
            "api_key_at": "2026-10-27T10:00",
        }
    )
    assert got == {
        "credentials_expires_at": "2026-10-27T10:00:00Z",
        "api_key": "sample-secret",
        "password": "sample-secret",
        "token_date": "sample-token",
        "api_key_at": "sample-secret",
    }


# A component that is an operation's whole request body ------------------------------

_LINKS_PATH = (
    "/v3/organization/{organization_id}/application/{application_id}/cases/{case_uuid}/links/"
)


def test_component_that_is_the_whole_request_body_is_the_params_type() -> None:
    files = generate(REPO / "openapi")
    declared = [path for path, text in files.items() if "class CasesLinksCreateParams(" in text]
    assert declared == ["src/didit/types/components/cases_links_create_params.py"]
    # The operation's own params module stays importable, as a generated re-export.
    reexport = files["src/didit/types/cases/links/create_params.py"]
    assert reexport.startswith(HEADER)
    assert "didit.types.components.cases_links_create_params import" in reexport
    assert "CasesLinksCreateParams as CasesLinksCreateParams" in reexport
    assert "class " not in reexport
    assert "src/didit/types/cases/links/__init__.py" in files
    links = files["src/didit/resources/cases/links.py"]
    assert "entity_type: Literal[" in links
    assert "entity_uuid: str," in links
    assert (
        "links: Sequence[CasesLinksCreateParams]" in files["src/didit/types/cases/create_params.py"]
    )


def test_two_different_types_with_one_name_still_collide(openapi: pathlib.Path) -> None:
    spec = _read(openapi / "verification.json")
    body = spec["paths"][_LINKS_PATH]["post"]["requestBody"]["content"]["application/json"]
    body["schema"] = {
        "type": "object",
        "required": ["note"],
        "properties": {"note": {"type": "string"}},
    }
    _write(openapi / "verification.json", spec)
    with pytest.raises(
        CodegenError, match="Two different types are both named CasesLinksCreateParams"
    ):
        generate(openapi)


def test_old_and_new_import_paths_give_the_same_type() -> None:
    from didit import types as didit_types
    from didit.types.cases.links.create_params import CasesLinksCreateParams as via_operation
    from didit.types.components.cases_links_create_params import (
        CasesLinksCreateParams as via_component,
    )

    assert via_operation is via_component is didit_types.CasesLinksCreateParams
