"""Build every generated file from ``openapi/`` (pure: no I/O besides reading the specs)."""

from __future__ import annotations

import pathlib

from .ops import Method, build_method
from .render import build_tree, render_resources, render_types
from .render_tests import render_tests
from .spec import Model, load
from .typegen import TypeBuilder, Usage, component_refs

GENERATED_ROOTS = ("src/didit/types", "src/didit/resources", "tests/generated")

# Attribute names of didit._models.BaseModel (and pydantic.BaseModel) that a
# response field must not shadow; such fields get a trailing underscore and an alias.
MODEL_RESERVED = frozenset(
    {
        "construct",
        "construct_lenient",
        "copy",
        "dict",
        "from_orm",
        "json",
        "parse_file",
        "parse_obj",
        "parse_raw",
        "schema",
        "schema_json",
        "to_dict",
        "to_json",
        "update_forward_refs",
        "validate",
        "model_computed_fields",
        "model_config",
        "model_construct",
        "model_copy",
        "model_dump",
        "model_dump_json",
        "model_extra",
        "model_fields",
        "model_fields_set",
        "model_json_schema",
        "model_parametrized_name",
        "model_post_init",
        "model_rebuild",
        "model_validate",
        "model_validate_json",
        "model_validate_strings",
        # Builtins used in annotations, which a class attribute would shadow.
        "bool",
        "bytes",
        "float",
        "int",
        "list",
        "object",
        "str",
    }
)


def usage_of(model: Model) -> Usage:
    usage = Usage()
    for op in model.server_operations:
        for code, raw in op.op.get("responses", {}).items():
            if str(code).startswith("2"):
                component_refs(op.spec, op.spec.resolve(raw), usage.response)
        body = op.op.get("requestBody")
        if body:
            body = op.spec.resolve(body)
            for media in body.get("content", {}).values():
                schema = media.get("schema", {})
                # The body root becomes <Resource><Method>Params; only nested refs count.
                component_refs(op.spec, op.spec.resolve(schema), usage.request)
    return usage


def build(openapi_dir: pathlib.Path) -> tuple[Model, TypeBuilder, list[Method]]:
    model = load(openapi_dir)
    builder = TypeBuilder(model.specs, usage_of(model), MODEL_RESERVED)
    methods = [build_method(op, builder) for op in model.server_operations]
    return model, builder, methods


def generate(openapi_dir: pathlib.Path) -> dict[str, str]:
    """Every generated file, keyed by its path relative to the repository root."""
    _, builder, methods = build(openapi_dir)
    files: dict[str, str] = {}
    for rel, text in render_types(builder.registry).items():
        files[f"src/didit/types/{rel}"] = text
    roots = build_tree(methods)
    for rel, text in render_resources(roots, builder.registry).items():
        files[f"src/didit/resources/{rel}"] = text
    for rel, text in render_tests(methods, builder.registry).items():
        files[f"tests/generated/{rel}"] = text
    return files
