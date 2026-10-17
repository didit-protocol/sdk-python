"""Didit webhook receiver for FastAPI.

pip install didit-sdk fastapi uvicorn
DIDIT_WEBHOOK_SECRET=... uvicorn examples.webhooks.fastapi_app:app --port 8000
"""

from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException, Request

import didit
from didit.webhooks import SessionStatusUpdatedEvent, TransactionStatusUpdatedEvent

app = FastAPI()
SECRET = os.environ["DIDIT_WEBHOOK_SECRET"]


@app.post("/webhooks/didit")
async def didit_webhook(request: Request) -> dict[str, str]:
    body = await request.body()  # the raw bytes, before any JSON parsing
    try:
        event = didit.webhooks.verify(body, request.headers, SECRET)
    except didit.WebhookVerificationError as err:
        raise HTTPException(status_code=400, detail=err.reason) from err

    if isinstance(event, SessionStatusUpdatedEvent):
        print("session", event.session_id, "is now", event.status)
    elif isinstance(event, TransactionStatusUpdatedEvent):
        print("transaction", event.transaction_id, "is now", event.status)
    # Answer 2xx quickly; do slow work in a background job keyed by event.event_id.
    return {"received": "ok"}
