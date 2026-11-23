"""Typed ``bank.*`` webhook events: every recorded delivery verifies and parses into its type."""

from __future__ import annotations

import json
import pathlib
from typing import Any

import pytest

from didit import webhooks
from didit.webhooks import (
    BankConnectionConsentExpiringEvent,
    BankConnectionCreatedEvent,
    BankConnectionDeletedEvent,
    BankConnectionHistoryCompleteEvent,
    BankConnectionRenewalRequiredEvent,
    BankConnectionRenewedEvent,
    BankConnectionRevokedEvent,
    BankConnectionUpdatedEvent,
    BankDataUpdatedEvent,
    BankLinkCancelledEvent,
    BankLinkCompletedEvent,
    BankLinkExpiredEvent,
    BankLinkFailedEvent,
    BankSyncCompletedEvent,
    BankSyncFailedEvent,
    BankSyncRecoveredEvent,
    UnknownEvent,
)

FIXTURE = pathlib.Path(__file__).resolve().parent / "fixtures" / "bank-deliveries.json"
DELIVERIES: list[dict[str, Any]] = json.loads(FIXTURE.read_text("utf-8"))
BY_NAME = {d["name"]: d for d in DELIVERIES}

EXPECTED: dict[str, type[webhooks.WebhookEventBase]] = {
    "bank_link_completed": BankLinkCompletedEvent,
    "bank_link_cancelled": BankLinkCancelledEvent,
    "bank_link_expired": BankLinkExpiredEvent,
    "bank_link_failed": BankLinkFailedEvent,
    "bank_connection_created": BankConnectionCreatedEvent,
    "bank_connection_updated": BankConnectionUpdatedEvent,
    "bank_connection_consent_expiring": BankConnectionConsentExpiringEvent,
    "bank_connection_renewal_required": BankConnectionRenewalRequiredEvent,
    "bank_connection_renewed": BankConnectionRenewedEvent,
    "bank_connection_revoked": BankConnectionRevokedEvent,
    "bank_connection_deleted": BankConnectionDeletedEvent,
    "bank_connection_history_complete": BankConnectionHistoryCompleteEvent,
    "bank_data_updated": BankDataUpdatedEvent,
    "bank_sync_completed": BankSyncCompletedEvent,
    "bank_sync_failed": BankSyncFailedEvent,
    "bank_sync_recovered": BankSyncRecoveredEvent,
}


def _receive(name: str, monkeypatch: pytest.MonkeyPatch) -> Any:
    delivery = BY_NAME[name]
    monkeypatch.setattr("didit.webhooks._verify.time.time", lambda: float(delivery["now"]))
    return webhooks.verify(
        delivery["body"].encode(), delivery["headers"], secret=delivery["secret"]
    )


def test_the_fixture_has_every_bank_event() -> None:
    assert set(EXPECTED) == set(BY_NAME)
    assert len(EXPECTED) == 16


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_a_signed_delivery_verifies_and_parses_into_its_type(
    name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    event = _receive(name, monkeypatch)
    body = json.loads(BY_NAME[name]["body"])
    assert type(event) is EXPECTED[name]
    assert event.webhook_type == body["webhook_type"]
    assert event.body_authenticated
    assert event.model_extra == {} or event.model_extra is None


def test_bank_link_events_carry_their_fields_under_data(monkeypatch: pytest.MonkeyPatch) -> None:
    done = _receive("bank_link_completed", monkeypatch)
    assert done.data is not None
    assert done.data.status == "completed"
    assert done.data.connection_id == "cccccccc-0000-4000-8000-000000000001"
    assert done.data.check_id == "dddddddd-0000-4000-8000-000000000001"
    assert done.data.error_code is None
    failed = _receive("bank_link_failed", monkeypatch)
    assert failed.data is not None
    assert failed.data.status == "failed"
    assert failed.data.error_code is not None


def test_connection_events_carry_their_fields_next_to_the_envelope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    renewed = _receive("bank_connection_renewed", monkeypatch)
    assert renewed.consent_version == 2
    assert renewed.link_id == "bbbbbbbb-0000-4000-8000-000000000005"
    revoked = _receive("bank_connection_revoked", monkeypatch)
    assert revoked.ended_by == "bank"
    assert revoked.status_reason == "revoked_by_bank"
    assert revoked.retain_until == "2027-02-20T09:00:00Z"
    deleted = _receive("bank_connection_deleted", monkeypatch)
    assert deleted.erasure_status == "erased"
    assert deleted.reason == "deleted_by_customer"
    assert deleted.erased_at == "2026-11-22T09:00:00Z"
    expiring = _receive("bank_connection_consent_expiring", monkeypatch)
    assert isinstance(expiring.days_left, int)
    assert expiring.days_left in (14, 7, 1)


def test_data_and_sync_events(monkeypatch: pytest.MonkeyPatch) -> None:
    updated = _receive("bank_data_updated", monkeypatch)
    assert updated.trigger == "scheduled"
    assert updated.balances_changed is True
    assert updated.accounts is not None
    assert [a.model_dump() for a in updated.accounts] == [
        {
            "account_id": "ffffffff-0000-4000-8000-000000000001",
            "added": 3,
            "modified": 1,
            "removed": 0,
        }
    ]
    completed = _receive("bank_sync_completed", monkeypatch)
    assert completed.outcome == "partial"
    assert completed.changed is True
    failed = _receive("bank_sync_failed", monkeypatch)
    assert failed.error_code == "bank_unavailable"
    assert failed.failing_since == "2026-11-21T09:00:00Z"
    recovered = _receive("bank_sync_recovered", monkeypatch)
    assert recovered.sync_id == "eeeeeeee-0000-4000-8000-000000000002"


def test_an_unknown_bank_event_falls_back_to_unknown_event() -> None:
    payload = {
        "event_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
        "webhook_type": "bank.something.new",
        "timestamp": 1760702400,
        "connection_id": "cccccccc-0000-4000-8000-000000000001",
    }
    event = webhooks.parse_event(payload)
    assert isinstance(event, UnknownEvent)
    assert event.webhook_type == "bank.something.new"
    assert event.payload == payload


def test_a_tampered_bank_delivery_is_still_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    delivery = BY_NAME["bank_sync_failed"]
    monkeypatch.setattr("didit.webhooks._verify.time.time", lambda: float(delivery["now"]))
    tampered = delivery["body"].replace("bank_unavailable", "other_error").encode()
    with pytest.raises(webhooks.WebhookVerificationError) as info:
        webhooks.verify(tampered, delivery["headers"], secret=delivery["secret"])
    assert info.value.reason == "invalid_signature"
