"""Didit webhook receiver for Flask.

pip install didit-sdk flask
DIDIT_WEBHOOK_SECRET=... flask --app examples/webhooks/flask_app.py run --port 8000
"""

from __future__ import annotations

import os

from flask import Flask, abort, request

import didit

app = Flask(__name__)
SECRET = os.environ["DIDIT_WEBHOOK_SECRET"]


@app.post("/webhooks/didit")
def didit_webhook() -> tuple[str, int]:
    try:
        event = didit.webhooks.verify(request.get_data(), request.headers, SECRET)
    except didit.WebhookVerificationError as err:
        abort(400, err.reason)
    print("received", event.webhook_type, event.event_id)
    return "", 204
