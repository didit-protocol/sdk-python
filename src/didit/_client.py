"""The :class:`Didit` and :class:`AsyncDidit` clients (docs/DESIGN.md section 6)."""

from __future__ import annotations

from collections.abc import Mapping
from types import TracebackType

import httpx
from typing_extensions import Self

from ._base_client import (
    DEFAULT_ACCOUNT_BASE_URL,
    DEFAULT_BASE_URL,
    DEFAULT_MAX_RETRIES,
    DEFAULT_TIMEOUT,
)
from ._types import NOT_GIVEN, NotGiven, Timeout
from ._utils import env
from .resources import AsyncRootResources, SyncRootResources

__all__ = ["AsyncDidit", "Didit"]


def _pick(value: str | None | NotGiven, current: str | None) -> str | None:
    return current if isinstance(value, NotGiven) else value


class Didit(SyncRootResources):
    """The Didit API client.

    ``client = Didit()`` reads the API key from ``DIDIT_API_KEY`` and the
    organization and application ids from ``DIDIT_ORGANIZATION_ID`` and
    ``DIDIT_APPLICATION_ID``. Create one client per process and reuse it: it
    keeps a connection pool and is safe to share between threads.
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str | None = None,
        organization_id: str | None = None,
        application_id: str | None = None,
        account_base_url: str | None = None,
        account_token: str | None = None,
        timeout: Timeout = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        default_headers: Mapping[str, str] | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        """Create a client.

        Args:
          api_key: The application's API key (header ``x-api-key``). Defaults to
            ``DIDIT_API_KEY``. Only needed for the methods that use it, so a client
            without one can still call ``client.account`` and verify webhooks.
          base_url: Defaults to ``https://verification.didit.me``.
          organization_id: Needed by application-scoped methods (cases, networks,
            regulatory reports...). Defaults to ``DIDIT_ORGANIZATION_ID``.
          application_id: Needed by application-scoped methods. Defaults to
            ``DIDIT_APPLICATION_ID``.
          account_base_url: Base URL of the account management API. Defaults to
            ``https://apx.didit.me/auth/v2``.
          account_token: The ``access_token`` from ``client.account.login(...)``,
            for the ``client.account`` methods that need it.
          timeout: Seconds, or an :class:`httpx.Timeout`. Default 60.
          max_retries: Retries of failed requests that are safe to retry. Default 2.
          default_headers: Headers to add to every request.
          http_client: Your own :class:`httpx.Client` (proxies, custom transports,
            mocks). The SDK does not close a client you pass in.
        """
        super().__init__(
            api_key=api_key if api_key is not None else env("DIDIT_API_KEY"),
            account_token=account_token,
            organization_id=organization_id
            if organization_id is not None
            else env("DIDIT_ORGANIZATION_ID"),
            application_id=application_id
            if application_id is not None
            else env("DIDIT_APPLICATION_ID"),
            base_url=base_url or DEFAULT_BASE_URL,
            account_base_url=account_base_url or DEFAULT_ACCOUNT_BASE_URL,
            timeout=timeout,
            max_retries=max_retries,
            default_headers=default_headers,
        )
        self._init_http(http_client)

    def with_options(
        self,
        *,
        api_key: str | None | NotGiven = NOT_GIVEN,
        base_url: str | NotGiven = NOT_GIVEN,
        organization_id: str | None | NotGiven = NOT_GIVEN,
        application_id: str | None | NotGiven = NOT_GIVEN,
        account_base_url: str | NotGiven = NOT_GIVEN,
        account_token: str | None | NotGiven = NOT_GIVEN,
        timeout: Timeout | NotGiven = NOT_GIVEN,
        max_retries: int | NotGiven = NOT_GIVEN,
        default_headers: Mapping[str, str] | NotGiven = NOT_GIVEN,
    ) -> Self:
        """A copy of this client with some options changed. It shares the
        connection pool, so it is cheap: ``client.with_options(max_retries=5).sessions.list()``."""
        copy = type(self).__new__(type(self))
        SyncRootResources.__init__(
            copy,
            api_key=_pick(api_key, self.api_key),
            account_token=_pick(account_token, self.account_token),
            organization_id=_pick(organization_id, self.organization_id),
            application_id=_pick(application_id, self.application_id),
            base_url=self.base_url if isinstance(base_url, NotGiven) else base_url,
            account_base_url=self.account_base_url
            if isinstance(account_base_url, NotGiven)
            else account_base_url,
            timeout=self.timeout if isinstance(timeout, NotGiven) else timeout,
            max_retries=self.max_retries if isinstance(max_retries, NotGiven) else max_retries,
            default_headers=self.default_headers
            if isinstance(default_headers, NotGiven)
            else default_headers,
        )
        copy._client = self._client
        copy._owns_client = False
        return copy

    copy = with_options

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()


class AsyncDidit(AsyncRootResources):
    """The asyncio Didit API client. Same options as :class:`Didit`;
    every method is awaitable and lists support ``async for``."""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str | None = None,
        organization_id: str | None = None,
        application_id: str | None = None,
        account_base_url: str | None = None,
        account_token: str | None = None,
        timeout: Timeout = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        default_headers: Mapping[str, str] | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        """Create a client. See :class:`Didit` for the options; ``http_client``
        is an :class:`httpx.AsyncClient` here."""
        super().__init__(
            api_key=api_key if api_key is not None else env("DIDIT_API_KEY"),
            account_token=account_token,
            organization_id=organization_id
            if organization_id is not None
            else env("DIDIT_ORGANIZATION_ID"),
            application_id=application_id
            if application_id is not None
            else env("DIDIT_APPLICATION_ID"),
            base_url=base_url or DEFAULT_BASE_URL,
            account_base_url=account_base_url or DEFAULT_ACCOUNT_BASE_URL,
            timeout=timeout,
            max_retries=max_retries,
            default_headers=default_headers,
        )
        self._init_http(http_client)

    def with_options(
        self,
        *,
        api_key: str | None | NotGiven = NOT_GIVEN,
        base_url: str | NotGiven = NOT_GIVEN,
        organization_id: str | None | NotGiven = NOT_GIVEN,
        application_id: str | None | NotGiven = NOT_GIVEN,
        account_base_url: str | NotGiven = NOT_GIVEN,
        account_token: str | None | NotGiven = NOT_GIVEN,
        timeout: Timeout | NotGiven = NOT_GIVEN,
        max_retries: int | NotGiven = NOT_GIVEN,
        default_headers: Mapping[str, str] | NotGiven = NOT_GIVEN,
    ) -> Self:
        """A copy of this client with some options changed, sharing the connection pool."""
        copy = type(self).__new__(type(self))
        AsyncRootResources.__init__(
            copy,
            api_key=_pick(api_key, self.api_key),
            account_token=_pick(account_token, self.account_token),
            organization_id=_pick(organization_id, self.organization_id),
            application_id=_pick(application_id, self.application_id),
            base_url=self.base_url if isinstance(base_url, NotGiven) else base_url,
            account_base_url=self.account_base_url
            if isinstance(account_base_url, NotGiven)
            else account_base_url,
            timeout=self.timeout if isinstance(timeout, NotGiven) else timeout,
            max_retries=self.max_retries if isinstance(max_retries, NotGiven) else max_retries,
            default_headers=self.default_headers
            if isinstance(default_headers, NotGiven)
            else default_headers,
        )
        copy._client = self._client
        copy._owns_client = False
        return copy

    copy = with_options

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.close()
