"""PKCE (RFC 7636), ``state`` and ``nonce`` values for the authorization code flow."""

from __future__ import annotations

import base64
import hashlib
import secrets
from dataclasses import dataclass, field
from typing import Literal

__all__ = ["PkcePair", "create_nonce", "create_pkce", "create_state", "s256_challenge"]

# 32 random octets, base64url encoded: the 43-character verifier RFC 7636 section 4.1 recommends.
_RANDOM_BYTES = 32


@dataclass(frozen=True)
class PkcePair:
    """A PKCE verifier and its S256 challenge.

    Send ``challenge`` and ``method`` with the authorization request, keep
    ``verifier`` on your server (it is left out of ``repr``) and pass it to
    ``exchange_code``.
    """

    verifier: str = field(repr=False)
    challenge: str
    method: Literal["S256"] = "S256"


def s256_challenge(verifier: str) -> str:
    """``BASE64URL(SHA256(ASCII(verifier)))`` without padding (RFC 7636 section 4.2)."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def create_pkce() -> PkcePair:
    """A new random PKCE verifier (43 characters from ``secrets``) and its S256 challenge."""
    verifier = secrets.token_urlsafe(_RANDOM_BYTES)
    return PkcePair(verifier=verifier, challenge=s256_challenge(verifier))


def create_state() -> str:
    """A new random ``state`` value. Store it with the sign-in attempt and compare it
    with the ``state`` on the callback before exchanging the code."""
    return secrets.token_urlsafe(_RANDOM_BYTES)


def create_nonce() -> str:
    """A new random ``nonce`` value. Send it with the authorization request and pass it
    to ``verify_id_token``, which checks the ID token carries the same value."""
    return secrets.token_urlsafe(_RANDOM_BYTES)
