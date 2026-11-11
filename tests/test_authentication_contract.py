"""Contract test (DESIGN 11) for the hand-written Authentication module (DESIGN 10).

``openapi/authentication.json`` is synced from docs.didit.me like the other documents,
but nothing is generated from it. Every ``server: true`` operation in it (its
``x-didit-sdk`` method, or each of its variants) must be a method of both clients, and
each one is sent to a stub issuer (tests/authentication_helpers.py) to check its HTTP
method, path, content type and grant against the document. A spec sync that adds,
removes or renames an Authentication operation fails here until the module follows.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import pathlib
import re
import urllib.parse
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from didit.authentication import AsyncAuthentication, Authentication
from tests.authentication_helpers import (
    ACCESS_TOKEN,
    CODE,
    CODE_VERIFIER,
    ISSUER,
    REDIRECT_URI,
    REFRESH_TOKEN,
    STEP_UP_ID,
    FakeClock,
    FakeIssuer,
    SigningKey,
    access_claims,
)
from tests.test_authentication import (
    AGENT_APPROVAL_OPTIONS,
    AGENT_CHALLENGE,
    AGENT_CONSENT_APPROVED,
    SESSION_RESPONSE,
    STEP_UP_REQUIRED,
    TOKEN_RESPONSE,
    configure,
)

DOCUMENT = json.loads(
    (pathlib.Path(__file__).resolve().parents[1] / "openapi" / "authentication.json").read_text(
        "utf-8"
    )
)
HTTP_METHODS = ("get", "put", "post", "delete", "patch")
# Public methods that are not API operations.
HELPERS = {"close", "create_nonce", "create_pkce", "create_state", "from_publishable_key"}
# Token verification fetches the discovery document and the keys itself (DESIGN 10):
# these operations have no method of their own, the verify methods stand for them.
FETCHED_BY_VERIFICATION = {"get_openid_configuration", "get_jwks"}
VERIFIERS = {"verify_access_token", "verify_id_token"}
# What the stub issuer answers per operation (the body of its first 2xx response).
REPLIES: dict[str, object] = {
    "exchange_code": TOKEN_RESPONSE,
    "refresh": TOKEN_RESPONSE,
    "get_session": SESSION_RESPONSE,
    "create_step_up": STEP_UP_REQUIRED,
    "retrieve_step_up": STEP_UP_REQUIRED,
    "submit_agent_consent": AGENT_CONSENT_APPROVED,
    "create_agent_approval_options": AGENT_APPROVAL_OPTIONS,
}


def _schema(op: dict[str, Any]) -> dict[str, Any]:
    """The request body schema of ``op`` (its first media type), references followed."""
    for media in ((op.get("requestBody") or {}).get("content") or {}).values():
        schema: dict[str, Any] = media.get("schema") or {}
        while "$ref" in schema:
            target: Any = DOCUMENT
            for part in schema["$ref"].removeprefix("#/").split("/"):
                target = target[part]
            schema = target
        return schema
    return {}


def _operations() -> dict[str, dict[str, Any]]:
    """Document method -> HTTP method, path pattern, request content types and grant."""
    found: dict[str, dict[str, Any]] = {}
    for path, item in DOCUMENT["paths"].items():
        for http_method in HTTP_METHODS:
            op = item.get(http_method)
            if op is None:
                continue
            naming = op["x-didit-sdk"]
            assert naming["resource"] == "authentication", (http_method, path)
            if not naming["server"]:
                continue
            content = sorted((op.get("requestBody") or {}).get("content") or {})
            discriminator = (_schema(op).get("discriminator") or {}).get("propertyName")
            successes = sorted(s for s in op["responses"] if s.startswith("2"))
            for variant in naming.get("variants") or [{"method": naming["method"]}]:
                assert variant["method"] not in found, variant
                found[variant["method"]] = {
                    "http": http_method.upper(),
                    "path": re.compile("^" + re.sub(r"\{[^}]+\}", "[^/]+", path) + "$"),
                    "raw_path": path,
                    "content": content,
                    "grant": (discriminator, variant.get("discriminator")),
                    "status": int(successes[0]),
                }
    return found


OPERATIONS = _operations()


def _hidden() -> set[str]:
    return {
        op["x-didit-sdk"]["method"]
        for item in DOCUMENT["paths"].values()
        for http_method in HTTP_METHODS
        if (op := item.get(http_method)) is not None and not op["x-didit-sdk"]["server"]
    }


def _public(cls: type) -> set[str]:
    return {n for n, value in inspect.getmembers(cls) if not n.startswith("_") and callable(value)}


@pytest.mark.parametrize("cls", [Authentication, AsyncAuthentication])
def test_document_operations_equal_module_methods(cls: type) -> None:
    documented = set(OPERATIONS)
    expected = documented - FETCHED_BY_VERIFICATION
    if documented >= FETCHED_BY_VERIFICATION:
        expected |= VERIFIERS
    methods = _public(cls) - HELPERS
    assert not expected - methods, f"operations without a method: {sorted(expected - methods)}"
    assert not methods - expected, f"methods without an operation: {sorted(methods - expected)}"
    # Device and end-user token operations are never in a server SDK (DESIGN 4).
    assert _hidden()
    assert not _hidden() & _public(cls)


def _calls(key: SigningKey) -> dict[str, Callable[[Any], Any]]:
    """How the module performs each document operation."""
    token = key.sign(access_claims())
    return {
        "get_openid_configuration": lambda auth: auth.verify_access_token(token),
        "get_jwks": lambda auth: auth.verify_access_token(token),
        "exchange_code": lambda auth: auth.exchange_code(
            CODE, code_verifier=CODE_VERIFIER, redirect_uri=REDIRECT_URI
        ),
        "refresh": lambda auth: auth.refresh(REFRESH_TOKEN),
        "get_session": lambda auth: auth.get_session(ACCESS_TOKEN),
        "revoke_session": lambda auth: auth.revoke_session(ACCESS_TOKEN),
        "create_step_up": lambda auth: auth.create_step_up(
            ACCESS_TOKEN, action="payout", amount="1500.00", currency="EUR", return_to=REDIRECT_URI
        ),
        "retrieve_step_up": lambda auth: auth.retrieve_step_up(ACCESS_TOKEN, STEP_UP_ID),
        "submit_agent_consent": lambda auth: auth.submit_agent_consent(
            ACCESS_TOKEN, challenge=AGENT_CHALLENGE, decision="approve"
        ),
        "create_agent_approval_options": lambda auth: auth.create_agent_approval_options(
            ACCESS_TOKEN, challenge=AGENT_CHALLENGE
        ),
    }


def _body(request: httpx.Request) -> dict[str, Any]:
    media = request.headers.get("content-type", "").split(";")[0]
    if media == "application/x-www-form-urlencoded":
        return dict(urllib.parse.parse_qsl(request.content.decode("ascii")))
    body: dict[str, Any] = json.loads(request.content)
    return body


def _sent(issuer: FakeIssuer, method: str) -> httpx.Request:
    """The request that performed the document operation ``method``."""
    operation = OPERATIONS[method]
    matching = [
        r
        for r in issuer.requests
        if r.method == operation["http"] and operation["path"].match(r.url.path)
    ]
    assert matching, f"{method}: no {operation['http']} {operation['raw_path']} was sent"
    request = matching[-1]
    assert str(request.url).startswith(f"{ISSUER}/")
    if operation["content"]:
        assert request.headers["content-type"].split(";")[0] in operation["content"], method
    prop, value = operation["grant"]
    if prop is not None:
        assert _body(request)[prop] == value, method
    return request


@pytest.fixture
def key() -> SigningKey:
    return SigningKey.generate("k_synthetic_contract")


@pytest.fixture
def issuer(key: SigningKey) -> FakeIssuer:
    issuer = FakeIssuer([key])
    for method, operation in OPERATIONS.items():
        if method not in FETCHED_BY_VERIFICATION:
            issuer.reply(
                operation["http"],
                operation["raw_path"].replace("{step_up_id}", STEP_UP_ID),
                operation["status"],
                REPLIES.get(method),
            )
    return issuer


@pytest.mark.parametrize("method", sorted(OPERATIONS))
def test_each_operation_is_sent_as_documented(
    method: str, issuer: FakeIssuer, key: SigningKey
) -> None:
    with issuer.client() as http:
        auth = configure(Authentication(ISSUER, http_client=http), FakeClock())
        _calls(key)[method](auth)
    _sent(issuer, method)


@pytest.mark.parametrize("method", sorted(OPERATIONS))
def test_each_operation_is_sent_as_documented_async(
    method: str, issuer: FakeIssuer, key: SigningKey
) -> None:
    async def run() -> None:
        async with issuer.async_client() as http:
            auth = configure(AsyncAuthentication(ISSUER, http_client=http), FakeClock())
            await _calls(key)[method](auth)

    asyncio.run(run())
    _sent(issuer, method)
