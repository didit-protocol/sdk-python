"""Canonical JSON, the string ``X-Signature-V2`` signs (docs/DESIGN.md section 9.2).

It is exactly ``json.dumps(shorten_floats(value), sort_keys=True,
separators=(",", ":"), ensure_ascii=False)``, the backend's own serialisation.
"""

from __future__ import annotations

import json
import math
from typing import Any, cast

from .._exceptions import WebhookVerificationError

__all__ = ["canonical_json", "parse_body", "shorten_floats"]


def shorten_floats(value: object) -> object:
    """Write floats with an integral value as integers (``87.0`` -> ``87``), recursively."""
    if isinstance(value, dict):
        return {k: shorten_floats(v) for k, v in cast("dict[str, object]", value).items()}
    if isinstance(value, list):
        return [shorten_floats(v) for v in cast("list[object]", value)]
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def _check_finite(value: object) -> None:
    stack = [value]
    while stack:
        cur = stack.pop()
        if isinstance(cur, float) and not math.isfinite(cur):
            raise WebhookVerificationError(
                "invalid_payload", "The webhook body holds a non-finite number."
            )
        if isinstance(cur, dict):
            stack.extend(cast("dict[str, object]", cur).values())
        elif isinstance(cur, list):
            stack.extend(cast("list[object]", cur))


def canonical_json(value: object) -> str:
    """The canonical JSON text of a parsed webhook body."""
    _check_finite(value)
    try:
        return json.dumps(
            shorten_floats(value),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError, RecursionError) as exc:
        raise WebhookVerificationError(
            "invalid_payload", "The webhook payload is not JSON data Didit sends."
        ) from exc


def _reject_constant(name: str) -> Any:
    raise ValueError(f"{name} is not valid JSON")


def parse_body(raw: bytes) -> dict[str, Any]:
    """Parse a webhook body strictly: UTF-8, standard JSON (no ``NaN``), an object."""
    try:
        text = raw.decode("utf-8")
        value = json.loads(text, parse_constant=_reject_constant)
    except (
        UnicodeDecodeError,
        ValueError,
        RecursionError,
    ) as exc:  # RecursionError: absurd nesting
        raise WebhookVerificationError(
            "invalid_payload", "The webhook body is not valid JSON."
        ) from exc
    if not isinstance(value, dict):
        raise WebhookVerificationError("invalid_payload", "The webhook body is not a JSON object.")
    body = cast("dict[str, Any]", value)
    _check_finite(body)
    return body
