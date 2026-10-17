"""The issuer URL and the publishable key that carries it.

An application's issuer is its canonical origin: ``https://<slug>.auth.didit.me``
(live), ``https://<slug>.sandbox.auth.didit.me`` (sandbox) or its active custom
domain, with no trailing slash. A publishable key is ``pk_live_`` (live) or
``pk_test_`` (sandbox) followed by the unpadded base64url encoding of the issuer.
"""

from __future__ import annotations

import base64
import binascii
import re
import urllib.parse

from .._exceptions import ConfigurationError

__all__ = ["issuer_from_publishable_key", "normalise_issuer"]

_BASE64URL = re.compile(r"[A-Za-z0-9_-]+")
_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
_PREFIXES = {"pk_live_": False, "pk_test_": True}


def _is_loopback(host: str) -> bool:
    return host in _LOOPBACK_HOSTS or host.endswith(".localhost")


def normalise_issuer(issuer: object, *, allow_loopback_http: bool = True) -> str:
    """The issuer without a trailing slash, or :class:`ConfigurationError`.

    The issuer must be an absolute ``https`` URL with no credentials, query or
    fragment. Plain ``http`` is accepted only for ``localhost`` and loopback
    addresses (a local test stack) when ``allow_loopback_http`` is true.
    """
    if not isinstance(issuer, str) or not issuer.strip():
        raise ConfigurationError(
            "The issuer is empty: pass your application's issuer "
            "(https://<slug>.auth.didit.me or your custom domain) or use "
            "Authentication.from_publishable_key(...)."
        )
    text = issuer.strip()
    parts: urllib.parse.SplitResult | None
    try:
        parts = urllib.parse.urlsplit(text)
        host = parts.hostname
        _ = parts.port
    except ValueError:
        parts, host = None, None
    if parts is not None and (parts.username is not None or parts.password is not None):
        raise ConfigurationError("The issuer URL must not contain a user name or password.")
    if (
        parts is None
        or not host
        or "?" in text
        or "#" in text
        or any(ch.isspace() or ord(ch) < 32 for ch in text)
    ):
        raise ConfigurationError(
            f"The issuer must be an absolute https URL with no query or fragment, got {text!r}."
        )
    secure = parts.scheme == "https"
    local = allow_loopback_http and parts.scheme == "http" and _is_loopback(host)
    if not secure and not local:
        raise ConfigurationError(
            f"The issuer must use https (http only for localhost while testing), got {text!r}."
        )
    return text.rstrip("/")


def issuer_from_publishable_key(publishable_key: object) -> str:
    """The issuer a ``pk_live_`` or ``pk_test_`` publishable key carries.

    A live key must name an ``https`` issuer; a test (sandbox) key may also name
    ``http`` on localhost, as the console allows for sandbox applications.
    """
    key = publishable_key.strip() if isinstance(publishable_key, str) else ""
    prefix = key[:8]
    if prefix not in _PREFIXES:
        raise ConfigurationError(
            "A publishable key starts with pk_live_ or pk_test_; copy it from the "
            "Developers section of Authentication in the Didit console."
        )
    encoded = key[8:]
    issuer: str | None = None
    if _BASE64URL.fullmatch(encoded) and len(encoded) % 4 != 1:
        try:
            raw = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
            issuer = raw.decode("utf-8")
        except (binascii.Error, UnicodeDecodeError):
            issuer = None
    if issuer is None:
        raise ConfigurationError(
            f"The publishable key is not valid: expected {prefix} followed by the "
            "base64url-encoded issuer."
        )
    return normalise_issuer(issuer, allow_loopback_http=_PREFIXES[prefix])
