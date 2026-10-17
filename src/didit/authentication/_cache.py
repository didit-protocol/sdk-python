"""Caching of the issuer's discovery document and key set (no I/O here).

Both are cached for the response's ``Cache-Control: max-age`` (Didit sends
``public, max-age=300``), five minutes when the header is absent, never less than
a minute and never more than a day. A token whose ``kid`` is not in the cached
key set triggers a refetch only when the last attempt, successful or not, is at
least a minute old; while the issuer's keys cannot be fetched, verification
fails fast for a minute instead of trying again on every token.
"""

from __future__ import annotations

import contextlib
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, cast

import httpx

from ._crypto import load_p256_key
from ._errors import TokenVerificationError
from ._jwt import p256_point

if TYPE_CHECKING:
    from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurvePublicKey

__all__ = [
    "DEFAULT_MAX_AGE",
    "MAX_MAX_AGE",
    "MIN_MAX_AGE",
    "REFETCH_INTERVAL",
    "Discovery",
    "IssuerCache",
    "KeySet",
    "cache_seconds",
    "parse_discovery",
    "parse_key_set",
]

DEFAULT_MAX_AGE = 300.0
MIN_MAX_AGE = 60.0
MAX_MAX_AGE = 86400.0
REFETCH_INTERVAL = 60.0


def cache_seconds(headers: httpx.Headers) -> float:
    """How long a discovery or JWKS response may be kept.

    ``max-age`` (less the ``Age`` a shared cache reports), or zero for
    ``no-store`` and ``no-cache``, or five minutes without either; then clamped
    to at least 60 seconds and at most a day.
    """
    max_age: float | None = None
    for directive in (headers.get("cache-control") or "").split(","):
        name, _, value = directive.partition("=")
        name = name.strip().lower()
        if name in ("no-store", "no-cache"):
            max_age = 0.0
            break
        if name == "max-age":
            try:
                max_age = float(int(value.strip().strip('"')))
            except ValueError:
                continue
    if max_age is None:
        seconds = DEFAULT_MAX_AGE
    else:
        seconds = max_age
        with contextlib.suppress(ValueError):
            seconds -= int(headers.get("age") or 0)
    return min(MAX_MAX_AGE, max(MIN_MAX_AGE, seconds))


@dataclass(frozen=True)
class Discovery:
    """The parts of ``/.well-known/openid-configuration`` the SDK uses."""

    issuer: str | None
    token_endpoint: str | None
    jwks_uri: str | None


def _absolute_url(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        url = httpx.URL(value)
    except httpx.InvalidURL:
        return None
    return value if url.scheme in ("https", "http") and url.host else None


def parse_discovery(data: object) -> Discovery | None:
    """The discovery document, or ``None`` when ``data`` is not a JSON object."""
    if not isinstance(data, dict):
        return None
    document = cast("dict[str, Any]", data)
    issuer = document.get("issuer")
    return Discovery(
        issuer=issuer if isinstance(issuer, str) else None,
        token_endpoint=_absolute_url(document.get("token_endpoint")),
        jwks_uri=_absolute_url(document.get("jwks_uri")),
    )


@dataclass
class KeySet:
    """The issuer's published keys by ``kid``, with the public keys built so far."""

    keys: dict[str, Mapping[str, Any]]
    _loaded: dict[str, EllipticCurvePublicKey] = field(default_factory=lambda: {}, repr=False)

    def public_key(self, kid: str) -> EllipticCurvePublicKey:
        """The P-256 key published as ``kid``, or ``TokenVerificationError("unknown_key")``."""
        key = self._loaded.get(kid)
        if key is not None:
            return key
        jwk = self.keys.get(kid)
        point = p256_point(jwk) if jwk is not None else None
        if point is not None:
            try:
                key = load_p256_key(*point)
            except ValueError:
                key = None
        if key is None:
            raise TokenVerificationError(
                "unknown_key",
                "The issuer publishes no ES256 (P-256) key with the token's key id (kid).",
            )
        self._loaded[kid] = key
        return key


def parse_key_set(data: object) -> KeySet | None:
    """The key set, or ``None`` when ``data`` is not a JWKS (``{"keys": [...]}``).

    Keys without a string ``kid`` are ignored: Didit always sets one, and a token
    is matched to its key by ``kid`` only.
    """
    if not isinstance(data, dict):
        return None
    keys = cast("dict[str, Any]", data).get("keys")
    if not isinstance(keys, list):
        return None
    by_kid: dict[str, Mapping[str, Any]] = {}
    for item in cast("list[object]", keys):
        if isinstance(item, dict):
            jwk = cast("dict[str, Any]", item)
            kid = jwk.get("kid")
            if isinstance(kid, str) and kid and kid not in by_kid:
                by_kid[kid] = jwk
    return KeySet(keys=by_kid)


@dataclass
class _Entry:
    value: Any
    expires_at: float


class IssuerCache:
    """What is cached for one issuer, and when to fetch again.

    The sync and async clients hold their own lock around a fetch; reads of a
    fresh entry need no lock, because entries are replaced, never mutated.
    """

    clock: Callable[[], float]

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self.clock = clock
        self._discovery: _Entry | None = None
        self._key_set: _Entry | None = None
        self._key_set_attempted_at: float | None = None
        self._key_set_failed = False

    def discovery(self) -> Discovery | None:
        """The cached discovery document while it is fresh."""
        entry = self._discovery
        if entry is None or self.clock() >= entry.expires_at:
            return None
        return cast("Discovery", entry.value)

    def store_discovery(self, discovery: Discovery, headers: httpx.Headers) -> Discovery:
        self._discovery = _Entry(discovery, self.clock() + cache_seconds(headers))
        return discovery

    def key_set(self) -> KeySet | None:
        """The cached key set while it is fresh."""
        entry = self._key_set
        if entry is None or self.clock() >= entry.expires_at:
            return None
        return cast("KeySet", entry.value)

    def start_key_set_fetch(self) -> None:
        """Note an attempt to fetch the key set; it counts as failed until stored."""
        self._key_set_attempted_at = self.clock()
        self._key_set_failed = True

    def store_key_set(self, key_set: KeySet, headers: httpx.Headers) -> KeySet:
        now = self.clock()
        self._key_set = _Entry(key_set, now + cache_seconds(headers))
        self._key_set_attempted_at = now
        self._key_set_failed = False
        return key_set

    def key_set_with(self, kid: str) -> KeySet | None:
        """The fresh key set when it has ``kid``: the lock-free fast path."""
        key_set = self.key_set()
        return key_set if key_set is not None and kid in key_set.keys else None

    def needs_key_set_fetch(self, kid: str) -> bool:
        """Whether verifying a token signed with ``kid`` should fetch the key set:
        when none is fresh, or when ``kid`` is unknown; either way at most once
        every :data:`REFETCH_INTERVAL` seconds, failed attempts included.

        Raises ``TokenVerificationError("unknown_key")`` when no key set is fresh
        and the last attempt to fetch one failed less than a minute ago.
        """
        key_set = self.key_set()
        if key_set is not None and kid in key_set.keys:
            return False
        attempted_at = self._key_set_attempted_at
        recent = attempted_at is not None and self.clock() - attempted_at < REFETCH_INTERVAL
        if key_set is None:
            if recent and self._key_set_failed:
                raise TokenVerificationError(
                    "unknown_key",
                    "The issuer's keys could not be fetched less than a minute ago; "
                    "the SDK tries again once that minute has passed.",
                )
            return True
        return not recent

    def current_key_set(self) -> KeySet:
        """The fresh key set, after :meth:`needs_key_set_fetch` said no fetch is needed."""
        key_set = self.key_set()
        if key_set is None:  # pragma: no cover - needs_key_set_fetch() is True then
            raise RuntimeError("no key set is cached")
        return key_set
