"""A scripted fake API for the core tests: queue responses, inspect requests."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx

from didit import AsyncDidit, Didit

API_KEY = "test-api-key"
ORG_ID = "0b5e8d2c-0000-4000-8000-0000000000aa"
APP_ID = "0b5e8d2c-0000-4000-8000-0000000000bb"

Responder = Callable[[httpx.Request], httpx.Response]


class MockAPI:
    """Answers requests from a queue; an exception in the queue is raised as a transport error."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self._queue: list[httpx.Response | Exception | Responder] = []
        self.default: httpx.Response | None = None

    def add(self, *items: httpx.Response | Exception | Responder) -> MockAPI:
        self._queue.extend(items)
        return self

    def json(self, status: int = 200, body: Any = None, **headers: str) -> MockAPI:
        return self.add(
            httpx.Response(status, json=body if body is not None else {}, headers=headers)
        )

    def __call__(self, request: httpx.Request) -> httpx.Response:
        request.read()
        self.requests.append(request)
        if not self._queue:
            if self.default is not None:
                return self.default
            raise AssertionError(f"Unexpected request {request.method} {request.url}")
        item = self._queue.pop(0)
        if isinstance(item, Exception):
            raise item
        if callable(item) and not isinstance(item, httpx.Response):
            return item(request)
        return item

    @property
    def last(self) -> httpx.Request:
        return self.requests[-1]

    def last_json(self) -> Any:
        return json.loads(self.last.content)

    def client(self, **options: Any) -> Didit:
        options.setdefault("api_key", API_KEY)
        options.setdefault("organization_id", ORG_ID)
        options.setdefault("application_id", APP_ID)
        return Didit(http_client=httpx.Client(transport=httpx.MockTransport(self)), **options)

    def async_client(self, **options: Any) -> AsyncDidit:
        options.setdefault("api_key", API_KEY)
        options.setdefault("organization_id", ORG_ID)
        options.setdefault("application_id", APP_ID)
        return AsyncDidit(
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(self)), **options
        )


SESSION = {
    "session_id": "11111111-2222-3333-4444-555555555555",
    "session_number": 7,
    "session_token": "abc123",
    "url": "https://verify.didit.me/session/abc123",
    "vendor_data": "user-1",
    "metadata": None,
    "status": "Not Started",
    "workflow_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    "workflow_version": 1,
    "callback": None,
}
