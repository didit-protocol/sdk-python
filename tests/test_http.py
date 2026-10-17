"""Errors, the retry policy, Retry-After and timeouts (DESIGN 7)."""

from __future__ import annotations

import asyncio
import email.utils
import time
from typing import Any

import httpx
import pytest

import didit
from didit._base_client import (
    parse_retry_after,
    retry_delay,
    should_retry_exception,
    should_retry_status,
)
from tests.mock_api import API_KEY, SESSION, MockAPI


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    delays: list[float] = []
    monkeypatch.setattr("didit._base_client.time.sleep", delays.append)

    async def fake_async_sleep(delay: float) -> None:
        delays.append(delay)

    monkeypatch.setattr("didit._base_client.asyncio.sleep", fake_async_sleep)
    return delays


def _request() -> httpx.Request:
    return httpx.Request("GET", "https://verification.didit.me/v3/x/")


# Errors ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "cls"),
    [
        (400, didit.BadRequestError),
        (401, didit.AuthenticationError),
        (403, didit.PermissionDeniedError),
        (404, didit.NotFoundError),
        (409, didit.ConflictError),
        (422, didit.UnprocessableEntityError),
        (429, didit.RateLimitError),
        (500, didit.InternalServerError),
        (503, didit.InternalServerError),
        (418, didit.APIStatusError),
    ],
)
def test_status_errors(status: int, cls: type[didit.APIStatusError]) -> None:
    api = MockAPI().add(
        httpx.Response(status, json={"detail": "nope"}, headers={"x-request-id": "req_9"})
    )
    client = api.client(max_retries=0)
    with pytest.raises(cls) as info:
        client.sessions.retrieve_decision("s")
    err = info.value
    assert type(err) is cls
    assert isinstance(err, didit.APIStatusError)
    assert isinstance(err, didit.DiditError)
    assert err.status == status == err.status_code
    assert err.body == {"detail": "nope"}
    assert err.request_id == "req_9"
    assert err.headers["x-request-id"] == "req_9"
    assert err.message == f"HTTP {status}: nope"
    assert str(err) == f"HTTP {status}: nope (request id req_9)"


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ({"error": "Invalid workflow"}, "HTTP 400: Invalid workflow"),
        ({"message": "bad"}, "HTTP 400: bad"),
        (
            {"workflow_id": ["This field is required."], "language": "unknown"},
            "HTTP 400: workflow_id: This field is required.; language: unknown",
        ),
        (["one", "two"], "HTTP 400: one; two"),
        ({}, "HTTP 400"),
    ],
)
def test_error_messages(body: Any, message: str) -> None:
    api = MockAPI().add(httpx.Response(400, json=body))
    with pytest.raises(didit.BadRequestError) as info:
        api.client().sessions.create(workflow_id="w")
    assert info.value.message == message
    assert info.value.request_id is None


def test_non_json_error_body() -> None:
    api = MockAPI().add(httpx.Response(502, text="<html>Bad gateway</html>"))
    with pytest.raises(didit.InternalServerError) as info:
        api.client(max_retries=0).sessions.retrieve_decision("s")
    assert info.value.body == "<html>Bad gateway</html>"
    empty = MockAPI().add(httpx.Response(404))
    with pytest.raises(didit.NotFoundError) as info2:
        empty.client().sessions.retrieve_decision("s")
    assert info2.value.body is None


def test_error_messages_never_contain_the_api_key() -> None:
    api = MockAPI().add(httpx.Response(403, json={"detail": f"Key {API_KEY} is revoked"}))
    with pytest.raises(didit.PermissionDeniedError) as info:
        api.client().sessions.retrieve_decision("s")
    assert API_KEY not in str(info.value)
    assert API_KEY not in repr(info.value)
    assert "[redacted]" in info.value.message


def test_html_on_success_is_a_response_validation_error() -> None:
    api = MockAPI().add(
        httpx.Response(200, text="<html></html>", headers={"content-type": "text/html"})
    )
    with pytest.raises(didit.APIResponseValidationError) as info:
        api.client().sessions.retrieve_decision("s")
    assert info.value.status == 200


def test_connection_and_timeout_errors() -> None:
    api = MockAPI().add(httpx.ConnectError("refused"))
    with pytest.raises(didit.APIConnectionError) as info:
        api.client(max_retries=0).sessions.retrieve_decision("s")
    assert not isinstance(info.value, didit.APITimeoutError)
    assert info.value.request.url.path == "/v3/session/s/decision/"
    api = MockAPI().add(httpx.ReadTimeout("slow"))
    with pytest.raises(didit.APITimeoutError):
        api.client(max_retries=0).sessions.retrieve_decision("s")


class _BrokenBody(httpx.SyncByteStream, httpx.AsyncByteStream):
    """A body that starts arriving and then stalls or drops."""

    def __init__(self, error: Exception) -> None:
        self.error = error

    def __iter__(self) -> Any:
        yield b'{"session_id": "'
        raise self.error

    async def __aiter__(self) -> Any:
        yield b'{"session_id": "'
        raise self.error


def _broken(status: int, error: Exception) -> Any:
    return lambda _request: httpx.Response(status, stream=_BrokenBody(error))


@pytest.mark.parametrize(
    ("error", "cls"),
    [
        (httpx.ReadTimeout("stalled"), didit.APITimeoutError),
        (httpx.RemoteProtocolError("peer closed"), didit.APIConnectionError),
        (httpx.ReadError("reset"), didit.APIConnectionError),
    ],
)
def test_errors_while_reading_the_body_are_sdk_errors_and_retried_for_get(
    error: Exception, cls: type[didit.APIConnectionError]
) -> None:
    api = MockAPI().add(_broken(200, error), _broken(200, error), _broken(200, error))
    with pytest.raises(cls) as info:
        api.client().sessions.retrieve_decision("s")
    assert len(api.requests) == 3
    assert info.value.request.headers["x-api-key"] == "[redacted]"
    # A GET whose body broke is retried and can then succeed.
    api = MockAPI().add(_broken(200, error)).json(200, {"session_id": "s"})
    assert api.client().sessions.retrieve_decision("s").session_id == "s"
    # An error response whose body broke is a connection error too.
    api = MockAPI().add(_broken(404, error))
    with pytest.raises(cls):
        api.client(max_retries=0).sessions.retrieve_decision("s")


def test_a_post_whose_body_broke_is_not_retried() -> None:
    api = MockAPI().add(_broken(201, httpx.ReadTimeout("stalled")))
    with pytest.raises(didit.APITimeoutError):
        api.client().sessions.create(workflow_id="w-1")
    assert len(api.requests) == 1


def test_async_errors_while_reading_the_body() -> None:
    async def run() -> None:
        api = MockAPI().add(*[_broken(200, httpx.ReadTimeout("stalled"))] * 3)
        with pytest.raises(didit.APITimeoutError):
            await api.async_client().sessions.retrieve_decision("s")
        assert len(api.requests) == 3
        api = MockAPI().add(_broken(201, httpx.RemoteProtocolError("dropped")))
        with pytest.raises(didit.APIConnectionError):
            await api.async_client().sessions.create(workflow_id="w-1")
        assert len(api.requests) == 1

    asyncio.run(run())


def test_streamed_body_errors_are_sdk_errors() -> None:
    api = MockAPI().add(_broken(200, httpx.ReadError("reset")))
    client = api.client()
    with (
        client.sessions.with_streaming_response.generate_pdf("s") as response,
        pytest.raises(didit.APIConnectionError),
    ):
        b"".join(response.iter_bytes())

    async def run() -> None:
        api = MockAPI().add(_broken(200, httpx.ReadTimeout("stalled")))
        async with api.async_client().sessions.with_streaming_response.generate_pdf(
            "s"
        ) as response:
            with pytest.raises(didit.APITimeoutError):
                await response.read()

    asyncio.run(run())


def test_errors_keep_no_credentials_on_their_request() -> None:
    api = MockAPI().add(httpx.Response(400, json={"detail": "bad"}))
    with pytest.raises(didit.BadRequestError) as info:
        api.client().sessions.retrieve_decision("s")
    assert info.value.response.request.headers["x-api-key"] == "[redacted]"
    assert API_KEY not in repr(info.value.response.request.headers)
    api = MockAPI().add(httpx.ConnectError("refused"))
    with pytest.raises(didit.APIConnectionError) as conn:
        api.client(max_retries=0).sessions.retrieve_decision("s")
    assert conn.value.request.headers["x-api-key"] == "[redacted]"


# Retry policy ---------------------------------------------------------------------


@pytest.mark.parametrize("method", ["GET", "HEAD", "PUT", "DELETE"])
@pytest.mark.parametrize("status", [408, 429, 500, 502, 503, 504])
def test_idempotent_methods_retry_on_retryable_statuses(method: str, status: int) -> None:
    assert should_retry_status(method, status)


@pytest.mark.parametrize("method", ["POST", "PATCH"])
def test_post_and_patch_retry_only_on_429(method: str) -> None:
    assert should_retry_status(method, 429)
    for status in (408, 500, 502, 503, 504):
        assert not should_retry_status(method, status)


@pytest.mark.parametrize("status", [400, 401, 403, 404, 409, 422])
def test_client_errors_never_retry(status: int) -> None:
    assert not should_retry_status("GET", status)


def test_exception_policy() -> None:
    request = _request()
    for exc in (
        httpx.ConnectError("x", request=request),
        httpx.ConnectTimeout("x", request=request),
        httpx.PoolTimeout("x", request=request),
    ):
        assert should_retry_exception("POST", exc)
        assert should_retry_exception("GET", exc)
    for late in (
        httpx.ReadTimeout("x", request=request),
        httpx.WriteTimeout("x", request=request),
        httpx.ReadError("x", request=request),
        httpx.RemoteProtocolError("x", request=request),
    ):
        assert not should_retry_exception("POST", late)
        assert not should_retry_exception("PATCH", late)
        assert should_retry_exception("GET", late)
    assert not should_retry_exception("GET", httpx.UnsupportedProtocol("x", request=request))


def test_get_retries_5xx_then_succeeds(no_sleep: list[float]) -> None:
    api = MockAPI().add(httpx.Response(503), httpx.Response(500)).json(200, {"session_id": "s"})
    result = api.client().sessions.retrieve_decision("s")
    assert result.session_id == "s"
    assert len(api.requests) == 3
    assert len(no_sleep) == 2
    assert 0 <= no_sleep[0] <= 0.5
    assert 0 <= no_sleep[1] <= 1.0


def test_retries_stop_at_max_retries() -> None:
    api = MockAPI().add(
        httpx.Response(500), httpx.Response(500), httpx.Response(500), httpx.Response(500)
    )
    with pytest.raises(didit.InternalServerError):
        api.client(max_retries=2).sessions.retrieve_decision("s")
    assert len(api.requests) == 3


def test_post_is_not_retried_after_a_5xx() -> None:
    api = MockAPI().add(httpx.Response(500)).json(201, SESSION)
    with pytest.raises(didit.InternalServerError):
        api.client().sessions.create(workflow_id="w")
    assert len(api.requests) == 1


def test_post_is_not_retried_after_a_read_timeout() -> None:
    api = MockAPI().add(httpx.ReadTimeout("slow")).json(201, SESSION)
    with pytest.raises(didit.APITimeoutError):
        api.client().sessions.create(workflow_id="w")
    assert len(api.requests) == 1


def test_post_is_retried_when_the_connection_failed_before_sending() -> None:
    api = (
        MockAPI()
        .add(httpx.ConnectError("refused"), httpx.ConnectTimeout("slow"))
        .json(201, SESSION)
    )
    session = api.client().sessions.create(workflow_id="w")
    assert session.session_id == SESSION["session_id"]
    assert len(api.requests) == 3


def test_post_is_retried_on_429_honouring_retry_after(no_sleep: list[float]) -> None:
    api = MockAPI().add(httpx.Response(429, headers={"Retry-After": "7"})).json(201, SESSION)
    api.client().sessions.create(workflow_id="w")
    assert len(api.requests) == 2
    assert no_sleep == [7.0]


def test_get_retries_timeouts_and_dropped_connections() -> None:
    api = (
        MockAPI().add(httpx.ReadTimeout("slow"), httpx.RemoteProtocolError("dropped")).json(200, {})
    )
    api.client().sessions.retrieve_decision("s")
    assert len(api.requests) == 3


def test_max_retries_zero_and_per_call_override() -> None:
    api = MockAPI().add(httpx.Response(503))
    with pytest.raises(didit.InternalServerError):
        api.client(max_retries=0).sessions.retrieve_decision("s")
    assert len(api.requests) == 1
    api = MockAPI().add(httpx.Response(503), httpx.Response(503)).json(200, {})
    client = api.client(max_retries=0)
    client.with_options(max_retries=2).sessions.retrieve_decision("s")
    assert len(api.requests) == 3


def test_retry_delays_are_capped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("didit._base_client.random.uniform", lambda low, high: high)
    assert [retry_delay(n, None) for n in range(6)] == [0.5, 1.0, 2.0, 4.0, 8.0, 8.0]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("3", 3.0),
        ("0.5", 0.5),
        ("120", 60.0),
        ("-4", 0.0),
        ("soon", None),
        ("", None),
        ("nan", None),
    ],
)
def test_retry_after_seconds(value: str, expected: float | None) -> None:
    assert parse_retry_after(httpx.Headers({"Retry-After": value})) == expected


def test_retry_after_http_date() -> None:
    now = time.time()
    date = email.utils.formatdate(now + 10, usegmt=True)
    parsed = parse_retry_after(httpx.Headers({"Retry-After": date}), now=now)
    assert parsed is not None
    assert 9 <= parsed <= 10
    far = email.utils.formatdate(now + 3600, usegmt=True)
    assert parse_retry_after(httpx.Headers({"Retry-After": far}), now=now) == 60.0
    assert parse_retry_after(httpx.Headers({})) is None


def test_retry_after_is_used_for_get(no_sleep: list[float]) -> None:
    api = MockAPI().add(httpx.Response(503, headers={"Retry-After": "2"})).json(200, {})
    api.client().sessions.retrieve_decision("s")
    assert no_sleep == [2.0]


def test_async_retry_policy(no_sleep: list[float]) -> None:
    api = MockAPI().add(httpx.Response(502), httpx.ConnectError("x")).json(200, {"session_id": "s"})
    post = MockAPI().add(httpx.Response(500))

    async def run() -> None:
        client = api.async_client()
        result = await client.sessions.retrieve_decision("s")
        assert result.session_id == "s"
        with pytest.raises(didit.InternalServerError):
            await post.async_client().sessions.create(workflow_id="w")
        with pytest.raises(didit.APITimeoutError):
            await (
                MockAPI()
                .add(httpx.ReadTimeout("x"))
                .async_client(max_retries=0)
                .sessions.retrieve_decision("s")
            )
        with pytest.raises(didit.APIConnectionError):
            await (
                MockAPI()
                .add(httpx.ConnectError("x"))
                .async_client(max_retries=0)
                .sessions.retrieve_decision("s")
            )
        with pytest.raises(didit.NotFoundError):
            await (
                MockAPI()
                .add(httpx.Response(404, json={"detail": "gone"}))
                .async_client()
                .sessions.retrieve_decision("s")
            )
        timeout_then_ok = MockAPI().add(httpx.ReadTimeout("x")).json(200, {})
        await timeout_then_ok.async_client().sessions.retrieve_decision("s")
        assert len(timeout_then_ok.requests) == 2

    asyncio.run(run())
    assert len(api.requests) == 3
    assert len(post.requests) == 1
    assert len(no_sleep) == 3
