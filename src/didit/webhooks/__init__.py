"""Verify Didit webhook deliveries and read them as typed events (docs/DESIGN.md section 9).

    import didit

    event = didit.webhooks.verify(request_body_bytes, request.headers, secret=WEBHOOK_SECRET)
    if isinstance(event, didit.webhooks.SessionStatusUpdatedEvent):
        ...

The verifier has no framework dependency; see ``examples/`` for FastAPI, Flask
and Django receivers.
"""

from .._exceptions import WebhookVerificationError, WebhookVerificationReason
from ._canonical import canonical_json
from ._events import (
    ActivityCreatedEvent,
    BusinessDataUpdatedEvent,
    BusinessStatusUpdatedEvent,
    KybRegistrySearchResolvedEvent,
    SessionDataUpdatedEvent,
    SessionStatusUpdatedEvent,
    TransactionCreatedEvent,
    TransactionStatusUpdatedEvent,
    TravelRuleStatusUpdatedEvent,
    UnknownEvent,
    UserDataUpdatedEvent,
    UserStatusUpdatedEvent,
    WebhookEvent,
    WebhookEventBase,
    WorkflowComplianceChangedEvent,
    parse_event,
)
from ._verify import DEFAULT_TOLERANCE, HeadersLike, verify, verify_parsed

__all__ = [
    "DEFAULT_TOLERANCE",
    "ActivityCreatedEvent",
    "BusinessDataUpdatedEvent",
    "BusinessStatusUpdatedEvent",
    "HeadersLike",
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
    "WebhookVerificationError",
    "WebhookVerificationReason",
    "WorkflowComplianceChangedEvent",
    "canonical_json",
    "parse_event",
    "verify",
    "verify_parsed",
]
