"""Webhook verification: every backend vector (openapi/webhook-vectors.json) and the edge cases."""

from __future__ import annotations

import hashlib
import hmac
import json
import pathlib
from typing import Any

import pytest

import didit
from didit import ConfigurationError, Didit, WebhookVerificationError, webhooks
from didit.webhooks import (
    SessionStatusUpdatedEvent,
    TransactionStatusUpdatedEvent,
    TravelRuleStatusUpdatedEvent,
    UnknownEvent,
    UserStatusUpdatedEvent,
    canonical_json,
)

VECTORS_FILE = pathlib.Path(__file__).resolve().parents[1] / "openapi" / "webhook-vectors.json"
VECTORS: list[dict[str, Any]] = json.loads(VECTORS_FILE.read_text("utf-8"))["vectors"]
SECRET = "whsec_test_unit_secret_0001"
PREVIOUS = "whsec_test_unit_secret_0000"
NOW = 1_760_702_400


@pytest.fixture
def frozen_time(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    clock = [float(NOW)]
    monkeypatch.setattr("didit.webhooks._verify.time.time", lambda: clock[0])
    return clock


def _sign(secret: str, message: bytes) -> str:
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def _delivery(payload: dict[str, Any], secret: str = SECRET) -> tuple[bytes, dict[str, str]]:
    """A delivery signed exactly like service-didit-verification does it."""
    body = json.dumps(webhooks._canonical.shorten_floats(payload), sort_keys=True, separators=(",", ":"))
    canonical = canonical_json(json.loads(body))
    simple = ":".join(str(payload.get(k, "")) for k in ("timestamp", "session_id", "status", "webhook_type"))
    headers = {
        "X-Signature": _sign(secret, body.encode()),
        "X-Signature-V2": _sign(secret, canonical.encode()),
        "X-Signature-Simple": _sign(secret, simple.encode()),
        "X-Timestamp": str(payload["timestamp"]),
    }
    return body.encode(), headers


def _payload(**extra: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "application_id": "0b5e8d2c-1f4a-4c3b-9d6e-2a7f8c1b3e5d",
        "created_at": NOW,
        "environment": "sandbox",
        "event_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
        "session_id": "11111111-2222-3333-4444-555555555555",
        "status": "Approved",
        "timestamp": NOW,
        "webhook_type": "status.updated",
    }
    base.update(extra)
    return base


# Backend vectors ------------------------------------------------------------------


@pytest.mark.parametrize("vector", VECTORS, ids=[v["name"] for v in VECTORS])
def test_vector(vector: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("didit.webhooks._verify.time.time", lambda: float(vector["now"]))
    body: str = vector["body"]
    headers: dict[str, str] = vector["headers"]
    secret: str = vector["secret"]
    expect: str = vector["expect"]

    if expect == "invalid_signature" and vector["name"] == "tampered_body":
        # The canonical string was recorded before the body was altered.
        assert canonical_json(json.loads(body)) != vector["canonical_v2"]
    else:
        assert canonical_json(json.loads(body)) == vector["canonical_v2"]

    if expect == "valid":
        event = webhooks.verify(body.encode(), headers, secret)
        assert event.body_authenticated
        assert event.webhook_type == json.loads(body)["webhook_type"]
        if vector["previous_secret"]:
            # A receiver that only has the previous secret still verifies during a rotation.
            assert webhooks.verify(body, headers, vector["previous_secret"]).body_authenticated
            assert webhooks.verify(body, headers, [vector["previous_secret"], secret]).body_authenticated
        # X-Signature-V2 alone also verifies, from the raw body or the parsed payload.
        v2_only = {
            k: v for k, v in headers.items() if k in ("X-Signature-V2", "X-Signature-V2-Previous", "X-Timestamp")
        }
        assert webhooks.verify(body, v2_only, secret).verified_by == "signature_v2"
        assert webhooks.verify_parsed(json.loads(body), v2_only, secret).verified_by == "signature_v2"
    elif expect == "valid_only_with_allow_simple":
        with pytest.raises(WebhookVerificationError) as info:
            webhooks.verify(body, headers, secret)
        assert info.value.reason == "invalid_signature"
        event = webhooks.verify(body, headers, secret, allow_simple=True)
        assert event.verified_by == "signature_simple"
        assert not event.body_authenticated
    else:
        with pytest.raises(WebhookVerificationError) as info:
            webhooks.verify(body.encode(), headers, secret)
        assert info.value.reason == expect


def test_vectors_cover_every_outcome() -> None:
    outcomes = {v["expect"] for v in VECTORS}
    assert outcomes == {
        "valid",
        "valid_only_with_allow_simple",
        "invalid_signature",
        "missing_signature",
        "timestamp_out_of_tolerance",
        "timestamp_mismatch",
    }
    assert len(VECTORS) == 25


# Canonical JSON -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ({"b": 1, "a": 2}, '{"a":2,"b":1}'),
        ({"score": 87.0}, '{"score":87}'),
        ({"x": 1e16}, '{"x":10000000000000000}'),
        ({"x": 1e-05}, '{"x":1e-05}'),
        ({"x": 1.5e-07}, '{"x":1.5e-07}'),
        ({"x": 0.1}, '{"x":0.1}'),
        ({"x": -2.5}, '{"x":-2.5}'),
        ({"x": 9007199254740993}, '{"x":9007199254740993}'),
        ({"x": [1.0, 2.5, None, True, False]}, '{"x":[1,2.5,null,true,false]}'),
        ({"s": "José \U0001f600"}, '{"s":"José \U0001f600"}'),
        ({"s": "a b c\u007f/"}, '{"s":"a b c\u007f/"}'),
        ({"s": 'q"\\\n\r\t\b\f\u0007\u001f'}, '{"s":"q\\"\\\\\\n\\r\\t\\b\\f\\u0007\\u001f"}'),
        # Keys sort by code point, not by UTF-16 code unit (U+FB00 < U+1F600).
        ({"\U0001f600": 1, "ﬀ": 2, "é": 3}, '{"é":3,"ﬀ":2,"\U0001f600":1}'),
    ],
)
def test_canonical_json(value: object, expected: str) -> None:
    assert canonical_json(value) == expected


def test_canonical_json_rejects_non_finite() -> None:
    with pytest.raises(WebhookVerificationError) as info:
        canonical_json({"x": float("nan")})
    assert info.value.reason == "invalid_payload"


# Verification rules ---------------------------------------------------------------


def test_valid_delivery_returns_typed_event(frozen_time: list[float]) -> None:
    body, headers = _delivery(_payload(vendor_data="user-1", workflow_version=3))
    event = webhooks.verify(body, headers, SECRET)
    assert isinstance(event, SessionStatusUpdatedEvent)
    assert event.verified_by == "signature"
    assert event.status == "Approved"
    assert event.vendor_data == "user-1"
    assert event.workflow_version == 3
    assert event.environment == "sandbox"


def test_reencoded_body_still_verifies_with_v2(frozen_time: list[float]) -> None:
    payload = _payload(metadata={"name": "José", "score": 87.0})
    body, headers = _delivery(payload)
    # Middleware that re-encodes the JSON (different key order, unescaped Unicode, 87.0).
    reencoded = json.dumps(json.loads(body), ensure_ascii=False, indent=2).replace("87", "87.0")
    event = webhooks.verify(reencoded.encode(), headers, SECRET)
    assert event.verified_by == "signature_v2"


def test_headers_are_case_insensitive_and_accept_pairs(frozen_time: list[float]) -> None:
    body, headers = _delivery(_payload())
    lower = {k.lower(): v for k, v in headers.items()}
    assert webhooks.verify(body, lower, SECRET).body_authenticated
    assert webhooks.verify(body, list(headers.items()), SECRET).body_authenticated
    wsgi = {"HTTP_" + k.upper().replace("-", "_"): v for k, v in headers.items()}
    assert webhooks.verify(body, wsgi, SECRET).body_authenticated


def test_secret_list_for_rotation(frozen_time: list[float]) -> None:
    body, headers = _delivery(_payload(), secret=PREVIOUS)
    with pytest.raises(WebhookVerificationError):
        webhooks.verify(body, headers, SECRET)
    assert webhooks.verify(body, headers, [SECRET, PREVIOUS]).body_authenticated


@pytest.mark.parametrize("secret", ["", [], [""], [SECRET, ""]])
def test_empty_secret_is_a_configuration_error(secret: Any, frozen_time: list[float]) -> None:
    body, headers = _delivery(_payload())
    with pytest.raises(ConfigurationError):
        webhooks.verify(body, headers, secret)


def test_tolerance_boundaries(frozen_time: list[float]) -> None:
    body, headers = _delivery(_payload())
    frozen_time[0] = NOW + 300
    assert webhooks.verify(body, headers, SECRET)
    frozen_time[0] = NOW + 301
    with pytest.raises(WebhookVerificationError) as info:
        webhooks.verify(body, headers, SECRET)
    assert info.value.reason == "timestamp_out_of_tolerance"
    assert webhooks.verify(body, headers, SECRET, tolerance=600)
    frozen_time[0] = NOW - 301
    with pytest.raises(WebhookVerificationError):
        webhooks.verify(body, headers, SECRET)


def test_negative_tolerance_is_a_configuration_error(frozen_time: list[float]) -> None:
    body, headers = _delivery(_payload())
    with pytest.raises(ConfigurationError):
        webhooks.verify(body, headers, SECRET, tolerance=-1)


@pytest.mark.parametrize(
    ("body", "reason"),
    [
        (b"not json", "invalid_payload"),
        (b"[1, 2]", "invalid_payload"),
        (b'{"timestamp": NaN}', "invalid_payload"),
        (b'{"timestamp": 1e400}', "invalid_payload"),
        (b"\xff\xfe", "invalid_payload"),
        (b'{"webhook_type": "status.updated"}', "missing_timestamp"),
        (b'{"timestamp": "1760702400"}', "missing_timestamp"),
        (b'{"timestamp": true}', "missing_timestamp"),
    ],
)
def test_malformed_bodies(body: bytes, reason: str, frozen_time: list[float]) -> None:
    headers = {"X-Signature": _sign(SECRET, body)}
    with pytest.raises(WebhookVerificationError) as info:
        webhooks.verify(body, headers, SECRET)
    assert info.value.reason == reason


def test_timestamp_header_must_be_an_integer(frozen_time: list[float]) -> None:
    body, headers = _delivery(_payload())
    headers["X-Timestamp"] = "soon"
    with pytest.raises(WebhookVerificationError) as info:
        webhooks.verify(body, headers, SECRET)
    assert info.value.reason == "timestamp_mismatch"


def test_missing_timestamp_header_is_allowed(frozen_time: list[float]) -> None:
    body, headers = _delivery(_payload())
    del headers["X-Timestamp"]
    assert webhooks.verify(body, headers, SECRET).body_authenticated


@pytest.mark.parametrize(
    "bad",
    [
        "A" * 64,  # uppercase hex
        "g" * 64,
        "0" * 63,
        "0" * 65,
        " " + "0" * 63,
    ],
)
def test_only_well_formed_lowercase_hex_counts(bad: str, frozen_time: list[float]) -> None:
    body, headers = _delivery(_payload())
    good = headers["X-Signature"]
    for header in ("X-Signature", "X-Signature-V2", "X-Signature-Simple"):
        headers[header] = bad
    with pytest.raises(WebhookVerificationError) as info:
        webhooks.verify(body, headers, SECRET, allow_simple=True)
    assert info.value.reason == "invalid_signature"
    assert good.upper() != good


def test_uppercase_version_of_a_valid_signature_is_rejected(frozen_time: list[float]) -> None:
    body, headers = _delivery(_payload())
    only = {"X-Signature": headers["X-Signature"].upper()}
    with pytest.raises(WebhookVerificationError) as info:
        webhooks.verify(body, only, SECRET)
    assert info.value.reason == "invalid_signature"


def test_previous_headers_alone_are_checked(frozen_time: list[float]) -> None:
    body, headers = _delivery(_payload(), secret=PREVIOUS)
    previous = {
        "X-Signature-Previous": headers["X-Signature"],
        "X-Timestamp": headers["X-Timestamp"],
    }
    assert webhooks.verify(body, previous, PREVIOUS).verified_by == "signature"
    v2_previous = {"X-Signature-V2-Previous": headers["X-Signature-V2"]}
    assert webhooks.verify(body, v2_previous, PREVIOUS).verified_by == "signature_v2"
    simple_previous = {"X-Signature-Simple-Previous": headers["X-Signature-Simple"]}
    assert webhooks.verify(body, simple_previous, PREVIOUS, allow_simple=True).verified_by == "signature_simple"


def test_simple_signature_formats_null_like_the_backend(frozen_time: list[float]) -> None:
    # str(None) is "None" in the backend's canonical string.
    payload = _payload(webhook_type="transaction.status.updated", session_id=None)
    body, headers = _delivery(payload)
    simple_only = {"X-Signature-Simple": headers["X-Signature-Simple"]}
    event = webhooks.verify(body, simple_only, SECRET, allow_simple=True)
    assert isinstance(event, TransactionStatusUpdatedEvent)
    assert not event.body_authenticated


def test_verify_parsed_needs_v2(frozen_time: list[float]) -> None:
    payload = _payload()
    body, headers = _delivery(payload)
    with pytest.raises(WebhookVerificationError) as info:
        webhooks.verify_parsed(payload, {"X-Signature": headers["X-Signature"]}, SECRET)
    assert info.value.reason == "missing_signature"
    with pytest.raises(WebhookVerificationError) as info:
        webhooks.verify_parsed({**payload, "status": "Declined"}, headers, SECRET)
    assert info.value.reason == "invalid_signature"
    with pytest.raises(WebhookVerificationError) as info:
        webhooks.verify_parsed([payload], headers, SECRET)  # type: ignore[arg-type]
    assert info.value.reason == "invalid_payload"


def test_client_webhooks_verify_delegates(frozen_time: list[float]) -> None:
    payload = _payload()
    body, headers = _delivery(payload)
    client = Didit(api_key=None)
    assert client.webhooks.verify(body, headers, SECRET).body_authenticated
    assert client.webhooks.verify_parsed(payload, headers, SECRET).verified_by == "signature_v2"


# Typed events --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("webhook_type", "cls", "extra"),
    [
        ("status.updated", webhooks.SessionStatusUpdatedEvent, {"session_kind": "user"}),
        ("data.updated", webhooks.SessionDataUpdatedEvent, {}),
        ("user.status.updated", webhooks.UserStatusUpdatedEvent, {"vendor_user_id": "u-1"}),
        ("user.data.updated", webhooks.UserDataUpdatedEvent, {}),
        ("business.status.updated", webhooks.BusinessStatusUpdatedEvent, {"vendor_business_id": "b-1"}),
        ("business.data.updated", webhooks.BusinessDataUpdatedEvent, {}),
        ("activity.created", webhooks.ActivityCreatedEvent, {}),
        ("transaction.created", webhooks.TransactionCreatedEvent, {"amount": "10.00", "score": 12.5}),
        ("transaction.status.updated", webhooks.TransactionStatusUpdatedEvent, {"txn_id": "t-1"}),
        ("travel_rule.status.updated", webhooks.TravelRuleStatusUpdatedEvent, {"rail": "TRP"}),
        ("workflow.compliance_changed", webhooks.WorkflowComplianceChangedEvent, {"workflow_id": "w"}),
        ("kyb.registry_search.resolved", webhooks.KybRegistrySearchResolvedEvent, {}),
    ],
)
def test_event_union(webhook_type: str, cls: type[webhooks.WebhookEventBase], extra: dict[str, Any]) -> None:
    event = webhooks.parse_event(_payload(webhook_type=webhook_type, **extra))
    assert type(event) is cls
    for key, value in extra.items():
        assert getattr(event, key) == value


def test_unknown_event_keeps_the_raw_payload() -> None:
    payload = _payload(webhook_type="transaction_rule_suggestions.created", suggestions=[1, 2])
    event = webhooks.parse_event(payload)
    assert isinstance(event, UnknownEvent)
    assert event.webhook_type == "transaction_rule_suggestions.created"
    assert event.payload == payload
    assert event.event_id == payload["event_id"]


def test_registry_search_callback_uses_event_type() -> None:
    event = webhooks.parse_event({"event_type": "kyb.registry_search.resolved", "timestamp": NOW})
    assert isinstance(event, webhooks.KybRegistrySearchResolvedEvent)


def test_events_keep_unknown_fields_and_survive_bad_shapes() -> None:
    event = webhooks.parse_event(_payload(new_field={"a": 1}, decision={"status": "Approved", "x": 1}))
    assert isinstance(event, SessionStatusUpdatedEvent)
    assert event.model_extra == {"new_field": {"a": 1}}
    assert event.decision is not None
    # A field of the wrong type never raises; the value is kept as sent.
    odd = webhooks.parse_event(_payload(webhook_type="user.status.updated", status=["not", "a", "string"]))
    assert isinstance(odd, UserStatusUpdatedEvent)
    assert odd.status == ["not", "a", "string"]


def test_travel_rule_vector_parses_to_its_event(monkeypatch: pytest.MonkeyPatch) -> None:
    vector = next(v for v in VECTORS if v["name"] == "travel_rule_status_updated")
    monkeypatch.setattr("didit.webhooks._verify.time.time", lambda: float(vector["now"]))
    event = webhooks.verify(vector["body"], vector["headers"], vector["secret"])
    assert isinstance(event, TravelRuleStatusUpdatedEvent)
    assert event.travel_rule_status is not None


def test_public_names() -> None:
    assert didit.webhooks.verify is webhooks.verify
    assert didit.WebhookVerificationError is WebhookVerificationError
