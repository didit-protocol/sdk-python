"""Small helpers shared by the core: request encoding and environment lookups."""

from __future__ import annotations

import datetime as _dt
import json
import os
import platform
import urllib.parse
from collections.abc import Iterable, Mapping
from typing import Any, cast

import httpx
import pydantic

from ._exceptions import DiditError
from ._files import HttpxFile, to_httpx_file
from ._types import NotGiven
from ._version import __version__

__all__ = [
    "encode_json",
    "encode_path",
    "env",
    "is_given",
    "multipart_fields",
    "query_params",
    "redact_request",
    "strip_not_given",
    "user_agent",
]


def is_given(value: object) -> bool:
    return not isinstance(value, NotGiven)


def env(name: str) -> str | None:
    value = os.environ.get(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


def strip_not_given(value: object) -> Any:
    """Drop omitted (``NOT_GIVEN``) values, encode dates as ISO 8601 text and turn
    response models back into the JSON the API sent (so a result can be posted again)."""
    if isinstance(value, pydantic.BaseModel):
        return value.model_dump(mode="json", by_alias=True, exclude_unset=True, warnings=False)
    if isinstance(value, Mapping):
        items = cast("Mapping[str, object]", value).items()
        return {k: strip_not_given(v) for k, v in items if not isinstance(v, NotGiven)}
    if isinstance(value, (list, tuple)):
        return [strip_not_given(v) for v in cast("Iterable[object]", value)]
    if isinstance(value, (_dt.datetime, _dt.date)):
        return value.isoformat()
    return value


def encode_json(value: object) -> bytes:
    """Compact JSON for a request body; raises :class:`DiditError` for values JSON
    cannot carry (``NaN``, ``Infinity``, arbitrary objects) before anything is sent."""
    try:
        return json.dumps(strip_not_given(value), separators=(",", ":"), allow_nan=False).encode()
    except (TypeError, ValueError) as exc:
        raise DiditError(f"The request body cannot be sent as JSON: {exc}") from exc


def _scalar_text(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (_dt.datetime, _dt.date)):
        return value.isoformat()
    return str(value)


def query_params(params: Mapping[str, object] | None) -> list[tuple[str, str]]:
    """Encode query parameters; ``NOT_GIVEN`` and ``None`` are left out."""
    out: list[tuple[str, str]] = []
    if not params:
        return out
    for key, value in params.items():
        if value is None or isinstance(value, NotGiven):
            continue
        if isinstance(value, (list, tuple)):
            out.extend((key, _scalar_text(v)) for v in cast("Iterable[object]", value))
        else:
            out.append((key, _scalar_text(value)))
    return out


def multipart_fields(
    body: Mapping[str, object], file_fields: Iterable[str]
) -> tuple[dict[str, str], list[tuple[str, HttpxFile]]]:
    """Split a request body into multipart text fields and files.

    Objects and arrays are sent as JSON-encoded text fields, which is how the
    Didit API reads structured values in multipart requests.
    """
    names = set(file_fields)
    data: dict[str, str] = {}
    files: list[tuple[str, HttpxFile]] = []
    for key, value in body.items():
        if value is None or isinstance(value, NotGiven):
            continue
        if key in names:
            if isinstance(value, list):
                files.extend((key, to_httpx_file(v)) for v in value)  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]
            else:
                files.append((key, to_httpx_file(cast("Any", value))))
        elif isinstance(value, (Mapping, list, tuple)):
            data[key] = encode_json(cast(object, value)).decode()
        else:
            data[key] = _scalar_text(value)
    return data, files


def encode_path(template: str, params: Mapping[str, object]) -> str:
    """Fill ``{name}`` placeholders with percent-encoded values.

    Empty values and the dot segments ``.`` and ``..`` are refused so that a
    caller-supplied id can never change which endpoint is called.
    """
    out = template
    for name, value in params.items():
        if isinstance(value, NotGiven) or value is None:
            raise ValueError(f"The path parameter {name!r} is required.")
        text = _scalar_text(value)
        if text in ("", ".", ".."):
            raise ValueError(f"The path parameter {name!r} must be a non-empty id, got {text!r}.")
        out = out.replace("{" + name + "}", urllib.parse.quote(text, safe=""))
    return out


# Request headers that carry credentials; blanked on requests attached to errors.
_CREDENTIAL_HEADERS = ("x-api-key", "authorization")


def redact_request(request: httpx.Request) -> None:
    """Blank the credentials on a request that an error keeps a reference to, so
    error reporters that serialise exception attributes never capture them."""
    for name in _CREDENTIAL_HEADERS:
        if name in request.headers:
            request.headers[name] = "[redacted]"


def user_agent() -> str:
    system = platform.system() or "unknown"
    return (
        f"didit-python/{__version__} "
        f"({platform.python_implementation()} {platform.python_version()}; {system})"
    )


def client_header() -> str:
    return f"python/{__version__}"
