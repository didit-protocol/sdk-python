"""The error raised when an Authentication token fails verification (docs/DESIGN.md section 10)."""

from __future__ import annotations

from typing import Literal

from .._exceptions import DiditError

__all__ = ["TokenVerificationError", "TokenVerificationReason"]

TokenVerificationReason = Literal[
    "malformed",
    "unsupported_algorithm",
    "invalid_type",
    "unknown_key",
    "invalid_signature",
    "invalid_issuer",
    "invalid_audience",
    "expired",
    "not_yet_valid",
    "invalid_issued_at",
    "invalid_nonce",
    "missing_claim",
]


class TokenVerificationError(DiditError):
    """An access token or ID token failed verification: do not trust any of its claims.

    ``reason`` is machine readable: ``malformed``, ``unsupported_algorithm``,
    ``invalid_type``, ``unknown_key``, ``invalid_signature``, ``invalid_issuer``,
    ``invalid_audience``, ``expired``, ``not_yet_valid``, ``invalid_issued_at``,
    ``invalid_nonce`` or ``missing_claim``. The message never contains the token.
    """

    reason: TokenVerificationReason

    def __init__(self, reason: TokenVerificationReason, message: str) -> None:
        super().__init__(message)
        self.reason = reason
