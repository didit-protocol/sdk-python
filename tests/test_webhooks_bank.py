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

CONNECTION_ID = "cccccccc-0000-4000-8000-000000000001"

EXPECTED: dict[str, type[webhooks.WebhookEventBase]] = {
    "bank.link.completed": BankLinkCompletedEvent,
    "bank.link.cancelled": BankLinkCancelledEvent,
    "bank.link.expired": BankLinkExpiredEvent,
    "bank.link.failed": BankLinkFailedEvent,
    "bank.connection.created": BankConnectionCreatedEvent,
    "bank.connection.updated": BankConnectionUpdatedEvent,
    "bank.connection.consent_expiring": BankConnectionConsentExpiringEvent,
    "bank.connection.renewal_required": BankConnectionRenewalRequiredEvent,
    "bank.connection.renewed": BankConnectionRenewedEvent,
    "bank.connection.revoked": BankConnectionRevokedEvent,
    "bank.connection.deleted": BankConnectionDeletedEvent,
    "bank.connection.history_complete": BankConnectionHistoryCompleteEvent,
    "bank.data.updated": BankDataUpdatedEvent,
    "bank.sync.completed": BankSyncCompletedEvent,
    "bank.sync.failed": BankSyncFailedEvent,
    "bank.sync.recovered": BankSyncRecoveredEvent,
}


def _receive(name: str, monkeypatch: pytest.MonkeyPatch) -> Any:
    delivery = BY_NAME[name]
    monkeypatch.setattr("didit.webhooks._verify.time.time", lambda: float(delivery["now"]))
    return webhooks.verify(
        delivery["body"].encode(), delivery["headers"], secret=delivery["secret"]
    )


def test_the_fixture_has_every_bank_event() -> None:
    assert set(EXPECTED) == {json.loads(d["body"])["webhook_type"] for d in DELIVERIES}
    assert len(EXPECTED) == 16


@pytest.mark.parametrize("name", sorted(BY_NAME))
def test_a_signed_delivery_verifies_and_parses_into_its_type(
    name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    event = _receive(name, monkeypatch)
    body = json.loads(BY_NAME[name]["body"])
    assert type(event) is EXPECTED[body["webhook_type"]]
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


@pytest.mark.parametrize(
    ("name", "has_target", "target", "result"),
    [
        ("bank_link_cancelled", True, CONNECTION_ID, None),
        ("bank_link_completed", True, CONNECTION_ID, CONNECTION_ID),
        ("bank_link_failed", False, None, CONNECTION_ID),
        ("bank_link_expired", False, None, None),
        ("bank_link_completed_without_renewal", True, None, CONNECTION_ID),
    ],
)
def test_renewal_target_and_result(
    name: str,
    has_target: bool,
    target: str | None,
    result: str | None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = _receive(name, monkeypatch).data
    assert data.renews_connection_id == target
    assert data.connection_id == result
    assert ("renews_connection_id" in data.model_fields_set) == has_target


def test_connection_update_shapes(monkeypatch: pytest.MonkeyPatch) -> None:
    pending = _receive("bank_connection_updated", monkeypatch)
    assert pending.revocation_status == "pending"
    assert pending.status_reason is None
    assert pending.ends_at is None
    assert pending.model_fields_set.isdisjoint({"status_reason", "ends_at"})

    paused = _receive("bank_connection_updated_insufficient_balance", monkeypatch)
    assert paused.revocation_status is None
    assert "revocation_status" not in paused.model_fields_set
    assert paused.status_reason == "insufficient_balance"
    assert paused.ends_at == "2026-12-01T00:00:00Z"

    active = _receive("bank_connection_updated_no_end", monkeypatch)
    assert {"status_reason", "ends_at"} <= active.model_fields_set
    assert active.status_reason is None
    assert active.ends_at is None


def test_system_revocation_for_unpaid_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    event = _receive("bank_connection_revoked_unpaid", monkeypatch)
    assert event.ended_by == "system"
    assert event.status_reason == "unpaid"


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
