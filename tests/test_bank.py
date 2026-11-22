"""Bank data through the public client: the contract's amount, id and error rules
(docs/DESIGN.md section 16)."""

from __future__ import annotations

from typing import Any

import httpx
import pydantic
import pytest

import didit
from didit.types.components.bank_balance import BankBalance
from didit.types.components.bank_connection import BankConnection
from didit.types.components.bank_link import BankLink
from tests.mock_api import API_KEY, MockAPI

CONNECTION = "c0a80104-1111-4111-8111-111111111111"


def _balance(amount: Any) -> dict[str, Any]:
    return {
        "type": "booked",
        "iso_type": "CLBD",
        "amount": amount,
        "currency": "EUR",
        "reference_date": "2026-11-20",
        "last_change_at": "2026-11-20T22:10:00Z",
        "credit_limit_included": False,
    }


def test_amounts_are_decimal_strings_never_floats() -> None:
    assert BankBalance.model_validate(_balance("18250.34")).amount == "18250.34"
    # The type is ``str``: a JSON number is refused by strict validation, so a generated
    # client can never read an amount as a float.
    with pytest.raises(pydantic.ValidationError):
        BankBalance.model_validate(_balance(18250.34))


def test_balances_reach_the_caller_as_strings() -> None:
    api = MockAPI().json(200, {"account_id": CONNECTION, "balances": [_balance("17990.34")]})
    balances = api.client().bank.get_balances(CONNECTION)
    assert balances.balances[0].amount == "17990.34"
    assert isinstance(balances.balances[0].amount, str)


def test_bank_data_permission_error_carries_the_code_and_next_action() -> None:
    body = {
        "code": "bank_data_access_denied",
        "message": "The API key needs the bank-data permission.",
        "request_id": "req_bank_403",
        "field": None,
        "next_action": "Create an API key with the bank-data permission.",
        "retry_after": None,
    }
    api = MockAPI().json(403, body, **{"x-request-id": "req_bank_403"})
    with pytest.raises(didit.PermissionDeniedError) as info:
        api.client().bank.get_connection(CONNECTION)
    error = info.value
    assert error.status == 403
    assert error.request_id == "req_bank_403"
    assert isinstance(error.body, dict)
    assert error.body["code"] == "bank_data_access_denied"
    assert error.body["next_action"].startswith("Create an API key")


def test_refresh_limit_reached_exposes_retry_after() -> None:
    body = {
        "code": "refresh_limit_reached",
        "message": "The bank's daily limit is used up.",
        "request_id": "req_bank_429",
        "retry_after": 3600,
        "sync": {"live_syncs_left_today": 0},
    }
    api = MockAPI().json(429, body, **{"retry-after": "3600"})
    with pytest.raises(didit.RateLimitError) as info:
        api.client(max_retries=0).bank.refresh_connection(CONNECTION)
    error = info.value
    # The header is exposed the way every other rate limit exposes it; the body repeats
    # the wait in seconds.
    assert error.headers["retry-after"] == "3600"
    assert isinstance(error.body, dict)
    assert error.body["retry_after"] == 3600
    assert error.body["code"] == "refresh_limit_reached"


def test_a_deleted_connection_reads_as_its_minimal_record() -> None:
    api = MockAPI().json(
        200,
        {
            "id": CONNECTION,
            "environment": "live",
            "status": "deleted",
            "status_reason": "revoked_by_customer",
            "created_at": "2026-11-01T09:00:00Z",
            "erasure": {"status": "erased", "requested_at": "2026-11-02T09:00:00Z"},
        },
    )
    connection = api.client().bank.get_connection(CONNECTION)
    assert isinstance(connection, BankConnection)
    assert connection.status == "deleted"
    assert connection.erasure is not None
    assert connection.erasure.status == "erased"
    # Nothing else survives the deletion, and reading it never raises.
    assert connection.consent is None
    assert connection.accounts is None


def test_ids_and_tokens_are_opaque_and_never_validated() -> None:
    api = MockAPI().json(
        200,
        {
            "id": "link_not_a_uuid",
            "url": "https://verify.didit.me/bank/link/opaque-url-token",
            "client_token": "opaque.client.token",
            "status": "pending",
            "mode": "connect",
            "access": "one_time",
            "expires_at": "2026-11-22T10:00:00Z",
            "created_at": "2026-11-22T09:00:00Z",
        },
    )
    link = api.client().bank.get_link("not-a-uuid-either")
    assert api.last.url.path == "/v3/bank/links/not-a-uuid-either/"
    assert isinstance(link, BankLink)
    assert link.client_token == "opaque.client.token"
    assert link.url is not None
    assert link.url.endswith("opaque-url-token")


def test_cursor_lists_send_cursor_and_limit_and_return_next_cursor() -> None:
    api = MockAPI().json(200, {"items": [], "next_cursor": "next-page"})
    page = api.client().bank.list_connections(cursor="first-page", limit=50)
    assert dict(api.last.url.params) == {"cursor": "first-page", "limit": "50"}
    assert page.next_cursor == "next-page"


def test_the_change_feed_sends_the_stored_cursor_and_page_token() -> None:
    api = MockAPI().json(
        200,
        {
            "connection_id": CONNECTION,
            "added": [{"account_id": CONNECTION, "transaction_id": "t-1"}],
            "modified": [],
            "removed": [],
            "has_more": True,
            "next_cursor": "feed-cursor",
            "next_page_token": "page-2",
        },
    )
    changes = api.client().bank.sync_transactions(
        CONNECTION, cursor="stored-cursor", page_token="page-1", limit=100
    )
    assert dict(api.last.url.params) == {
        "cursor": "stored-cursor",
        "page_token": "page-1",
        "limit": "100",
    }
    assert changes.has_more is True
    assert changes.next_page_token == "page-2"


def test_a_full_access_key_is_refused_with_the_documented_code() -> None:
    api = MockAPI().add(
        httpx.Response(
            403,
            json={"code": "bank_data_access_denied", "message": "No bank-data permission."},
            headers={"x-request-id": "req_full_access"},
        )
    )
    client = didit.Didit(
        api_key=API_KEY, http_client=httpx.Client(transport=httpx.MockTransport(api))
    )
    with pytest.raises(didit.PermissionDeniedError) as info:
        client.bank.list_accounts(CONNECTION)
    assert info.value.request_id == "req_full_access"
