# Didit server SDKs: shared design contract

This document is identical in every Didit server SDK repository: `sdk-python`, `sdk-node`, `sdk-go`, `sdk-java`, `sdk-php`, `sdk-ruby` and `sdk-dotnet`.
It is the contract that keeps the seven SDKs consistent.
A change to it is made in all seven repositories, in the same words.
Where this document and an SDK disagree, the SDK is wrong.

Version 1, 2026-10-17.

## 1. Goal

A backend developer integrates Didit in minutes, in their own language, with an SDK that feels native to that language.
The SDK covers the whole public server-side API, with real types for every request and response, and it stays current as the API changes.
Quality bar: the official Stripe, OpenAI and Twilio libraries.
The SDKs are thin, predictable and boring: no hidden magic, no framework lock-in, minimal dependencies.

## 2. Repositories and packages

| Language | Repository | Package | Import / namespace | Minimum runtime |
|---|---|---|---|---|
| Python | `didit-protocol/sdk-python` | PyPI `didit-sdk` (see 2.1) | `import didit` | Python 3.10 |
| TypeScript / JavaScript | `didit-protocol/sdk-node` | npm `@didit-protocol/sdk-node` | `import Didit from "@didit-protocol/sdk-node"` | Node 18 (also Bun, Deno, edge runtimes with `fetch`) |
| Go | `didit-protocol/sdk-go` | module `github.com/didit-protocol/sdk-go` | `package didit` | Go 1.22 |
| Java / Kotlin | `didit-protocol/sdk-java` | Maven `me.didit:didit-java` | `me.didit` | Java 11 |
| PHP | `didit-protocol/sdk-php` | Packagist `didit-protocol/sdk-php` | `Didit\` | PHP 8.1 |
| Ruby | `didit-protocol/sdk-ruby` | RubyGems `didit-sdk` (the name `didit` is taken) | `require "didit"`, module `Didit` | Ruby 3.1 |
| C# / .NET | `didit-protocol/sdk-dotnet` | NuGet `Didit` | `namespace Didit` | .NET 8 and .NET Standard 2.0 |

The repository names follow the existing client SDKs (`sdk-web`, `sdk-ios`, `sdk-android`, `sdk-flutter`, `sdk-react-native`).
The Maven group `me.didit` is the one `sdk-android` already publishes under.

### 2.1 Python package name

PyPI `didit` belongs to an unrelated project from 2013.
PyPI `didit-sdk` is a community package by Agustin Saiz (MIT, unofficial, sessions only).
Didit is asking him to transfer the `didit-sdk` project to Didit, so the official SDK ships under that name.
Until the transfer is confirmed, keep `didit-sdk` as the distribution name in `pyproject.toml` and do not publish.
The fallback name, if the transfer does not happen, is `didit-python`.

## 3. Source of truth: the OpenAPI contract

Every SDK is generated from Didit's published OpenAPI documents and checked against them in CI.

| File in `openapi/` | Upstream | Base URL |
|---|---|---|
| `verification.json` | `https://docs.didit.me/openapi-25.json` (mintlify-docs `openapi-25.json`, branch `main`) | `https://verification.didit.me` |
| `account.json` | `https://docs.didit.me/openapi-auth.json` (mintlify-docs `openapi-auth.json`) | `https://apx.didit.me/auth/v2` |
| `overlay.json` | this repository | - |
| `webhook-vectors.json` | generated from `service-didit-verification/src/sessions/utils/webhooks.py` | - |
| `SOURCE.json` | URL, SHA-256 and fetch time of each upstream file | - |

The upstream files are copied byte for byte and never edited by hand.
`overlay.json` holds the SDK naming (section 4) for operations whose upstream definition does not carry it yet.
When an operation carries `x-didit-sdk` upstream, the upstream value wins and the overlay entry is deleted.
The Authentication runtime (section 10) has no OpenAPI document yet; mintlify-docs will publish `openapi-authentication.json`, and until then that module is hand-written from section 10.

### 3.1 Spec sync

Every repository has `.github/workflows/spec-sync.yml`, run daily and on `workflow_dispatch`.
It downloads the upstream files, and when any of them changed it regenerates the code, runs the full test suite and opens a pull request titled `chore(spec): sync API spec YYYY-MM-DD`.
The pull request body lists added, removed and changed operations and schemas, and calls out anything breaking.
A new server operation without SDK naming fails the generator with a message that names the operation; the fix is an entry in `overlay.json` (or upstream).
The sync never deletes a public SDK method silently: a removed operation is marked deprecated for one minor version first, and the pull request says so.

## 4. Naming layer: `x-didit-sdk`

Every operation has an `x-didit-sdk` object:

```json
{"resource": "sessions.imports", "method": "create", "auth": "api_key", "server": true, "scope": "application"}
```

- `resource`: dot path of snake_case resource names; each segment becomes a nested resource accessor.
- `method`: snake_case method name on that resource.
- `auth`: `api_key` (header `x-api-key`), `account_token` (Bearer from `account.login`), `none`, `device_token` or `public`.
- `server`: `false` for operations that use an end-user or device token (`Session-Token`, `X-Transaction-Token`, case-request tokens, Travel Rule pickup and widget links). Server SDKs do not expose them.
- `scope: "application"`: the path starts with `/v3/organization/{organization_id}/application/{application_id}/`. The SDK fills both ids from the client options, so methods never take them as arguments. Calling such a method without both options raises a configuration error before any request is sent.

Convert names to the language's idiom and nothing else:

| Language | Example: `sessions.imports.create` |
|---|---|
| Python | `client.sessions.imports.create(...)` and `await client.sessions.imports.create(...)` on `AsyncDidit` |
| TypeScript | `await didit.sessions.imports.create({...})` |
| Go | `client.Sessions.Imports.Create(ctx, params)` |
| Java | `client.sessions().imports().create(params)` plus `createAsync` returning `CompletableFuture` |
| PHP | `$didit->sessions->imports->create([...])` |
| Ruby | `didit.sessions.imports.create(...)` |
| C# | `await client.Sessions.Imports.CreateAsync(...)` |

The full resource tree (version 1, 248 server operations in 47 resources) is in `overlay.json`.
Highlights: `sessions`, `sessions.imports`, `sessions.reviews`, the standalone APIs (`id_verification.verify`, `face_match.compare`, `face_search.search`, `passive_liveness.check`, `age_estimation.estimate`, `proof_of_address.verify`, `document_ai.analyze`, `aml.screen`, `database_validation.validate`, `phone.send_code`, `email.check_code`, `ip.assess_risk`, `kyb.search`), `id_wallets`, `fraud_checks`, `users`, `businesses`, `transactions`, `transactions.rules`, `transactions.travel_rule`, `wallet_screening`, `travel_rule`, `travel_rule.wallet_addresses`, `workflows`, `questionnaires`, `webhooks.destinations`, `billing`, `biometric_templates`, `customization`, `cases` (with `notes`, `links`, `checklist`, `requests`, `teams`, `routing_rules`, `blueprints`, `regulatory_reports`), `regulatory_reports`, `report_templates`, `networks`, and `account` (`account.organizations`, `account.applications`).

## 5. Architecture

Two layers, kept strictly apart.

**Generated layer** (`resources/` and `types/` or the language equivalent): one class or module per resource, one method per operation, one type per request and response schema.
Every generated file starts with `Code generated by codegen from openapi/*.json. DO NOT EDIT.`
CI regenerates and fails when the result differs from what is committed.
The generator lives in the repository (`codegen/`), is written in the SDK's own language or in Python, and reads only `openapi/`.

**Core layer** (hand-written, small, fully tested): configuration, HTTP transport, authentication headers, retries, timeouts, errors, pagination, multipart and binary bodies, webhook verification (section 9) and the Authentication helpers (section 10).

### 5.1 Type naming

- A `$ref` component keeps its component name in the language's case (`SessionDecision`).
- An inline request body becomes `<Resource><Method>Params` (`SessionsImportsCreateParams`); an inline response becomes `<Resource><Method>Response`.
- Inline nested objects take their parent's name plus the property name (`SessionsCreateParamsContactDetails`).
- Enums are open: unknown values from the API must never raise. Python uses `Literal[...] | str`; TypeScript a string union plus `(string & {})`; Go, Java and C# a string-backed type with constants for the known values; PHP string constants; Ruby frozen string constants.
- Unknown response fields are preserved and readable (forward compatibility), never dropped and never an error.
- Distinguish absent from `null` where the language allows it (Python `NotGiven`, TypeScript optional versus `| null`, Go `Opt[T]`, Java `Optional`/`JsonNullable`, C# `Optional<T>`).
- Date-time strings are exposed as the language's date-time type; money and score fields keep the spec's type (string decimals stay strings).

## 6. The client

```text
Didit(api_key, base_url?, organization_id?, application_id?, timeout = 60s, max_retries = 2, default_headers?, http_client?)
```

- `api_key` falls back to the `DIDIT_API_KEY` environment variable; `organization_id` and `application_id` to `DIDIT_ORGANIZATION_ID` and `DIDIT_APPLICATION_ID`.
- `base_url` defaults to `https://verification.didit.me`; `account_base_url` to `https://apx.didit.me/auth/v2`.
- Every option can be overridden per request (`with_options(...)` or a request options argument).
- Headers on every request: `x-api-key`, `User-Agent: didit-<language>/<version> (<runtime> <version>; <os>)`, `X-Didit-Client: <language>/<version>`, `Accept: application/json`.
- The API key is never logged, never included in an error message and never sent to any origin other than `base_url` (a pagination `next` URL on another origin is refused).
- Optional debug logging (`DIDIT_LOG=debug`) prints method, path, status, duration and request id, never bodies or headers.
- Thread-safe and reusable: one client per process is the documented pattern.

## 7. Errors, retries and timeouts

| Error | When |
|---|---|
| `DiditError` | base of everything below |
| `APIConnectionError` / `APITimeoutError` | no response |
| `APIStatusError` | any non-2xx, with `status`, `body` (parsed JSON when possible), `headers`, `request_id` |
| `BadRequestError` 400, `AuthenticationError` 401, `PermissionDeniedError` 403, `NotFoundError` 404, `ConflictError` 409, `UnprocessableEntityError` 422, `RateLimitError` 429, `InternalServerError` 5xx | subclasses of `APIStatusError` |
| `WebhookVerificationError` | section 9, with a machine-readable `reason` |
| `ConfigurationError` | missing API key, missing organization or application id |

Retries: up to `max_retries` (default 2), exponential backoff starting at 0.5 s with full jitter, capped at 8 s, honouring `Retry-After` (seconds or HTTP date, capped at 60 s).
Retry on connection errors, timeouts, 408, 429 and 5xx for `GET`, `HEAD`, `PUT` and `DELETE`.
Never retry `POST` or `PATCH` after the request may have reached the server (a 5xx or a read timeout); retry them only on a connection that failed before sending, or on 429.
Every response exposes the raw HTTP response (status, headers, request id) through the language's usual pattern (`with_raw_response`, `.asResponse()`, a `Response` field).

## 8. Lists, files and binary responses

- Lists use `limit` and `offset` and return `{count, next, previous, results}`. The SDK returns a page object with those fields plus auto-pagination: Python `for x in client.sessions.list(...)` and `async for`, TypeScript `for await`, Go an iterator (`iter.Seq2`), Java `Iterable` and `autoPager()`, PHP and Ruby `each`/`auto_paging_each`, C# `IAsyncEnumerable`.
- Multipart operations (standalone APIs with images, document uploads, face uploads) accept a path, bytes or a stream, with an optional file name and content type.
- Binary responses (PDF reports, network reports, wallet screening PDFs) return bytes or a stream, never parsed JSON.

## 9. Webhooks

`webhooks.verify(raw_body, headers, secret, tolerance = 300, allow_simple = false)` returns the typed event or raises `WebhookVerificationError`.
`secret` may be one secret or a list (rotation).
A second entry point, `webhooks.verify_parsed(payload, headers, secret)`, exists for frameworks that only expose the parsed JSON body; it can check `X-Signature-V2` only.
Ship the verifier in the core with no framework dependency; framework examples (FastAPI, Django, Flask, Express, Next.js, Gin, Spring Boot, Laravel, Symfony, Rails, ASP.NET Core) live in `examples/`, not in the package.

### 9.1 What Didit sends

From `build_webhook_signature_headers` in `service-didit-verification/src/sessions/utils/webhooks.py`:

- The body is `json.dumps(shorten_floats(payload), sort_keys=True, separators=(",", ":"))` in UTF-8, with Python's default `ensure_ascii=True` (non-ASCII as `\uXXXX`).
- `X-Signature`: lowercase hex HMAC-SHA256 of the exact body bytes.
- `X-Signature-V2`: lowercase hex HMAC-SHA256 of the canonical JSON (9.2). Recommended, because it survives middleware that re-encodes the body.
- `X-Signature-Simple` (deprecated, envelope only): HMAC-SHA256 of `"{timestamp}:{session_id}:{status}:{webhook_type}"`, missing fields as empty strings.
- During a secret rotation the same three signatures made with the previous secret arrive as `X-Signature-Previous`, `X-Signature-V2-Previous` and `X-Signature-Simple-Previous`.
- `X-Timestamp`: unix seconds, equal to the body's `timestamp`.
- The HMAC key is the secret's UTF-8 bytes.

### 9.2 Canonical JSON (what `X-Signature-V2` signs)

Parse the body, then serialise it exactly like Python's `json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)` after `shorten_floats`:

- Objects: keys sorted by Unicode code point (not UTF-16 code unit order), written as `{"k":v,...}` with no whitespace.
- Strings: escape `"` as `\"`, `\` as `\\`, and `\n`, `\r`, `\t`, `\b`, `\f` with their short escapes; every other character below U+0020 as `\u00XX` with lowercase hex; everything else literal UTF-8 (including `/`, U+007F, U+2028 and U+2029).
- Numbers: a float with an integral value is written as an integer (`87.0` becomes `87`, `1e16` becomes `10000000000000000`); integers in plain decimal; other floats in Python `repr` form, which is the shortest round-trip digits with scientific notation when the decimal exponent is below -4 or at least 16, written `1e-05`, `1e-07`, `1.5e-05` (sign always, at least two exponent digits).
- `true`, `false`, `null` as is.

Implementations must parse numbers losslessly where the language allows it (Go `json.Number`, Java `BigDecimal`, C# `JsonElement` raw text, Python and Ruby native), so integers above 2^53 survive.
In TypeScript, canonicalise from the raw body with a token-preserving parser, because `JSON.parse` loses precision on such integers.

### 9.3 Verification rules

1. Read the timestamp from the body's `timestamp` (an integer); if `X-Timestamp` is present it must be equal (`timestamp_mismatch`).
2. Reject when `|now - timestamp| > tolerance` (`timestamp_out_of_tolerance`).
3. For each secret, accept when `X-Signature` matches the HMAC of the raw body, or `X-Signature-V2` matches the HMAC of the canonical JSON, or their `-Previous` variants match.
4. `X-Signature-Simple` (and its `-Previous`) counts only with `allow_simple = true`; even then the result says the body is unauthenticated, and the docs tell the receiver to re-fetch the record from the API.
5. Compare in constant time, and only well-formed 64-character lowercase hex values.
6. No signature header at all is `missing_signature`; no match is `invalid_signature`; an empty secret is a `ConfigurationError`.

`openapi/webhook-vectors.json` holds vectors produced by running the backend's own signing functions.
Every SDK test suite runs every vector and asserts the expected outcome, and asserts its canonical JSON equals `canonical_v2` byte for byte.

### 9.4 Typed events

Parse the verified body into a discriminated union on `webhook_type`: `status.updated`, `data.updated`, `user.status.updated`, `user.data.updated`, `business.status.updated`, `business.data.updated`, `activity.created`, `transaction.created`, `transaction.status.updated`, `travel_rule.status.updated`, `workflow.compliance_changed`, `kyb.registry_search.resolved`, plus an `UnknownEvent` that keeps the raw payload for any other type.
Envelope fields on every event: `event_id`, `webhook_type`, `timestamp`, `created_at`, `application_id`, `environment` (`live` or `sandbox`).
Session events add `session_id`, `business_session_id`, `session_kind`, `status`, `workflow_id`, `workflow_version`, `vendor_data`, `metadata`, `decision`, `resubmit_info`; transaction events add `transaction_id`, `txn_id`, `status`, `score`, `severity`, `amount`, `currency`, `direction`, `action_required`; Travel Rule events add `transaction_id`, `txn_id`, `travel_rule_status`, `rail`, `direction`; user and business events add `vendor_user_id` or `vendor_business_id`, `vendor_data`, `status`.
Where the spec has a schema for the payload (for example the session decision), reuse the generated type.

## 10. Authentication (Didit customer authentication)

Didit Authentication gives each application its own OpenID Connect issuer for the application's end users: hosted sign-in pages, passwords, codes, magic links, passkeys, social and enterprise SSO, MFA, organizations, step-up verification and agent access.
Source: `service-didit-auth/src/authentication/` (README, `urls.py`, `runtime_urls.py`, `host_urls.py`) on `development`; docs in mintlify-docs `authentication/` and `quickstarts/`.
It is in early access and reaches production in the 2026-11-01 release.

The server SDKs ship an `authentication` module for the customer's backend.
It never takes the API key: it talks to the application's issuer (`https://<slug>.auth.didit.me` or the customer's own domain), whose discovery document is `/.well-known/openid-configuration`.

- `Authentication(issuer)` or `Authentication.from_publishable_key("pk_live_..." | "pk_test_...")` (the key carries the base64url issuer).
- Discovery and JWKS fetched lazily and cached, honouring `Cache-Control` (5 minutes today); an unknown `kid` triggers at most one refetch per minute.
- `verify_access_token(token, audience?)`: ES256 only (reject `none`, HS*, RS* and any other algorithm), header `typ` `at+jwt`, `iss` equal to the issuer, `aud` when given, `exp`, `nbf` and `iat` with 60 s leeway. Returns typed claims: `iss`, `aud`, `client_id`, `sub`, `sid`, `jti`, `iat`, `exp`, `vendor_data`, `amr`, `org` (`id`, `role`), `verified`, `act`.
- `verify_id_token(token, nonce, audience)`: same checks plus `nonce`; claims add `auth_time`, `email`, `email_verified`, `name`, `phone_number`.
- `create_pkce()` (S256 verifier and challenge), `create_state()` and `create_nonce()`.
- `exchange_code(code, code_verifier, redirect_uri)` and `refresh(refresh_token)` against `POST token/`; document that refreshes for one session must be serialised, because reusing a consumed refresh token revokes the session.
- `get_session(access_token)` (`GET session/`) for instant revocation checks, and `revoke_session(access_token)` (`DELETE session/`).
- `create_step_up(access_token, action, amount?, currency?, return_to?)` (`POST step-up/`) and `retrieve_step_up(access_token, id)`; document that the backend acts only on status `approved`.
- Browser-only routes (hosted pages, password, email and phone codes, passkeys, MFA, social, SSO) are out of scope.
- The console management API for Authentication uses console sessions, not API keys, so it is out of scope until it accepts API keys.
- Authentication events do not exist as webhooks yet; do not invent `auth.*` webhook types.

Tests use a locally generated ES256 key pair and a stubbed issuer; never call a real issuer in unit tests.

## 11. Tests and quality gates

- Unit tests for the core: configuration, headers, errors per status, retry policy (including the no-retry cases for `POST`), `Retry-After`, timeouts, pagination, multipart, binary responses, origin check, redaction.
- Generated tests: one test per server operation from the spec's examples, with a mocked HTTP layer, asserting method, path (ids filled, application scope expanded), query, body encoding and response parsing.
- Contract test: every `server: true` operation in `openapi/` has exactly one SDK method, and nothing else exists.
- Webhook vectors (9.3) and Authentication token tests (10).
- Optional live smoke tests against a sandbox application, run only when `DIDIT_SANDBOX_API_KEY` is set; never in default CI; they create nothing that costs money beyond sandbox sessions.
- Strict static checks: Python `mypy --strict` and `pyright`, ruff; TypeScript `strict` with no `any` in public types, eslint; Go `go vet`, `staticcheck`, `golangci-lint`; Java `-Werror` with errorprone and nullness annotations; PHP PHPStan level max and PHP-CS-Fixer; Ruby RBS signatures checked with Steep, RuboCop; C# nullable enabled with warnings as errors.
- CI matrix over every supported runtime version on Linux, plus macOS and Windows where the language is commonly used there.
- Coverage of the core at 90 % or more; the number is not a substitute for behaviour tests.

## 12. Dependencies

Minimal and mainstream.
Python: `httpx`, `pydantic>=2`, `typing-extensions`, and `cryptography` only for the Authentication module (optional extra `didit-sdk[auth]`).
TypeScript: no runtime dependencies (`fetch`, `crypto.subtle`).
Go: standard library only.
Java: `java.net.http` and Jackson.
PHP: PSR-18 and PSR-17 with discovery, Guzzle as the suggested default, `firebase/php-jwt` or an equivalent only for Authentication.
Ruby: `net/http` from the standard library, `jwt` only for Authentication.
.NET: `System.Net.Http`, `System.Text.Json`, `Microsoft.IdentityModel.Tokens` only for Authentication.

## 13. Versioning and release

- Semantic versioning; a breaking change to the public SDK surface is a major version.
- Releases are cut by release-please from conventional commits; `CHANGELOG.md` is generated and never edited by hand.
- Release workflows publish with trusted publishing where the registry supports it (PyPI, npm with provenance, RubyGems and NuGet), Maven Central through the Central Portal with signed artifacts (token and signing key in the `maven-central` environment), Packagist through its GitHub hook, and Go module tags announced to proxy.golang.org.
- 1.0.0 shipped on 2026-10-29 with Alex's approval, and the repositories are public.
- Every release after that publishes straight from the repository: merging the release-please pull request is the approval, and the workflow creates the vX.Y.Z tag and publishes.
- A release created with `GITHUB_TOKEN` does not trigger other workflows, so a repository that publishes from a separate `release.yml` has release-please start it with `workflow_dispatch` for the new tag. No personal access token is stored.

## 14. Documentation and positioning

- README: one-line pitch ("The official Didit <language> library"), install, a quickstart (create a session, read the decision, verify a webhook), configuration, errors, pagination, webhooks, Authentication, links to docs.didit.me, supported runtimes, and versioning policy.
- `examples/`: runnable examples for the main flows (KYC session, standalone ID verification, AML screening, transaction screening, Travel Rule, Authentication token verification) and webhook receivers for the popular frameworks.
- Package metadata with description, keywords (identity verification, KYC, KYB, AML, liveness, transaction monitoring, Travel Rule, Didit), homepage `https://didit.me`, docs `https://docs.didit.me`, repository and license.
- docs.didit.me gets a Server SDKs section and per-operation code samples in every language (OpenAPI `x-codeSamples`), published together with the first release.
- License MIT (`Copyright (c) 2026 Didit`), like the client SDKs. `SECURITY.md` points to GitHub private vulnerability reporting and support@didit.me.

## 15. Keeping SDKs current (the rule)

Any change to a public API endpoint, parameter, request or response field, enum value, error, webhook payload or authentication flow in `service-didit-verification` or `service-didit-auth` must update the OpenAPI documents in mintlify-docs in the same change set.
The spec sync (3.1) then opens a pull request in every SDK repository; whoever changed the backend makes sure those pull requests merge, adding hand-written core changes (webhooks, Authentication) where the change needs them.
The rule lives in `CLAUDE.md` and `AGENTS.md` of the backends, of mintlify-docs, of every SDK repository, and of the Didit workspace.
