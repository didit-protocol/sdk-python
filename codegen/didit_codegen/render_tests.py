"""One generated test per server operation (docs/DESIGN.md section 11).

Each test calls the SDK method with values from the spec's examples (or values
synthesised from the schema), against a mocked HTTP layer, on both ``Didit``
and ``AsyncDidit``, and asserts the method, path, query, credentials, body
encoding and the parsed response type.
"""

from __future__ import annotations

import json
import re
import urllib.parse
from collections import defaultdict
from typing import Any

from .ops import Arg, Method
from .render import HEADER
from .spec import Spec
from .typegen import Registry, _split_union

Json = Any

ORG_ID = "0b5e8d2c-0000-4000-8000-0000000000aa"
APP_ID = "0b5e8d2c-0000-4000-8000-0000000000bb"
MAX_DEPTH = 6


def _uuid(n: int) -> str:
    return f"00000000-0000-4000-8000-{n:012d}"


# Values ------------------------------------------------------------------------------


def _string_sample(schema: Json, n: int) -> str:
    fmt = schema.get("format")
    if fmt == "date-time":
        return "2026-01-01T00:00:00Z"
    if fmt == "date":
        return "2026-01-01"
    if fmt == "uuid":
        return _uuid(n)
    if fmt in ("uri", "url"):
        return "https://example.com/resource"
    if fmt == "email":
        return "user@example.com"
    min_len = schema.get("minLength") or 0
    text = "sample"
    if isinstance(min_len, int) and min_len > len(text):
        text = text + "x" * (min_len - len(text))
    max_len = schema.get("maxLength")
    if isinstance(max_len, int) and max_len < len(text):
        text = text[: max(max_len, 1)]
    return text


def sample(spec: Spec, schema: Json, *, request: bool, depth: int = 0, full: bool = True) -> Json:
    """A value that conforms to ``schema``."""
    if not isinstance(schema, dict):
        return "value"
    if "$ref" in schema:
        if depth > MAX_DEPTH:
            return None
        return sample(spec, spec.resolve(schema), request=request, depth=depth + 1, full=full)
    if "allOf" in schema:
        merged: dict[str, Json] = {"type": "object", "properties": {}, "required": []}
        stack = [*schema["allOf"], {k: v for k, v in schema.items() if k != "allOf"}]
        for part in stack:
            part = spec.resolve(part)
            if "allOf" in part:
                stack.extend(part["allOf"])
            merged["properties"].update(part.get("properties", {}))
            merged["required"] += part.get("required", [])
        if not merged["properties"]:
            first = spec.resolve(schema["allOf"][0])
            return sample(spec, first, request=request, depth=depth + 1, full=full)
        return sample(spec, merged, request=request, depth=depth + 1, full=full)
    for key in ("oneOf", "anyOf"):
        if schema.get(key):
            return sample(spec, schema[key][0], request=request, depth=depth + 1, full=full)
    if "enum" in schema:
        values = [v for v in schema["enum"] if v is not None]
        return values[0] if values else None
    if "example" in schema and conforms(spec, schema, schema["example"], request=request):
        example = schema["example"]
        if not (request and _has_unknown_keys(spec, schema, example)):
            return example
    kind = schema.get("type")
    if kind == "string":
        if schema.get("format") == "binary":
            return b"file-content" if request else "binary"
        return _string_sample(schema, depth + 1)
    if kind == "integer":
        minimum = schema.get("minimum")
        return int(minimum) if isinstance(minimum, (int, float)) and minimum > 1 else 1
    if kind == "number":
        return 1.5
    if kind == "boolean":
        return True
    if kind == "array":
        if depth > MAX_DEPTH:
            return []
        item = sample(spec, schema.get("items", {}), request=request, depth=depth + 1, full=full)
        min_items = schema.get("minItems") or 1
        return [item] * max(1, min(int(min_items), 3))
    if kind == "object" or "properties" in schema:
        props = schema.get("properties", {})
        if not props:
            extra = schema.get("additionalProperties")
            if isinstance(extra, dict) and extra and depth <= MAX_DEPTH:
                return {"key": sample(spec, extra, request=request, depth=depth + 1, full=full)}
            return {}
        required = set(schema.get("required", []))
        out: dict[str, Json] = {}
        for name, prop in props.items():
            resolved = spec.resolve(prop)
            if request and resolved.get("readOnly"):
                continue
            if not request and resolved.get("writeOnly"):
                continue
            if not full and name not in required:
                continue
            if depth > MAX_DEPTH and name not in required:
                continue
            out[name] = sample(spec, prop, request=request, depth=depth + 1, full=full)
        return out
    return "value"


def _has_unknown_keys(spec: Spec, schema: Json, value: Json) -> bool:
    schema = spec.resolve(schema)
    if isinstance(value, dict) and isinstance(schema, dict) and schema.get("properties"):
        props = schema["properties"]
        for key, item in value.items():
            if key not in props or _has_unknown_keys(spec, props[key], item):
                return True
    if isinstance(value, list) and isinstance(schema, dict) and schema.get("type") == "array":
        return any(_has_unknown_keys(spec, schema.get("items", {}), item) for item in value)
    return False


def conforms(spec: Spec, schema: Json, value: Json, *, request: bool, depth: int = 0) -> bool:
    """Whether ``value`` matches ``schema`` closely enough to type-check as the SDK's type."""
    if depth > 20 or not isinstance(schema, dict):
        return True
    schema = spec.resolve(schema)
    if value is None:
        return schema.get("nullable") is True or not schema
    if "allOf" in schema:
        return all(
            conforms(spec, part, value, request=request, depth=depth + 1)
            for part in schema["allOf"]
        )
    for key in ("oneOf", "anyOf"):
        if key in schema:
            return any(
                conforms(spec, part, value, request=request, depth=depth + 1)
                for part in schema[key]
            )
    if "enum" in schema:
        if all(isinstance(v, str) for v in schema["enum"] if v is not None):
            return isinstance(value, str)
        return value in schema["enum"]
    kind = schema.get("type")
    if kind == "string":
        if schema.get("format") == "binary":
            return isinstance(value, (bytes, str))
        if not isinstance(value, str):
            return False
        max_len = schema.get("maxLength")
        return not (isinstance(max_len, int) and len(value) > max_len)
    if kind == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if kind == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if kind == "boolean":
        return isinstance(value, bool)
    if kind == "array":
        return isinstance(value, list) and all(
            conforms(spec, schema.get("items", {}), v, request=request, depth=depth + 1)
            for v in value
        )
    if kind == "object" or "properties" in schema:
        if not isinstance(value, dict):
            return False
        props = schema.get("properties", {})
        if props:
            for name in schema.get("required", []):
                if name not in value and not (
                    request and spec.resolve(props.get(name, {})).get("readOnly")
                ):
                    return False
            for key, item in value.items():
                if key in props:
                    resolved = spec.resolve(props[key])
                    if request and resolved.get("readOnly"):
                        return False
                    if not conforms(spec, props[key], item, request=request, depth=depth + 1):
                        return False
                elif request:
                    return False
            return True
        extra = schema.get("additionalProperties")
        if isinstance(extra, dict) and extra:
            return all(
                conforms(spec, extra, v, request=request, depth=depth + 1) for v in value.values()
            )
        return True
    return True


def literal(value: Json) -> str:
    """A Python literal for a JSON value."""
    if isinstance(value, bytes):
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return "True" if value else "False"
    if value is None:
        return "None"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, list):
        return "[" + ", ".join(literal(v) for v in value) + "]"
    if isinstance(value, dict):
        return (
            "{"
            + ", ".join(
                f"{json.dumps(k, ensure_ascii=False)}: {literal(v)}" for k, v in value.items()
            )
            + "}"
        )
    raise TypeError(f"Unsupported example value {value!r}")


def _query_text(value: Json) -> list[str]:
    if isinstance(value, bool):
        return ["true" if value else "false"]
    if isinstance(value, list):
        return [t for v in value for t in _query_text(v)]
    return [str(value)]


# Tests -----------------------------------------------------------------------------


def _check_expr(ann: str, registry: Registry, imports: set[tuple[str, str]], depth: int = 0) -> str:
    parts = _split_union(ann)
    checks: list[str] = []
    for part in parts:
        checks.append(_part_check(part, registry, imports, depth))
    if "True" in checks:
        return "True"
    return " or ".join(f"({c})" for c in checks) if len(checks) > 1 else checks[0]


def _part_check(part: str, registry: Registry, imports: set[tuple[str, str]], depth: int) -> str:
    var = "r" if depth == 0 else f"x{depth}"
    if part == "None":
        return f"{var} is None"
    if part in ("str", "int", "float", "bool", "bytes"):
        return f"isinstance({var}, {part})"
    if part.startswith("Literal["):
        return f"isinstance({var}, str)"
    if part in ("object",) or part.startswith("_dt."):
        return "True"
    if part.startswith("list["):
        inner = part[len("list[") : -1]
        inner_check = _check_expr(inner, registry, imports, depth + 1)
        nxt = f"x{depth + 1}"
        if inner_check == "True":
            return f"isinstance({var}, list)"
        return f"isinstance({var}, list) and all({inner_check} for {nxt} in {var})"
    if part.startswith("dict["):
        return f"isinstance({var}, dict)"
    td = registry.defs.get(part)
    if td is None:
        return "True"
    if td.kind == "alias":
        assert td.alias is not None
        return _check_expr(td.alias.expr, registry, imports, depth)
    imports.add((td.module, td.name))
    return f"isinstance({var}, {td.name})"


def _kwargs_for(method: Method) -> list[tuple[Arg, Json]]:
    spec = method.op.spec
    out: list[tuple[Arg, Json]] = []
    body_args = [a for a in method.kwargs if a.location == "body"]
    by_wire = {a.wire: a for a in body_args}
    example = method.body_example if method.has_body_example else None
    use_example = (
        isinstance(example, dict)
        and example
        and all(
            k in by_wire
            and conforms(spec, by_wire[k].schema, v, request=True)
            and not _has_unknown_keys(spec, by_wire[k].schema, v)
            for k, v in example.items()
        )
        and all(a.wire in example for a in body_args if a.required)
    )
    chosen: dict[str, Json] = {}
    if use_example:
        assert isinstance(example, dict)
        for key, value in example.items():
            if key in method.file_fields:
                value = b"file-content"
            chosen[key] = value
    else:
        for i, arg in enumerate(body_args):
            if arg.required or (not any(a.required for a in body_args) and i == 0):
                chosen[arg.wire] = sample(spec, arg.schema, request=True, full=False)
    for name in method.file_fields:
        if name in chosen:
            chosen[name] = b"file-content"
    for arg in body_args:
        if arg.wire in chosen:
            out.append((arg, chosen[arg.wire]))
    for arg in (a for a in method.kwargs if a.location == "query"):
        if (
            arg.has_example
            and conforms(spec, arg.schema, arg.example, request=True)
            and arg.example is not None
        ):
            value = arg.example
        else:
            value = sample(spec, arg.schema, request=True, full=False)
            if value is None:
                continue
        out.append((arg, value))
    return out


def _path_values(method: Method) -> list[tuple[Arg, str]]:
    out: list[tuple[Arg, str]] = []
    for i, arg in enumerate(method.path_args):
        value = (
            arg.example
            if isinstance(arg.example, str) and re.fullmatch(r"[A-Za-z0-9_-]+", arg.example or "")
            else _uuid(i + 1)
        )
        out.append((arg, value))
    return out


def _response_value(method: Method) -> tuple[int, Json, bool]:
    """(status, body, strict): ``strict`` when the body was synthesised from the schema."""
    resp = method.response
    spec = method.op.spec
    if resp.kind in ("model", "page"):
        if resp.has_example and resp.example is not None:
            return resp.status, resp.example, False
        return resp.status, sample(spec, resp.schema, request=False), True
    return resp.status, None, False


def _render_test(method: Method, registry: Registry, imports: set[tuple[str, str]]) -> str:
    op = method.op
    path_values = _path_values(method)
    kwargs = _kwargs_for(method)
    path = op.path
    if op.sdk.scope == "application":
        path = path.replace("{organization_id}", ORG_ID).replace("{application_id}", APP_ID)
    for arg, value in path_values:
        path = path.replace("{" + arg.wire + "}", urllib.parse.quote(value, safe=""))
    query: dict[str, list[str]] = defaultdict(list)
    json_body: dict[str, Json] = {}
    for arg, value in kwargs:
        if arg.location == "query":
            query[arg.wire].extend(_query_text(value))
        else:
            json_body[arg.wire] = value
    call_args = [literal(v) for _, v in path_values]
    call_args += [f"{a.py}={literal(v)}" for a, v in kwargs]
    resource = op.sdk.resource
    call = f"c.{resource}.{op.sdk.method}({', '.join(call_args)})"

    status, response, strict = _response_value(method)
    multipart = method.body_mode == "multipart" or (
        method.body_mode == "auto" and any(name in json_body for name in method.file_fields)
    )
    resp = method.response
    if resp.kind == "page":
        assert resp.item is not None
        item_check = _check_expr(resp.item.expr, registry, imports, depth=1)
        items = "x1"
        sync_check = f"isinstance(r, SyncPage) and all({item_check} for {items} in r.results)"
        async_check = f"isinstance(r, AsyncPage) and all({item_check} for {items} in r.results)"
        if item_check == "True":
            sync_check, async_check = "isinstance(r, SyncPage)", "isinstance(r, AsyncPage)"
        imports.add(("@didit", "AsyncPage"))
        imports.add(("@didit", "SyncPage"))
        strict_type = None
    elif resp.kind == "bytes":
        sync_check = async_check = "r == BINARY_BODY"
        strict_type = None
    elif resp.kind == "none":
        sync_check = async_check = "r is None"
        strict_type = None
    else:
        sync_check = async_check = _check_expr(resp.annotation.expr, registry, imports)
        strict_type = resp.cast_to if strict and not resp.cast_to.startswith("{") else None
        if strict_type:
            for dep in resp.annotation.deps:
                if not dep.startswith("@"):
                    imports.add((registry.defs[dep].module, dep))

    fields: list[str] = [
        f'method="{op.http_method.upper()}"',
        f"path={json.dumps(path)}",
        f'api="{op.api}"',
        f'auth="{op.sdk.auth}"',
    ]
    if query:
        fields.append(f"query={literal(dict(query))}")
    if method.body_mode != "none":
        if multipart:
            text_fields = sorted(k for k in json_body if k not in method.file_fields)
            file_fields = sorted(k for k in json_body if k in method.file_fields)
            fields.append(f"multipart_fields={literal(text_fields)}")
            fields.append(f"multipart_files={literal(file_fields)}")
        else:
            fields.append(f"json_body={literal(json_body)}")
    fields.append(f"status={status}")
    if resp.kind == "bytes":
        fields.append("response_bytes=BINARY_BODY")
        fields.append(f"response_content_type={json.dumps(resp.content_type)}")
    elif response is not None:
        fields.append(f"response_json={literal(response)}")
    if strict_type:
        fields.append(f"strict_type={strict_type}")

    name = f"test_{resource.replace('.', '_')}_{op.sdk.method}"
    deprecated = op.deprecated
    out = []
    if deprecated:
        out.append('@pytest.mark.filterwarnings("ignore::DeprecationWarning")\n')
    out.append(f"def {name}() -> None:\n")
    out.append(f'    """``{op.http_method.upper()} {op.path}``"""\n')
    out.append("    check_operation(\n")
    out.append("        Expect(\n")
    out.extend(f"            {f},\n" for f in fields)
    out.append("        ),\n")
    out.append(f"        lambda c: {call},\n")
    out.append(f"        lambda c: {call},\n")
    out.append(f"        lambda r: {sync_check},\n")
    out.append(f"        lambda r: {async_check},\n")
    out.append("    )\n")
    return "".join(out)


def render_tests(methods: list[Method], registry: Registry) -> dict[str, str]:
    by_root: dict[str, list[Method]] = defaultdict(list)
    for method in methods:
        by_root[method.resource.split(".")[0]].append(method)
    files: dict[str, str] = {"__init__.py": HEADER}
    for root, group in sorted(by_root.items()):
        imports: set[tuple[str, str]] = set()
        bodies = [
            _render_test(m, registry, imports)
            for m in sorted(group, key=lambda m: (m.resource, m.name))
        ]
        out = [HEADER, f'"""Generated tests of the ``{root}`` resources: one per operation."""\n\n']
        out.append("from __future__ import annotations\n\n")
        if any(m.op.deprecated for m in group):
            out.append("import pytest\n\n")
        didit_names = sorted(n for m, n in imports if m == "@didit")
        if didit_names:
            out.append(f"from didit import {', '.join(didit_names)}\n")
        by_module: dict[str, list[str]] = defaultdict(list)
        for module, name in imports:
            if module != "@didit":
                by_module[module].append(name)
        for module in sorted(by_module):
            out.append(f"from didit.types.{module} import {', '.join(sorted(by_module[module]))}\n")
        harness = ["Expect", "check_operation"]
        if any(m.response.kind == "bytes" for m in group):
            harness.insert(0, "BINARY_BODY")
        out.append(f"from tests.harness import {', '.join(harness)}\n")
        for body in bodies:
            out.append("\n\n")
            out.append(body)
        files[f"test_{root}.py"] = "".join(out)
    return files
