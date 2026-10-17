"""``client.webhooks.verify(...)``: the verifier, reachable from the client too."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from ._events import WebhookEvent
from ._verify import DEFAULT_TOLERANCE, HeadersLike, verify, verify_parsed

__all__ = ["WebhooksMixin"]


class WebhooksMixin:
    """Adds :func:`didit.webhooks.verify` and :func:`didit.webhooks.verify_parsed`
    to ``client.webhooks``. They need no API key and send no request."""

    def verify(
        self,
        raw_body: bytes | bytearray | memoryview | str,
        headers: HeadersLike,
        secret: str | Sequence[str] | None,
        *,
        tolerance: int = DEFAULT_TOLERANCE,
        allow_simple: bool = False,
    ) -> WebhookEvent:
        """See :func:`didit.webhooks.verify`."""
        return verify(raw_body, headers, secret, tolerance=tolerance, allow_simple=allow_simple)

    def verify_parsed(
        self,
        payload: Mapping[str, Any],
        headers: HeadersLike,
        secret: str | Sequence[str] | None,
        *,
        tolerance: int = DEFAULT_TOLERANCE,
    ) -> WebhookEvent:
        """See :func:`didit.webhooks.verify_parsed`."""
        return verify_parsed(payload, headers, secret, tolerance=tolerance)
