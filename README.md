# Didit Python SDK

The official Didit Python library: identity verification (KYC), business verification (KYB), AML screening, biometrics, transaction monitoring, Travel Rule and customer authentication, from your Python backend.

> In development, not released yet. The package will be published on PyPI as `didit-sdk` with the first release.

- Every server-side endpoint of the Didit API, with typed requests and responses
- `Didit` (blocking) and `AsyncDidit` (asyncio) clients with the same methods
- Webhook verification with every Didit signature scheme, and typed events
- Authentication helpers: verify the access and ID tokens your users get from Didit Authentication
- Retries, timeouts, auto-pagination, file uploads and raw response access built in

## Install

```sh
pip install didit-sdk            # Python 3.10 or newer
pip install "didit-sdk[auth]"    # adds token verification for Didit Authentication
```

## Quickstart

Create an API key in the Business Console (Developers, API keys) and a workflow, then:

```python
from didit import Didit

client = Didit()  # reads DIDIT_API_KEY

# 1. Create a verification session and send the user to its URL.
session = client.sessions.create(workflow_id="<your workflow id>", vendor_data="user-123")
print(session.url)

# 2. Read the decision once the user is done (or when the webhook arrives).
decision = client.sessions.retrieve_decision(session.session_id)
print(decision.status)
```

```python
# 3. Verify the webhook Didit sends to your backend (Flask shown; see examples/).
import didit


@app.post("/webhooks/didit")
def didit_webhook():
    try:
        event = didit.webhooks.verify(request.get_data(), request.headers, WEBHOOK_SECRET)
    except didit.WebhookVerificationError as err:
        return err.reason, 400
    if isinstance(event, didit.webhooks.SessionStatusUpdatedEvent):
        print(event.session_id, event.status)
    return "", 204
```

More in [`examples/`](examples/): standalone ID verification, AML screening, transactions, Travel Rule, Authentication tokens and webhook receivers for FastAPI, Flask and Django.

## The API

Methods follow the API's resources: `client.<resource>.<method>(...)`. Path ids are positional arguments; everything else is a keyword argument.

```python
from pathlib import Path

client.sessions.list(status="Approved", limit=50)
client.sessions.imports.create(file=open("users.csv", "rb"), import_type="user_verification")
client.id_verification.verify(front_image=Path("front.jpg"), back_image=Path("back.jpg"))
client.aml.screen(full_name="Maria Garcia", date_of_birth="1992-03-14")
client.users.retrieve("user-123")
client.workflows.list()
client.webhooks.destinations.list()
client.cases.list()  # application scoped, see Configuration
client.account.login(email="you@example.com", password="...")
```

The resource tree covers sessions (with imports and reviews), the standalone APIs (`id_verification`, `face_match`, `face_search`, `passive_liveness`, `age_estimation`, `proof_of_address`, `document_ai`, `aml`, `database_validation`, `phone`, `email`, `ip`, `kyb`), `id_wallets`, `fraud_checks`, `users`, `businesses`, `transactions`, `wallet_screening`, `travel_rule`, `workflows`, `questionnaires`, `webhooks.destinations`, `billing`, `biometric_templates`, `customization`, `cases`, `regulatory_reports`, `report_templates`, `networks` and `account`. The API reference at [docs.didit.me](https://docs.didit.me) documents every endpoint; each SDK method's docstring names the endpoint it calls.

Request and response types live in `didit.types`, named after the method (`SessionsCreateResponse`, `SessionsCreateParams`) or after the API schema (`TransactionDetail`). Responses are [pydantic](https://docs.pydantic.dev) models:

```python
decision = client.sessions.retrieve_decision(session_id)
decision.status  # typed attributes
decision.to_dict()  # plain JSON data, with the API's field names
decision.model_extra  # fields this SDK version does not know yet
"aml" in decision.model_fields_set  # was the field present (even as null)?
```

## Transactions and Travel Rule

```python
transaction = client.transactions.create(
    transaction_id="your-txn-001",
    transaction_category="finance",
    transaction_details={
        "direction": "outbound",
        "amount": 1500,
        "currency": "EUR",
        "action_type": "withdrawal",
    },
    subject={"entity_type": "individual", "vendor_data": "user-12345", "full_name": "Maria Garcia"},
)
client.transactions.rules.list()
client.transactions.travel_rule.confirm_ownership("your-txn-001", confirmed=True)
client.wallet_screening.screen(wallet_address="bc1q...", blockchain="BTC")
client.travel_rule.list_vasps(search="exchange")
client.travel_rule.wallet_addresses.create(address="bc1q...", chain="BTC")
```

Their webhooks arrive as `TransactionCreatedEvent`, `TransactionStatusUpdatedEvent` and `TravelRuleStatusUpdatedEvent`.

## Configuration

```python
client = Didit(
    api_key="...",  # default: DIDIT_API_KEY
    organization_id="...",  # default: DIDIT_ORGANIZATION_ID
    application_id="...",  # default: DIDIT_APPLICATION_ID
    base_url="https://verification.didit.me",
    timeout=60,  # seconds, or an httpx.Timeout
    max_retries=2,
    default_headers={"X-My-Header": "..."},
    http_client=httpx.Client(proxy="http://proxy:8080"),  # optional
)
client.with_options(timeout=5, max_retries=0).sessions.list()
```

- Methods under `/v3/organization/{organization_id}/application/{application_id}/` (cases, networks, regulatory reports, report templates and some user and business tools) take both ids from the client options. Without them they raise `ConfigurationError` before sending anything.
- The `account` methods talk to `https://apx.didit.me/auth/v2` and never send the API key. `client.account.login(...)` returns an `access_token`; pass it as `account_token` (`client.with_options(account_token=...)`) for the methods that need it.
- Every method also accepts `extra_headers`, `extra_query`, `extra_body` and `timeout` for one request.
- One client per process is the intended pattern: it keeps a connection pool and is safe to share between threads. `with Didit() as client:` closes the pool at the end.
- `DIDIT_LOG=debug` logs method, path, status, duration and request id of every request to stderr (never bodies or headers). The logger is called `didit`.

## Errors

```python
import didit

try:
    client.sessions.retrieve_decision("...")
except didit.NotFoundError:
    ...
except didit.RateLimitError as err:
    print(err.status, err.request_id, err.headers.get("retry-after"))
except didit.APIStatusError as err:  # any other non-2xx
    print(err.status, err.body)
except didit.APIConnectionError:  # no response (APITimeoutError is a subclass)
    ...
```

| Error | When |
|---|---|
| `DiditError` | Base of everything below |
| `APIConnectionError`, `APITimeoutError` | No response |
| `APIStatusError` | Any non-2xx, with `status`, `body`, `headers`, `request_id`, `response` |
| `BadRequestError` 400, `AuthenticationError` 401, `PermissionDeniedError` 403, `NotFoundError` 404, `ConflictError` 409, `UnprocessableEntityError` 422, `RateLimitError` 429, `InternalServerError` 5xx | Subclasses of `APIStatusError` |
| `WebhookVerificationError` | A webhook failed verification; see `reason` |
| `ConfigurationError` | Missing API key, account token, organization or application id, or webhook secret |
| `APIResponseValidationError` | A successful response was not the documented content (for example HTML instead of JSON) |

A response that does not match the published schema never raises: the SDK returns it with the fields it could read, and unknown values stay available.

### Retries and timeouts

Failed requests are retried up to `max_retries` times (default 2) with exponential backoff (from 0.5 s, capped at 8 s, with jitter), honouring `Retry-After`. `GET`, `HEAD`, `PUT` and `DELETE` are retried on connection errors, timeouts, 408, 429 and 5xx. `POST` and `PATCH` are retried only when the connection failed before the request was sent, or on 429, so a create is never sent twice. Where an endpoint accepts an idempotency key (`idempotency_key=`), use it.

## Pagination

List methods return a page with `count`, `next`, `previous` and `results`. Iterating it walks every item of every page:

```python
for session in client.sessions.list(limit=100):
    print(session.session_id)

page = client.sessions.list(limit=100)
page.results, page.count, page.has_next_page()
next_page = page.get_next_page()

async for session in async_client.sessions.list(limit=100):
    ...
```

Next links are followed only on the API's own origin; the API key is never sent anywhere else.

## Files and binary responses

Upload parameters accept a path (`pathlib.Path`), bytes, an open binary file, or a tuple `(filename, content)` or `(filename, content, content_type)`. Endpoints that return files (session PDFs, network reports, wallet screening PDFs) return `bytes`; stream large ones:

```python
pdf = client.sessions.generate_pdf(session_id)

with client.sessions.with_streaming_response.generate_pdf(session_id) as response:
    response.write_to_file("session.pdf")
```

## Raw responses

```python
response = client.sessions.with_raw_response.retrieve_decision(session_id)
response.status_code, response.headers, response.request_id
decision = response.parse()
```

## Async

```python
import asyncio
from didit import AsyncDidit


async def main() -> None:
    async with AsyncDidit() as client:
        session = await client.sessions.create(workflow_id="...")
        async for row in client.sessions.list():
            ...


asyncio.run(main())
```

## Webhooks

`didit.webhooks.verify(raw_body, headers, secret)` checks the delivery and returns a typed event, or raises `WebhookVerificationError` with a machine-readable `reason` (`missing_signature`, `invalid_signature`, `missing_timestamp`, `timestamp_mismatch`, `timestamp_out_of_tolerance`, `invalid_payload`).

- Pass the exact raw body bytes and the request headers (any mapping or list of pairs).
- `X-Signature` (raw body) and `X-Signature-V2` (canonical JSON, which survives middleware that re-encodes the body) are checked, and their `-Previous` variants during a secret rotation. `secret` can be a list: `verify(body, headers, [new_secret, old_secret])`.
- Deliveries older or newer than `tolerance` seconds (default 300) are refused.
- `X-Signature-Simple` (deprecated) counts only with `allow_simple=True`; it covers the envelope, not the body, so `event.body_authenticated` is then `False` and you should re-fetch the record from the API.
- `didit.webhooks.verify_parsed(payload, headers, secret)` is for frameworks that only give you the parsed JSON; it can check `X-Signature-V2` only.

Events: `SessionStatusUpdatedEvent`, `SessionDataUpdatedEvent`, `UserStatusUpdatedEvent`, `UserDataUpdatedEvent`, `BusinessStatusUpdatedEvent`, `BusinessDataUpdatedEvent`, `ActivityCreatedEvent`, `TransactionCreatedEvent`, `TransactionStatusUpdatedEvent`, `TravelRuleStatusUpdatedEvent`, `WorkflowComplianceChangedEvent`, `KybRegistrySearchResolvedEvent`, and `UnknownEvent` (with the whole `payload`) for types this version does not know. `client.webhooks.verify(...)` does the same as `didit.webhooks.verify(...)`.

## Authentication

[Didit Authentication](https://docs.didit.me) gives your application its own OpenID Connect issuer for your end users (early access; production with the 2026-11-01 release). The `didit.authentication` module verifies the tokens that issuer signs, in your backend, and calls its token, session and step-up endpoints. It never uses the API key. Install it with `pip install "didit-sdk[auth]"`.

```python
from didit.authentication import Authentication, TokenVerificationError

# The publishable key (pk_live_... or pk_test_...) carries the issuer URL;
# Authentication("https://<slug>.auth.didit.me") works too. client_id is your application id.
auth = Authentication.from_publishable_key("pk_live_...", client_id="<application id>")

try:
    claims = auth.verify_access_token(access_token)
except TokenVerificationError as err:
    ...  # err.reason: "expired", "invalid_signature", "invalid_audience", ...
print(claims.sub, claims.sid, claims.vendor_data, claims.org)
```

- `verify_access_token(token, audience=None)` accepts ES256 only (never `none`, HS* or RS*), requires the header `typ: at+jwt`, checks `iss`, `aud` (the given audience, else `client_id`), `exp`, `nbf` and `iat` with 60 s leeway, and the signature against the issuer's keys. Discovery and keys are fetched on first use and cached as the issuer says (5 minutes today); an unknown key id triggers at most one refetch per minute.
- `verify_id_token(token, nonce=..., audience=None)` does the same for ID tokens and checks the nonce of the sign-in (pass `nonce=None` for an ID token from a refresh, which has none).
- `create_pkce()`, `create_state()` and `create_nonce()` for the sign-in redirect; `exchange_code(code, code_verifier=..., redirect_uri=...)` and `refresh(refresh_token)` for tokens. Serialise refreshes for one session: reusing a consumed refresh token revokes the session.
- `get_session(access_token)` asks the issuer whether the session is still live (instant revocation check); `revoke_session(access_token)` signs the person out.
- `create_step_up(access_token, action="payout", amount="250.00", currency="EUR", return_to=...)` and `retrieve_step_up(access_token, step_up_id)`: act on a sensitive action only when `step_up.approved` is true.
- `AsyncAuthentication` has the same methods with `await`. One instance per process is the intended use.

See [`examples/authentication.py`](examples/authentication.py).

## Language notes

Choices the shared design leaves to each language, made the Python way:

- Method arguments: path ids are positional; body and query fields are keyword-only and default to `NOT_GIVEN`, so an omitted field is left out of the request and `None` is sent as JSON `null`. Each request body also has a `TypedDict` (`SessionsCreateParams`) for building it as a dict.
- Field names are the API's own. A name that is a Python keyword or would shadow a model method gets a trailing underscore in Python (`from_`), and keeps its wire name in `to_dict()`. A query parameter with the same name as a body field gets a `_query` suffix (`node_id_query`).
- Enums are open: `Literal["Approved", "Declined", ...] | str`, so a new value from the API never raises.
- Dates and date-times are `datetime.date` and `datetime.datetime` in responses, and accept either the object or an ISO 8601 string in requests. Decimal amounts stay strings, as the API sends them.
- Async list methods return an object you can `await` for the first page or `async for` over for every item.
- Operations that accept JSON or a file upload send multipart only when you pass a file.
- `api_key` is checked when a method needs it, so a client without one can still use `client.account` and verify webhooks.
- Types load on first use, so `import didit` stays fast even though the SDK has more than 800 types.

## Supported runtimes

CPython 3.10, 3.11, 3.12, 3.13 and 3.14 on Linux, macOS and Windows. Dependencies: `httpx`, `pydantic` 2 and `typing-extensions`; `cryptography` only with the `auth` extra.

## Versioning

Semantic versioning. Until 1.0.0 the version stays `0.x` and minor versions may change the public API. Releases are cut by release-please from conventional commits; see [CHANGELOG.md](CHANGELOG.md) once the first release is out. When an endpoint is removed from the API, its method stays for one more minor version and is marked deprecated.

## Contributing and security

See [CONTRIBUTING.md](CONTRIBUTING.md) (how the generated code is produced from `openapi/` and how to run the checks) and [SECURITY.md](SECURITY.md) for reporting vulnerabilities. [`docs/DESIGN.md`](docs/DESIGN.md) is the design contract shared by every Didit server SDK.

## License

MIT
