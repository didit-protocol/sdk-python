"""Client configuration, headers, application scope, redaction and logging (DESIGN 6)."""

from __future__ import annotations

import asyncio
import logging
import platform

import httpx
import pytest

import didit
from didit import AsyncDidit, ConfigurationError, Didit
from tests.mock_api import API_KEY, APP_ID, ORG_ID, SESSION, MockAPI


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("DIDIT_API_KEY", "DIDIT_ORGANIZATION_ID", "DIDIT_APPLICATION_ID", "DIDIT_LOG"):
        monkeypatch.delenv(name, raising=False)


def test_defaults() -> None:
    client = Didit(api_key=API_KEY)
    assert client.base_url == "https://verification.didit.me"
    assert client.account_base_url == "https://apx.didit.me/auth/v2"
    assert client.timeout == 60.0
    assert client.max_retries == 2
    assert client.organization_id is None


def test_environment_fallbacks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIDIT_API_KEY", "env-key")
    monkeypatch.setenv("DIDIT_ORGANIZATION_ID", "org-env")
    monkeypatch.setenv("DIDIT_APPLICATION_ID", "app-env")
    client = Didit()
    assert (client.api_key, client.organization_id, client.application_id) == (
        "env-key",
        "org-env",
        "app-env",
    )
    explicit = Didit(api_key="explicit", organization_id="o", application_id="a")
    assert (explicit.api_key, explicit.organization_id, explicit.application_id) == (
        "explicit",
        "o",
        "a",
    )
    asynchronous = AsyncDidit()
    assert asynchronous.api_key == "env-key"


def test_missing_api_key_fails_before_sending() -> None:
    api = MockAPI()
    client = api.client(api_key=None)
    with pytest.raises(ConfigurationError, match="DIDIT_API_KEY"):
        client.sessions.retrieve_decision("s-1")
    assert api.requests == []


def test_invalid_options() -> None:
    with pytest.raises(ConfigurationError):
        Didit(api_key=API_KEY, base_url="verification.didit.me")
    with pytest.raises(ConfigurationError):
        Didit(api_key=API_KEY, max_retries=-1)
    with pytest.raises(ConfigurationError):
        Didit(http_client=httpx.AsyncClient())  # type: ignore[arg-type]
    with pytest.raises(ConfigurationError):
        AsyncDidit(http_client=httpx.Client())  # type: ignore[arg-type]


def test_headers_on_every_request() -> None:
    api = MockAPI().json(201, SESSION)
    client = api.client(default_headers={"X-Team": "risk"})
    client.sessions.create(workflow_id="w-1")
    headers = api.last.headers
    assert headers["x-api-key"] == API_KEY
    assert headers["accept"] == "application/json"
    assert headers["content-type"] == "application/json"
    assert headers["x-didit-client"] == f"python/{didit.__version__}"
    assert headers["user-agent"] == (
        f"didit-python/{didit.__version__} ({platform.python_implementation()} "
        f"{platform.python_version()}; {platform.system()})"
    )
    assert headers["x-team"] == "risk"


def test_extra_headers_add_and_remove() -> None:
    api = MockAPI().json(201, SESSION)
    client = api.client()
    client.sessions.create(
        workflow_id="w-1",
        extra_headers={"X-Trace": "t-1", "X-Didit-Client": None},
        extra_query={"debug": True},
        extra_body={"new_field": 1},
    )
    assert api.last.headers["x-trace"] == "t-1"
    assert "x-didit-client" not in api.last.headers
    assert api.last.url.params["debug"] == "true"
    assert api.last_json() == {"workflow_id": "w-1", "new_field": 1}


def test_header_names_are_merged_case_insensitively() -> None:
    api = MockAPI().json(201, SESSION).json(201, SESSION)
    client = api.client(
        default_headers={"accept": "text/plain", "user-agent": "me/1", "X-API-KEY": "other"}
    )
    client.sessions.create(
        workflow_id="w-1", extra_headers={"content-type": "application/json; charset=utf-8"}
    )
    raw = api.last.headers.raw
    names = [name.lower() for name, _ in raw]
    assert len(names) == len(set(names)), names
    assert api.last.headers["accept"] == "text/plain"
    assert api.last.headers["user-agent"] == "me/1"
    assert api.last.headers["x-api-key"] == API_KEY  # the client's key wins
    assert api.last.headers["content-type"] == "application/json; charset=utf-8"
    # Removing User-Agent removes it: httpx does not put its own one back.
    client.sessions.create(workflow_id="w-1", extra_headers={"user-agent": None})
    assert "user-agent" not in api.last.headers


def test_bodies_json_cannot_carry_fail_before_sending() -> None:
    api = MockAPI()
    client = api.client()
    for bad in (float("nan"), float("inf"), object()):
        with pytest.raises(didit.DiditError, match="cannot be sent as JSON"):
            client.sessions.create(workflow_id="w-1", metadata={"x": bad})
    assert api.requests == []


def test_response_models_can_be_sent_back() -> None:
    from didit._models import validate_response
    from didit.types import SessionImportJob

    job = validate_response(SessionImportJob, {"uuid": "j-1", "status": "pending", "extra": 1})
    api = MockAPI().json(201, SESSION)
    api.client().sessions.create(workflow_id="w-1", metadata={"job": job})  # type: ignore[dict-item]
    assert api.last_json()["metadata"] == {"job": {"uuid": "j-1", "status": "pending", "extra": 1}}


def test_omitted_and_null_values() -> None:
    api = MockAPI().json(201, SESSION)
    client = api.client()
    client.sessions.create(workflow_id="w-1", vendor_data=didit.NOT_GIVEN, metadata=None)
    assert api.last_json() == {"workflow_id": "w-1", "metadata": None}
    assert repr(didit.NOT_GIVEN) == "NOT_GIVEN"
    assert not didit.NOT_GIVEN
    assert didit.NotGiven() is didit.NOT_GIVEN


def test_application_scope_fills_ids_and_needs_them() -> None:
    api = MockAPI().json(200, {"count": 0, "next": None, "previous": None, "results": []})
    client = api.client()
    client.cases.list()
    assert api.last.url.path == f"/v3/organization/{ORG_ID}/application/{APP_ID}/cases/"
    for options in ({"organization_id": None}, {"application_id": None}):
        unscoped = MockAPI()
        with pytest.raises(ConfigurationError, match="organization_id and application_id"):
            unscoped.client(**options).cases.list()
        assert unscoped.requests == []


def test_path_parameters_are_encoded_and_dot_segments_refused() -> None:
    api = MockAPI().json(200, {})
    client = api.client()
    client.sessions.retrieve_decision("a/b c?")
    assert api.last.url.raw_path == b"/v3/session/a%2Fb%20c%3F/decision/"
    for bad in ("", ".", ".."):
        with pytest.raises(ValueError, match="non-empty id"):
            client.sessions.retrieve_decision(bad)


def test_with_options_copies_and_shares_the_pool() -> None:
    api = MockAPI().json(200, {}).json(200, {})
    client = api.client()
    other = client.with_options(api_key="other-key", timeout=5, max_retries=0, organization_id="o2")
    assert other.api_key == "other-key"
    assert other.timeout == 5
    assert other.max_retries == 0
    assert other.organization_id == "o2"
    assert other.application_id == client.application_id
    assert other._client is client._client
    assert client.api_key == API_KEY
    other.sessions.retrieve_decision("s")
    assert api.last.headers["x-api-key"] == "other-key"
    assert client.copy(api_key=None).api_key is None
    other.close()  # does not close the shared pool
    client.sessions.retrieve_decision("s")


def test_timeout_reaches_httpx() -> None:
    seen: list[dict[str, float | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.extensions["timeout"])
        return httpx.Response(200, json={})

    client = Didit(
        api_key=API_KEY,
        timeout=12.5,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    client.sessions.retrieve_decision("s")
    client.sessions.retrieve_decision("s", timeout=3)
    client.sessions.retrieve_decision("s", timeout=httpx.Timeout(1.0, connect=2.0))
    assert seen[0]["read"] == 12.5
    assert seen[1]["read"] == 3
    assert seen[2]["connect"] == 2.0


def test_account_api_uses_its_own_base_url_and_token() -> None:
    api = MockAPI()
    api.json(200, {"access_token": "acct-token", "refresh_token": "r", "expires_in": 86400})
    api.json(200, [])
    client = api.client()
    login = client.account.login(email="dev@example.com", password="pw")
    request = api.last
    assert request.url.host == "apx.didit.me"
    assert request.url.path == "/auth/v2/programmatic/login/"
    assert "x-api-key" not in request.headers
    assert "authorization" not in request.headers
    with pytest.raises(ConfigurationError, match="account token"):
        client.account.organizations.list()
    authed = client.with_options(account_token=login.access_token)
    authed.account.organizations.list()
    assert api.last.headers["authorization"] == "Bearer acct-token"
    assert "x-api-key" not in api.last.headers


def test_account_methods_work_without_an_api_key() -> None:
    api = MockAPI().json(200, {"access_token": "t"})
    Didit(api_key=None, http_client=httpx.Client(transport=httpx.MockTransport(api))).account.login(
        email="a@example.com", password="p"
    )
    assert len(api.requests) == 1


def test_repr_never_shows_the_api_key() -> None:
    client = Didit(api_key="super-secret-key")
    assert "super-secret-key" not in repr(client)
    assert "***" in repr(client)
    assert "api_key=None" in repr(Didit(api_key=None))


def _closed(client: Didit | AsyncDidit) -> bool:
    return client._client.is_closed


def test_context_managers_close_owned_clients() -> None:
    with Didit(api_key=API_KEY) as client:
        assert not _closed(client)
    assert _closed(client)
    shared = httpx.Client()
    with Didit(api_key=API_KEY, http_client=shared):
        pass
    assert not shared.is_closed
    shared.close()

    async def run() -> AsyncDidit:
        async with AsyncDidit(api_key=API_KEY) as aclient:
            assert not _closed(aclient)
        return aclient

    aclient = asyncio.run(run())
    assert _closed(aclient)


def test_async_with_options() -> None:
    api = MockAPI().json(200, {})
    client = api.async_client()
    other = client.with_options(api_key="k2")

    async def run() -> None:
        await other.sessions.retrieve_decision("s")
        await other.close()

    asyncio.run(run())
    assert api.last.headers["x-api-key"] == "k2"
    assert other._client is client._client


def test_debug_logging_has_no_headers_or_bodies(caplog: pytest.LogCaptureFixture) -> None:
    api = MockAPI().add(httpx.Response(201, json=SESSION, headers={"x-request-id": "req_42"}))
    client = api.client()
    with caplog.at_level(logging.DEBUG, logger="didit"):
        client.sessions.create(workflow_id="w-1", vendor_data="private-user-ref")
    text = caplog.text
    assert "POST /v3/session/ -> 201" in text
    assert "req_42" in text
    assert API_KEY not in text
    assert "private-user-ref" not in text
    assert "w-1" not in text


def test_didit_log_environment_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    from didit._logging import logger, setup_logging

    monkeypatch.setenv("DIDIT_LOG", "debug")
    before = list(logger.handlers)
    try:
        setup_logging()
        setup_logging()  # idempotent
        added = [h for h in logger.handlers if h not in before]
        assert len(added) == 1
        assert logger.level == logging.DEBUG
    finally:
        for handler in logger.handlers[:]:
            if handler not in before:
                logger.removeHandler(handler)
        logger.setLevel(logging.NOTSET)
    monkeypatch.setenv("DIDIT_LOG", "off")
    setup_logging()
    assert logger.handlers == before
