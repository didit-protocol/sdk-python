"""Verify a Didit webhook and reconcile it with the API decision.

pip install didit-sdk
DIDIT_API_KEY=... DIDIT_WEBHOOK_SECRET=... \
  python examples/reconcile_session.py body.txt headers.json

``body.txt`` is the exact raw request body and ``headers.json`` is the request
headers as a JSON object. Re-fetching the decision is the recommended check for
``X-Signature-Simple`` deliveries, whose body is not authenticated.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import cast

import didit
from didit.webhooks import SessionStatusUpdatedEvent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("body", type=Path, help="raw request body")
    parser.add_argument("headers", type=Path, help="request headers as JSON")
    args = parser.parse_args()

    body = args.body.read_bytes()
    headers = cast("dict[str, str]", json.loads(args.headers.read_text()))
    secret = os.environ["DIDIT_WEBHOOK_SECRET"]

    try:
        event = didit.webhooks.verify(body, headers, secret)
    except didit.WebhookVerificationError as err:
        raise SystemExit(f"invalid webhook: {err.reason}") from err

    if not isinstance(event, SessionStatusUpdatedEvent):
        raise SystemExit(f"not a session event: {event.webhook_type}")
    if event.session_id is None:
        raise SystemExit("session event without a session_id")

    if not event.body_authenticated:
        print("warning: the body is not authenticated; re-fetching the decision anyway")

    with didit.Didit() as client:
        decision = client.sessions.retrieve_decision(event.session_id)

    if event.status != decision.status:
        raise SystemExit(f"drift: webhook says {event.status!r}, API says {decision.status!r}")
    print("ok", event.session_id, event.status)


if __name__ == "__main__":
    main()
