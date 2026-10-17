"""The mocked HTTP layer behind the generated per-operation tests (tests/generated).

Each generated test describes the request it expects and the response the
fake API returns; :func:`check_operation` runs the call on ``Didit`` and on
``AsyncDidit`` and checks both. No test here touches the network.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

import httpx
import pydantic

from didit import AsyncDidit, Didit

TEST_API_KEY = "test-api-key"
TEST_ACCOUNT_TOKEN = "test-account-token"
ORG_ID = "0b5e8d2c-0000-4000-8000-0000000000aa"
APP_ID = "0b5e8d2c-0000-4000-8000-0000000000bb"
BINARY_BODY = b"%PDF-1.4\n% synthetic test document\n"

_MISSING: Any = object()
_HOSTS = {"verification": ("verification.didit.me", ""), "account": ("apx.didit.me", "/auth/v2")}


@dataclass(frozen=True)
class Expect:
    method: str
    path: str
    api: str
    auth: str
    status: int
    query: Mapping[str, list[str]] = field(default_factory=lambda: {})
    json_body: object = _MISSING
    multipart_fields: list[str] | None = None
    multipart_files: list[str] | None = None
    response_json: object = None
    response_bytes: bytes | None = None
    response_content_type: str | None = None
    strict_type: object = None


def _response(expect: Expect) -> httpx.Response:
    if expect.response_bytes is not None:
        return httpx.Response(
            expect.status,
            content=expect.response_bytes,
            headers={"content-type": expect.response_content_type or "application/octet-stream"},
        )
    if expect.response_json is None:
        return httpx.Response(expect.status)
    return httpx.Response(
        expect.status, json=expect.response_json, headers={"x-request-id": "req_test"}
    )


def _check_request(request: httpx.Request, expect: Expect) -> None:
    host, prefix = _HOSTS[expect.api]
    assert request.method == expect.method
    assert request.url.scheme == "https"
    assert request.url.host == host
    assert request.url.path == prefix + expect.path, (request.url.path, prefix + expect.path)
    query: dict[str, list[str]] = {}
    for key, value in request.url.params.multi_items():
        query.setdefault(key, []).append(value)
    assert query == dict(expect.query), (query, expect.query)

    headers = request.headers
    assert headers["user-agent"].startswith("didit-python/")
    assert headers["x-didit-client"].startswith("python/")
    if expect.auth == "api_key":
        assert headers.get("x-api-key") == TEST_API_KEY
        assert "authorization" not in headers
    elif expect.auth == "account_token":
        assert headers.get("authorization") == f"Bearer {TEST_ACCOUNT_TOKEN}"
        assert "x-api-key" not in headers
    else:
        assert "x-api-key" not in headers
        assert "authorization" not in headers

    content = request.read()
    if expect.multipart_fields is not None or expect.multipart_files is not None:
        assert headers["content-type"].startswith("multipart/form-data; boundary=")
        text = content.decode("utf-8", "replace")
        for name in expect.multipart_fields or []:
            assert f'name="{name}"\r\n' in text, name
        for name in expect.multipart_files or []:
            assert f'name="{name}"; filename=' in text, name
    elif expect.json_body is not _MISSING:
        assert headers["content-type"] == "application/json"
        assert json.loads(content) == expect.json_body
    else:
        assert content == b""


def check_operation(
    expect: Expect,
    sync_call: Callable[[Didit], object],
    async_call: Callable[[AsyncDidit], Awaitable[object]],
    sync_check: Callable[[Any], bool],
    async_check: Callable[[Any], bool],
) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return _response(expect)

    options: dict[str, Any] = {
        "api_key": TEST_API_KEY,
        "organization_id": ORG_ID,
        "application_id": APP_ID,
        "account_token": TEST_ACCOUNT_TOKEN,
        "max_retries": 0,
    }
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        result = sync_call(Didit(http_client=http, **options))
    assert len(seen) == 1
    _check_request(seen[0], expect)
    assert sync_check(result), result

    async def run() -> object:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            return await async_call(AsyncDidit(http_client=http, **options))

    result = asyncio.run(run())
    assert len(seen) == 2
    _check_request(seen[1], expect)
    assert async_check(result), result

    if expect.strict_type is not None:
        # Synthesised from the schema, so it must also pass strict validation.
        strict: Any = expect.strict_type
        pydantic.TypeAdapter(strict).validate_python(expect.response_json)
