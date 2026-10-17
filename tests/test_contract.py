"""Contract test (DESIGN 11): every ``server: true`` operation in openapi/ has exactly
one SDK method, on both clients, and the SDK has no other API methods.

It reads the specs and the overlay directly, independently of the generator.
"""

from __future__ import annotations

import inspect
import json
import pathlib
import re
from typing import Any

import pytest

from didit import AsyncDidit, Didit
from didit._resource import AsyncAPIResource, SyncAPIResource

OPENAPI = pathlib.Path(__file__).resolve().parents[1] / "openapi"
METHODS = ("get", "put", "post", "delete", "patch", "head", "options")
# Hand-written helpers that are not API operations.
CORE_METHODS = {("webhooks", "verify"), ("webhooks", "verify_parsed")}


def _spec_operations() -> dict[tuple[str, str], dict[str, Any]]:
    overlay = json.loads((OPENAPI / "overlay.json").read_text("utf-8"))["operations"]
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for name, prefix in (("verification.json", ""), ("account.json", "account ")):
        spec = json.loads((OPENAPI / name).read_text("utf-8"))
        for path, item in spec["paths"].items():
            for method in METHODS:
                op = item.get(method)
                if op is None:
                    continue
                key = f"{prefix}{method.upper()} {path}"
                naming = op.get("x-didit-sdk") or overlay[key]
                if not naming["server"]:
                    continue
                name_key = (naming["resource"], naming["method"])
                assert name_key not in out, f"{key} duplicates {name_key}"
                out[name_key] = {"key": key, "path": path, "naming": naming, "op": op, "item": item}
    deprecated = json.loads((OPENAPI / "deprecated-operations.json").read_text("utf-8"))[
        "operations"
    ]
    for key, entry in deprecated.items():
        naming = entry["x-didit-sdk"]
        path = key.removeprefix("account ").split(" ", 1)[1]
        out.setdefault(
            (naming["resource"], naming["method"]),
            {"key": key, "path": path, "naming": naming, "op": entry["operation"], "item": {}},
        )
    return out


def _sdk_methods(root: Any, base: type) -> dict[tuple[str, str], Any]:
    found: dict[tuple[str, str], Any] = {}

    def walk(resource: Any, path: str) -> None:
        for name in dir(resource):
            if name.startswith("_") or name in ("with_raw_response", "with_streaming_response"):
                continue
            value = getattr(resource, name)
            if isinstance(value, base):
                walk(value, f"{path}.{name}" if path else name)
            elif callable(value):
                found[(path, name)] = value

    for name in dir(type(root)):
        if name.startswith("_"):
            continue
        value = getattr(root, name)
        if isinstance(value, base):
            walk(value, name)
    return found


SPEC = _spec_operations()


def test_operation_counts() -> None:
    assert len(SPEC) == 257
    resources = {resource for resource, _ in SPEC}
    assert len(resources) == 50


@pytest.mark.parametrize(
    ("client", "base"),
    [
        (Didit(api_key="contract"), SyncAPIResource),
        (AsyncDidit(api_key="contract"), AsyncAPIResource),
    ],
    ids=["Didit", "AsyncDidit"],
)
def test_spec_operations_equal_sdk_methods(client: Any, base: type) -> None:
    sdk = _sdk_methods(client, base)
    api_methods = {k for k in sdk if k not in CORE_METHODS}
    missing = sorted(set(SPEC) - api_methods)
    extra = sorted(api_methods - set(SPEC))
    assert not missing, f"operations without an SDK method: {missing}"
    assert not extra, f"SDK methods without an operation: {extra}"
    assert set(sdk) >= CORE_METHODS


def test_signatures_follow_the_paths() -> None:
    client = Didit(api_key="contract")
    sdk = _sdk_methods(client, SyncAPIResource)
    for name, info in SPEC.items():
        params = inspect.signature(sdk[name]).parameters
        positional = [
            p for p in params.values() if p.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
        ]
        path_names = re.findall(r"\{([^}]+)\}", info["path"])
        if info["naming"].get("scope") == "application":
            assert info["path"].startswith(
                "/v3/organization/{organization_id}/application/{application_id}/"
            )
            path_names = [p for p in path_names if p not in ("organization_id", "application_id")]
        assert len(positional) == len(path_names), name
        for option in ("extra_headers", "extra_query", "extra_body", "timeout"):
            assert option in params, (name, option)
        has_idempotency = any(
            p.get("in") == "header" and p.get("name", "").lower() == "idempotency-key"
            for p in [*info["item"].get("parameters", []), *info["op"].get("parameters", [])]
        )
        assert ("idempotency_key" in params) == has_idempotency, name


def test_async_methods_are_awaitable() -> None:
    client = AsyncDidit(api_key="contract")
    for name, method in _sdk_methods(client, AsyncAPIResource).items():
        if name in CORE_METHODS:
            continue
        returns = str(inspect.signature(method).return_annotation)
        assert inspect.iscoroutinefunction(method) or returns.startswith("AsyncPaginator["), name


def test_device_and_public_operations_are_not_exposed() -> None:
    overlay = json.loads((OPENAPI / "overlay.json").read_text("utf-8"))["operations"]
    hidden = {(v["resource"], v["method"]) for v in overlay.values() if not v["server"]}
    assert len(hidden) == 9
    sdk = _sdk_methods(Didit(api_key="contract"), SyncAPIResource)
    assert not hidden & set(sdk)
