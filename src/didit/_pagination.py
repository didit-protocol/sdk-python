"""Pages of ``limit``/``offset`` lists with auto-pagination (docs/DESIGN.md section 8).

``for item in client.sessions.list()`` walks every item of every page;
``async for item in client.sessions.list()`` does the same on :class:`AsyncDidit`.
"""

from __future__ import annotations

from typing import (
    TYPE_CHECKING,
    Any,
    AsyncIterator,
    Awaitable,
    Callable,
    Generator,
    Generic,
    Iterator,
    TypeVar,
    cast,
)

import httpx

from ._exceptions import DiditError
from ._models import BaseModel, validate_response
from ._response import response_mode

if TYPE_CHECKING:
    from ._base_client import AsyncAPIClient, PreparedRequest, SyncAPIClient

__all__ = ["AsyncPage", "AsyncPaginator", "SyncPage"]

ItemT = TypeVar("ItemT")


class _BasePage(Generic[ItemT]):
    count: int | None
    """Total number of items across all pages, when the API reports it."""
    next: str | None
    """URL of the next page, or ``None`` on the last page."""
    previous: str | None
    """URL of the previous page, or ``None`` on the first page."""
    results: list[ItemT]
    """The items on this page."""
    response: BaseModel | None
    """The whole response body as its generated model, including any fields besides
    ``count``, ``next``, ``previous`` and ``results``."""

    def __init__(
        self,
        *,
        results: list[ItemT],
        count: int | None,
        next: str | None,
        previous: str | None,
        response: BaseModel | None,
        prepared: PreparedRequest,
        cast_to: Any,
        item_type: Any,
    ) -> None:
        self.results = results
        self.count = count
        self.next = next
        self.previous = previous
        self.response = response
        self._prepared = prepared
        self._cast_to = cast_to
        self._item_type = item_type

    @staticmethod
    def _fields(data: object, cast_to: Any, item_type: Any) -> dict[str, Any]:
        if not isinstance(data, dict):
            raise DiditError("Expected a paginated JSON object with a 'results' list.")
        body = cast("dict[str, Any]", data)
        parsed = validate_response(cast_to, body)
        raw_results = body.get("results")
        results = cast("list[Any]", validate_response(list[item_type], raw_results or []))  # type: ignore[valid-type]
        count = body.get("count")
        return {
            "results": results,
            "count": count if isinstance(count, int) else None,
            "next": body.get("next") if isinstance(body.get("next"), str) else None,
            "previous": body.get("previous") if isinstance(body.get("previous"), str) else None,
            "response": parsed if isinstance(parsed, BaseModel) else None,
        }

    def has_next_page(self) -> bool:
        return bool(self.next) and bool(self.results)

    def __repr__(self) -> str:
        return (
            f"<{type(self).__name__} count={self.count} results={len(self.results)} "
            f"next={self.next!r}>"
        )


class SyncPage(_BasePage[ItemT]):
    """One page of a list. Iterating it yields every item of every page."""

    _client: SyncAPIClient

    @classmethod
    def from_response(
        cls,
        client: SyncAPIClient,
        prepared: PreparedRequest,
        response: httpx.Response,
        cast_to: Any,
        item_type: Any,
    ) -> SyncPage[Any]:
        page: SyncPage[Any] = cls(
            **cls._fields(response.json(), cast_to, item_type),
            prepared=prepared,
            cast_to=cast_to,
            item_type=item_type,
        )
        page._client = client
        return page

    def get_next_page(self) -> SyncPage[ItemT]:
        """Fetch the next page. The link must point at the API's own origin."""
        if not self.next:
            raise DiditError("This is the last page.")
        prepared = self._client._next_page_request(self._prepared, self.next)
        cast_to, item_type, client = self._cast_to, self._item_type, self._client
        token = response_mode.set("parsed")
        try:
            return cast(
                "SyncPage[ItemT]",
                client._send(
                    prepared,
                    lambda r: SyncPage.from_response(client, prepared, r, cast_to, item_type),
                ),
            )
        finally:
            response_mode.reset(token)

    def iter_pages(self) -> Iterator[SyncPage[ItemT]]:
        page: SyncPage[ItemT] = self
        while True:
            yield page
            if not page.has_next_page():
                return
            page = page.get_next_page()

    def __iter__(self) -> Iterator[ItemT]:  # type: ignore[override]
        for page in self.iter_pages():
            yield from page.results


class AsyncPage(_BasePage[ItemT]):
    """One page of a list. ``async for`` over it yields every item of every page."""

    _client: AsyncAPIClient

    @classmethod
    def from_response(
        cls,
        client: AsyncAPIClient,
        prepared: PreparedRequest,
        response: httpx.Response,
        cast_to: Any,
        item_type: Any,
    ) -> AsyncPage[Any]:
        page: AsyncPage[Any] = cls(
            **cls._fields(response.json(), cast_to, item_type),
            prepared=prepared,
            cast_to=cast_to,
            item_type=item_type,
        )
        page._client = client
        return page

    async def get_next_page(self) -> AsyncPage[ItemT]:
        """Fetch the next page. The link must point at the API's own origin."""
        if not self.next:
            raise DiditError("This is the last page.")
        prepared = self._client._next_page_request(self._prepared, self.next)
        cast_to, item_type, client = self._cast_to, self._item_type, self._client
        token = response_mode.set("parsed")
        try:
            return cast(
                "AsyncPage[ItemT]",
                await client._send(
                    prepared,
                    lambda r: AsyncPage.from_response(client, prepared, r, cast_to, item_type),
                ),
            )
        finally:
            response_mode.reset(token)

    async def iter_pages(self) -> AsyncIterator[AsyncPage[ItemT]]:
        page: AsyncPage[ItemT] = self
        while True:
            yield page
            if not page.has_next_page():
                return
            page = await page.get_next_page()

    async def __aiter__(self) -> AsyncIterator[ItemT]:
        async for page in self.iter_pages():
            for item in page.results:
                yield item


class AsyncPaginator(Generic[ItemT]):
    """What an async list method returns: ``await`` it for the first page, or
    ``async for`` over it for every item."""

    def __init__(self, first_page: Callable[[], Awaitable[AsyncPage[ItemT]]]) -> None:
        self._first_page = first_page

    def __await__(self) -> Generator[Any, None, AsyncPage[ItemT]]:
        return self._first_page().__await__()

    async def __aiter__(self) -> AsyncIterator[ItemT]:
        page = await self._first_page()
        async for item in page:
            yield item
