"""Auto-pagination and the next-link origin check (DESIGN 6 and 8)."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest

import didit
from didit.types import BusinessListItem
from tests.mock_api import API_KEY, MockAPI

BASE = "https://verification.didit.me/v3/businesses/"


def _page(ids: list[str], next_url: str | None, count: int = 5, **extra: Any) -> dict[str, Any]:
    return {
        "count": count,
        "next": next_url,
        "previous": None,
        "results": [{"didit_internal_id": i, "vendor_data": f"b-{i}"} for i in ids],
        **extra,
    }


def _three_pages() -> MockAPI:
    return (
        MockAPI()
        .json(200, _page(["1", "2"], f"{BASE}?limit=2&offset=2"))
        .json(200, _page(["3", "4"], f"{BASE}?limit=2&offset=4"))
        .json(200, _page(["5"], None))
    )


def test_page_fields_and_iteration() -> None:
    api = _three_pages()
    page = api.client().businesses.list(limit=2)
    assert isinstance(page, didit.SyncPage)
    assert page.count == 5
    assert page.next == f"{BASE}?limit=2&offset=2"
    assert page.previous is None
    assert [b.didit_internal_id for b in page.results] == ["1", "2"]
    assert all(isinstance(b, BusinessListItem) for b in page.results)
    assert page.response is not None
    assert page.has_next_page()
    assert "count=5" in repr(page)
    assert len(api.requests) == 1
    assert api.requests[0].url.params["limit"] == "2"

    assert [b.didit_internal_id for b in page] == ["1", "2", "3", "4", "5"]
    assert len(api.requests) == 3
    assert api.requests[1].url.params["offset"] == "2"
    assert api.requests[2].url.params["offset"] == "4"
    for request in api.requests:
        assert request.headers["x-api-key"] == API_KEY


def test_iter_pages_and_get_next_page() -> None:
    api = _three_pages()
    pages = list(api.client().businesses.list(limit=2).iter_pages())
    assert [len(p.results) for p in pages] == [2, 2, 1]
    assert not pages[-1].has_next_page()
    with pytest.raises(didit.DiditError, match="last page"):
        pages[-1].get_next_page()


def test_next_link_on_another_origin_is_refused() -> None:
    for evil in (
        "https://evil.example.com/v3/businesses/?offset=2",
        "http://verification.didit.me/v3/businesses/?offset=2",
        "https://verification.didit.me:8443/v3/businesses/?offset=2",
    ):
        api = MockAPI().json(200, _page(["1"], evil))
        page = api.client().businesses.list()
        with pytest.raises(didit.DiditError, match="another origin"):
            page.get_next_page()
        with pytest.raises(didit.DiditError):
            list(page)
        assert len(api.requests) == 1


def test_default_port_counts_as_the_same_origin() -> None:
    api = (
        MockAPI()
        .json(200, _page(["1"], "https://verification.didit.me:443/v3/businesses/?offset=1"))
        .json(200, _page(["2"], None))
    )
    assert [b.didit_internal_id for b in api.client().businesses.list()] == ["1", "2"]


def test_extra_list_fields_are_kept_on_the_response() -> None:
    api = MockAPI().json(
        200,
        {"count": 1, "next": None, "previous": None, "results": [], "total_transactions": 42},
    )
    page = api.client().transactions.list()
    assert page.response is not None
    assert page.response.model_dump()["total_transactions"] == 42


def test_raw_response_of_a_list() -> None:
    api = MockAPI().add(
        httpx.Response(200, json=_page(["1"], None), headers={"x-request-id": "req_1"})
    )
    raw = api.client().businesses.with_raw_response.list()
    assert raw.status_code == 200
    assert raw.request_id == "req_1"
    page = raw.parse()
    assert isinstance(page, didit.SyncPage)
    assert [b.didit_internal_id for b in page] == ["1"]


def test_empty_page_stops() -> None:
    api = MockAPI().json(200, _page([], f"{BASE}?offset=0", count=0))
    assert list(api.client().businesses.list()) == []
    assert len(api.requests) == 1


def test_async_pagination() -> None:
    api = _three_pages()

    async def run() -> None:
        client = api.async_client()
        page = await client.businesses.list(limit=2)
        assert isinstance(page, didit.AsyncPage)
        assert [b.didit_internal_id for b in page.results] == ["1", "2"]
        seen = [b.didit_internal_id async for b in page]
        assert seen == ["1", "2", "3", "4", "5"]

    asyncio.run(run())
    assert len(api.requests) == 3

    api = _three_pages()

    async def run_direct() -> list[str | None]:
        client = api.async_client()
        return [b.didit_internal_id async for b in client.businesses.list(limit=2)]

    assert asyncio.run(run_direct()) == ["1", "2", "3", "4", "5"]

    api = _three_pages()
    api.json(200, _page(["3", "4"], f"{BASE}?limit=2&offset=4")).json(200, _page(["5"], None))
    api.json(200, _page(["1"], None))

    async def run_pages() -> list[int]:
        client = api.async_client()
        first = await client.businesses.list(limit=2)
        sizes = [len(p.results) async for p in first.iter_pages()]
        last = await (await first.get_next_page()).get_next_page()
        with pytest.raises(didit.DiditError):
            await last.get_next_page()
        raw = await client.businesses.with_raw_response.list()
        parsed = await raw.parse()
        assert isinstance(parsed, didit.AsyncPage)
        return sizes

    assert asyncio.run(run_pages()) == [2, 2, 1]


def test_async_next_link_on_another_origin_is_refused() -> None:
    api = MockAPI().json(200, _page(["1"], "https://evil.example.com/v3/businesses/"))

    async def run() -> None:
        page = await api.async_client().businesses.list()
        with pytest.raises(didit.DiditError, match="another origin"):
            await page.get_next_page()

    asyncio.run(run())


def test_not_a_page() -> None:
    api = MockAPI().json(200, [])
    with pytest.raises(didit.DiditError):
        api.client().businesses.list()


def _looping_api() -> MockAPI:
    loop = f"{BASE}?limit=1&offset=1"
    return MockAPI().add(*[lambda _r: httpx.Response(200, json=_page(["1"], loop))] * 5)


def test_a_repeated_next_link_stops_instead_of_looping() -> None:
    api = _looping_api()
    with pytest.raises(didit.DiditError, match="twice"):
        list(api.client().businesses.list(limit=1))
    assert len(api.requests) == 2

    async def run() -> None:
        with pytest.raises(didit.DiditError, match="twice"):
            async for _ in api.async_client().businesses.list(limit=1):
                pass

    api = _looping_api()
    asyncio.run(run())
    assert len(api.requests) == 2


def test_a_relative_next_link_is_resolved_against_the_page_url() -> None:
    api = (
        MockAPI()
        .json(200, _page(["1"], "/v3/businesses/?limit=1&offset=1"))
        .json(200, _page(["2"], "?limit=1&offset=2"))
        .json(200, _page(["3"], None))
    )
    ids = [b.didit_internal_id for b in api.client().businesses.list(limit=1)]
    assert ids == ["1", "2", "3"]
    assert [str(r.url) for r in api.requests[1:]] == [
        f"{BASE}?limit=1&offset=1",
        f"{BASE}?limit=1&offset=2",
    ]
    assert all(r.headers["x-api-key"] == API_KEY for r in api.requests)


def test_a_list_that_is_not_json_raises_a_validation_error() -> None:
    for response in (
        httpx.Response(200, text="<html>maintenance</html>", headers={"content-type": "text/html"}),
        httpx.Response(204),
    ):
        api = MockAPI().add(response)
        with pytest.raises(didit.APIResponseValidationError, match="paginated JSON object"):
            api.client().businesses.list()

    async def run() -> None:
        api = MockAPI().add(httpx.Response(200, text="not json"))
        with pytest.raises(didit.APIResponseValidationError):
            await api.async_client().businesses.list()

    asyncio.run(run())
