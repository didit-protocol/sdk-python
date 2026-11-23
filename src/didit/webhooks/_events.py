"""Typed webhook events (docs/DESIGN.md section 9.4)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal, Union

from pydantic import Field, PrivateAttr

from .._models import BaseModel, validate_response

if TYPE_CHECKING:
    from ..types.components.session_decision import SessionDecision

__all__ = [
    "ActivityCreatedEvent",
    "BankConnectionConsentExpiringEvent",
    "BankConnectionCreatedEvent",
    "BankConnectionDeletedEvent",
    "BankConnectionHistoryCompleteEvent",
    "BankConnectionRenewalRequiredEvent",
    "BankConnectionRenewedEvent",
    "BankConnectionRevokedEvent",
    "BankConnectionUpdatedEvent",
    "BankDataUpdatedAccount",
    "BankDataUpdatedEvent",
    "BankLinkCancelledEvent",
    "BankLinkCompletedEvent",
    "BankLinkEventData",
    "BankLinkExpiredEvent",
    "BankLinkFailedEvent",
    "BankSyncCompletedEvent",
    "BankSyncFailedEvent",
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
    """Ids and statuses of a Bank Link, in ``data`` of the ``bank.link.*`` events. No personal data."""

    link_id: str | None = None
    status: Literal["completed", "cancelled", "expired", "failed"] | str | None = None
    connection_id: str | None = None
    """The connection the link created or renewed."""
    check_id: str | None = None
    """The ownership result, when one was asked for."""
    error_code: (
        Literal[
            "duplicate_conflict",
            "renewal_login_mismatch",
            "reduced_grant",
            "corporate_approval_not_supported",
            "ongoing_access_not_available",
            "bank_unavailable",
            "bank_cancelled",
            "consent_declined",
            "read_limit",
            "renewal_not_needed",
            "renewal_window_expired",
            "first_sync_failed",
        ]
        | str
        | None
    ) = None
    """Why the link failed, with ``bank.link.failed``; ``None`` otherwise."""


class _BankLinkEvent(WebhookEventBase):
    data: BankLinkEventData | None = None
    """The link's ids and statuses (the ``bank.link.*`` events carry them under ``data``)."""


class BankLinkCompletedEvent(_BankLinkEvent):
    """``bank.link.completed``: the person connected a bank or renewed a connection; ``data.connection_id`` is set."""

    webhook_type: Literal["bank.link.completed"] = "bank.link.completed"  # pyright: ignore[reportIncompatibleVariableOverride]


class BankLinkCancelledEvent(_BankLinkEvent):
    """``bank.link.cancelled``: a Bank Link was cancelled, by the person or through the API."""

    webhook_type: Literal["bank.link.cancelled"] = "bank.link.cancelled"  # pyright: ignore[reportIncompatibleVariableOverride]


class BankLinkExpiredEvent(_BankLinkEvent):
    """``bank.link.expired``: a Bank Link expired before it was completed."""

    webhook_type: Literal["bank.link.expired"] = "bank.link.expired"  # pyright: ignore[reportIncompatibleVariableOverride]


class BankLinkFailedEvent(_BankLinkEvent):
    """``bank.link.failed``: a Bank Link failed; ``data.error_code`` says why. Nothing was published or charged."""

    webhook_type: Literal["bank.link.failed"] = "bank.link.failed"  # pyright: ignore[reportIncompatibleVariableOverride]


# The connection, data and sync events carry their fields next to the envelope
# fields (no ``data`` object). Date-times are the ISO 8601 strings as sent.

BankConnectionStatus = Literal[
    "pending", "active", "renewal_required", "paused", "revoked", "deleted", "failed"
]
BankSyncTrigger = Literal["initial", "scheduled", "requested"]


class BankConnectionCreatedEvent(WebhookEventBase):
    """``bank.connection.created``: the first sync finished and the accounts are readable."""

    webhook_type: Literal["bank.connection.created"] = "bank.connection.created"  # pyright: ignore[reportIncompatibleVariableOverride]
    connection_id: str | None = None
    initial_status: Literal["succeeded", "partial"] | str | None = None
    """How the first sync ended."""


class BankConnectionUpdatedEvent(WebhookEventBase):
    """``bank.connection.updated``: a revocation started; ``bank.connection.revoked`` follows."""

    webhook_type: Literal["bank.connection.updated"] = "bank.connection.updated"  # pyright: ignore[reportIncompatibleVariableOverride]
    connection_id: str | None = None
    status: BankConnectionStatus | str | None = None
    revocation_status: Literal["pending"] | str | None = None
    """``pending``: the bank has not confirmed the revocation yet."""


class BankConnectionConsentExpiringEvent(WebhookEventBase):
    """``bank.connection.consent_expiring``: the consent ends in 14, 7 or 1 days."""

    webhook_type: Literal["bank.connection.consent_expiring"] = "bank.connection.consent_expiring"  # pyright: ignore[reportIncompatibleVariableOverride]
    connection_id: str | None = None
    days_left: int | None = None
    """Days left before the consent ends: 14, 7 or 1."""
    consent_expires_at: str | None = None
    renew_by: str | None = None
    """The consent's end: renew before it for no gap."""


class BankConnectionRenewalRequiredEvent(WebhookEventBase):
    """``bank.connection.renewal_required``: the consent ended or the bank asks the person to sign in again."""

    webhook_type: Literal["bank.connection.renewal_required"] = "bank.connection.renewal_required"  # pyright: ignore[reportIncompatibleVariableOverride]
    connection_id: str | None = None
    status: Literal["renewal_required"] | str | None = None
    reason: Literal["consent_expired", "bank_requires_sign_in"] | str | None = None
    renew_by: str | None = None
    renewable_until: str | None = None
    """The last moment the same connection can be revived; after it the person connects again."""


class BankConnectionRenewedEvent(WebhookEventBase):
    """``bank.connection.renewed``: a renew link completed; the connection and account ids are unchanged."""

    webhook_type: Literal["bank.connection.renewed"] = "bank.connection.renewed"  # pyright: ignore[reportIncompatibleVariableOverride]
    connection_id: str | None = None
    status: BankConnectionStatus | str | None = None
    consent_version: int | None = None
    """The consent version the renewal created."""
    link_id: str | None = None
    """The renew link that completed, when there is one."""
    consent_expires_at: str | None = None


class BankConnectionRevokedEvent(WebhookEventBase):
    """``bank.connection.revoked``: access ended and the bank confirmed it."""

    webhook_type: Literal["bank.connection.revoked"] = "bank.connection.revoked"  # pyright: ignore[reportIncompatibleVariableOverride]
    connection_id: str | None = None
    status: Literal["revoked"] | str | None = None
    ended_by: Literal["end_user", "bank", "customer", "unknown"] | str | None = None
    """Who ended access."""
    status_reason: (
        Literal[
            "revoked_by_end_user",
            "revoked_by_bank",
            "revoked_by_customer",
            "consent_expired",
            "consent_lapsed",
            "bank_requires_sign_in",
            "insufficient_balance",
            "paused_by_customer",
            "first_sync_failed",
            "collection_complete",
        ]
        | str
        | None
    ) = None
    ended_at: str | None = None
    retain_until: str | None = None
    """How long the stored data stays readable, set by the retention setting of your application."""


class BankConnectionDeletedEvent(WebhookEventBase):
    """``bank.connection.deleted``: the connection's data was deleted."""

    webhook_type: Literal["bank.connection.deleted"] = "bank.connection.deleted"  # pyright: ignore[reportIncompatibleVariableOverride]
    connection_id: str | None = None
    status: Literal["deleted"] | str | None = None
    erasure_status: Literal["erased"] | str | None = None
    """``erased``: the deletion finished."""
    reason: (
        Literal[
            "deleted_by_customer",
            "consent_lapsed",
            "retention_elapsed",
            "application_deleted",
        ]
        | str
        | None
    ) = None
    """Why the connection was deleted."""
    erased_at: str | None = None


class BankConnectionHistoryCompleteEvent(WebhookEventBase):
    """``bank.connection.history_complete``: the history backfill ended."""

    webhook_type: Literal["bank.connection.history_complete"] = "bank.connection.history_complete"  # pyright: ignore[reportIncompatibleVariableOverride]
    connection_id: str | None = None
    status: Literal["complete", "partial"] | str | None = None
    """``partial`` when the bank could not deliver every range."""


class BankDataUpdatedAccount(BaseModel):
    """Transactions changed in one account, in ``bank.data.updated``."""

    account_id: str | None = None
    added: int | None = None
    modified: int | None = None
    removed: int | None = None


class BankDataUpdatedEvent(WebhookEventBase):
    """``bank.data.updated``: a sync stored changes. A signal only: read them with ``sync_transactions``."""

    webhook_type: Literal["bank.data.updated"] = "bank.data.updated"  # pyright: ignore[reportIncompatibleVariableOverride]
    connection_id: str | None = None
    sync_id: str | None = None
    trigger: BankSyncTrigger | str | None = None
    accounts: list[BankDataUpdatedAccount] | None = None
    """The accounts whose transactions changed, with counts."""
    balances_changed: bool | None = None


class BankSyncCompletedEvent(WebhookEventBase):
    """``bank.sync.completed``: a sync finished (off by default)."""

    webhook_type: Literal["bank.sync.completed"] = "bank.sync.completed"  # pyright: ignore[reportIncompatibleVariableOverride]
    connection_id: str | None = None
    sync_id: str | None = None
    trigger: BankSyncTrigger | str | None = None
    outcome: Literal["succeeded", "partial", "failed"] | str | None = None
    changed: bool | None = None
    """Whether the sync stored changes."""


class BankSyncFailedEvent(WebhookEventBase):
    """``bank.sync.failed``: syncs have been failing for 24 hours; they are retried."""

    webhook_type: Literal["bank.sync.failed"] = "bank.sync.failed"  # pyright: ignore[reportIncompatibleVariableOverride]
    connection_id: str | None = None
    sync_id: str | None = None
    """The latest failed sync."""
    error_code: str | None = None
    failing_since: str | None = None


class BankSyncRecoveredEvent(WebhookEventBase):
    """``bank.sync.recovered``: syncs work again after ``bank.sync.failed``."""

    webhook_type: Literal["bank.sync.recovered"] = "bank.sync.recovered"  # pyright: ignore[reportIncompatibleVariableOverride]
    connection_id: str | None = None
    sync_id: str | None = None


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
