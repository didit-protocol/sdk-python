"""Response model base class and tolerant response parsing.

Response models keep every field the API sends, including fields this version
of the SDK does not know yet (``model_extra``). A response that does not match
the published contract is still returned: when strict validation fails, the
model is built field by field without raising (docs/DESIGN.md section 5.1).
"""

from __future__ import annotations

import datetime as _dt
import functools
import logging
import types
from typing import Annotated, Any, Literal, Union, cast, get_args, get_origin

import pydantic
import typing_extensions
from typing_extensions import Self

__all__ = ["BaseModel", "construct_type", "validate_response"]

log = logging.getLogger("didit")


class BaseModel(pydantic.BaseModel):
    """Base class of every response model.

    Unknown fields are kept and readable through ``model_extra`` (or as
    attributes). ``model_fields_set`` tells a field that was absent from one
    that was sent as ``null``.
    """

    model_config = pydantic.ConfigDict(
        extra="allow",
        defer_build=True,
        protected_namespaces=(),
    )

    def to_dict(self) -> dict[str, Any]:
        """The model as plain JSON data, with the API's field names, without
        fields the API did not send."""
        return self.model_dump(mode="json", by_alias=True, exclude_unset=True)

    def to_json(self, *, indent: int | None = 2) -> str:
        """The model as a JSON string, with the API's field names."""
        return self.model_dump_json(by_alias=True, exclude_unset=True, indent=indent)

    @classmethod
    def construct_lenient(cls, data: dict[str, Any]) -> Self:
        """Build the model from ``data`` without raising on contract mismatches."""
        by_alias = {(field.alias or name): name for name, field in cls.model_fields.items()}
        values: dict[str, Any] = {}
        for key, value in data.items():
            name = by_alias.get(key)
            if name is None:
                values[key] = value
                continue
            values[key] = construct_type(cls.model_fields[name].annotation, value)
        return cls.model_construct(**values)


@functools.cache
def _adapter(type_: Any) -> pydantic.TypeAdapter[Any]:
    return pydantic.TypeAdapter(type_)


def _is_union(origin: Any) -> bool:
    return origin is Union or origin is types.UnionType


def construct_type(type_: Any, value: object) -> object:
    """Best-effort conversion of ``value`` to ``type_`` that never raises."""
    if value is None or type_ is Any or type_ is object:
        return value
    origin = get_origin(type_)
    if origin is Annotated:
        return construct_type(get_args(type_)[0], value)
    if _is_union(origin):
        members = [arg for arg in get_args(type_) if arg is not type(None)]
        for member in members:
            try:
                return _adapter(member).validate_python(value)
            except pydantic.ValidationError:
                continue
        if len(members) == 1:
            return construct_type(members[0], value)
        if isinstance(value, list):
            lists = [m for m in members if get_origin(m) is list]
            if lists:
                return construct_type(lists[0], cast("list[object]", value))
        if isinstance(value, dict):
            models = [m for m in members if isinstance(m, type) and issubclass(m, BaseModel)]
            if models:
                best = max(models, key=lambda m: _overlap(m, cast("dict[str, Any]", value)))
                return best.construct_lenient(cast("dict[str, Any]", value))
        return value  # pyright: ignore[reportUnknownVariableType]
    if isinstance(type_, type) and issubclass(type_, BaseModel):
        if isinstance(value, dict):
            try:
                return type_.model_validate(value)
            except pydantic.ValidationError:
                return type_.construct_lenient(cast("dict[str, Any]", value))
        return value
    if origin in (list, list):
        if isinstance(value, list):
            (inner,) = get_args(type_) or (Any,)
            return [construct_type(inner, item) for item in cast("list[object]", value)]
        return value
    if origin in (dict, dict):
        if isinstance(value, dict):
            args = get_args(type_)
            inner = args[1] if len(args) == 2 else Any
            return {
                k: construct_type(inner, v) for k, v in cast("dict[str, object]", value).items()
            }
        return value
    if origin is Literal or origin is typing_extensions.Literal:
        return value
    if type_ in (_dt.datetime, _dt.date):
        try:
            return _adapter(type_).validate_python(value)
        except pydantic.ValidationError:
            return value
    return value


def _overlap(model: type[BaseModel], data: dict[str, Any]) -> int:
    names = {(field.alias or name) for name, field in model.model_fields.items()}
    return len(names.intersection(data))


def validate_response(type_: Any, data: object) -> Any:
    """Validate ``data`` as ``type_``; fall back to :func:`construct_type`."""
    if type_ is Any or type_ is object:
        return data
    try:
        return _adapter(type_).validate_python(data)
    except pydantic.ValidationError as exc:
        log.debug(
            "Response does not match the published schema of %s (%d errors); "
            "returning it without validation.",
            getattr(type_, "__name__", type_),
            exc.error_count(),
        )
        return construct_type(type_, data)
