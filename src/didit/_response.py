"""Raw and streamed HTTP response access (docs/DESIGN.md section 7).

``client.sessions.with_raw_response.create(...)`` returns an :class:`APIResponse`
with the status, the headers and the request id; ``.parse()`` gives the value the
plain method returns. ``with_streaming_response`` does the same without reading
the body first, for large binary downloads.
"""

from __future__ import annotations

import contextvars
import functools
from types import TracebackType
from typing import (
    AsyncIterator,
    Awaitable,
    Callable,
    Generic,
    Iterator,
    Literal,
    TypeVar,
    cast,
)

import httpx
from typing_extensions import ParamSpec

from ._exceptions import _request_id

__all__ = [
    "APIResponse",
    "AsyncAPIResponse",
    "AsyncResponseContextManager",
    "ResponseContextManager",
    "async_to_raw_response_wrapper",
    "async_to_streamed_response_wrapper",
    "to_raw_response_wrapper",
    "to_streamed_response_wrapper",
]

R = TypeVar("R")
P = ParamSpec("P")

ResponseMode = Literal["parsed", "raw", "stream"]
response_mode: contextvars.ContextVar[ResponseMode] = contextvars.ContextVar(
    "didit_response_mode", default="parsed"
)


class _BaseAPIResponse(Generic[R]):
    http_response: httpx.Response
    retries_taken: int

    def __init__(
        self,
        http_response: httpx.Response,
        parse: Callable[[httpx.Response], R],
        retries_taken: int,
    ) -> None:
        self.http_response = http_response
        self.retries_taken = retries_taken
        self._parse = parse
        self._parsed: list[R] = []

    @property
    def status_code(self) -> int:
        return self.http_response.status_code

    @property
    def headers(self) -> httpx.Headers:
        return self.http_response.headers

    @property
    def request_id(self) -> str | None:
        return _request_id(self.http_response.headers)

    @property
    def url(self) -> httpx.URL:
        return self.http_response.url

    @property
    def method(self) -> str:
        return self.http_response.request.method

    @property
    def elapsed(self) -> float:
        """Seconds between sending the request and reading the response headers."""
        return self.http_response.elapsed.total_seconds()

    def __repr__(self) -> str:
        return (
            f"<{type(self).__name__} [{self.status_code}] {self.method} {self.url.path}"
            f" request_id={self.request_id!r}>"
        )


class APIResponse(_BaseAPIResponse[R]):
    """A raw HTTP response; :meth:`parse` returns the typed value."""

    def parse(self) -> R:
        if not self._parsed:
            self.http_response.read()
            self._parsed.append(self._parse(self.http_response))
        return self._parsed[0]

    def read(self) -> bytes:
        return self.http_response.read()

    def text(self) -> str:
        self.http_response.read()
        return self.http_response.text

    def json(self) -> object:
        self.http_response.read()
        return self.http_response.json()

    def iter_bytes(self, chunk_size: int | None = None) -> Iterator[bytes]:
        return self.http_response.iter_bytes(chunk_size)

    def iter_text(self, chunk_size: int | None = None) -> Iterator[str]:
        return self.http_response.iter_text(chunk_size)

    def iter_lines(self) -> Iterator[str]:
        return self.http_response.iter_lines()

    def write_to_file(self, path: str) -> None:
        """Stream the body to ``path``."""
        with open(path, "wb") as fh:
            for chunk in self.http_response.iter_bytes():
                fh.write(chunk)

    def close(self) -> None:
        self.http_response.close()


class AsyncAPIResponse(_BaseAPIResponse[R]):
    """A raw HTTP response; ``await`` :meth:`parse` for the typed value."""

    async def parse(self) -> R:
        if not self._parsed:
            await self.http_response.aread()
            self._parsed.append(self._parse(self.http_response))
        return self._parsed[0]

    async def read(self) -> bytes:
        return await self.http_response.aread()

    async def text(self) -> str:
        await self.http_response.aread()
        return self.http_response.text

    async def json(self) -> object:
        await self.http_response.aread()
        return self.http_response.json()

    def iter_bytes(self, chunk_size: int | None = None) -> AsyncIterator[bytes]:
        return self.http_response.aiter_bytes(chunk_size)

    def iter_text(self, chunk_size: int | None = None) -> AsyncIterator[str]:
        return self.http_response.aiter_text(chunk_size)

    def iter_lines(self) -> AsyncIterator[str]:
        return self.http_response.aiter_lines()

    async def write_to_file(self, path: str) -> None:
        """Stream the body to ``path``."""
        with open(path, "wb") as fh:
            async for chunk in self.http_response.aiter_bytes():
                fh.write(chunk)

    async def close(self) -> None:
        await self.http_response.aclose()


def to_raw_response_wrapper(func: Callable[P, R]) -> Callable[P, APIResponse[R]]:
    @functools.wraps(func)
    def wrapped(*args: P.args, **kwargs: P.kwargs) -> APIResponse[R]:
        token = response_mode.set("raw")
        try:
            return cast("APIResponse[R]", func(*args, **kwargs))
        finally:
            response_mode.reset(token)

    return wrapped


def async_to_raw_response_wrapper(
    func: Callable[P, Awaitable[R]],
) -> Callable[P, Awaitable[AsyncAPIResponse[R]]]:
    @functools.wraps(func)
    async def wrapped(*args: P.args, **kwargs: P.kwargs) -> AsyncAPIResponse[R]:
        token = response_mode.set("raw")
        try:
            return cast("AsyncAPIResponse[R]", await func(*args, **kwargs))
        finally:
            response_mode.reset(token)

    return wrapped


class ResponseContextManager(Generic[R]):
    """Sends the request on ``__enter__`` and closes the response on ``__exit__``."""

    def __init__(self, call: Callable[[], APIResponse[R]]) -> None:
        self._call = call
        self._response: APIResponse[R] | None = None

    def __enter__(self) -> APIResponse[R]:
        token = response_mode.set("stream")
        try:
            self._response = self._call()
        finally:
            response_mode.reset(token)
        return self._response

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._response is not None:
            self._response.close()


class AsyncResponseContextManager(Generic[R]):
    """Sends the request on ``__aenter__`` and closes the response on ``__aexit__``."""

    def __init__(self, call: Callable[[], Awaitable[AsyncAPIResponse[R]]]) -> None:
        self._call = call
        self._response: AsyncAPIResponse[R] | None = None

    async def __aenter__(self) -> AsyncAPIResponse[R]:
        token = response_mode.set("stream")
        try:
            self._response = await self._call()
        finally:
            response_mode.reset(token)
        return self._response

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._response is not None:
            await self._response.close()


def to_streamed_response_wrapper(
    func: Callable[P, R],
) -> Callable[P, ResponseContextManager[R]]:
    @functools.wraps(func)
    def wrapped(*args: P.args, **kwargs: P.kwargs) -> ResponseContextManager[R]:
        return ResponseContextManager(
            lambda: cast("APIResponse[R]", func(*args, **kwargs)),
        )

    return wrapped


def async_to_streamed_response_wrapper(
    func: Callable[P, Awaitable[R]],
) -> Callable[P, AsyncResponseContextManager[R]]:
    @functools.wraps(func)
    def wrapped(*args: P.args, **kwargs: P.kwargs) -> AsyncResponseContextManager[R]:
        async def call() -> AsyncAPIResponse[R]:
            return cast("AsyncAPIResponse[R]", await func(*args, **kwargs))

        return AsyncResponseContextManager(call)

    return wrapped

