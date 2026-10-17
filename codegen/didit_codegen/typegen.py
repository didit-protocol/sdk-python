"""OpenAPI schemas to Python types (docs/DESIGN.md section 5.1).

Responses become pydantic models (``didit._models.BaseModel``: unknown fields
kept); request bodies become ``TypedDict``s. ``$ref`` components keep their
component name; inline objects are named after their parent plus the property.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Literal

from .naming import identifier, pascal, snake
from .spec import CodegenError, Spec

Json = Any

# Markers for names that need an import from outside the generated types.
DATETIME = "@datetime"
DATE = "@date"
LITERAL = "@Literal"
FILE_TYPES = "@FileTypes"
SEQUENCE = "@Sequence"
MAPPING = "@Mapping"
FIELD = "@Field"
REQUIRED = "@Required"


@dataclass(frozen=True)
class Ann:
    """A type annotation and the names it needs."""

    expr: str
    deps: frozenset[str] = frozenset()

    def optional(self) -> Ann:
        if self.expr == "object" or self.expr.endswith(" | None"):
            return self
        return Ann(f"{self.expr} | None", self.deps)


def union(anns: list[Ann]) -> Ann:
    parts: list[str] = []
    deps: set[str] = set()
    nullable = False
    for ann in anns:
        deps |= ann.deps
        for part in _split_union(ann.expr):
            if part == "None":
                nullable = True
            elif part not in parts:
                parts.append(part)
    if "object" in parts:
        return Ann("object", frozenset(deps))
    if "str" in parts:
        # ``Literal[...] | str`` already accepts any string.
        parts = [p for p in parts if p == "str" or not p.startswith("Literal[")] if len(parts) > 1 else parts
    expr = " | ".join(parts) if parts else "object"
    if nullable:
        expr += " | None"
    return Ann(expr, frozenset(deps))


def _split_union(expr: str) -> list[str]:
    out: list[str] = []
    depth = 0
    current = ""
    i = 0
    while i < len(expr):
        ch = expr[i]
        if ch in "[(":
            depth += 1
        elif ch in "])":
            depth -= 1
        if depth == 0 and expr.startswith(" | ", i):
            out.append(current)
            current = ""
            i += 3
            continue
        current += ch
        i += 1
    out.append(current)
    return [p.strip() for p in out if p.strip()]


@dataclass
class FieldDef:
    wire: str
    name: str
    annotation: Ann
    required: bool
    description: str | None
    deprecated: bool = False


@dataclass
class TypeDef:
    kind: Literal["model", "typeddict", "alias"]
    name: str
    module: str
    description: str | None = None
    fields: list[FieldDef] = field(default_factory=lambda: [])
    bases: list[str] = field(default_factory=lambda: [])
    alias: Ann | None = None

    @property
    def deps(self) -> set[str]:
        out: set[str] = set(self.bases)
        for f in self.fields:
            out |= set(f.annotation.deps)
        if self.alias is not None:
            out |= set(self.alias.deps)
        return out


class Registry:
    """Every generated type, by name and by module."""

    def __init__(self) -> None:
        self.defs: dict[str, TypeDef] = {}
        self.modules: dict[str, list[str]] = {}

    def add(self, td: TypeDef) -> None:
        existing = self.defs.get(td.name)
        if existing is not None:
            raise CodegenError(
                f"Two different types are both named {td.name} ({existing.module} and {td.module}); "
                "rename one of the operations or properties in openapi/overlay.json."
            )
        self.defs[td.name] = td
        self.modules.setdefault(td.module, []).append(td.name)

    def reserve(self, name: str, module: str) -> bool:
        """Whether ``name`` is still free (and not yet defined)."""
        return name not in self.defs


def _literal(values: list[Json]) -> str:
    return "Literal[" + ", ".join(json.dumps(v, ensure_ascii=False) for v in values) + "]"


def _description(schema: Json) -> str | None:
    text = schema.get("description") if isinstance(schema, dict) else None
    if isinstance(text, str) and text.strip():
        return text.strip()
    return None


@dataclass
class Usage:
    response: set[tuple[str, str]] = field(default_factory=lambda: set())
    request: set[tuple[str, str]] = field(default_factory=lambda: set())


def component_refs(spec: Spec, node: Json, out: set[tuple[str, str]]) -> None:
    """Every component reachable from ``node`` (transitively)."""
    stack = [node]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            ref = cur.get("$ref")
            if isinstance(ref, str):
                if ref.startswith("#/components/schemas/"):
                    key = (spec.name, ref.rsplit("/", 1)[1])
                    if key not in out:
                        out.add(key)
                        stack.append(spec.pointer(ref))
                else:
                    stack.append(spec.pointer(ref))
            for k, v in cur.items():
                if k in ("example", "examples"):
                    continue
                stack.append(v)
        elif isinstance(cur, list):
            stack.extend(cur)


class TypeBuilder:
    def __init__(self, specs: dict[str, Spec], usage: Usage, base_names: frozenset[str]) -> None:
        self.specs = specs
        self.usage = usage
        self.base_names = base_names
        self.registry = Registry()
        self._models: dict[tuple[str, str], str] = {}
        self._params: dict[tuple[str, str], str] = {}
        names_by_spec: dict[str, set[str]] = {}
        for spec in specs.values():
            names_by_spec[spec.name] = set(spec.components)
        self._component_names: dict[tuple[str, str], str] = {}
        for spec in specs.values():
            others = set().union(*(n for s, n in names_by_spec.items() if s != spec.name))
            for name in spec.components:
                py = name if name.isidentifier() and name[0].isupper() else pascal(name)
                if name in others and spec.name == "account":
                    py = "Account" + py
                self._component_names[(spec.name, name)] = py

    # Components ------------------------------------------------------------

    def component_name(self, spec: Spec, name: str) -> str:
        return self._component_names[(spec.name, name)]

    def component_module(self, spec: Spec, name: str) -> str:
        return "components." + snake(self.component_name(spec, name))

    def component_model(self, spec: Spec, name: str) -> Ann:
        key = (spec.name, name)
        if key not in self._models:
            py = self.component_name(spec, name)
            self._models[key] = py
            schema = spec.components[name]
            module = self.component_module(spec, name)
            ann = self._response_inner(spec, schema, py, module, define_as=py)
            if ann.expr != py:
                self.registry.add(TypeDef("alias", py, module, _description(schema), alias=ann))
        py = self._models[key]
        return Ann(py, frozenset({py}))

    def component_param(self, spec: Spec, name: str) -> Ann:
        key = (spec.name, name)
        if key not in self._params:
            base = self.component_name(spec, name)
            suffix = "Param" if key in self.usage.response else ""
            py = base + suffix
            self._params[key] = py
            schema = spec.components[name]
            module = self.component_module(spec, name)
            ann = self._param_inner(spec, schema, base, module, suffix, define_as=py)
            if ann.expr != py:
                model_alias = self.registry.defs.get(base)
                if suffix and model_alias is not None and model_alias.kind == "alias" and model_alias.alias == ann:
                    self._params[key] = base
                else:
                    self.registry.add(TypeDef("alias", py, module, _description(schema), alias=ann))
        py = self._params[key]
        return Ann(py, frozenset({py}))

    # Responses ---------------------------------------------------------------

    def response(self, spec: Spec, schema: Json, hint: str, module: str) -> Ann:
        ann = self._response_inner(spec, schema, hint, module)
        if isinstance(schema, dict) and schema.get("nullable") is True:
            ann = ann.optional()
        return ann

    def _response_inner(
        self, spec: Spec, schema: Json, hint: str, module: str, define_as: str | None = None
    ) -> Ann:
        if not isinstance(schema, dict):
            return Ann("object")
        ref = schema.get("$ref")
        if isinstance(ref, str):
            if ref.startswith("#/components/schemas/"):
                return self.component_model(spec, ref.rsplit("/", 1)[1])
            return self._response_inner(spec, spec.pointer(ref), hint, module, define_as)
        if "allOf" in schema:
            parts = schema["allOf"]
            if len(parts) == 1 and not schema.get("properties"):
                return self.response(spec, parts[0], hint, module)
            return self._model(spec, schema, define_as or hint, module, mode="response")
        for key in ("oneOf", "anyOf"):
            if key in schema:
                members = [
                    self.response(spec, member, self._variant_name(spec, member, hint, i), module)
                    for i, member in enumerate(schema[key])
                ]
                return union(members)
        if "enum" in schema:
            return self._enum(schema)
        kind = schema.get("type")
        if kind == "string":
            fmt = schema.get("format")
            if fmt == "date-time":
                return Ann("datetime", frozenset({DATETIME}))
            if fmt == "date":
                return Ann("date", frozenset({DATE}))
            if fmt == "binary":
                return Ann("bytes")
            return Ann("str")
        if kind == "integer":
            return Ann("int")
        if kind == "number":
            return Ann("float")
        if kind == "boolean":
            return Ann("bool")
        if kind == "array":
            item = self.response(spec, schema.get("items", {}), hint, module)
            return Ann(f"list[{item.expr}]", item.deps)
        if kind == "object" or "properties" in schema:
            if schema.get("properties"):
                return self._model(spec, schema, define_as or hint, module, mode="response")
            extra = schema.get("additionalProperties")
            if isinstance(extra, dict) and extra:
                value = self.response(spec, extra, hint + "Value", module)
                return Ann(f"dict[str, {value.expr}]", value.deps)
            return Ann("dict[str, object]")
        return Ann("object")

    # Request parameters -----------------------------------------------------

    def param(self, spec: Spec, schema: Json, hint: str, module: str, suffix: str = "") -> Ann:
        ann = self._param_inner(spec, schema, hint, module, suffix)
        if isinstance(schema, dict) and schema.get("nullable") is True:
            ann = ann.optional()
        return ann

    def _param_inner(
        self,
        spec: Spec,
        schema: Json,
        hint: str,
        module: str,
        suffix: str = "",
        define_as: str | None = None,
    ) -> Ann:
        if not isinstance(schema, dict):
            return Ann("object")
        ref = schema.get("$ref")
        if isinstance(ref, str):
            if ref.startswith("#/components/schemas/"):
                return self.component_param(spec, ref.rsplit("/", 1)[1])
            return self._param_inner(spec, spec.pointer(ref), hint, module, suffix, define_as)
        if "allOf" in schema:
            parts = schema["allOf"]
            if len(parts) == 1 and not schema.get("properties"):
                return self.param(spec, parts[0], hint, module, suffix)
            return self._model(spec, schema, define_as or hint + suffix, module, mode="param", suffix=suffix, hint=hint)
        for key in ("oneOf", "anyOf"):
            if key in schema:
                members = [
                    self.param(spec, member, self._variant_name(spec, member, hint, i), module, suffix)
                    for i, member in enumerate(schema[key])
                ]
                return union(members)
        if "enum" in schema:
            return self._enum(schema)
        kind = schema.get("type")
        if kind == "string":
            fmt = schema.get("format")
            if fmt == "date-time":
                return Ann("str | datetime", frozenset({DATETIME}))
            if fmt == "date":
                return Ann("str | date", frozenset({DATE}))
            if fmt == "binary":
                return Ann("FileTypes", frozenset({FILE_TYPES}))
            return Ann("str")
        if kind == "integer":
            return Ann("int")
        if kind == "number":
            return Ann("float")
        if kind == "boolean":
            return Ann("bool")
        if kind == "array":
            item = self.param(spec, schema.get("items", {}), hint, module, suffix)
            return Ann(f"Sequence[{item.expr}]", item.deps | {SEQUENCE})
        if kind == "object" or "properties" in schema:
            if schema.get("properties"):
                return self._model(spec, schema, define_as or hint + suffix, module, mode="param", suffix=suffix, hint=hint)
            extra = schema.get("additionalProperties")
            if isinstance(extra, dict) and extra:
                value = self.param(spec, extra, hint + "Value", module, suffix)
                return Ann(f"Mapping[str, {value.expr}]", value.deps | {MAPPING})
            return Ann("Mapping[str, object]", frozenset({MAPPING}))
        return Ann("object")

    # Shared ------------------------------------------------------------------

    def _variant_name(self, spec: Spec, member: Json, hint: str, index: int) -> str:
        member = spec.resolve(member) if isinstance(member, dict) and "$ref" not in member else member
        title = member.get("title") if isinstance(member, dict) else None
        if isinstance(title, str) and title.strip():
            return hint + pascal(title)
        return f"{hint}Variant{index + 1}"

    def _enum(self, schema: Json) -> Ann:
        values = [v for v in schema["enum"] if v is not None]
        kind = schema.get("type")
        if values and all(isinstance(v, str) for v in values):
            return Ann(f"{_literal(values)} | str", frozenset({LITERAL}))
        if kind == "integer" or (values and all(isinstance(v, int) and not isinstance(v, bool) for v in values)):
            return Ann("int")
        if kind == "boolean":
            return Ann("bool")
        if kind == "number":
            return Ann("float")
        return Ann("object")

    def _collect(self, spec: Spec, schema: Json) -> tuple[dict[str, Json], set[str], list[Json]]:
        """Merge ``allOf`` parts into one property map; returns (properties, required, ref parts)."""
        props: dict[str, Json] = {}
        required: set[str] = set(schema.get("required", []))
        refs: list[Json] = []
        for part in schema.get("allOf", []):
            if isinstance(part, dict) and "$ref" in part:
                refs.append(part)
            target = spec.resolve(part)
            sub_props, sub_required, _ = self._collect(spec, target)
            props.update(sub_props)
            required |= sub_required
        props.update(schema.get("properties", {}))
        return props, required, refs

    def _model(
        self,
        spec: Spec,
        schema: Json,
        name: str,
        module: str,
        *,
        mode: Literal["response", "param"],
        suffix: str = "",
        hint: str | None = None,
    ) -> Ann:
        hint = hint or name
        if name in self.registry.defs:
            raise CodegenError(f"Two different types are both named {name} (in {module}).")
        props, required, ref_parts = self._collect(spec, schema)
        bases: list[str] = []
        inherited: set[str] = set()
        own_props = props
        if len(ref_parts) == 1:
            target = spec.resolve(ref_parts[0])
            ref_name = ref_parts[0]["$ref"]
            if (
                ref_name.startswith("#/components/schemas/")
                and isinstance(target, dict)
                and target.get("properties")
                and "allOf" not in target
                and target.get("type", "object") == "object"
            ):
                comp = ref_name.rsplit("/", 1)[1]
                base_ann = (
                    self.component_model(spec, comp) if mode == "response" else self.component_param(spec, comp)
                )
                base_td = self.registry.defs.get(base_ann.expr)
                if base_td is not None and base_td.kind == ("model" if mode == "response" else "typeddict"):
                    bases.append(base_ann.expr)
                    inherited = set(target.get("properties", {}))
                    base_required = set(target.get("required", []))
                    own_props = {
                        k: v
                        for k, v in props.items()
                        if k not in inherited or (k in required) != (k in base_required)
                    }
        td = TypeDef(
            "model" if mode == "response" else "typeddict",
            name,
            module,
            _description(schema),
            bases=bases,
        )
        # Register first so that nested names can never collide with it.
        self.registry.add(td)
        taken = set(self.base_names) if mode == "response" else set()
        for wire, prop in own_props.items():
            resolved = spec.resolve(prop) if isinstance(prop, dict) else {}
            if mode == "response" and resolved.get("writeOnly") is True and prop.get("writeOnly", True):
                continue
            if mode == "param" and resolved.get("readOnly") is True:
                continue
            child_hint = hint + pascal(wire)
            if mode == "response":
                ann = self.response(spec, prop, child_hint, module)
            else:
                ann = self.param(spec, prop, child_hint, module, suffix)
            is_required = wire in required
            if mode == "response" and not is_required:
                ann = ann.optional()
            py_name = identifier(wire, taken=frozenset(taken))
            taken.add(py_name)
            td.fields.append(
                FieldDef(
                    wire=wire,
                    name=py_name,
                    annotation=ann,
                    required=is_required,
                    description=_description(prop) or _description(resolved),
                    deprecated=bool(resolved.get("deprecated")) if isinstance(resolved, dict) else False,
                )
            )
        return Ann(name, frozenset({name}))
