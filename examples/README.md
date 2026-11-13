# Examples

Each script reads the API key from `DIDIT_API_KEY` (Business Console, Developers, API keys).
Use a sandbox application while you try them.

| Script | What it shows |
|---|---|
| `quickstart.py` | Create a KYC session, read its decision, verify a webhook (needs `DIDIT_WORKFLOW_ID`) |
| `async_quickstart.py` | The same with `AsyncDidit`, and `async for` auto-pagination |
| `poll_decision.py` | Poll a session decision until it is final, with a deadline and backoff (takes a session id) |
| `reconcile_session.py` | Verify a webhook and re-fetch the decision from the API to reconcile it (needs `DIDIT_WEBHOOK_SECRET` and a captured body/headers) |
| `id_verification.py` | Standalone ID verification with file uploads |
| `aml_screening.py` | AML screening with an idempotency key, and error handling |
| `transaction_screening.py` | Transactions (KYT): submit one, then list with auto-pagination |
| `travel_rule.py` | Travel Rule settings, VASP directory, wallet addresses, wallet screening |
| `authentication.py` | Verify a Didit Authentication access token in your backend (needs `didit-sdk[auth]`) |
| `webhooks/fastapi_app.py` | Webhook receiver for FastAPI |
| `webhooks/flask_app.py` | Webhook receiver for Flask |
| `webhooks/django_app.py` | Webhook receiver for Django (single file) |

```
pip install didit-sdk
python examples/quickstart.py
```

The webhook receivers need their framework (`pip install fastapi uvicorn`, `flask` or `django`)
and `DIDIT_WEBHOOK_SECRET`, the secret of the webhook destination. Always pass the raw request
body to `didit.webhooks.verify`; verify before you parse.
