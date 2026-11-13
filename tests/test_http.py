"""Errors, the retry policy, Retry-After and timeouts (DESIGN 7)."""

from __future__ import annotations

import asyncio
import email.utils
import time
from collections.abc import AsyncIterator, Iterator
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

    def __iter__(self) -> Iterator[bytes]:
        yield b'{"session_id": "'
        raise self.error

    async def __aiter__(self) -> AsyncIterator[bytes]:
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
    api = MockAPI().add(httpx.Response(200, text="<html>", headers={"content-type": "text/html"}))
    with pytest.raises(didit.APIResponseValidationError) as html:
        api.client().sessions.retrieve_decision("s")
    assert html.value.response.request.headers["x-api-key"] == "[redacted]"
    api = MockAPI().add(httpx.Response(200, text="<html>"))
    with pytest.raises(didit.APIResponseValidationError) as page:
        api.client().businesses.list()
    assert page.value.response.request.headers["x-api-key"] == "[redacted]"
    api = MockAPI().add(_broken(200, httpx.ReadTimeout("stalled")))
    with (
        api.client().sessions.with_streaming_response.generate_pdf("s") as response,
        pytest.raises(didit.APITimeoutError) as streamed,
    ):
        response.read()
    assert streamed.value.request.headers["x-api-key"] == "[redacted]"


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


# Idempotency key option (DESIGN 6 and 7) ------------------------------------------------

KEY = "order-1042"


def _conflict(code: str, **headers: str) -> httpx.Response:
    return httpx.Response(409, json={"detail": "x", "code": code}, headers=headers)


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_idempotency_key_header_is_sent_on_writes(method: str) -> None:
    api = MockAPI().json(200, {})
    client = api.client().with_options(idempotency_key=KEY)
    client.request(method, "/v3/x/", cast_to=None)
    assert api.last.headers["idempotency-key"] == KEY


@pytest.mark.parametrize("method", ["GET", "HEAD"])
def test_idempotency_key_header_is_left_out_of_reads(method: str) -> None:
    api = MockAPI().json(200, {})
    api.client().with_options(idempotency_key=KEY).request(method, "/v3/x/", cast_to=None)
    assert "idempotency-key" not in api.last.headers


def test_idempotency_key_is_not_a_constructor_option() -> None:
    with pytest.raises(TypeError):
        didit.Didit(api_key=API_KEY, idempotency_key=KEY)  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        didit.AsyncDidit(api_key=API_KEY, idempotency_key=KEY)  # type: ignore[call-arg]


@pytest.mark.parametrize("bad", ["", "k" * 256, 12, None, b"key"])
def test_idempotency_key_is_validated_before_any_request(bad: Any) -> None:
    api = MockAPI().json(201, SESSION)
    with pytest.raises(didit.ConfigurationError):
        api.client().with_options(idempotency_key=bad)
    with pytest.raises(didit.ConfigurationError):
        api.async_client().with_options(idempotency_key=bad)
    assert api.requests == []


def test_idempotency_key_boundary_lengths_are_accepted() -> None:
    api = MockAPI().json(201, SESSION).json(201, SESSION)
    client = api.client()
    client.with_options(idempotency_key="k").sessions.create(workflow_id="w")
    client.with_options(idempotency_key="k" * 255).sessions.create(workflow_id="w")
    assert len(api.requests) == 2


def test_idempotency_key_survives_further_with_options() -> None:
    api = MockAPI().json(201, SESSION)
    client = api.client().with_options(idempotency_key=KEY).with_options(max_retries=0)
    client.sessions.create(workflow_id="w")
    assert api.last.headers["idempotency-key"] == KEY


@pytest.mark.parametrize(
    "failure", [httpx.Response(500), httpx.Response(503), httpx.ReadTimeout("slow")]
)
def test_post_with_a_key_is_retried_with_the_same_key(failure: Any) -> None:
    api = MockAPI().add(failure, failure).json(201, SESSION)
    client = api.client().with_options(idempotency_key=KEY)
    assert client.sessions.create(workflow_id="w").session_id == SESSION["session_id"]
    assert [r.headers["idempotency-key"] for r in api.requests] == [KEY] * 3


def test_post_with_a_key_stops_at_max_retries() -> None:
    api = MockAPI().add(httpx.Response(500), httpx.Response(500), httpx.Response(500))
    with pytest.raises(didit.InternalServerError):
        api.client(max_retries=1).with_options(idempotency_key=KEY).sessions.create(workflow_id="w")
    assert len(api.requests) == 2


def test_patch_with_a_key_is_retried_and_without_a_key_is_not() -> None:
    api = MockAPI().add(httpx.Response(502), httpx.ReadTimeout("slow")).json(200, {})
    client = api.client().with_options(idempotency_key=KEY)
    client.request("PATCH", "/v3/x/", cast_to=None)
    assert len(api.requests) == 3
    assert {r.headers["idempotency-key"] for r in api.requests} == {KEY}
    api = MockAPI().add(httpx.Response(502)).json(200, {})
    with pytest.raises(didit.InternalServerError):
        api.client().request("PATCH", "/v3/x/", cast_to=None)
    assert len(api.requests) == 1


def test_async_post_with_a_key_is_retried() -> None:
    api = (
        MockAPI()
        .add(
            httpx.Response(500), httpx.ReadTimeout("slow"), _conflict("idempotency_key_in_progress")
        )
        .json(201, SESSION)
    )

    async def run() -> Any:
        return (
            await api.async_client(max_retries=3)
            .with_options(idempotency_key=KEY)
            .sessions.create(workflow_id="w")
        )

    assert asyncio.run(run()).session_id == SESSION["session_id"]
    assert len(api.requests) == 4
    assert {r.headers["idempotency-key"] for r in api.requests} == {KEY}


def test_in_progress_conflict_is_retried_honouring_retry_after(no_sleep: list[float]) -> None:
    api = (
        MockAPI()
        .add(_conflict("idempotency_key_in_progress", **{"Retry-After": "1"}))
        .json(201, SESSION)
    )
    client = api.client().with_options(idempotency_key=KEY)
    assert client.sessions.create(workflow_id="w").session_id == SESSION["session_id"]
    assert len(api.requests) == 2
    assert no_sleep == [1.0]


def test_reused_key_conflict_is_raised_at_once() -> None:
    api = MockAPI().add(_conflict("idempotency_key_reused")).json(201, SESSION)
    with pytest.raises(didit.ConflictError) as info:
        api.client().with_options(idempotency_key=KEY).sessions.create(workflow_id="w")
    assert info.value.body == {"detail": "x", "code": "idempotency_key_reused"}
    assert len(api.requests) == 1


def test_in_progress_conflict_without_a_key_or_with_a_plain_409_is_not_retried() -> None:
    api = MockAPI().add(_conflict("idempotency_key_in_progress")).json(201, SESSION)
    with pytest.raises(didit.ConflictError):
        api.client().sessions.create(workflow_id="w")
    assert len(api.requests) == 1
    api = MockAPI().add(httpx.Response(409, text="busy")).json(201, SESSION)
    with pytest.raises(didit.ConflictError):
        api.client().with_options(idempotency_key=KEY).sessions.create(workflow_id="w")
    assert len(api.requests) == 1


def test_option_wins_over_a_generated_header_parameter() -> None:
    api = MockAPI().json(200, {})
    client = api.client().with_options(idempotency_key=KEY)
    client.aml.screen(full_name="Jane Doe", idempotency_key="from-parameter")
    assert api.last.headers.get_list("idempotency-key") == [KEY]
    api = MockAPI().json(200, {})
    api.client().aml.screen(full_name="Jane Doe", idempotency_key="from-parameter")
    assert api.last.headers["idempotency-key"] == "from-parameter"


def test_the_key_is_never_logged(caplog: pytest.LogCaptureFixture) -> None:
    import logging

    api = MockAPI().add(httpx.Response(500)).json(201, SESSION)
    with caplog.at_level(logging.DEBUG, logger="didit"):
        api.client().with_options(idempotency_key=KEY).sessions.create(workflow_id="w")
    assert "retrying" in caplog.text
    assert KEY not in caplog.text


def test_retry_policy_functions_with_a_key() -> None:
    assert should_retry_status("POST", 500, keyed=True)
    assert should_retry_status("PATCH", 408, keyed=True)
    assert not should_retry_status("POST", 400, keyed=True)
    assert not should_retry_status("POST", 500)
    assert should_retry_exception("POST", httpx.ReadTimeout("x"), keyed=True)
    assert not should_retry_exception("POST", httpx.ReadTimeout("x"))


def test_idempotency_key_is_never_sent_on_other_methods() -> None:
    api = MockAPI().json(200, {}).json(200, {})
    client = api.client().with_options(idempotency_key=KEY)
    client.request("OPTIONS", "/v3/x/", cast_to=None)
    assert "idempotency-key" not in api.last.headers
    client.request("OPTIONS", "/v3/x/", cast_to=None, extra_headers={"Idempotency-Key": "raw"})
    assert "idempotency-key" not in api.last.headers


def test_a_client_default_idempotency_key_header_is_ignored() -> None:
    api = MockAPI().add(httpx.Response(500)).json(201, SESSION)
    client = api.client(default_headers={"idempotency-key": "default"})
    with pytest.raises(didit.InternalServerError):
        client.sessions.create(workflow_id="w")
    assert len(api.requests) == 1
    assert "idempotency-key" not in api.last.headers
    api = MockAPI().add(httpx.Response(500)).json(201, SESSION)
    derived = api.client(default_headers={"Idempotency-Key": "default"}).with_options(max_retries=3)
    with pytest.raises(didit.InternalServerError):
        derived.sessions.create(workflow_id="w")
    assert len(api.requests) == 1
    assert "idempotency-key" not in api.last.headers


def test_the_option_still_works_on_a_client_with_a_default_key_header() -> None:
    api = MockAPI().add(httpx.Response(500)).json(201, SESSION)
    client = api.client(default_headers={"Idempotency-Key": "default"})
    client.with_options(idempotency_key=KEY).sessions.create(workflow_id="w")
    assert [r.headers.get_list("idempotency-key") for r in api.requests] == [[KEY], [KEY]]


def test_a_lowercase_raw_header_is_one_header_and_makes_a_post_retryable() -> None:
    api = MockAPI().add(httpx.Response(500)).json(201, SESSION)
    api.client().sessions.create(workflow_id="w", extra_headers={"idempotency-key": KEY})
    assert [r.headers.get_list("idempotency-key") for r in api.requests] == [[KEY], [KEY]]
    assert sum(1 for k, _ in api.requests[0].headers.raw if k.lower() == b"idempotency-key") == 1


@pytest.mark.parametrize("bad", ["", "k" * 256])
def test_an_invalid_generated_parameter_or_raw_header_is_a_configuration_error(bad: str) -> None:
    api = MockAPI().json(200, {}).json(201, SESSION)
    with pytest.raises(didit.ConfigurationError):
        api.client().aml.screen(full_name="Jane Doe", idempotency_key=bad)
    with pytest.raises(didit.ConfigurationError):
        api.client().sessions.create(workflow_id="w", extra_headers={"Idempotency-Key": bad})
    with pytest.raises(didit.ConfigurationError):
        asyncio.run(api.async_client().aml.screen(full_name="Jane Doe", idempotency_key=bad))
    assert api.requests == []


def test_a_valid_generated_parameter_makes_the_post_retryable() -> None:
    api = MockAPI().add(httpx.Response(503)).json(200, {})
    api.client().aml.screen(full_name="Jane Doe", idempotency_key=KEY)
    assert [r.headers["idempotency-key"] for r in api.requests] == [KEY, KEY]


def test_option_raw_header_and_parameter_together_send_one_header() -> None:
    api = MockAPI().json(200, {})
    client = api.client().with_options(idempotency_key=KEY)
    client.aml.screen(
        full_name="Jane Doe",
        idempotency_key="from-parameter",
        extra_headers={"idempotency-key": "from-raw"},
    )
    assert api.last.headers.get_list("idempotency-key") == [KEY]
    assert sum(1 for k, _ in api.last.headers.raw if k.lower() == b"idempotency-key") == 1


def test_a_raw_header_beats_the_generated_parameter() -> None:
    api = MockAPI().json(200, {})
    api.client().aml.screen(
        full_name="Jane Doe",
        idempotency_key="from-parameter",
        extra_headers={"idempotency-key": "raw"},
    )
    assert api.last.headers.get_list("idempotency-key") == ["raw"]


def test_a_raw_key_header_is_dropped_on_a_non_write_method() -> None:
    api = MockAPI().json(200, {})
    api.client().request("GET", "/v3/x/", cast_to=None, extra_headers={"Idempotency-Key": KEY})
    assert "idempotency-key" not in api.last.headers


def test_a_409_with_a_key_and_a_non_json_body_is_raised_at_once() -> None:
    api = MockAPI().add(httpx.Response(409, text="idempotency_key_in_progress")).json(201, SESSION)
    with pytest.raises(didit.ConflictError):
        api.client().with_options(idempotency_key=KEY).sessions.create(workflow_id="w")
    assert len(api.requests) == 1


def test_in_progress_conflicts_count_against_max_retries() -> None:
    api = MockAPI().add(*[_conflict("idempotency_key_in_progress") for _ in range(3)])
    with pytest.raises(didit.ConflictError):
        api.client(max_retries=2).with_options(idempotency_key=KEY).sessions.create(workflow_id="w")
    assert len(api.requests) == 3
