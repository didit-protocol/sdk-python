"""Webhook signature verification (docs/DESIGN.md section 9.3)."""

from __future__ import annotations

import hashlib
import hmac
import math
import re
import time
from collections.abc import Iterable, Mapping, Sequence
from typing import Any, Union, cast

from .._exceptions import ConfigurationError, WebhookVerificationError
from ._canonical import canonical_json, parse_body
from ._events import VerifiedBy, WebhookEvent, parse_event

__all__ = ["DEFAULT_TOLERANCE", "HeadersLike", "verify", "verify_parsed"]

DEFAULT_TOLERANCE = 300
_HEX = re.compile(r"^[0-9a-f]{64}\Z")
_DIGITS = re.compile(r"^[0-9]{1,20}\Z")

HeadersLike = Union[Mapping[str, Any], Iterable[tuple[str, str]]]
"""The request headers: any mapping (Django ``request.headers``, Starlette and
Flask headers, ``dict``) or a list of ``(name, value)`` pairs. Names are
matched case-insensitively."""

_RAW = ("x-signature", "x-signature-previous")
_V2 = ("x-signature-v2", "x-signature-v2-previous")
_SIMPLE = ("x-signature-simple", "x-signature-simple-previous")


def _normalise_headers(headers: HeadersLike) -> dict[str, str]:
    pairs: Iterable[tuple[Any, Any]]
    pairs = cast("Mapping[Any, Any]", headers).items() if isinstance(headers, Mapping) else headers
    out: dict[str, str] = {}
    for raw_name, raw_value in pairs:
        if isinstance(raw_name, bytes):  # raw ASGI scope["headers"]
            raw_name = raw_name.decode("latin-1")
        name = str(raw_name).lower()
        if name.startswith("http_"):  # WSGI environ / Django request.META
            name = name[5:].replace("_", "-")
        value = raw_value
        if isinstance(value, (list, tuple)):
            items = cast("Sequence[Any]", value)
            value = items[0] if items else ""
        if isinstance(value, bytes):
            value = value.decode("latin-1")
        out.setdefault(name, str(value).strip())
    return out


def _secrets(secret: str | Sequence[str] | None) -> list[bytes]:
    if secret is None:
        raise ConfigurationError(
            "No webhook secret (None); copy it from the webhook destination in the console, "
            "for example into DIDIT_WEBHOOK_SECRET."
        )
    if isinstance(secret, (bytes, bytearray, memoryview)):
        raise ConfigurationError("The webhook secret must be a str, not bytes.")
    items: list[object] = [secret] if isinstance(secret, str) else list(secret)
    if any(not isinstance(s, str) for s in items):
        raise ConfigurationError("Every webhook secret must be a str.")
    if not items or any(not s for s in items):
        raise ConfigurationError(
            "The webhook secret is empty; copy it from the webhook destination in the console."
        )
    return [cast("str", s).encode("utf-8") for s in items]


def _check_tolerance(tolerance: int) -> None:
    # ``not >= 0`` also refuses NaN, which would otherwise switch the replay check off.
    if isinstance(tolerance, bool) or not isinstance(tolerance, (int, float)) or not tolerance >= 0:  # pyright: ignore[reportUnnecessaryIsInstance]
        raise ConfigurationError("tolerance must be 0 or more seconds.")


def _timestamp(
    payload: Mapping[str, Any], headers: Mapping[str, str], tolerance: int, now: float
) -> int:
    # Didit writes the timestamp as a JSON integer (floats with an integral value
    # are shortened before signing), so anything else is not a Didit delivery.
    raw = payload.get("timestamp")
    if not isinstance(raw, int) or isinstance(raw, bool):
        raise WebhookVerificationError(
            "missing_timestamp", "The webhook body has no integer timestamp."
        )
    header = headers.get("x-timestamp")
    if header is not None:
        header_value = int(header) if _DIGITS.match(header) else None
        if header_value != raw:
            raise WebhookVerificationError(
                "timestamp_mismatch",
                "X-Timestamp does not match the timestamp in the webhook body.",
            )
    try:
        skew = abs(now - raw)
    except OverflowError:  # an integer too large for a float
        skew = math.inf
    if skew > tolerance:
        raise WebhookVerificationError(
            "timestamp_out_of_tolerance",
            f"The webhook timestamp is more than {tolerance} seconds away from now; it may be a replay.",
        )
    return raw


def _matches(message: bytes, secrets: list[bytes], candidates: list[str]) -> bool:
    good = [c for c in candidates if _HEX.match(c)]
    if not good:
        return False
    for key in secrets:
        expected = hmac.new(key, message, hashlib.sha256).hexdigest()
        for candidate in good:
            if hmac.compare_digest(expected, candidate):
                return True
    return False


def _simple_message(payload: Mapping[str, Any]) -> bytes:
    # The backend formats each field with str(), so a JSON null reads "None".
    parts = [str(payload.get(k, "")) for k in ("timestamp", "session_id", "status", "webhook_type")]
    return ":".join(parts).encode("utf-8")


def _canonical_bytes(payload: Mapping[str, Any]) -> bytes:
    return canonical_json(payload).encode("utf-8", "surrogatepass")


def verify(
    raw_body: bytes | bytearray | memoryview | str,
    headers: HeadersLike,
    secret: str | Sequence[str] | None,
    *,
    tolerance: int = DEFAULT_TOLERANCE,
    allow_simple: bool = False,
) -> WebhookEvent:
    """Verify a webhook delivery and return its typed event.

    Pass the exact bytes of the request body. ``secret`` is the destination's
    secret, or a list of secrets during a rotation. The delivery is accepted when
    ``X-Signature`` matches the body, or ``X-Signature-V2`` matches its canonical
    JSON, or one of their ``-Previous`` variants matches. ``X-Signature-Simple``
    (deprecated) counts only with ``allow_simple=True``, and then
    ``event.body_authenticated`` is ``False``: re-fetch the record from the API.

    Raises :class:`didit.WebhookVerificationError` (see ``reason``) for anything
    the request carries, or :class:`didit.ConfigurationError` for a missing or
    empty secret or a negative tolerance.
    """
    keys = _secrets(secret)
    _check_tolerance(tolerance)
    try:
        raw = raw_body.encode("utf-8") if isinstance(raw_body, str) else bytes(raw_body)
    except UnicodeEncodeError as exc:  # a str with a lone surrogate
        raise WebhookVerificationError(
            "invalid_payload", "The webhook body is not valid UTF-8 text."
        ) from exc
    payload = parse_body(raw)
    normalised = _normalise_headers(headers)
    _timestamp(payload, normalised, tolerance, time.time())

    present = [h for h in (*_RAW, *_V2, *_SIMPLE) if normalised.get(h)]
    if not present:
        raise WebhookVerificationError(
            "missing_signature", "The delivery has no X-Signature header."
        )
    verified_by: VerifiedBy | None = None
    raw_candidates = [normalised[h] for h in _RAW if normalised.get(h)]
    v2_candidates = [normalised[h] for h in _V2 if normalised.get(h)]
    simple_candidates = [normalised[h] for h in _SIMPLE if normalised.get(h)]
    if raw_candidates and _matches(raw, keys, raw_candidates):
        verified_by = "signature"
    elif v2_candidates and _matches(_canonical_bytes(payload), keys, v2_candidates):
        verified_by = "signature_v2"
    elif (
        allow_simple
        and simple_candidates
        and _matches(_simple_message(payload), keys, simple_candidates)
    ):
        verified_by = "signature_simple"
    if verified_by is None:
        raise WebhookVerificationError(
            "invalid_signature", "No webhook signature matches the secret."
        )
    return parse_event(payload, verified_by)


def verify_parsed(
    payload: Mapping[str, Any],
    headers: HeadersLike,
    secret: str | Sequence[str] | None,
    *,
    tolerance: int = DEFAULT_TOLERANCE,
) -> WebhookEvent:
    """Verify a delivery when only the parsed JSON body is available.

    Only ``X-Signature-V2`` (and ``X-Signature-V2-Previous``) can be checked,
    because the other signatures cover the exact body bytes. Prefer
    :func:`verify` with the raw body whenever the framework gives access to it.
    """
    keys = _secrets(secret)
    _check_tolerance(tolerance)
    if not isinstance(payload, Mapping):  # pyright: ignore[reportUnnecessaryIsInstance]
        raise WebhookVerificationError(
            "invalid_payload", "The webhook payload is not a JSON object."
        )
    body = dict(payload)
    normalised = _normalise_headers(headers)
    _timestamp(body, normalised, tolerance, time.time())
    v2_candidates = [normalised[h] for h in _V2 if normalised.get(h)]
    if not v2_candidates:
        raise WebhookVerificationError(
            "missing_signature",
            "verify_parsed needs X-Signature-V2; pass the raw body to verify() to check X-Signature.",
        )
    if not _matches(_canonical_bytes(body), keys, v2_candidates):
        raise WebhookVerificationError(
            "invalid_signature", "No webhook signature matches the secret."
        )
    return parse_event(body, "signature_v2")
