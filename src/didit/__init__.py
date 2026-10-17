"""The official Didit Python library.

    from didit import Didit

    client = Didit()  # reads DIDIT_API_KEY
    session = client.sessions.create(workflow_id="...", vendor_data="user-123")
    print(session.url)

See https://docs.didit.me and the README for the full guide.
"""

from . import types, webhooks
from ._base_client import DEFAULT_ACCOUNT_BASE_URL, DEFAULT_BASE_URL, DEFAULT_MAX_RETRIES, DEFAULT_TIMEOUT
from ._client import AsyncDidit, Didit
from ._exceptions import (
    APIConnectionError,
    APIResponseValidationError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    ConfigurationError,
    ConflictError,
    DiditError,
    InternalServerError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    UnprocessableEntityError,
    WebhookVerificationError,
)
from ._models import BaseModel
from ._pagination import AsyncPage, AsyncPaginator, SyncPage
from ._response import APIResponse, AsyncAPIResponse
from ._types import NOT_GIVEN, FileTypes, NotGiven, Timeout
from ._version import __version__

__all__ = [
    "DEFAULT_ACCOUNT_BASE_URL",
    "DEFAULT_BASE_URL",
    "DEFAULT_MAX_RETRIES",
    "DEFAULT_TIMEOUT",
    "NOT_GIVEN",
    "APIConnectionError",
    "APIResponse",
    "APIResponseValidationError",
    "APIStatusError",
    "APITimeoutError",
    "AsyncAPIResponse",
    "AsyncDidit",
    "AsyncPage",
    "AsyncPaginator",
    "AuthenticationError",
    "BadRequestError",
    "BaseModel",
    "ConfigurationError",
    "ConflictError",
    "Didit",
    "DiditError",
    "FileTypes",
    "InternalServerError",
    "NotFoundError",
    "NotGiven",
    "PermissionDeniedError",
    "RateLimitError",
    "SyncPage",
    "Timeout",
    "UnprocessableEntityError",
    "WebhookVerificationError",
    "__version__",
    "types",
    "webhooks",
]

from ._logging import setup_logging as _setup_logging

_setup_logging()
