"""HTTP transport shared by :class:`didit.Didit` and :class:`didit.AsyncDidit`.

Everything that decides *what* is sent and *whether* to retry lives in plain
functions and in :class:`BaseClient`; :class:`SyncAPIClient` and
:class:`AsyncAPIClient` only differ in how they send and sleep.
"""

from __future__ import annotations

import asyncio
import email.utils
import logging
import random
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any, Literal, TypeVar, cast

import httpx

from ._exceptions import (
    APIConnectionError,
    APIResponseValidationError,
    APITimeoutError,
    ConfigurationError,
    DiditError,
    _request_id,  # pyright: ignore[reportPrivateUsage]
    make_status_error,
)
from ._files import HttpxFile
from ._models import validate_response
from ._response import APIResponse, AsyncAPIResponse, response_mode
from ._types import NOT_GIVEN, Headers, NotGiven, Query, Timeout
from ._utils import (
    client_header,
    encode_json,
    encode_path,
    multipart_fields,
    query_params,
    user_agent,
)

if TYPE_CHECKING:
    from ._pagination import AsyncPage, AsyncPaginator, SyncPage

__all__ = [
    "DEFAULT_ACCOUNT_BASE_URL",
    "DEFAULT_BASE_URL",
    "DEFAULT_MAX_RETRIES",
    "DEFAULT_TIMEOUT",
    "AsyncAPIClient",
    "BaseClient",
    "SyncAPIClient",
]

log = logging.getLogger("didit")

DEFAULT_BASE_URL = "https://verification.didit.me"
DEFAULT_ACCOUNT_BASE_URL = "https://apx.didit.me/auth/v2"
DEFAULT_TIMEOUT = 60.0
DEFAULT_MAX_RETRIES = 2
INITIAL_RETRY_DELAY = 0.5
MAX_RETRY_DELAY = 8.0
MAX_RETRY_AFTER = 60.0

AuthKind = Literal["api_key", "account_token", "none"]
Scope = Literal["application"]
Multipart = Literal[False, True, "auto"]

_IDEMPOTENT_METHODS = frozenset({"GET", "HEAD", "PUT", "DELETE", "OPTIONS"})
# Errors raised before any byte of the request left this process.
_NOT_SENT_ERRORS = (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout, httpx.ProxyError)
# Request headers that carry credentials; blanked on requests attached to errors.
_CREDENTIAL_HEADERS = ("x-api-key", "authorization")

T = TypeVar("T")
ItemT = TypeVar("ItemT")


@dataclass(frozen=True)
class PreparedRequest:
    """A request with everything resolved except the credentials header."""

    method: str
    url: str
    auth: AuthKind
    origin: str
    params: list[tuple[str, str]] = field(default_factory=lambda: [])
    json_content: bytes | None = None
    data: dict[str, str] | None = None
    files: list[tuple[str, HttpxFile]] | None = None
    headers: Mapping[str, str | None] = field(default_factory=lambda: {})
    timeout: Timeout | NotGiven = NOT_GIVEN
    accept: str = "application/json"


def origin_of(url: httpx.URL | str) -> str:
    """``scheme://host[:port]`` with the default port left out."""
    parsed = httpx.URL(url)
    port = parsed.port
    default = {"http": 80, "https": 443}.get(parsed.scheme)
    netloc = parsed.host if port is None or port == default else f"{parsed.host}:{port}"
    return f"{parsed.scheme}://{netloc}"


def should_retry_status(method: str, status: int) -> bool:
    """Whether a response with ``status`` may be retried (docs/DESIGN.md section 7).

    ``POST`` and ``PATCH`` reached the server, so only 429 (which guarantees the
    request was not processed) is retried for them.
    """
    if status == 429:
        return True
    if method.upper() not in _IDEMPOTENT_METHODS:
        return False
    return status == 408 or status >= 500


def should_retry_exception(method: str, exc: Exception) -> bool:
    """Whether a transport error may be retried.

    A connection that failed before sending is always safe to retry. Anything
    later (a read timeout, a dropped connection) may have reached the server, so
    it is retried only for idempotent methods.
    """
    if isinstance(exc, _NOT_SENT_ERRORS):
        return True
    if method.upper() not in _IDEMPOTENT_METHODS:
        return False
    return isinstance(exc, (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError))


def parse_retry_after(headers: httpx.Headers, now: float | None = None) -> float | None:
    """Seconds to wait from a ``Retry-After`` header (seconds or HTTP date), capped at 60."""
    value = headers.get("retry-after")
    if not value:
        return None
    value = value.strip()
    seconds: float | None
    try:
        seconds = float(value)
    except ValueError:
        try:
            parsed = email.utils.parsedate_to_datetime(value)
        except (TypeError, ValueError, IndexError):
            return None
        seconds = parsed.timestamp() - (time.time() if now is None else now)
    if seconds != seconds:  # NaN
        return None
    return max(0.0, min(seconds, MAX_RETRY_AFTER))


def retry_delay(retries_taken: int, headers: httpx.Headers | None) -> float:
    """Exponential backoff from 0.5 s with full jitter, capped at 8 s, unless
    the server said how long to wait."""
    if headers is not None:
        retry_after = parse_retry_after(headers)
        if retry_after is not None:
            return retry_after
    ceiling = min(MAX_RETRY_DELAY, INITIAL_RETRY_DELAY * (2**retries_taken))
    return random.uniform(0, ceiling)  # noqa: S311 - jitter, not cryptography


def _validate_base_url(name: str, url: str) -> str:
    parsed = httpx.URL(url)
    if parsed.scheme not in ("http", "https") or not parsed.host:
        raise ConfigurationError(f"{name} must be an absolute http(s) URL, got {url!r}.")
    return str(parsed).rstrip("/")


class BaseClient:
    """Configuration and request building shared by the sync and async clients."""

    api_key: str | None
    account_token: str | None
    organization_id: str | None
    application_id: str | None
    base_url: str
    account_base_url: str
    timeout: Timeout
    max_retries: int
    default_headers: Mapping[str, str]

    def __init__(
        self,
        *,
        api_key: str | None,
        account_token: str | None,
        organization_id: str | None,
        application_id: str | None,
        base_url: str,
        account_base_url: str,
        timeout: Timeout,
        max_retries: int,
        default_headers: Mapping[str, str] | None,
    ) -> None:
        if max_retries < 0:
            raise ConfigurationError("max_retries must be 0 or more.")
        self.api_key = api_key or None
        self.account_token = account_token or None
        self.organization_id = organization_id or None
        self.application_id = application_id or None
        self.base_url = _validate_base_url("base_url", base_url)
        self.account_base_url = _validate_base_url("account_base_url", account_base_url)
        self.timeout = timeout
        self.max_retries = max_retries
        self.default_headers = dict(default_headers or {})

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}(base_url={self.base_url!r}, "
            f"organization_id={self.organization_id!r}, application_id={self.application_id!r}, "
            f"api_key={'***' if self.api_key else None})"
        )

    # Request building -------------------------------------------------------

    def _prepare(
        self,
        method: str,
        path: str,
        *,
        path_params: Mapping[str, object] | None,
        scope: Scope | None,
        auth: AuthKind,
        api: Literal["verification", "account"],
        query: Mapping[str, object] | None,
        body: Mapping[str, object] | None,
        multipart: Multipart,
        file_fields: tuple[str, ...],
        headers: Mapping[str, str | NotGiven | None] | None,
        extra_headers: Headers | None,
        extra_query: Query | None,
        extra_body: Mapping[str, object] | None,
        timeout: Timeout | NotGiven,
        accept: str,
    ) -> PreparedRequest:
        params = dict(path_params or {})
        if scope == "application":
            if not self.organization_id or not self.application_id:
                raise ConfigurationError(
                    "This method is application scoped: pass organization_id and application_id "
                    "to the client (or set DIDIT_ORGANIZATION_ID and DIDIT_APPLICATION_ID)."
                )
            params["organization_id"] = self.organization_id
            params["application_id"] = self.application_id
        self._check_credentials(auth)
        base = self.account_base_url if api == "account" else self.base_url
        url = base + encode_path(path, params)

        all_query = query_params(query)
        if extra_query:
            all_query.extend(query_params(extra_query))

        json_content: bytes | None = None
        data: dict[str, str] | None = None
        files: list[tuple[str, HttpxFile]] | None = None
        if body is not None or extra_body:
            merged: dict[str, object] = dict(body or {})
            if extra_body:
                merged.update(extra_body)
            use_multipart = multipart is True or (
                multipart == "auto"
                and any(merged.get(name) not in (None, NOT_GIVEN) for name in file_fields)
            )
            if use_multipart:
                data, files = multipart_fields(merged, file_fields)
            else:
                json_content = encode_json(merged)

        merged_headers: dict[str, str | None] = {
            k: v for k, v in (headers or {}).items() if not isinstance(v, NotGiven)
        }
        if extra_headers:
            merged_headers.update(extra_headers)
        return PreparedRequest(
            method=method.upper(),
            url=url,
            auth=auth,
            origin=origin_of(base),
            params=all_query,
            json_content=json_content,
            data=data,
            files=files,
            headers=merged_headers,
            timeout=timeout,
            accept=accept,
        )

    def _check_credentials(self, auth: AuthKind) -> None:
        if auth == "api_key" and not self.api_key:
            raise ConfigurationError(
                "No API key: pass api_key to the client or set the DIDIT_API_KEY environment variable."
            )
        if auth == "account_token" and not self.account_token:
            raise ConfigurationError(
                "This account method needs an account token: call client.account.login(...) and "
                "pass its access_token as account_token (client.with_options(account_token=...))."
            )

    def _next_page_request(self, prepared: PreparedRequest, next_url: str) -> PreparedRequest:
        """The request for a page's ``next`` link, refused if it leaves the API origin.

        A relative link is resolved against the URL of the page that returned it.
        """
        current = httpx.URL(prepared.url, params=prepared.params or None)
        try:
            absolute = current.join(next_url)
        except httpx.InvalidURL as exc:
            raise DiditError(f"The API returned an invalid pagination link: {exc}") from exc
        if absolute.scheme not in ("http", "https") or origin_of(absolute) != prepared.origin:
            raise DiditError(
                f"Refusing to follow a pagination link to another origin ({origin_of(absolute)}); "
                f"the API key is only sent to {prepared.origin}."
            )
        return replace(prepared, url=str(absolute), params=[])

    def _build_httpx_request(
        self, prepared: PreparedRequest, client: httpx.Client | httpx.AsyncClient
    ) -> httpx.Request:
        # Header names are case-insensitive: a later value replaces an earlier one
        # whatever its case, so no header is ever sent twice.
        headers: dict[str, str] = {}
        removed: set[str] = set()

        def put(name: str, value: str | None) -> None:
            for existing in [k for k in headers if k.lower() == name.lower()]:
                del headers[existing]
            if value is None:
                removed.add(name.lower())
            else:
                removed.discard(name.lower())
                headers[name] = value

        put("Accept", prepared.accept)
        put("User-Agent", user_agent())
        put("X-Didit-Client", client_header())
        for name, value in self.default_headers.items():
            put(name, value)
        # Credentials are only ever attached for the origin the request was built for.
        if prepared.auth == "api_key" and self.api_key:
            put("x-api-key", self.api_key)
        elif prepared.auth == "account_token" and self.account_token:
            put("Authorization", f"Bearer {self.account_token}")
        for name, value in prepared.headers.items():
            put(name, value)

        kwargs: dict[str, Any] = {"headers": headers, "params": prepared.params or None}
        if prepared.json_content is not None:
            if not any(k.lower() == "content-type" for k in headers):
                headers["Content-Type"] = "application/json"
            kwargs["content"] = prepared.json_content
        elif prepared.files is not None or prepared.data is not None:
            if prepared.files:
                kwargs["files"] = prepared.files
                kwargs["data"] = prepared.data or {}
            else:
                # httpx sends form fields without files as urlencoded; force multipart.
                kwargs["files"] = [(k, (None, v)) for k, v in (prepared.data or {}).items()]
        timeout = self.timeout if isinstance(prepared.timeout, NotGiven) else prepared.timeout
        kwargs["timeout"] = timeout
        request = client.build_request(prepared.method, prepared.url, **kwargs)
        # httpx adds its own defaults (User-Agent, ...); honour an explicit removal.
        for name in removed:
            if name in request.headers:
                del request.headers[name]
        return request

    # Response handling ------------------------------------------------------

    def _redactions(self) -> tuple[str, ...]:
        return tuple(x for x in (self.api_key, self.account_token) if x)

    def _status_error(self, response: httpx.Response) -> DiditError:
        body: object
        try:
            body = response.json()
        except ValueError:
            body = response.text or None
        _redact_request(response.request)
        return make_status_error(response, body, redact=self._redactions())

    @staticmethod
    def _transport_error(request: httpx.Request, exc: httpx.HTTPError) -> DiditError:
        _redact_request(request)
        if isinstance(exc, httpx.TimeoutException):
            return APITimeoutError(request=request)
        return APIConnectionError(request=request)

    @staticmethod
    def _parse(response: httpx.Response, cast_to: Any) -> Any:
        if cast_to is bytes:
            return response.content
        if cast_to is None:
            return None
        if isinstance(cast_to, dict):
            by_status = cast("dict[int, Any]", cast_to)
            cast_to = by_status.get(response.status_code, next(iter(by_status.values())))
        if response.status_code == 204 or not response.content:
            return None
        try:
            data = response.json()
        except ValueError as exc:
            raise APIResponseValidationError(
                response=response,
                message=(
                    f"Expected a JSON response from {response.request.method} "
                    f"{response.request.url.path}, got {response.headers.get('content-type', 'no content type')}."
                ),
            ) from exc
        return validate_response(cast_to, data)

    def _log_response(
        self, request: httpx.Request, response: httpx.Response, started: float
    ) -> None:
        if log.isEnabledFor(logging.DEBUG):
            log.debug(
                "%s %s -> %d in %.0f ms (request id %s)",
                request.method,
                request.url.path,
                response.status_code,
                (time.monotonic() - started) * 1000,
                _request_id(response.headers) or "-",
            )

    def _log_retry(
        self, request: httpx.Request, reason: str, delay: float, retries_left: int
    ) -> None:
        log.debug(
            "%s %s: %s; retrying in %.2f s (%d retries left)",
            request.method,
            request.url.path,
            reason,
            delay,
            retries_left,
        )


class SyncAPIClient(BaseClient):
    """The blocking transport, on :class:`httpx.Client`."""

    _client: httpx.Client
    _owns_client: bool

    def _init_http(self, http_client: httpx.Client | None) -> None:
        if http_client is not None and not isinstance(http_client, httpx.Client):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise ConfigurationError(
                "http_client must be an httpx.Client (use AsyncDidit for httpx.AsyncClient)."
            )
        self._owns_client = http_client is None
        self._client = http_client or httpx.Client(follow_redirects=False)

    def close(self) -> None:
        """Close the HTTP connection pool (only if this client created it)."""
        if self._owns_client:
            self._client.close()

    def request(
        self,
        method: str,
        path: str,
        *,
        cast_to: Any,
        path_params: Mapping[str, object] | None = None,
        scope: Scope | None = None,
        auth: AuthKind = "api_key",
        api: Literal["verification", "account"] = "verification",
        query: Mapping[str, object] | None = None,
        body: Mapping[str, object] | None = None,
        multipart: Multipart = False,
        file_fields: tuple[str, ...] = (),
        headers: Mapping[str, str | NotGiven | None] | None = None,
        extra_headers: Headers | None = None,
        extra_query: Query | None = None,
        extra_body: Mapping[str, object] | None = None,
        timeout: Timeout | NotGiven = NOT_GIVEN,
        accept: str = "application/json",
    ) -> Any:
        prepared = self._prepare(
            method, path, path_params=path_params, scope=scope, auth=auth, api=api,
            query=query, body=body, multipart=multipart, file_fields=file_fields,
            headers=headers, extra_headers=extra_headers, extra_query=extra_query,
            extra_body=extra_body, timeout=timeout, accept=accept,
        )  # fmt: skip
        return self._send(prepared, lambda r: self._parse(r, cast_to))

    def request_page(
        self,
        method: str,
        path: str,
        *,
        cast_to: Any,
        item_type: Any,
        **kwargs: Any,
    ) -> SyncPage[Any]:
        from ._pagination import SyncPage

        prepared = self._prepare(method, path, **_prepare_defaults(kwargs))
        return cast(
            "SyncPage[Any]",
            self._send(
                prepared, lambda r: SyncPage.from_response(self, prepared, r, cast_to, item_type)
            ),
        )

    def _send(self, prepared: PreparedRequest, parse: Callable[[httpx.Response], T]) -> Any:
        mode = response_mode.get()
        retries_taken = 0
        while True:
            request = self._build_httpx_request(prepared, self._client)
            started = time.monotonic()
            retry_status = False
            try:
                response = self._client.send(request, stream=True, follow_redirects=False)
                elapsed = time.monotonic() - started
                self._log_response(request, response, started)
                retry_status = (
                    not response.is_success
                    and retries_taken < self.max_retries
                    and should_retry_status(request.method, response.status_code)
                )
                if retry_status:
                    response.close()
                elif mode != "stream" or not response.is_success:
                    # Reading the body can fail like sending did (a stalled or
                    # dropped connection), so it is handled the same way.
                    try:
                        response.read()
                    finally:
                        response.close()
            except httpx.HTTPError as exc:
                if retries_taken < self.max_retries and should_retry_exception(request.method, exc):
                    delay = retry_delay(retries_taken, None)
                    self._log_retry(request, _describe(exc), delay, self.max_retries - retries_taken)
                    retries_taken += 1
                    time.sleep(delay)
                    continue
                raise self._transport_error(request, exc) from exc

            if retry_status:
                delay = retry_delay(retries_taken, response.headers)
                self._log_retry(
                    request, f"HTTP {response.status_code}", delay, self.max_retries - retries_taken
                )
                retries_taken += 1
                time.sleep(delay)
                continue
            if not response.is_success:
                raise self._status_error(response)
            if mode == "stream" or mode == "raw":
                return APIResponse(response, parse, retries_taken, elapsed)
            return parse(response)


class AsyncAPIClient(BaseClient):
    """The asyncio transport, on :class:`httpx.AsyncClient`."""

    _client: httpx.AsyncClient
    _owns_client: bool

    def _init_http(self, http_client: httpx.AsyncClient | None) -> None:
        if http_client is not None and not isinstance(http_client, httpx.AsyncClient):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise ConfigurationError(
                "http_client must be an httpx.AsyncClient (use Didit for httpx.Client)."
            )
        self._owns_client = http_client is None
        self._client = http_client or httpx.AsyncClient(follow_redirects=False)

    async def close(self) -> None:
        """Close the HTTP connection pool (only if this client created it)."""
        if self._owns_client:
            await self._client.aclose()

    async def request(
        self,
        method: str,
        path: str,
        *,
        cast_to: Any,
        path_params: Mapping[str, object] | None = None,
        scope: Scope | None = None,
        auth: AuthKind = "api_key",
        api: Literal["verification", "account"] = "verification",
        query: Mapping[str, object] | None = None,
        body: Mapping[str, object] | None = None,
        multipart: Multipart = False,
        file_fields: tuple[str, ...] = (),
        headers: Mapping[str, str | NotGiven | None] | None = None,
        extra_headers: Headers | None = None,
        extra_query: Query | None = None,
        extra_body: Mapping[str, object] | None = None,
        timeout: Timeout | NotGiven = NOT_GIVEN,
        accept: str = "application/json",
    ) -> Any:
        prepared = self._prepare(
            method, path, path_params=path_params, scope=scope, auth=auth, api=api,
            query=query, body=body, multipart=multipart, file_fields=file_fields,
            headers=headers, extra_headers=extra_headers, extra_query=extra_query,
            extra_body=extra_body, timeout=timeout, accept=accept,
        )  # fmt: skip
        return await self._send(prepared, lambda r: self._parse(r, cast_to))

    def request_page(
        self,
        method: str,
        path: str,
        *,
        cast_to: Any,
        item_type: Any,
        **kwargs: Any,
    ) -> AsyncPaginator[Any]:
        from ._pagination import AsyncPage, AsyncPaginator

        prepared = self._prepare(method, path, **_prepare_defaults(kwargs))

        async def first_page() -> AsyncPage[Any]:
            return cast(
                "AsyncPage[Any]",
                await self._send(
                    prepared,
                    lambda r: AsyncPage.from_response(self, prepared, r, cast_to, item_type),
                ),
            )

        return AsyncPaginator(first_page)

    async def _send(self, prepared: PreparedRequest, parse: Callable[[httpx.Response], T]) -> Any:
        mode = response_mode.get()
        retries_taken = 0
        while True:
            request = self._build_httpx_request(prepared, self._client)
            started = time.monotonic()
            retry_status = False
            try:
                response = await self._client.send(request, stream=True, follow_redirects=False)
                elapsed = time.monotonic() - started
                self._log_response(request, response, started)
                retry_status = (
                    not response.is_success
                    and retries_taken < self.max_retries
                    and should_retry_status(request.method, response.status_code)
                )
                if retry_status:
                    await response.aclose()
                elif mode != "stream" or not response.is_success:
                    # Reading the body can fail like sending did (a stalled or
                    # dropped connection), so it is handled the same way.
                    try:
                        await response.aread()
                    finally:
                        await response.aclose()
            except httpx.HTTPError as exc:
                if retries_taken < self.max_retries and should_retry_exception(request.method, exc):
                    delay = retry_delay(retries_taken, None)
                    self._log_retry(request, _describe(exc), delay, self.max_retries - retries_taken)
                    retries_taken += 1
                    await asyncio.sleep(delay)
                    continue
                raise self._transport_error(request, exc) from exc

            if retry_status:
                delay = retry_delay(retries_taken, response.headers)
                self._log_retry(
                    request, f"HTTP {response.status_code}", delay, self.max_retries - retries_taken
                )
                retries_taken += 1
                await asyncio.sleep(delay)
                continue
            if not response.is_success:
                raise self._status_error(response)
            if mode == "stream" or mode == "raw":
                return AsyncAPIResponse(response, parse, retries_taken, elapsed)
            return parse(response)


def _describe(exc: httpx.HTTPError) -> str:
    return "timed out" if isinstance(exc, httpx.TimeoutException) else type(exc).__name__


def _redact_request(request: httpx.Request) -> None:
    """Blank the credentials on a request that an error keeps a reference to, so
    error reporters that serialise exception attributes never capture them."""
    for name in _CREDENTIAL_HEADERS:
        if name in request.headers:
            request.headers[name] = "[redacted]"


def _prepare_defaults(kwargs: dict[str, Any]) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "path_params": None,
        "scope": None,
        "auth": "api_key",
        "api": "verification",
        "query": None,
        "body": None,
        "multipart": False,
        "file_fields": (),
        "headers": None,
        "extra_headers": None,
        "extra_query": None,
        "extra_body": None,
        "timeout": NOT_GIVEN,
        "accept": "application/json",
    }
    unknown = set(kwargs) - set(defaults)
    if unknown:
        raise TypeError(f"Unexpected request arguments: {sorted(unknown)}")
    defaults.update(kwargs)
    return defaults
