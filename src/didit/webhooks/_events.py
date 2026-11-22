"""Typed webhook events (docs/DESIGN.md section 9.4)."""

from __future__ import annotations

import datetime as _dt
from typing import TYPE_CHECKING, Any, Literal, Union

from pydantic import Field, PrivateAttr

from .._models import BaseModel, validate_response

if TYPE_CHECKING:
    from ..types.components.session_decision import SessionDecision

__all__ = [
    "ActivityCreatedEvent",
    "BankConnectionConsentExpiringData",
    "BankConnectionConsentExpiringEvent",
    "BankConnectionCreatedEvent",
    "BankConnectionDeletedData",
    "BankConnectionDeletedEvent",
    "BankConnectionEventData",
    "BankConnectionHistoryCompleteEvent",
    "BankConnectionRenewalRequiredEvent",
    "BankConnectionRenewedEvent",
    "BankConnectionRevokedData",
    "BankConnectionRevokedEvent",
    "BankConnectionUpdatedEvent",
    "BankDataUpdatedData",
    "BankDataUpdatedEvent",
    "BankLinkCancelledEvent",
    "BankLinkCompletedEvent",
    "BankLinkEventData",
    "BankLinkExpiredEvent",
    "BankLinkFailedEvent",
    "BankSyncCompletedData",
    "BankSyncCompletedEvent",
    "BankSyncFailedData",
    "BankSyncFailedEvent",
    "BankSyncRecoveredData",
    "BankSyncRecoveredEvent",
    "BusinessDataUpdatedEvent",
    "BusinessStatusUpdatedEvent",
    "KybRegistrySearchResolvedEvent",
    "SessionDataUpdatedEvent",
    "SessionStatusUpdatedEvent",
    "TransactionCreatedEvent",
    "TransactionStatusUpdatedEvent",
    "TravelRuleStatusUpdatedEvent",
    "UnknownEvent",
    "UserDataUpdatedEvent",
    "UserStatusUpdatedEvent",
    "WebhookEvent",
    "WebhookEventBase",
    "WorkflowComplianceChangedEvent",
    "parse_event",
]

VerifiedBy = Literal["signature", "signature_v2", "signature_simple", "none"]


class WebhookEventBase(BaseModel):
    """Fields on every event. Unknown fields are kept (``model_extra``)."""

    event_id: str | None = None
    webhook_type: str | None = None
    timestamp: int | None = None
    created_at: int | None = None
    application_id: str | None = None
    environment: Literal["live", "sandbox"] | str | None = None

    _verified_by: VerifiedBy = PrivateAttr(default="none")

    @property
    def verified_by(self) -> VerifiedBy:
        """Which header authenticated the delivery: ``signature`` (``X-Signature``),
        ``signature_v2`` (``X-Signature-V2``) or ``signature_simple``."""
        return self._verified_by

    @property
    def body_authenticated(self) -> bool:
        """``False`` when only the deprecated ``X-Signature-Simple`` matched: it
        signs the envelope, not the body, so re-fetch the record from the API
        before acting on anything else in this event."""
        return self._verified_by in ("signature", "signature_v2")


if TYPE_CHECKING:
    LazySessionDecision = SessionDecision
else:

    class LazySessionDecision:
        """Stands for ``SessionDecision``, imported when a model is first built.

        The decision model pulls in the whole decision component graph (dozens
        of generated modules, and more with every spec sync), so ``import didit``
        does not load it. Pydantic asks for the schema when the event model is
        first validated or its schema is generated, whichever entry point is used.
        """

        @staticmethod
        def __didit_resolve__() -> type[BaseModel]:
            from ..types.components.session_decision import SessionDecision

            return SessionDecision

        @classmethod
        def __get_pydantic_core_schema__(cls, source: Any, handler: Any) -> Any:
            return handler(cls.__didit_resolve__())


class _SessionEvent(WebhookEventBase):
    session_id: str | None = None
    business_session_id: str | None = None
    session_kind: Literal["user", "business"] | str | None = None
    status: str | None = None
    workflow_id: str | None = None
    workflow_version: int | None = None
    vendor_data: str | None = None
    metadata: object = None
    decision: LazySessionDecision | None = None
    resubmit_info: object = None


class SessionStatusUpdatedEvent(_SessionEvent):
    """``status.updated``: a verification session changed status."""

    webhook_type: Literal["status.updated"] = "status.updated"  # pyright: ignore[reportIncompatibleVariableOverride]


class SessionDataUpdatedEvent(_SessionEvent):
    """``data.updated``: the data of a verification session changed."""

    webhook_type: Literal["data.updated"] = "data.updated"  # pyright: ignore[reportIncompatibleVariableOverride]


class _UserEvent(WebhookEventBase):
    vendor_user_id: str | None = None
    vendor_data: str | None = None
    status: str | None = None


class UserStatusUpdatedEvent(_UserEvent):
    """``user.status.updated``."""

    webhook_type: Literal["user.status.updated"] = "user.status.updated"  # pyright: ignore[reportIncompatibleVariableOverride]


class UserDataUpdatedEvent(_UserEvent):
    """``user.data.updated``."""

    webhook_type: Literal["user.data.updated"] = "user.data.updated"  # pyright: ignore[reportIncompatibleVariableOverride]


class _BusinessEvent(WebhookEventBase):
    vendor_business_id: str | None = None
    vendor_data: str | None = None
    status: str | None = None


class BusinessStatusUpdatedEvent(_BusinessEvent):
    """``business.status.updated``."""

    webhook_type: Literal["business.status.updated"] = "business.status.updated"  # pyright: ignore[reportIncompatibleVariableOverride]


class BusinessDataUpdatedEvent(_BusinessEvent):
    """``business.data.updated``."""

    webhook_type: Literal["business.data.updated"] = "business.data.updated"  # pyright: ignore[reportIncompatibleVariableOverride]


class ActivityCreatedEvent(WebhookEventBase):
    """``activity.created``."""

    webhook_type: Literal["activity.created"] = "activity.created"  # pyright: ignore[reportIncompatibleVariableOverride]


class _TransactionEvent(WebhookEventBase):
    transaction_id: str | None = None
    txn_id: str | None = None
    status: str | None = None
    score: float | None = None
    severity: str | None = None
    amount: str | None = None
    """A decimal string, as the API sends it."""
    currency: str | None = None
    direction: str | None = None
    action_required: object = None


class TransactionCreatedEvent(_TransactionEvent):
    """``transaction.created``."""

    webhook_type: Literal["transaction.created"] = "transaction.created"  # pyright: ignore[reportIncompatibleVariableOverride]


class TransactionStatusUpdatedEvent(_TransactionEvent):
    """``transaction.status.updated``."""

    webhook_type: Literal["transaction.status.updated"] = "transaction.status.updated"  # pyright: ignore[reportIncompatibleVariableOverride]


class TravelRuleStatusUpdatedEvent(WebhookEventBase):
    """``travel_rule.status.updated``."""

    webhook_type: Literal["travel_rule.status.updated"] = "travel_rule.status.updated"  # pyright: ignore[reportIncompatibleVariableOverride]
    transaction_id: str | None = None
    txn_id: str | None = None
    travel_rule_status: str | None = None
    rail: str | None = None
    direction: str | None = None


class WorkflowComplianceChangedEvent(WebhookEventBase):
    """``workflow.compliance_changed``."""

    webhook_type: Literal["workflow.compliance_changed"] = "workflow.compliance_changed"  # pyright: ignore[reportIncompatibleVariableOverride]
    workflow_id: str | None = None


class KybRegistrySearchResolvedEvent(WebhookEventBase):
    """``kyb.registry_search.resolved``."""

    webhook_type: Literal["kyb.registry_search.resolved"] = "kyb.registry_search.resolved"  # pyright: ignore[reportIncompatibleVariableOverride]


class BankLinkEventData(BaseModel):
    """``data`` of a ``bank.link.*`` event: the link, its status and what it produced."""

    link_id: str | None = None
    """The link id."""

    status: Literal["completed", "cancelled", "expired", "failed"] | str | None = None
    """How the link ended."""

    connection_id: str | None = None
    """The connection the link created or renewed; ``None`` when there is none."""

    check_id: str | None = None
    """The ownership result, when one was asked for."""

    error_code: str | None = None
    """With ``bank.link.failed``: why, for example ``duplicate_conflict``."""


class BankConnectionEventData(BaseModel):
    """``data`` of the connection events that carry a status: ``created``, ``updated``,
    ``renewal_required``, ``renewed`` and ``history_complete``."""

    connection_id: str | None = None
    """The connection id."""

    status: (
        Literal["pending", "active", "renewal_required", "paused", "revoked", "deleted", "failed"]
        | str
        | None
    ) = None
    """The connection status after the change."""

    status_reason: str | None = None
    """Why the status is what it is, when the API says."""


class BankConnectionConsentExpiringData(BaseModel):
    """``data`` of ``bank.connection.consent_expiring``."""

    connection_id: str | None = None
    """The connection id."""

    days_left: int | None = None
    """14, 7 or 1."""

    expires_at: _dt.datetime | None = None
    """When the consent ends."""

    renew_url: str | None = None
    """A ready renew link, only when your application turned automatic renew links on.
    It is a credential: never log it."""


class BankConnectionRevokedData(BaseModel):
    """``data`` of ``bank.connection.revoked``."""

    connection_id: str | None = None
    """The connection id."""

    status: Literal["revocation_pending", "revoked", "revocation_failed"] | str | None = None
    """The consent status."""

    ended_by: Literal["end_user", "bank", "customer", "unknown"] | str | None = None
    """Who ended access."""


class BankConnectionDeletedData(BaseModel):
    """``data`` of ``bank.connection.deleted``."""

    connection_id: str | None = None
    """The connection id."""

    erasure_status: str | None = None
    """``erased``."""


class BankDataUpdatedData(BaseModel):
    """``data`` of ``bank.data.updated``: what a sync stored. Read the change feed
    (``client.bank.sync_transactions``) for the rows; nothing is pushed."""

    connection_id: str | None = None
    """The connection id."""

    sync_id: str | None = None
    """The sync that stored the changes."""

    account_ids: list[str] | None = None
    """Accounts whose data changed."""

    added: int | None = None
    """Transactions added."""

    modified: int | None = None
    """Transactions modified."""

    removed: int | None = None
    """Transactions removed."""

    balances_changed: bool | None = None
    """Whether a balance changed too."""


class BankSyncCompletedData(BaseModel):
    """``data`` of ``bank.sync.completed``. Off by default: ``bank.data.updated`` is
    the usual signal."""

    connection_id: str | None = None
    """The connection id."""

    sync_id: str | None = None
    """The sync that finished."""

    trigger: Literal["scheduled", "requested", "initial"] | str | None = None
    """What started the sync."""

    outcome: Literal["succeeded", "partial", "failed"] | str | None = None
    """How it ended."""

    changed: bool | None = None
    """Whether it stored anything."""


class BankSyncFailedData(BaseModel):
    """``data`` of ``bank.sync.failed``."""

    connection_id: str | None = None
    """The connection id."""

    sync_id: str | None = None
    """The latest failed sync."""

    error_code: str | None = None
    """Why it failed."""


class BankSyncRecoveredData(BaseModel):
    """``data`` of ``bank.sync.recovered``."""

    connection_id: str | None = None
    """The connection id."""

    sync_id: str | None = None
    """The sync that succeeded."""


class _BankEvent(WebhookEventBase):
    """A ``bank.*`` event. The payload is ids and statuses only, under ``data``:
    fetch the connection, the link or the account from the API to read it."""


class BankLinkCompletedEvent(_BankEvent):
    """``bank.link.completed``: the person finished a Bank Link."""

    webhook_type: Literal["bank.link.completed"] = "bank.link.completed"  # pyright: ignore[reportIncompatibleVariableOverride]
    data: BankLinkEventData | None = None


class BankLinkCancelledEvent(_BankEvent):
    """``bank.link.cancelled``: the link was cancelled before the person finished."""

    webhook_type: Literal["bank.link.cancelled"] = "bank.link.cancelled"  # pyright: ignore[reportIncompatibleVariableOverride]
    data: BankLinkEventData | None = None


class BankLinkExpiredEvent(_BankEvent):
    """``bank.link.expired``: the link was not finished before it expired."""

    webhook_type: Literal["bank.link.expired"] = "bank.link.expired"  # pyright: ignore[reportIncompatibleVariableOverride]
    data: BankLinkEventData | None = None


class BankLinkFailedEvent(_BankEvent):
    """``bank.link.failed``: the link ended in failure; ``data.error_code`` says why."""

    webhook_type: Literal["bank.link.failed"] = "bank.link.failed"  # pyright: ignore[reportIncompatibleVariableOverride]
    data: BankLinkEventData | None = None


class BankConnectionCreatedEvent(_BankEvent):
    """``bank.connection.created``: the first sync finished and the accounts are
    readable. Read the connection, then its accounts."""

    webhook_type: Literal["bank.connection.created"] = "bank.connection.created"  # pyright: ignore[reportIncompatibleVariableOverride]
    data: BankConnectionEventData | None = None


class BankConnectionUpdatedEvent(_BankEvent):
    """``bank.connection.updated``: status, consent or sync state changed."""

    webhook_type: Literal["bank.connection.updated"] = "bank.connection.updated"  # pyright: ignore[reportIncompatibleVariableOverride]
    data: BankConnectionEventData | None = None


class BankConnectionConsentExpiringEvent(_BankEvent):
    """``bank.connection.consent_expiring``: 14, 7 or 1 day before the consent ends."""

    webhook_type: Literal["bank.connection.consent_expiring"] = "bank.connection.consent_expiring"  # pyright: ignore[reportIncompatibleVariableOverride]
    data: BankConnectionConsentExpiringData | None = None


class BankConnectionRenewalRequiredEvent(_BankEvent):
    """``bank.connection.renewal_required``: the consent ended or the bank asks the
    person back. Create a renew link with ``client.bank.create_link``."""

    webhook_type: Literal["bank.connection.renewal_required"] = "bank.connection.renewal_required"  # pyright: ignore[reportIncompatibleVariableOverride]
    data: BankConnectionEventData | None = None


class BankConnectionRenewedEvent(_BankEvent):
    """``bank.connection.renewed``: a renew link completed."""

    webhook_type: Literal["bank.connection.renewed"] = "bank.connection.renewed"  # pyright: ignore[reportIncompatibleVariableOverride]
    data: BankConnectionEventData | None = None


class BankConnectionRevokedEvent(_BankEvent):
    """``bank.connection.revoked``: access ended; ``data.ended_by`` says who ended it."""

    webhook_type: Literal["bank.connection.revoked"] = "bank.connection.revoked"  # pyright: ignore[reportIncompatibleVariableOverride]
    data: BankConnectionRevokedData | None = None


class BankConnectionDeletedEvent(_BankEvent):
    """``bank.connection.deleted``: the connection's data is deleted."""

    webhook_type: Literal["bank.connection.deleted"] = "bank.connection.deleted"  # pyright: ignore[reportIncompatibleVariableOverride]
    data: BankConnectionDeletedData | None = None


class BankConnectionHistoryCompleteEvent(_BankEvent):
    """``bank.connection.history_complete``: the backfill of older movements finished."""

    webhook_type: Literal["bank.connection.history_complete"] = "bank.connection.history_complete"  # pyright: ignore[reportIncompatibleVariableOverride]
    data: BankConnectionEventData | None = None


class BankDataUpdatedEvent(_BankEvent):
    """``bank.data.updated``: a sync stored changes, or the first read of a connection
    published its accounts. Call the change feed (``client.bank.sync_transactions``)."""

    webhook_type: Literal["bank.data.updated"] = "bank.data.updated"  # pyright: ignore[reportIncompatibleVariableOverride]
    data: BankDataUpdatedData | None = None


class BankSyncCompletedEvent(_BankEvent):
    """``bank.sync.completed``: a sync finished."""

    webhook_type: Literal["bank.sync.completed"] = "bank.sync.completed"  # pyright: ignore[reportIncompatibleVariableOverride]
    data: BankSyncCompletedData | None = None


class BankSyncFailedEvent(_BankEvent):
    """``bank.sync.failed``: a sync failed; the connection may need the person back."""

    webhook_type: Literal["bank.sync.failed"] = "bank.sync.failed"  # pyright: ignore[reportIncompatibleVariableOverride]
    data: BankSyncFailedData | None = None


class BankSyncRecoveredEvent(_BankEvent):
    """``bank.sync.recovered``: syncs work again after a failure."""

    webhook_type: Literal["bank.sync.recovered"] = "bank.sync.recovered"  # pyright: ignore[reportIncompatibleVariableOverride]
    data: BankSyncRecoveredData | None = None


class UnknownEvent(WebhookEventBase):
    """An event type this version of the SDK does not know. ``payload`` holds
    the whole body."""

    payload: dict[str, Any] = Field(default_factory=dict)


WebhookEvent = Union[
    SessionStatusUpdatedEvent,
    SessionDataUpdatedEvent,
    UserStatusUpdatedEvent,
    UserDataUpdatedEvent,
    BusinessStatusUpdatedEvent,
    BusinessDataUpdatedEvent,
    ActivityCreatedEvent,
    TransactionCreatedEvent,
    TransactionStatusUpdatedEvent,
    TravelRuleStatusUpdatedEvent,
    WorkflowComplianceChangedEvent,
    KybRegistrySearchResolvedEvent,
    BankLinkCompletedEvent,
    BankLinkCancelledEvent,
    BankLinkExpiredEvent,
    BankLinkFailedEvent,
    BankConnectionCreatedEvent,
    BankConnectionUpdatedEvent,
    BankConnectionConsentExpiringEvent,
    BankConnectionRenewalRequiredEvent,
    BankConnectionRenewedEvent,
    BankConnectionRevokedEvent,
    BankConnectionDeletedEvent,
    BankConnectionHistoryCompleteEvent,
    BankDataUpdatedEvent,
    BankSyncCompletedEvent,
    BankSyncFailedEvent,
    BankSyncRecoveredEvent,
    UnknownEvent,
]
"""Every webhook event; narrow it with ``isinstance`` or ``match``."""

_BY_TYPE: dict[str, type[WebhookEventBase]] = {
    "status.updated": SessionStatusUpdatedEvent,
    "data.updated": SessionDataUpdatedEvent,
    "user.status.updated": UserStatusUpdatedEvent,
    "user.data.updated": UserDataUpdatedEvent,
    "business.status.updated": BusinessStatusUpdatedEvent,
    "business.data.updated": BusinessDataUpdatedEvent,
    "activity.created": ActivityCreatedEvent,
    "transaction.created": TransactionCreatedEvent,
    "transaction.status.updated": TransactionStatusUpdatedEvent,
    "travel_rule.status.updated": TravelRuleStatusUpdatedEvent,
    "workflow.compliance_changed": WorkflowComplianceChangedEvent,
    "kyb.registry_search.resolved": KybRegistrySearchResolvedEvent,
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


def parse_event(payload: dict[str, Any], verified_by: VerifiedBy = "none") -> WebhookEvent:
    """Turn a webhook body into its typed event, never raising on unknown data."""
    kind = payload.get("webhook_type")
    if not isinstance(kind, str):
        kind = payload.get("event_type") if isinstance(payload.get("event_type"), str) else None
    cls = _BY_TYPE.get(kind) if isinstance(kind, str) else None
    event: WebhookEventBase
    if cls is None:
        envelope = {k: payload[k] for k in WebhookEventBase.model_fields if k in payload}
        event = validate_response(UnknownEvent, {**envelope, "payload": payload})
    else:
        event = validate_response(cls, payload)
    event._verified_by = verified_by  # pyright: ignore[reportPrivateUsage]
    return event  # type: ignore[return-value]
