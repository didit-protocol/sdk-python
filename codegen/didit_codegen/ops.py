"""Turn each server operation into the description of one SDK method."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

from .naming import RESERVED_KWARGS, identifier, pascal, resource_class, snake
from .spec import CodegenError, Operation
from .typegen import Ann, TypeBuilder, TypeDef

Json = Any

BINARY_TYPES = ("application/pdf", "text/csv", "image/", "application/octet-stream", "application/zip")


@dataclass
class Arg:
    py: str
    wire: str
    location: Literal["path", "query", "body"]
    annotation: Ann
    required: bool
    description: str | None
    schema: Json = None
    example: Json = None
    has_example: bool = False


@dataclass
class ResponseInfo:
    kind: Literal["model", "bytes", "none", "page"]
    annotation: Ann
    cast_to: str
    item: Ann | None = None
    accept: str = "application/json"
    status: int = 200
    example: Json = None
    has_example: bool = False
    schema: Json = None
    content_type: str | None = None


@dataclass
class Method:
    op: Operation
    resource: str
    name: str
    path_args: list[Arg]
    kwargs: list[Arg]
    body_mode: Literal["none", "json", "multipart", "auto"]
    file_fields: list[str]
    idempotency: bool
    response: ResponseInfo
    params_type: str | None
    body_example: Json = None
    has_body_example: bool = False
    whole_body: Arg | None = None
    summary: str = ""
    description: str = ""
    deps: set[str] = field(default_factory=lambda: set())

    @property
    def is_async_def(self) -> bool:
        return self.response.kind != "page"


def types_module(resource: str, method: str, kind: str) -> str:
    return ".".join([*resource.split("."), f"{method}_{kind}"])


def _example_of(media: Json, spec_schema: Json) -> tuple[bool, Json]:
    if not isinstance(media, dict):
        return False, None
    if "example" in media:
        return True, media["example"]
    examples = media.get("examples")
    if isinstance(examples, dict) and examples:
        first = next(iter(examples.values()))
        if isinstance(first, dict) and "value" in first:
            return True, first["value"]
    if isinstance(spec_schema, dict) and "example" in spec_schema:
        return True, spec_schema["example"]
    return False, None


def _first_text(op: Json, key: str) -> str:
    text = op.get(key)
    return text.strip() if isinstance(text, str) else ""


def _has_binary(spec_schema: Json, op: Operation) -> set[str]:
    out: set[str] = set()
    schema = op.spec.resolve(spec_schema)
    if not isinstance(schema, dict):
        return out
    for name, prop in schema.get("properties", {}).items():
        prop = op.spec.resolve(prop)
        if prop.get("format") == "binary" or (prop.get("type") == "array" and op.spec.resolve(prop.get("items", {})).get("format") == "binary"):
            out.add(name)
    return out


def _merge_body(op: Operation, content: dict[str, Json]) -> tuple[Json, str, list[str], Json]:
    """The schema of the method's body arguments, the body mode, the file fields and the media."""
    json_media = content.get("application/json")
    multipart_media = content.get("multipart/form-data")
    if json_media is None and multipart_media is None:
        form = content.get("application/x-www-form-urlencoded")
        if form is None:
            raise CodegenError(f"{op.key}: unsupported request content types {sorted(content)}.")
        json_media = form
    if json_media is not None and multipart_media is None:
        return json_media.get("schema", {}), "json", [], json_media
    if json_media is None:
        assert multipart_media is not None
        schema = multipart_media.get("schema", {})
        return schema, "multipart", sorted(_has_binary(schema, op)), multipart_media
    assert multipart_media is not None
    json_schema = op.spec.resolve(json_media.get("schema", {}))
    multipart_schema = op.spec.resolve(multipart_media.get("schema", {}))
    files = _has_binary(multipart_schema, op) - set(json_schema.get("properties", {}))
    if not files:
        return json_media.get("schema", {}), "json", [], json_media
    merged = dict(json_schema)
    props = dict(json_schema.get("properties", {}))
    for name, prop in multipart_schema.get("properties", {}).items():
        props.setdefault(name, prop)
    merged["properties"] = props
    merged["required"] = [
        r for r in json_schema.get("required", []) if r in set(multipart_schema.get("required", [])) or r not in files
    ]
    merged.pop("$ref", None)
    return merged, "auto", sorted(files), json_media


def _all_fields(builder: TypeBuilder, td: TypeDef) -> list[Any]:
    out: list[Any] = []
    for base in td.bases:
        out.extend(_all_fields(builder, builder.registry.defs[base]))
    names = {f.wire for f in td.fields}
    out = [f for f in out if f.wire not in names]
    out.extend(td.fields)
    return out


def _path_names(path: str) -> list[str]:
    return re.findall(r"\{([^}]+)\}", path)


def build_method(op: Operation, builder: TypeBuilder) -> Method:
    sdk = op.sdk
    spec = op.spec
    rc = resource_class(sdk.resource) + pascal(sdk.method)
    params_name = rc + "Params"
    params_module = types_module(sdk.resource, sdk.method, "params")

    # Path arguments, in path order.
    path_params = {p["name"]: p for p in op.parameters if p["in"] == "path"}
    path_args: list[Arg] = []
    used: set[str] = set(RESERVED_KWARGS)
    for name in _path_names(op.path):
        if sdk.scope == "application" and name in ("organization_id", "application_id"):
            continue
        param = path_params.get(name, {"name": name, "schema": {"type": "string"}})
        py = identifier(snake(name), taken=frozenset(used))
        used.add(py)
        schema = param.get("schema", {"type": "string"})
        has_ex = "example" in param or (isinstance(schema, dict) and "example" in schema)
        path_args.append(
            Arg(
                py=py,
                wire=name,
                location="path",
                annotation=Ann("str"),
                required=True,
                description=_first_text(param, "description") or None,
                schema=schema,
                example=param.get("example", schema.get("example") if isinstance(schema, dict) else None),
                has_example=has_ex,
            )
        )

    # Body arguments.
    kwargs: list[Arg] = []
    body_mode: Literal["none", "json", "multipart", "auto"] = "none"
    file_fields: list[str] = []
    params_type: str | None = None
    body_example: Json = None
    has_body_example = False
    whole_body: Arg | None = None
    request_body = spec.resolve(op.op.get("requestBody")) if op.op.get("requestBody") else None
    if request_body:
        schema, mode, file_fields, media = _merge_body(op, request_body.get("content", {}))
        body_mode = mode  # type: ignore[assignment]
        has_body_example, body_example = _example_of(media, spec.resolve(schema))
        root = spec.resolve(schema)
        ann = builder.param(spec, root, params_name, params_module)
        td = builder.registry.defs.get(ann.expr)
        if td is not None and td.kind == "typeddict" and ann.expr == params_name:
            params_type = params_name
            for f in _all_fields(builder, td):
                py = identifier(f.wire, taken=frozenset(used))
                used.add(py)
                prop_schema = _prop_schema(spec, root, f.wire)
                kwargs.append(
                    Arg(
                        py=py,
                        wire=f.wire,
                        location="body",
                        annotation=f.annotation,
                        required=f.required,
                        description=f.description,
                        schema=prop_schema,
                    )
                )
        else:
            whole_body = Arg(
                py=identifier("body", taken=frozenset(used)),
                wire="",
                location="body",
                annotation=ann,
                required=bool(request_body.get("required")),
                description=_first_text(request_body, "description") or None,
                schema=root,
            )
            used.add(whole_body.py)

    # Query arguments.
    for param in op.parameters:
        if param["in"] != "query":
            continue
        name = param["name"]
        base = snake(name) if not name.isidentifier() else name
        if base in used:
            base = f"{base}_query"
        py = identifier(base, taken=frozenset(used))
        used.add(py)
        schema = param.get("schema", {})
        ann = builder.param(spec, schema, params_name + pascal(name), params_module)
        has_ex = "example" in param or (isinstance(schema, dict) and "example" in schema)
        kwargs.append(
            Arg(
                py=py,
                wire=name,
                location="query",
                annotation=ann,
                required=bool(param.get("required")),
                description=_first_text(param, "description") or None,
                schema=schema,
                example=param.get("example", schema.get("example") if isinstance(schema, dict) else None),
                has_example=has_ex,
            )
        )

    idempotency = any(
        p["in"] == "header" and p["name"].lower() == "idempotency-key" for p in op.parameters
    )

    response = _response(op, builder, rc)
    method = Method(
        op=op,
        resource=sdk.resource,
        name=sdk.method,
        path_args=path_args,
        kwargs=sorted(kwargs, key=lambda a: not a.required),
        body_mode=body_mode,
        file_fields=file_fields,
        idempotency=idempotency,
        response=response,
        params_type=params_type,
        body_example=body_example,
        has_body_example=has_body_example,
        whole_body=whole_body,
        summary=_first_text(op.op, "summary"),
        description=_first_text(op.op, "description"),
    )
    deps: set[str] = set()
    for arg in [*method.kwargs, *([whole_body] if whole_body else [])]:
        deps |= set(arg.annotation.deps)
    deps |= set(response.annotation.deps)
    if response.item is not None:
        deps |= set(response.item.deps)
    method.deps = deps
    return method


def _prop_schema(spec: Any, root: Json, wire: str) -> Json:
    props: dict[str, Json] = {}
    stack = [root]
    while stack:
        cur = spec.resolve(stack.pop())
        if not isinstance(cur, dict):
            continue
        props.update({k: v for k, v in cur.get("properties", {}).items() if k not in props})
        stack.extend(cur.get("allOf", []))
    return props.get(wire, {})


def _response(op: Operation, builder: TypeBuilder, rc: str) -> ResponseInfo:
    spec = op.spec
    successes: list[tuple[int, Json]] = []
    for code, raw in op.op.get("responses", {}).items():
        if not str(code).startswith("2"):
            continue
        successes.append((int(code), spec.resolve(raw)))
    successes.sort(key=lambda x: x[0])
    json_responses: list[tuple[int, Json]] = []
    binary: tuple[int, str] | None = None
    empty = False
    for code, resp in successes:
        content = resp.get("content") or {}
        media = content.get("application/json")
        if media is not None and "schema" in media:
            json_responses.append((code, media))
            continue
        if media is not None:
            json_responses.append((code, {"schema": {}, **media}))
            continue
        other = [ct for ct in content if any(ct.startswith(b) for b in BINARY_TYPES)]
        if other:
            binary = (code, other[0])
        else:
            empty = True
    module = types_module(op.sdk.resource, op.sdk.method, "response")
    if json_responses:
        anns: list[tuple[int, Ann]] = []
        seen_schemas: list[tuple[Json, Ann]] = []
        for index, (code, media) in enumerate(json_responses):
            schema = media.get("schema", {})
            reuse = next((a for s, a in seen_schemas if s == schema), None)
            if reuse is not None:
                anns.append((code, reuse))
                continue
            hint = rc + "Response" + ("" if index == 0 else str(code))
            resolved = spec.resolve(schema)
            if isinstance(resolved, dict) and resolved.get("type") == "array" and "$ref" not in schema:
                item = builder.response(spec, resolved.get("items", {}), hint + "Item", module)
                ann = Ann(f"list[{item.expr}]", item.deps)
                if resolved.get("nullable"):
                    ann = ann.optional()
            else:
                ann = builder.response(spec, schema, hint, module)
            seen_schemas.append((schema, ann))
            anns.append((code, ann))
        code, media = json_responses[0]
        has_ex, example = _example_of(media, spec.resolve(media.get("schema", {})))
        distinct: list[Ann] = []
        for _, a in anns:
            if a not in distinct:
                distinct.append(a)
        if len(distinct) == 1:
            annotation = distinct[0]
            cast_to = _runtime_expr(annotation)
        else:
            parts = " | ".join(a.expr for a in distinct)
            deps: set[str] = set()
            for a in distinct:
                deps |= set(a.deps)
            annotation = Ann(parts, frozenset(deps))
            cast_to = "{" + ", ".join(f"{c}: {_runtime_expr(a)}" for c, a in anns) + "}"
        if empty:
            annotation = annotation.optional()
        page_item = _page_item(op, builder, annotation)
        if page_item is not None:
            return ResponseInfo(
                kind="page",
                annotation=annotation,
                cast_to=cast_to,
                item=page_item,
                status=code,
                example=example,
                has_example=has_ex,
                schema=media.get("schema", {}),
                content_type="application/json",
            )
        return ResponseInfo(
            kind="model",
            annotation=annotation,
            cast_to=cast_to,
            status=code,
            example=example,
            has_example=has_ex,
            schema=media.get("schema", {}),
            content_type="application/json",
        )
    if binary is not None:
        code, content_type = binary
        return ResponseInfo(
            kind="bytes",
            annotation=Ann("bytes"),
            cast_to="bytes",
            accept=f"{content_type}, application/json",
            status=code,
            content_type=content_type,
        )
    code = successes[0][0] if successes else 204
    return ResponseInfo(kind="none", annotation=Ann("None"), cast_to="None", status=code)


def _runtime_expr(ann: Ann) -> str:
    return ann.expr


def _page_item(op: Operation, builder: TypeBuilder, annotation: Ann) -> Ann | None:
    if op.http_method != "get":
        return None
    query = {p["name"] for p in op.parameters if p["in"] == "query"}
    if not {"limit", "offset"} <= query:
        return None
    td = builder.registry.defs.get(annotation.expr)
    if td is None or td.kind != "model":
        return None
    fields = {f.wire: f for f in _all_fields(builder, td)}
    if not {"count", "next", "previous", "results"} <= set(fields):
        return None
    results = fields["results"].annotation.expr
    if results.endswith(" | None"):
        results = results[: -len(" | None")]
    if not results.startswith("list[") or not results.endswith("]"):
        return None
    inner = results[len("list[") : -1]
    return Ann(inner, fields["results"].annotation.deps)
