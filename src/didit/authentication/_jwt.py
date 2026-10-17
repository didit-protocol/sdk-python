"""JWS parsing and claim checks for Didit Authentication tokens (no I/O here).

Didit issuers sign with ES256 only (``service-didit-auth``
``authentication/services/issuer.py``): access tokens carry the header
``typ: at+jwt`` and ID tokens ``typ: JWT``. Every other algorithm, including
``none``, is refused before any key is looked up.
"""

from __future__ import annotations

import base64
import binascii
import hmac
import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal, NoReturn

from ._errors import TokenVerificationError, TokenVerificationReason

__all__ = [
    "ALGORITHM",
    "ParsedToken",
    "TokenKind",
    "check_claims",
    "p256_point",
    "parse_token",
]

ALGORITHM = "ES256"
MAX_TOKEN_LENGTH = 16384
TokenKind = Literal["access", "id"]

_ACCESS_TYPES = frozenset({"at+jwt", "application/at+jwt"})
_ID_TYPES = frozenset({"jwt", "application/jwt"})
_BASE64URL = re.compile(r"[A-Za-z0-9_-]*")


@dataclass(frozen=True)
class ParsedToken:
    """A JWS whose header passed the algorithm and type checks; not yet verified."""

    header: dict[str, Any]
    claims: dict[str, Any]
    signing_input: bytes
    signature: bytes
    kid: str


def _fail(reason: TokenVerificationReason, message: str) -> NoReturn:
    raise TokenVerificationError(reason, message)


def _shown(value: object) -> str:
    """A short, safe rendering of a header or claim value for an error message."""
    text = repr(value)
    return text if len(text) <= 64 else text[:61] + "..."


def b64url_decode(segment: str) -> bytes | None:
    """Unpadded base64url (RFC 7515 section 2), or ``None`` when ``segment`` is not."""
    if not _BASE64URL.fullmatch(segment) or len(segment) % 4 == 1:
        return None
    try:
        return base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))
    except (binascii.Error, ValueError):  # pragma: no cover - excluded by the pattern above
        return None


def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ValueError(f"duplicate member {key!r}")
        out[key] = value
    return out


def _no_constants(name: str) -> NoReturn:
    raise ValueError(f"{name} is not JSON")


def _json_object(segment: str, part: str) -> dict[str, Any]:
    raw = b64url_decode(segment)
    if raw is None:
        _fail("malformed", f"The token {part} is not base64url.")
    try:
        value: object = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_no_duplicates, parse_constant=_no_constants
        )
    except (UnicodeDecodeError, ValueError, RecursionError):
        _fail("malformed", f"The token {part} is not valid JSON.")
    if not isinstance(value, dict):
        _fail("malformed", f"The token {part} is not a JSON object.")
    return value  # pyright: ignore[reportUnknownVariableType]


def _check_type(header: Mapping[str, Any], kind: TokenKind) -> None:
    typ = header.get("typ")
    if kind == "access":
        if not isinstance(typ, str) or typ.lower() not in _ACCESS_TYPES:
            _fail(
                "invalid_type",
                f"The token is not an access token: its header typ is {_shown(typ)}, not 'at+jwt'.",
            )
        return
    # ID tokens are signed with typ JWT; refusing at+jwt keeps an access token from passing as one.
    if typ is not None and (not isinstance(typ, str) or typ.lower() not in _ID_TYPES):
        _fail(
            "invalid_type",
            f"The token is not an ID token: its header typ is {_shown(typ)}, not 'JWT'.",
        )


def parse_token(token: object, kind: TokenKind) -> ParsedToken:
    """Split and decode a compact JWS and check its header (``alg``, ``typ``, ``kid``).

    Raises :class:`TokenVerificationError`; nothing here is trusted until the
    signature has been checked.
    """
    if not isinstance(token, str) or not token:
        _fail("malformed", "The token is empty or not a string.")
    if len(token) > MAX_TOKEN_LENGTH:
        _fail("malformed", f"The token is longer than {MAX_TOKEN_LENGTH} characters.")
    parts = token.split(".")
    if len(parts) != 3:
        _fail("malformed", "The token is not a compact JWS (three dot-separated segments).")
    header = _json_object(parts[0], "header")
    alg = header.get("alg")
    if alg != ALGORITHM:
        _fail(
            "unsupported_algorithm",
            f"The token is signed with {_shown(alg)}; only ES256 is accepted.",
        )
    if "crit" in header:
        _fail(
            "malformed", "The token header has critical extensions (crit), which are not supported."
        )
    _check_type(header, kind)
    kid = header.get("kid")
    if not isinstance(kid, str) or not kid:
        _fail("malformed", "The token header names no signing key (kid).")
    claims = _json_object(parts[1], "payload")
    signature = b64url_decode(parts[2])
    if signature is None:
        _fail("malformed", "The token signature is not base64url.")
    return ParsedToken(
        header=header,
        claims=claims,
        signing_input=f"{parts[0]}.{parts[1]}".encode("ascii"),
        signature=signature,
        kid=kid,
    )


def p256_point(jwk: Mapping[str, Any]) -> tuple[int, int] | None:
    """The ``(x, y)`` point of a P-256 signing key in JWK form, or ``None`` when the
    key is anything else (another curve or key type, or not meant for ES256 signatures)."""
    if jwk.get("kty") != "EC" or jwk.get("crv") != "P-256":
        return None
    if jwk.get("use", "sig") != "sig" or jwk.get("alg", ALGORITHM) != ALGORITHM:
        return None
    coordinates: list[int] = []
    for name in ("x", "y"):
        value = jwk.get(name)
        raw = b64url_decode(value) if isinstance(value, str) else None
        if raw is None or len(raw) != 32:
            return None
        coordinates.append(int.from_bytes(raw, "big"))
    return coordinates[0], coordinates[1]


def _numeric_date(claims: Mapping[str, Any], name: str) -> float:
    if name not in claims:
        _fail("missing_claim", f"The token has no {name} claim.")
    value = claims[name]
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        _fail("malformed", f"The token's {name} claim is not a number of seconds.")
    return float(value)


def _audiences(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]  # pyright: ignore[reportUnknownVariableType]
    return []


def check_claims(
    claims: Mapping[str, Any],
    *,
    kind: TokenKind,
    issuer: str,
    audience: tuple[str, ...] | None,
    nonce: str | None,
    leeway: float,
    now: float,
) -> None:
    """Check the registered claims of a token whose signature is already verified.

    ``iss`` must equal ``issuer``; ``sub``, ``exp`` and ``iat`` must be present;
    ``exp``, ``nbf`` and ``iat`` are compared with ``now`` allowing ``leeway``
    seconds of clock skew; ``aud`` must contain one of ``audience`` when it is
    given; for an ID token ``nonce`` must equal ``nonce`` when it is given.
    """
    iss = claims.get("iss")
    if iss is None:
        _fail("missing_claim", "The token has no iss claim.")
    if iss != issuer:
        _fail("invalid_issuer", f"The token was issued by {_shown(iss)}, not by {issuer!r}.")
    sub = claims.get("sub")
    if not isinstance(sub, str) or not sub:
        _fail("missing_claim", "The token has no sub claim.")
    exp = _numeric_date(claims, "exp")
    iat = _numeric_date(claims, "iat")
    nbf = _numeric_date(claims, "nbf") if "nbf" in claims else None
    if now >= exp + leeway:
        _fail("expired", "The token has expired.")
    if nbf is not None and now + leeway < nbf:
        _fail("not_yet_valid", "The token is not valid yet (nbf is in the future).")
    if now + leeway < iat:
        _fail("invalid_issued_at", "The token was issued in the future (iat).")
    if audience is not None:
        if "aud" not in claims:
            _fail("missing_claim", "The token has no aud claim.")
        if not set(_audiences(claims["aud"])).intersection(audience):
            _fail("invalid_audience", "The token was not issued for this audience.")
    if kind == "id" and nonce is not None:
        token_nonce = claims.get("nonce")
        if not isinstance(token_nonce, str) or not hmac.compare_digest(
            token_nonce.encode("utf-8"), nonce.encode("utf-8")
        ):
            _fail("invalid_nonce", "The ID token's nonce does not match this sign-in.")
