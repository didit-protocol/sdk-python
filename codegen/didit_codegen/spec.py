"""Load ``openapi/`` and merge the ``x-didit-sdk`` naming layer (docs/DESIGN.md sections 3 and 4)."""

from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass, field
from typing import Any

HTTP_METHODS = ("get", "put", "post", "delete", "patch", "head", "options")
AUTH_VALUES = frozenset({"api_key", "account_token", "none", "device_token", "public"})
SDK_KEYS = frozenset({"resource", "method", "auth", "server", "scope"})
APPLICATION_PREFIX = "/v3/organization/{organization_id}/application/{application_id}/"

Json = Any


class CodegenError(Exception):
    """The OpenAPI documents or the overlay cannot be turned into the SDK."""


@dataclass(frozen=True)
class SdkNaming:
    resource: str
    method: str
    auth: str
    server: bool
    scope: str | None

    @staticmethod
    def parse(key: str, raw: Json) -> SdkNaming:
        if not isinstance(raw, dict):
            raise CodegenError(f"{key}: x-didit-sdk must be an object.")
        unknown = set(raw) - SDK_KEYS
        if unknown:
            raise CodegenError(f"{key}: unknown x-didit-sdk keys {sorted(unknown)}.")
        for required in ("resource", "method", "auth", "server"):
            if required not in raw:
                raise CodegenError(f"{key}: x-didit-sdk is missing {required!r}.")
        resource, method, auth, server = raw["resource"], raw["method"], raw["auth"], raw["server"]
        scope = raw.get("scope")
        if not isinstance(resource, str) or not all(
            seg.isidentifier() and seg == seg.lower() for seg in resource.split(".")
        ):
            raise CodegenError(f"{key}: resource {resource!r} must be a dot path of snake_case names.")
        if not isinstance(method, str) or not method.isidentifier() or method != method.lower():
            raise CodegenError(f"{key}: method {method!r} must be a snake_case name.")
        if auth not in AUTH_VALUES:
            raise CodegenError(f"{key}: auth {auth!r} must be one of {sorted(AUTH_VALUES)}.")
        if not isinstance(server, bool):
            raise CodegenError(f"{key}: server must be true or false.")
        if scope not in (None, "application"):
            raise CodegenError(f"{key}: scope must be \"application\" when present.")
        return SdkNaming(resource, method, auth, server, scope)

    def as_json(self) -> dict[str, Json]:
        out: dict[str, Json] = {
            "auth": self.auth,
            "method": self.method,
            "resource": self.resource,
            "server": self.server,
        }
        if self.scope:
            out["scope"] = self.scope
        return out


@dataclass
class Spec:
    """One OpenAPI document: ``verification`` or ``account``."""

    name: str
    doc: Json

    def resolve(self, node: Json) -> Json:
        seen: set[str] = set()
        while isinstance(node, dict) and "$ref" in node:
            ref = node["$ref"]
            if ref in seen:
                raise CodegenError(f"{self.name}: circular $ref {ref}.")
            seen.add(ref)
            node = self.pointer(ref)
        return node

    def pointer(self, ref: str) -> Json:
        if not ref.startswith("#/"):
            raise CodegenError(f"{self.name}: only local $refs are supported, got {ref}.")
        cur = self.doc
        for part in ref[2:].split("/"):
            part = part.replace("~1", "/").replace("~0", "~")
            try:
                cur = cur[part]
            except (KeyError, TypeError) as exc:
                raise CodegenError(f"{self.name}: unresolvable $ref {ref}.") from exc
        return cur

    @property
    def components(self) -> dict[str, Json]:
        return dict(self.doc.get("components", {}).get("schemas", {}))


@dataclass
class Operation:
    key: str
    api: str
    http_method: str
    path: str
    op: Json
    path_item: Json
    spec: Spec
    sdk: SdkNaming
    deprecated: bool = False
    deprecation_note: str | None = None
    parameters: list[Json] = field(default_factory=lambda: [])

    @property
    def operation_id(self) -> str:
        return str(self.op.get("operationId") or self.key)


@dataclass
class Model:
    specs: dict[str, Spec]
    operations: list[Operation]

    @property
    def server_operations(self) -> list[Operation]:
        return [op for op in self.operations if op.sdk.server]


def _key(api: str, method: str, path: str) -> str:
    prefix = "account " if api == "account" else ""
    return f"{prefix}{method.upper()} {path}"


def load(openapi_dir: pathlib.Path) -> Model:
    specs = {
        "verification": Spec("verification", json.loads((openapi_dir / "verification.json").read_text("utf-8"))),
        "account": Spec("account", json.loads((openapi_dir / "account.json").read_text("utf-8"))),
    }
    overlay = json.loads((openapi_dir / "overlay.json").read_text("utf-8"))
    overlay_ops: dict[str, Json] = dict(overlay.get("operations", {}))
    deprecated_path = openapi_dir / "deprecated-operations.json"
    deprecated: dict[str, Json] = {}
    if deprecated_path.exists():
        deprecated = dict(json.loads(deprecated_path.read_text("utf-8")).get("operations", {}))

    operations: list[Operation] = []
    seen_keys: set[str] = set()
    missing: list[str] = []
    for api, spec in specs.items():
        for path, item in spec.doc.get("paths", {}).items():
            item = spec.resolve(item)
            for method in HTTP_METHODS:
                op = item.get(method)
                if op is None:
                    continue
                key = _key(api, method, path)
                seen_keys.add(key)
                raw = op.get("x-didit-sdk")
                if raw is None:
                    raw = overlay_ops.get(key)
                if raw is None:
                    missing.append(f"{key} (operationId {op.get('operationId', '-')})")
                    continue
                params = _merge_parameters(spec, item.get("parameters", []), op.get("parameters", []))
                operations.append(
                    Operation(
                        key=key,
                        api=api,
                        http_method=method,
                        path=path,
                        op=op,
                        path_item=item,
                        spec=spec,
                        sdk=SdkNaming.parse(key, raw),
                        deprecated=bool(op.get("deprecated")),
                        parameters=params,
                    )
                )
    if missing:
        lines = "\n  ".join(missing)
        raise CodegenError(
            "These operations have no SDK naming (x-didit-sdk). Add an entry to openapi/overlay.json "
            "(or ask for x-didit-sdk upstream) with resource, method, auth and server; see "
            f"docs/DESIGN.md section 4:\n  {lines}"
        )
    stale = sorted(set(overlay_ops) - seen_keys)
    if stale:
        raise CodegenError(
            "openapi/overlay.json names operations that no longer exist upstream. Run "
            "codegen/spec_sync.py, which records removed operations in "
            "openapi/deprecated-operations.json, or delete the entries:\n  " + "\n  ".join(stale)
        )

    for key, entry in sorted(deprecated.items()):
        if key in seen_keys:
            continue
        api = "account" if key.startswith("account ") else "verification"
        method, path = key.removeprefix("account ").split(" ", 1)
        doc = {"openapi": "3.0.0", "paths": {}, "components": {"schemas": {}}}
        spec = Spec(f"{api} (deprecated)", doc)
        op = entry["operation"]
        operations.append(
            Operation(
                key=key,
                api=api,
                http_method=method.lower(),
                path=path,
                op=op,
                path_item={},
                spec=spec,
                sdk=SdkNaming.parse(key, entry["x-didit-sdk"]),
                deprecated=True,
                deprecation_note=entry.get("note")
                or f"Removed from the API contract on {entry.get('removed_on', 'an unknown date')}.",
                parameters=list(op.get("parameters", [])),
            )
        )

    _check_unique(operations)
    for operation in operations:
        if operation.sdk.scope == "application" and not operation.path.startswith(APPLICATION_PREFIX):
            raise CodegenError(f"{operation.key}: scope application needs a path under {APPLICATION_PREFIX}.")
    return Model(specs=specs, operations=operations)


def _merge_parameters(spec: Spec, shared: list[Json], own: list[Json]) -> list[Json]:
    out: dict[tuple[str, str], Json] = {}
    for raw in [*shared, *own]:
        param = spec.resolve(raw)
        out[(param["in"], param["name"])] = param
    return list(out.values())


def _check_unique(operations: list[Operation]) -> None:
    by_name: dict[tuple[str, str], str] = {}
    for operation in operations:
        if not operation.sdk.server:
            continue
        name = (operation.sdk.resource, operation.sdk.method)
        if name in by_name:
            raise CodegenError(
                f"{operation.key} and {by_name[name]} both map to {name[0]}.{name[1]}; "
                "give one of them another method name in openapi/overlay.json."
            )
        by_name[name] = operation.key
    resources = {op.sdk.resource for op in operations if op.sdk.server}
    for operation in operations:
        if not operation.sdk.server:
            continue
        child = f"{operation.sdk.resource}.{operation.sdk.method}"
        if child in resources or any(r.startswith(child + ".") for r in resources):
            raise CodegenError(
                f"{operation.key}: method {operation.sdk.method!r} clashes with the nested resource {child!r}."
            )
