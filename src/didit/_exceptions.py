"""The exceptions raised by the SDK (docs/DESIGN.md section 7)."""

from __future__ import annotations

from typing import Any, Literal

import httpx
from typing_extensions import override

__all__ = [
    "APIConnectionError",
    "APIResponseValidationError",
    "APIStatusError",
    "APITimeoutError",
    "AuthenticationError",
    "BadRequestError",
    "ConfigurationError",
    "ConflictError",
    "DiditError",
    "InternalServerError",
    "NotFoundError",
    "PermissionDeniedError",
    "RateLimitError",
    "UnprocessableEntityError",
    "WebhookVerificationError",
    "WebhookVerificationReason",
]


class DiditError(Exception):
    """Base class of every error the SDK raises."""

    message: str

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class ConfigurationError(DiditError):
    """The client is missing something it needs: an API key, an account token,
    the organization or application id, or a webhook secret. Raised before any
    request is sent."""


class APIConnectionError(DiditError):
    """No response arrived: the connection failed or broke."""

    request: httpx.Request

    def __init__(self, *, request: httpx.Request, message: str = "Connection error.") -> None:
        super().__init__(message)
        self.request = request


class APITimeoutError(APIConnectionError):
    """The request timed out before a response arrived."""

    def __init__(self, *, request: httpx.Request) -> None:
        super().__init__(request=request, message="Request timed out.")


class APIResponseValidationError(DiditError):
    """A successful response could not be read as the documented content (for
    example HTML where JSON was expected)."""

    response: httpx.Response
    status: int

    def __init__(self, *, response: httpx.Response, message: str) -> None:
        super().__init__(message)
        self.response = response
        self.status = response.status_code


class APIStatusError(DiditError):
    """The API answered with a non-2xx status."""

    status: int
    """The HTTP status code."""
    body: object
    """The parsed JSON body when the response was JSON, else the text, else ``None``."""
    headers: httpx.Headers
    request_id: str | None
    response: httpx.Response

    def __init__(self, message: str, *, response: httpx.Response, body: object) -> None:
        super().__init__(message)
        self.response = response
        self.status = response.status_code
        self.headers = response.headers
        self.body = body
        self.request_id = _request_id(response.headers)

    @property
    def status_code(self) -> int:
        """Alias of :attr:`status`."""
        return self.status

    @override
    def __str__(self) -> str:
        suffix = f" (request id {self.request_id})" if self.request_id else ""
        return f"{self.message}{suffix}"


class BadRequestError(APIStatusError):
    """HTTP 400."""


class AuthenticationError(APIStatusError):
    """HTTP 401."""


class PermissionDeniedError(APIStatusError):
    """HTTP 403."""


class NotFoundError(APIStatusError):
    """HTTP 404."""


class ConflictError(APIStatusError):
    """HTTP 409."""


class UnprocessableEntityError(APIStatusError):
    """HTTP 422."""


class RateLimitError(APIStatusError):
    """HTTP 429."""


class InternalServerError(APIStatusError):
    """HTTP 5xx."""


WebhookVerificationReason = Literal[
    "missing_signature",
    "invalid_signature",
    "missing_timestamp",
    "timestamp_mismatch",
    "timestamp_out_of_tolerance",
    "invalid_payload",
]


class WebhookVerificationError(DiditError):
    """A webhook delivery failed verification (docs/DESIGN.md section 9.3).

    ``reason`` is machine readable: ``missing_signature``, ``invalid_signature``,
    ``missing_timestamp``, ``timestamp_mismatch``, ``timestamp_out_of_tolerance``
    or ``invalid_payload``.
    """

    reason: WebhookVerificationReason

    def __init__(self, reason: WebhookVerificationReason, message: str) -> None:
        super().__init__(message)
        self.reason = reason


_STATUS_ERRORS: dict[int, type[APIStatusError]] = {
    400: BadRequestError,
    401: AuthenticationError,
    403: PermissionDeniedError,
    404: NotFoundError,
    409: ConflictError,
    422: UnprocessableEntityError,
    429: RateLimitError,
}

_REQUEST_ID_HEADERS = ("x-request-id", "request-id", "x-amzn-requestid", "x-correlation-id")


def _request_id(headers: httpx.Headers) -> str | None:
    for name in _REQUEST_ID_HEADERS:
        value: str | None = headers.get(name)
        if value:
            return value
    return None


def _error_message(status: int, body: object) -> str:
    detail: Any = None
    if isinstance(body, dict):
        error, description = body.get("error"), body.get("error_description")  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        if isinstance(error, str) and error and isinstance(description, str) and description:
            # OAuth 2.0 errors (RFC 6749 section 5.2): the code and what it means.
            body = {"detail": f"{error}: {description}", **body}  # pyright: ignore[reportUnknownVariableType]
        for key in ("detail", "message", "error", "error_description"):
            value = body.get(key)  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
            if isinstance(value, str) and value:
                detail = value
                break
        if detail is None and body:
            detail = "; ".join(_field_errors(body))  # pyright: ignore[reportUnknownArgumentType]
    elif isinstance(body, list) and body and all(isinstance(x, str) for x in body):  # pyright: ignore[reportUnknownVariableType]
        detail = "; ".join(body)  # pyright: ignore[reportUnknownArgumentType]
    elif isinstance(body, str) and body.strip() and len(body) <= 500:
        detail = body.strip()
    text = f"HTTP {status}"
    if detail:
        text += f": {detail}"
    return text


def _field_errors(body: dict[str, Any]) -> list[str]:
    parts: list[str] = []
    for key, value in list(body.items())[:5]:
        if isinstance(value, list) and value and isinstance(value[0], str):
            parts.append(f"{key}: {value[0]}")
        elif isinstance(value, str):
            parts.append(f"{key}: {value}")
    return parts


def make_status_error(
    response: httpx.Response, body: object, *, redact: tuple[str, ...] = ()
) -> APIStatusError:
    """Build the right :class:`APIStatusError` subclass for ``response``."""
    status = response.status_code
    message = _error_message(status, body)
    for secret in redact:
        if secret and secret in message:
            message = message.replace(secret, "[redacted]")
    cls = _STATUS_ERRORS.get(status)
    if cls is None:
        cls = InternalServerError if status >= 500 else APIStatusError
    return cls(message, response=response, body=body)
