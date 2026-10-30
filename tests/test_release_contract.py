"""Release contract (DESIGN 3, 9.4 and 13): what a release promises its users.

The generated per-operation tests cover requests and responses, and
``test_contract.py`` covers the operation surface. These tests cover the two
promises the release itself makes and that nothing else checks:

- every webhook event name the released OpenAPI document accepts is a delivery
  the SDK verifies, returns and keeps whole (DESIGN 9.3, 9.4);
- the version a release publishes is the same in every file release-please
  updates, because ``release.yml`` refuses a tag that disagrees with it.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import pathlib
from typing import Any

import pytest

import didit
from didit import webhooks
from didit.webhooks import UnknownEvent, canonical_json
from didit.webhooks._events import _BY_TYPE  # pyright: ignore[reportPrivateUsage]

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10
    import tomli as tomllib  # type: ignore[no-redef]

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = json.loads((ROOT / "openapi" / "verification.json").read_text("utf-8"))
RELEASED_EVENTS: list[str] = SPEC["components"]["schemas"]["WebhookEvent"]["enum"]
SECRET = "whsec_test_release_contract_0001"
NOW = 1_760_702_400

# The events DESIGN 9.4 types, plus the registry-search event it names there.
# Everything else the released document accepts arrives as UnknownEvent, which
# keeps the whole body in ``payload`` (DESIGN 9.4).
TYPED_EVENTS = {
    "status.updated",
    "data.updated",
    "user.status.updated",
    "user.data.updated",
    "business.status.updated",
    "business.data.updated",
    "activity.created",
    "transaction.created",
    "transaction.status.updated",
    "travel_rule.status.updated",
    "workflow.compliance_changed",
    "kyb.registry_search.resolved",
}


def _sign(message: bytes) -> str:
    return hmac.new(SECRET.encode(), message, hashlib.sha256).hexdigest()


def _delivery(webhook_type: str) -> tuple[bytes, dict[str, str], dict[str, Any]]:
    """A delivery signed the way service-didit-verification signs one."""
    payload: dict[str, Any] = {
        "application_id": "0b5e8d2c-1f4a-4c3b-9d6e-2a7f8c1b3e5d",
        "created_at": NOW,
        "environment": "sandbox",
        "event_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
        "timestamp": NOW,
        "webhook_type": webhook_type,
        "vendor_user_id": "user-1",
        "vendor_data": "vendor-1",
        "status": "Approved",
    }
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    headers = {
        "X-Signature": _sign(body),
        "X-Signature-V2": _sign(canonical_json(payload).encode()),
        "X-Timestamp": str(NOW),
    }
    return body, headers, payload


@pytest.mark.parametrize("webhook_type", RELEASED_EVENTS)
def test_every_released_webhook_event_verifies(
    webhook_type: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A customer may subscribe to any released event; each one verifies and is whole."""
    monkeypatch.setattr("didit.webhooks._verify.time.time", lambda: float(NOW))
    body, headers, payload = _delivery(webhook_type)

    event = webhooks.verify(body, headers, SECRET)

    assert event.webhook_type == webhook_type
    assert event.body_authenticated is True
    if isinstance(event, UnknownEvent):
        assert event.payload == payload
    else:
        assert webhook_type in TYPED_EVENTS
        assert getattr(event, "vendor_data", None) == "vendor-1"


def test_typed_events_are_the_design_set() -> None:
    """The hand-written typed union is exactly DESIGN 9.4, so a new one is a design change."""
    assert set(_BY_TYPE) == TYPED_EVENTS
    assert TYPED_EVENTS - {"kyb.registry_search.resolved"} <= set(RELEASED_EVENTS)


def test_version_contract_agrees_across_release_files() -> None:
    """release.yml refuses a tag that disagrees with these files; keep them in step."""
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text("utf-8"))
    manifest = json.loads((ROOT / ".release-please-manifest.json").read_text("utf-8"))
    lock = tomllib.loads((ROOT / "uv.lock").read_text("utf-8"))
    locked = [p for p in lock["package"] if p.get("name") == "didit-sdk"]

    assert len(locked) == 1
    assert didit.__version__ == pyproject["project"]["version"] == manifest["."]
    assert locked[0]["version"] == didit.__version__
