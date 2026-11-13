"""Verify a Didit webhook and reconcile it with the API decision.

DIDIT_API_KEY=... DIDIT_WEBHOOK_SECRET=... \
  python examples/reconcile_session.py body.txt headers.json

``body.txt`` is the exact raw request body and ``headers.json`` is the request
headers as a JSON object. Re-fetching the decision is the recommended check for
``X-Signature-Simple`` deliveries, whose body is not authenticated. Pass a list
of secrets during a rotation.
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
from typing import cast

import didit
from didit import Didit
from didit.webhooks import SessionStatusUpdatedEvent


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: python examples/reconcile_session.py body.txt headers.json")
    body_path = pathlib.Path(sys.argv[1])
    headers_path = pathlib.Path(sys.argv[2])

    try:
        body = body_path.read_bytes()
        raw_headers = json.loads(headers_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as err:
        raise SystemExit(f"cannot read the webhook files: {err}") from err
    if not isinstance(raw_headers, dict) or not all(
        isinstance(name, str) and isinstance(value, str) for name, value in raw_headers.items()
    ):
        raise SystemExit("headers.json must be an object of strings")
    headers = cast("dict[str, str]", raw_headers)

    secret = os.environ.get("DIDIT_WEBHOOK_SECRET")
    if not secret:
        raise SystemExit("DIDIT_WEBHOOK_SECRET is not set")

    try:
        event = didit.webhooks.verify(body, headers, secret)
    except didit.WebhookVerificationError as err:
        raise SystemExit(f"invalid webhook: {err.reason}") from err
    except didit.ConfigurationError as err:
        raise SystemExit(str(err)) from err

    if not isinstance(event, SessionStatusUpdatedEvent):
        raise SystemExit(f"not a session event: {event.webhook_type}")
    if event.session_id is None:
        raise SystemExit("session event without a session_id")

    if not event.body_authenticated:
        print("warning: the body is not authenticated; re-fetching the decision anyway")

    try:
        with Didit() as client:
            decision = client.sessions.retrieve_decision(event.session_id)
    except didit.APIStatusError as err:
        raise SystemExit(f"API error {err.status} (request {err.request_id})") from err
    except didit.DiditError as err:
        raise SystemExit(str(err)) from err

    if event.status != decision.status:
        raise SystemExit(f"drift: webhook says {event.status!r}, API says {decision.status!r}")
    print("OK:", event.session_id, event.status)


if __name__ == "__main__":
    main()
