"""Quickstart: create a verification session, read its decision, verify a webhook.

export DIDIT_API_KEY=...            # Business Console > Developers > API keys
export DIDIT_WORKFLOW_ID=...        # a published workflow
python examples/quickstart.py
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time

import didit
from didit import Didit

client = Didit(base_url=os.environ.get("DIDIT_BASE_URL"))  # api key from DIDIT_API_KEY

# 1. Create a session and send the user to its hosted URL.
session = client.sessions.create(
    workflow_id=os.environ["DIDIT_WORKFLOW_ID"],
    vendor_data="user-123",
    callback="https://example.com/verification/done",
)
print("Send the user to:", session.url)

# 2. Later (or from the status.updated webhook), read the decision.
decision = client.sessions.retrieve_decision(session.session_id)
print("Status:", decision.status)

# 3. Verify a webhook delivery. Here we sign a sample body ourselves; in your app the
#    body and headers come from the request (see examples/webhooks/).
secret = os.environ.get("DIDIT_WEBHOOK_SECRET", "whsec_test_quickstart_example")
body = json.dumps(
    {
        "session_id": session.session_id,
        "status": "Approved",
        "webhook_type": "status.updated",
        "timestamp": int(time.time()),
    },
    sort_keys=True,
    separators=(",", ":"),
).encode()
headers = {"X-Signature": hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()}

event = didit.webhooks.verify(body, headers, secret)
if isinstance(event, didit.webhooks.SessionStatusUpdatedEvent):
    print("Webhook verified:", event.session_id, event.status)
