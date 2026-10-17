"""Typed webhook events (docs/DESIGN.md section 9.4)."""

from __future__ import annotations

from typing import Any, Literal, Union

from pydantic import Field, PrivateAttr

from .._models import BaseModel, validate_response
from ..types.sessions.retrieve_decision_response import SessionsRetrieveDecisionResponse

__all__ = [
    "ActivityCreatedEvent",
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


class _SessionEvent(WebhookEventBase):
    session_id: str | None = None
    business_session_id: str | None = None
    session_kind: Literal["user", "business"] | str | None = None
    status: str | None = None
    workflow_id: str | None = None
    workflow_version: int | None = None
    vendor_data: str | None = None
    metadata: object = None
    decision: SessionsRetrieveDecisionResponse | None = None
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
