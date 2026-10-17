"""``Authentication`` and ``AsyncAuthentication`` (docs/DESIGN.md section 10).

Everything that decides what is sent, what is cached and whether a token is
valid lives in :class:`_AuthenticationBase` and the pure helpers it calls;
:class:`Authentication` and :class:`AsyncAuthentication` only differ in how they
send a request and which lock guards a fetch.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
import urllib.parse
import weakref
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from types import TracebackType
from typing import Any, TypeVar, Union, cast

import httpx
from typing_extensions import Self

from .._exceptions import (
    APIConnectionError,
    APIResponseValidationError,
    APITimeoutError,
    ConfigurationError,
    _request_id,  # pyright: ignore[reportPrivateUsage]
    make_status_error,
)
from .._models import BaseModel, validate_response
from .._utils import client_header, encode_path, user_agent
from ._cache import Discovery, IssuerCache, KeySet, parse_discovery, parse_key_set
from ._crypto import verify_es256
from ._errors import TokenVerificationError
from ._issuer import issuer_from_publishable_key, normalise_issuer
from ._jwt import ParsedToken, TokenKind, check_claims, parse_token
from ._pkce import create_nonce as _create_nonce
from ._pkce import create_pkce as _create_pkce
from ._pkce import create_state as _create_state
from ._types import (
    AccessTokenClaims,
    AuthenticationSession,
    IdTokenClaims,
    StepUp,
    StepUpAction,
    TokenResponse,
)

__all__ = [
    "DEFAULT_LEEWAY",
    "DEFAULT_TIMEOUT",
    "Amount",
    "AsyncAuthentication",
    "Audience",
    "Authentication",
]

log = logging.getLogger("didit")

DEFAULT_TIMEOUT = 10.0
DEFAULT_LEEWAY = 60
_DISCOVERY_PATH = ".well-known/openid-configuration"
_JWKS_PATH = ".well-known/jwks.json"
_TOKEN_PATH = "token/"  # noqa: S105 - a path, not a secret
_SESSION_PATH = "session/"
_STEP_UP_PATH = "step-up/"

Audience = Union[str, Sequence[str]]
"""One audience (the application id) or several, any of which is accepted."""
Amount = Union[str, int, float, Decimal]
"""A money amount; sent as a decimal string."""

ModelT = TypeVar("ModelT", bound=BaseModel)


@dataclass(frozen=True)
class _Call:
    """One request to the issuer, before it is bound to an HTTP client."""

    method: str
    url: str
    bearer: str | None = None
    form: Mapping[str, str] | None = None
    json_body: Mapping[str, object] | None = None
    secrets: tuple[str, ...] = ()
    """Values redacted from error messages: tokens, codes and verifiers."""


def _required_text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is empty.")
    return value.strip()


def _amount_text(amount: Amount) -> str:
    if isinstance(amount, bool) or not isinstance(amount, (str, int, float, Decimal)):  # pyright: ignore[reportUnnecessaryIsInstance]
        raise TypeError("amount must be a decimal string, an int, a float or a Decimal.")
    try:
        value = Decimal(repr(amount)) if isinstance(amount, float) else Decimal(amount)
    except InvalidOperation as exc:
        raise ValueError(f"amount must be a decimal number, got {amount!r}.") from exc
    if not value.is_finite():
        raise ValueError(f"amount must be a finite number, got {amount!r}.")
    if isinstance(amount, str):
        return amount.strip()
    return format(value, "f")


class _AuthenticationBase:
    """Configuration, request building, response parsing and token checks shared by
    the sync and async classes. Nothing here does I/O."""

    issuer: str
    """The issuer every token must name in ``iss``, without a trailing slash."""
    client_id: str | None
    """The application id: sent with token requests and the default audience."""
    timeout: float | httpx.Timeout
    leeway: float
    """Seconds of clock skew allowed for ``exp``, ``nbf`` and ``iat``."""

    create_pkce = staticmethod(_create_pkce)
    create_state = staticmethod(_create_state)
    create_nonce = staticmethod(_create_nonce)

    def __init__(
        self,
        issuer: str,
        *,
        client_id: str | None,
        timeout: float | httpx.Timeout,
        leeway: float,
    ) -> None:
        self.issuer = normalise_issuer(issuer)
        if client_id is not None and (not isinstance(client_id, str) or not client_id.strip()):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise ConfigurationError(
                "client_id is empty: pass your application id or leave it out."
            )
        self.client_id = client_id.strip() if client_id else None
        if isinstance(leeway, bool) or not isinstance(leeway, (int, float)) or not leeway >= 0:  # pyright: ignore[reportUnnecessaryIsInstance]
            raise ConfigurationError("leeway must be 0 or more seconds.")
        self.leeway = float(leeway)
        self.timeout = timeout
        self._cache = IssuerCache()
        self._now: Callable[[], float] = time.time

    def __repr__(self) -> str:
        return f"{type(self).__name__}(issuer={self.issuer!r}, client_id={self.client_id!r})"

    # Requests ---------------------------------------------------------------

    def _url(self, path: str) -> str:
        return f"{self.issuer}/{path}"

    def _discovery_call(self) -> _Call:
        return _Call("GET", self._url(_DISCOVERY_PATH))

    def _jwks_call(self, discovery: Discovery) -> _Call:
        return _Call("GET", discovery.jwks_uri or self._url(_JWKS_PATH))

    @staticmethod
    def _exchange_form(
        code: str, code_verifier: str, redirect_uri: str
    ) -> tuple[dict[str, str], tuple[str, ...]]:
        code = _required_text(code, "code")
        code_verifier = _required_text(code_verifier, "code_verifier")
        form = {
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": code_verifier,
            "redirect_uri": _required_text(redirect_uri, "redirect_uri"),
        }
        return form, (code, code_verifier)

    @staticmethod
    def _refresh_form(refresh_token: str) -> tuple[dict[str, str], tuple[str, ...]]:
        refresh_token = _required_text(refresh_token, "refresh_token")
        return {"grant_type": "refresh_token", "refresh_token": refresh_token}, (refresh_token,)

    def _token_call(
        self, discovery: Discovery, form: dict[str, str], secrets: tuple[str, ...]
    ) -> _Call:
        if self.client_id:
            form = {**form, "client_id": self.client_id}
        url = discovery.token_endpoint or self._url(_TOKEN_PATH)
        return _Call("POST", url, form=form, secrets=secrets)

    def _session_call(self, method: str, access_token: str) -> _Call:
        token = _required_text(access_token, "access_token")
        return _Call(method, self._url(_SESSION_PATH), bearer=token, secrets=(token,))

    def _create_step_up_call(
        self,
        access_token: str,
        *,
        action: StepUpAction | str,
        amount: Amount | None,
        currency: str | None,
        return_to: str | None,
    ) -> _Call:
        token = _required_text(access_token, "access_token")
        body: dict[str, object] = {"action": _required_text(action, "action")}
        if amount is not None:
            body["amount"] = _amount_text(amount)
        if currency is not None:
            body["currency"] = currency
        if return_to is not None:
            body["return_to"] = return_to
        return _Call(
            "POST", self._url(_STEP_UP_PATH), bearer=token, json_body=body, secrets=(token,)
        )

    def _retrieve_step_up_call(self, access_token: str, step_up_id: str) -> _Call:
        token = _required_text(access_token, "access_token")
        path = encode_path(_STEP_UP_PATH + "{step_up_id}/", {"step_up_id": step_up_id})
        return _Call("GET", self._url(path), bearer=token, secrets=(token,))

    def _build(self, call: _Call, client: httpx.Client | httpx.AsyncClient) -> httpx.Request:
        headers = {
            "Accept": "application/json",
            "User-Agent": user_agent(),
            "X-Didit-Client": client_header(),
        }
        if call.bearer is not None:
            headers["Authorization"] = f"Bearer {call.bearer}"
        content: bytes | None = None
        if call.form is not None:
            headers["Content-Type"] = "application/x-www-form-urlencoded"
            content = urllib.parse.urlencode(call.form).encode("ascii")
        elif call.json_body is not None:
            headers["Content-Type"] = "application/json"
            content = json.dumps(call.json_body, separators=(",", ":")).encode("utf-8")
        return client.build_request(
            call.method, call.url, headers=headers, content=content, timeout=self.timeout
        )

    # Responses --------------------------------------------------------------

    @staticmethod
    def _transport_error(exc: httpx.HTTPError, request: httpx.Request) -> APIConnectionError:
        if isinstance(exc, httpx.TimeoutException):
            return APITimeoutError(request=request)
        return APIConnectionError(request=request)

    @staticmethod
    def _log(request: httpx.Request, response: httpx.Response, started: float) -> None:
        if log.isEnabledFor(logging.DEBUG):
            log.debug(
                "%s %s -> %d in %.0f ms (request id %s)",
                request.method,
                request.url.path,
                response.status_code,
                (time.monotonic() - started) * 1000,
                _request_id(response.headers) or "-",
            )

    @staticmethod
    def _read(call: _Call, response: httpx.Response) -> object:
        if not response.is_success:
            body: object
            try:
                body = response.json()
            except ValueError:
                body = response.text or None
            raise make_status_error(response, body, redact=call.secrets)
        if response.status_code == 204 or not response.content:
            return None
        try:
            return response.json()
        except ValueError as exc:
            raise APIResponseValidationError(
                response=response,
                message=(
                    f"Expected a JSON response from {call.method} {httpx.URL(call.url).path}, "
                    f"got {response.headers.get('content-type', 'no content type')}."
                ),
            ) from exc

    def _model(self, call: _Call, response: httpx.Response, model: type[ModelT]) -> ModelT:
        data = self._read(call, response)
        if not isinstance(data, dict):
            raise APIResponseValidationError(
                response=response,
                message=f"Expected a JSON object from {call.method} {httpx.URL(call.url).path}.",
            )
        return cast("ModelT", validate_response(model, cast("dict[str, Any]", data)))

    def _store_discovery(self, call: _Call, response: httpx.Response) -> Discovery:
        discovery = parse_discovery(self._read(call, response))
        if discovery is None:
            raise APIResponseValidationError(
                response=response, message="The issuer's discovery document is not a JSON object."
            )
        if discovery.issuer is None:
            raise APIResponseValidationError(
                response=response,
                message=f"The discovery document at {call.url} names no issuer.",
            )
        if discovery.issuer != self.issuer:
            raise ConfigurationError(
                f"The discovery document at {call.url} names the issuer {discovery.issuer!r}, "
                f"not {self.issuer!r}. Configure Authentication with {discovery.issuer!r} "
                "(an application's issuer changes when its custom domain is activated)."
            )
        # Codes and refresh tokens go to the token endpoint, and the keys decide which
        # tokens are trusted: neither may downgrade to plain http, and tokens never
        # leave the issuer's own origin.
        issuer = httpx.URL(self.issuer)
        for name, value, same_origin in (
            ("token_endpoint", discovery.token_endpoint, True),
            ("jwks_uri", discovery.jwks_uri, False),
        ):
            if value is None:
                continue
            url = httpx.URL(value)
            if url.scheme != "https" and url.scheme != issuer.scheme:
                raise APIResponseValidationError(
                    response=response,
                    message=f"The discovery document's {name} {value!r} does not use https.",
                )
            if same_origin and (url.scheme, url.host, url.port) != (
                issuer.scheme,
                issuer.host,
                issuer.port,
            ):
                raise APIResponseValidationError(
                    response=response,
                    message=(
                        f"The discovery document's {name} {value!r} is not on the issuer's "
                        f"origin {self.issuer!r}."
                    ),
                )
        return self._cache.store_discovery(discovery, response.headers)

    def _store_key_set(self, call: _Call, response: httpx.Response) -> KeySet:
        key_set = parse_key_set(self._read(call, response))
        if key_set is None:
            raise APIResponseValidationError(
                response=response, message='The issuer\'s JWKS is not a key set ({"keys": [...]}).'
            )
        return self._cache.store_key_set(key_set, response.headers)

    # Token checks -----------------------------------------------------------

    def _audience(self, audience: Audience | None, *, required: bool) -> tuple[str, ...] | None:
        if audience is None:
            if self.client_id:
                return (self.client_id,)
            if required:
                raise ConfigurationError(
                    "verify_id_token needs the audience: pass audience=<application id>, "
                    "or client_id=<application id> to the Authentication client."
                )
            return None
        values = (audience,) if isinstance(audience, str) else tuple(audience)
        if not values or any(not isinstance(v, str) or not v for v in values):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise ValueError("audience must be a non-empty string or a list of them.")
        return values

    @staticmethod
    def _nonce(nonce: str | None) -> str | None:
        if nonce is not None and (not isinstance(nonce, str) or not nonce):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise ValueError("nonce is empty: pass the nonce of this sign-in, or None.")
        return nonce

    def _finish(
        self,
        parsed: ParsedToken,
        key_set: KeySet,
        model: type[ModelT],
        *,
        kind: TokenKind,
        audience: tuple[str, ...] | None,
        nonce: str | None,
    ) -> ModelT:
        key = key_set.public_key(parsed.kid)
        if not verify_es256(key, parsed.signing_input, parsed.signature):
            raise TokenVerificationError(
                "invalid_signature", "The token's signature does not verify with the issuer's key."
            )
        check_claims(
            parsed.claims,
            kind=kind,
            issuer=self.issuer,
            audience=audience,
            nonce=nonce,
            leeway=self.leeway,
            now=self._now(),
        )
        return cast("ModelT", validate_response(model, parsed.claims))


class Authentication(_AuthenticationBase):
    """Didit Authentication for your backend: verify the tokens your application's
    issuer signs and call its token, session and step-up endpoints.

        from didit.authentication import Authentication

        auth = Authentication.from_publishable_key("pk_live_...", client_id=APPLICATION_ID)
        claims = auth.verify_access_token(access_token)
        print(claims.sub, claims.vendor_data)

    It never takes or sends your Didit API key. Discovery and the issuer's keys
    are fetched on first use and cached; one instance per process is the
    intended use and is thread safe. Token verification needs the ``auth``
    extra: ``pip install 'didit-sdk[auth]'``.
    """

    _client: httpx.Client

    def __init__(
        self,
        issuer: str,
        *,
        client_id: str | None = None,
        http_client: httpx.Client | None = None,
        timeout: float | httpx.Timeout = DEFAULT_TIMEOUT,
        leeway: float = DEFAULT_LEEWAY,
    ) -> None:
        """``issuer`` is the application's issuer: ``https://<slug>.auth.didit.me``,
        ``https://<slug>.sandbox.auth.didit.me`` or its active custom domain.
        ``client_id`` is the application id; when set it is sent with token
        requests (the issuer checks it) and is the default audience."""
        super().__init__(issuer, client_id=client_id, timeout=timeout, leeway=leeway)
        if http_client is not None and not isinstance(http_client, httpx.Client):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise ConfigurationError(
                "http_client must be an httpx.Client (use AsyncAuthentication for httpx.AsyncClient)."
            )
        self._owns_client = http_client is None
        self._client = http_client or httpx.Client(follow_redirects=False)
        self._lock = threading.Lock()

    @classmethod
    def from_publishable_key(
        cls,
        publishable_key: str,
        *,
        client_id: str | None = None,
        http_client: httpx.Client | None = None,
        timeout: float | httpx.Timeout = DEFAULT_TIMEOUT,
        leeway: float = DEFAULT_LEEWAY,
    ) -> Self:
        """The client for the issuer a ``pk_live_`` or ``pk_test_`` publishable key carries."""
        return cls(
            issuer_from_publishable_key(publishable_key),
            client_id=client_id,
            http_client=http_client,
            timeout=timeout,
            leeway=leeway,
        )

    def close(self) -> None:
        """Close the HTTP connection pool (only if this client created it)."""
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    # Tokens -----------------------------------------------------------------

    def verify_access_token(
        self, token: str, audience: Audience | None = None
    ) -> AccessTokenClaims:
        """Verify an access token offline and return its claims.

        Checks, in order: the header (``alg`` ES256 only, so ``none``, HS*, RS*,
        PS*, EdDSA and every other algorithm are refused; ``typ`` ``at+jwt``), the
        ES256 signature against the issuer's published key with the token's
        ``kid``, then ``iss`` (equal to the issuer), ``sub``, ``exp``, ``nbf`` and
        ``iat`` (with ``leeway`` seconds of clock skew) and, when ``audience`` is
        given or ``client_id`` is configured, ``aud``.

        An offline check cannot see a session revoked a moment ago: access
        tokens expire within five minutes. Call ``get_session`` when the action
        needs an instant revocation check.

        Raises :class:`TokenVerificationError` with a machine-readable ``reason``.
        """
        expected = self._audience(audience, required=False)
        parsed = parse_token(token, "access")
        key_set = self._key_set_for(parsed.kid)
        return self._finish(
            parsed, key_set, AccessTokenClaims, kind="access", audience=expected, nonce=None
        )

    def verify_id_token(
        self, token: str, *, nonce: str | None, audience: Audience | None = None
    ) -> IdTokenClaims:
        """Verify an ID token and return its claims.

        The same checks as :meth:`verify_access_token` (``typ`` must be ``JWT`` or
        absent, never ``at+jwt``), plus ``aud``, which is always checked: pass
        ``audience`` or configure ``client_id``. ``nonce`` must equal the
        ``nonce`` you sent with the authorization request; pass ``None`` only for
        an ID token returned by :meth:`refresh`, which carries no nonce.
        """
        expected = self._audience(audience, required=True)
        nonce = self._nonce(nonce)
        parsed = parse_token(token, "id")
        key_set = self._key_set_for(parsed.kid)
        return self._finish(
            parsed, key_set, IdTokenClaims, kind="id", audience=expected, nonce=nonce
        )

    def exchange_code(self, code: str, *, code_verifier: str, redirect_uri: str) -> TokenResponse:
        """Exchange an authorization code for tokens (``POST token/``, form encoded).

        Check the callback's ``state`` first. The code is single use and expires
        after 60 seconds; ``code_verifier`` is the PKCE verifier of this sign-in
        and ``redirect_uri`` must be exactly the one the sign-in used. Token
        requests are never retried.
        """
        form, secrets = self._exchange_form(code, code_verifier, redirect_uri)
        call = self._token_call(self._discovery(), form, secrets)
        return self._model(call, self._send(call), TokenResponse)

    def refresh(self, refresh_token: str) -> TokenResponse:
        """Swap a refresh token for new tokens (``POST token/``, form encoded).

        Refresh tokens are single use: replace both tokens with the result.
        Serialise refreshes for one session (one at a time, across processes
        and browser tabs), because presenting a refresh token that was already
        used revokes the whole session. For the same reason this request is
        never retried; if its outcome is unknown, sign the person in again.
        """
        form, secrets = self._refresh_form(refresh_token)
        call = self._token_call(self._discovery(), form, secrets)
        return self._model(call, self._send(call), TokenResponse)

    # Sessions and step-ups --------------------------------------------------

    def get_session(self, access_token: str) -> AuthenticationSession:
        """The live session behind ``access_token`` (``GET session/``).

        The instant revocation check: unlike :meth:`verify_access_token` it fails
        (``AuthenticationError``, HTTP 401) as soon as the session is revoked,
        expired or idle, or the token was replaced by a refresh. Agent access
        tokens are refused here.
        """
        call = self._session_call("GET", access_token)
        return self._model(call, self._send(call), AuthenticationSession)

    def revoke_session(self, access_token: str) -> None:
        """Sign the person out: revoke the session behind ``access_token`` (``DELETE session/``)."""
        call = self._session_call("DELETE", access_token)
        self._read(call, self._send(call))

    def create_step_up(
        self,
        access_token: str,
        *,
        action: StepUpAction | str,
        amount: Amount | None = None,
        currency: str | None = None,
        return_to: str | None = None,
    ) -> StepUp:
        """Ask whether the person must verify before a sensitive action (``POST step-up/``).

        ``action`` is ``payout`` (with ``amount`` and an optional three-letter
        ``currency``), ``bank`` or ``contact``. ``return_to`` is where the person
        comes back after verifying and must be one of the application's
        registered redirect URIs; the issuer currently requires it on every
        call and answers HTTP 400 (``BadRequestError``) without it.

        ``required=False`` means no rule applies and the action may go ahead.
        Otherwise send the person to ``verification_url``; they return to
        ``return_to`` with ``step_up=<id>&status=approved``, which proves
        nothing: call :meth:`retrieve_step_up` and act only on status
        ``approved``.
        """
        call = self._create_step_up_call(
            access_token, action=action, amount=amount, currency=currency, return_to=return_to
        )
        return self._model(call, self._send(call), StepUp)

    def retrieve_step_up(self, access_token: str, step_up_id: str) -> StepUp:
        """Read a step-up (``GET step-up/{id}/``) with a token of the session that
        asked for it. Act only when its status is ``approved`` (:attr:`StepUp.approved`);
        ``pending``, ``review``, ``declined``, ``expired`` and ``superseded`` all mean no."""
        call = self._retrieve_step_up_call(access_token, step_up_id)
        return self._model(call, self._send(call), StepUp)

    # I/O ----------------------------------------------------------------------

    def _send(self, call: _Call) -> httpx.Response:
        request = self._build(call, self._client)
        started = time.monotonic()
        try:
            response = self._client.send(request, follow_redirects=False)
        except httpx.HTTPError as exc:
            raise self._transport_error(exc, request) from exc
        self._log(request, response, started)
        return response

    def _discovery(self) -> Discovery:
        discovery = self._cache.discovery()
        if discovery is not None:
            return discovery
        with self._lock:
            return self._discovery_locked()

    def _discovery_locked(self) -> Discovery:
        discovery = self._cache.discovery()
        if discovery is None:
            call = self._discovery_call()
            discovery = self._store_discovery(call, self._send(call))
        return discovery

    def _key_set_for(self, kid: str) -> KeySet:
        key_set = self._cache.key_set_with(kid)
        if key_set is not None:
            return key_set
        with self._lock:
            if not self._cache.needs_key_set_fetch(kid):
                return self._cache.current_key_set()
            self._cache.start_key_set_fetch()
            call = self._jwks_call(self._discovery_locked())
            return self._store_key_set(call, self._send(call))


class AsyncAuthentication(_AuthenticationBase):
    """The asyncio variant of :class:`Authentication`, on ``httpx.AsyncClient``.

        auth = AsyncAuthentication.from_publishable_key("pk_live_...", client_id=APPLICATION_ID)
        claims = await auth.verify_access_token(access_token)

    Every method has the same arguments and checks as on :class:`Authentication`.
    """

    _client: httpx.AsyncClient

    def __init__(
        self,
        issuer: str,
        *,
        client_id: str | None = None,
        http_client: httpx.AsyncClient | None = None,
        timeout: float | httpx.Timeout = DEFAULT_TIMEOUT,
        leeway: float = DEFAULT_LEEWAY,
    ) -> None:
        super().__init__(issuer, client_id=client_id, timeout=timeout, leeway=leeway)
        if http_client is not None and not isinstance(http_client, httpx.AsyncClient):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise ConfigurationError(
                "http_client must be an httpx.AsyncClient (use Authentication for httpx.Client)."
            )
        self._owns_client = http_client is None
        self._client = http_client or httpx.AsyncClient(follow_redirects=False)
        # An asyncio.Lock belongs to one event loop; keep one per loop so that the
        # instance also works across several asyncio.run() calls.
        self._locks: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Lock] = (
            weakref.WeakKeyDictionary()
        )

    @classmethod
    def from_publishable_key(
        cls,
        publishable_key: str,
        *,
        client_id: str | None = None,
        http_client: httpx.AsyncClient | None = None,
        timeout: float | httpx.Timeout = DEFAULT_TIMEOUT,
        leeway: float = DEFAULT_LEEWAY,
    ) -> Self:
        """The client for the issuer a ``pk_live_`` or ``pk_test_`` publishable key carries."""
        return cls(
            issuer_from_publishable_key(publishable_key),
            client_id=client_id,
            http_client=http_client,
            timeout=timeout,
            leeway=leeway,
        )

    async def close(self) -> None:
        """Close the HTTP connection pool (only if this client created it)."""
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.close()

    # Tokens -----------------------------------------------------------------

    async def verify_access_token(
        self, token: str, audience: Audience | None = None
    ) -> AccessTokenClaims:
        """Verify an access token offline and return its claims.

        Checks, in order: the header (``alg`` ES256 only, so ``none``, HS*, RS*,
        PS*, EdDSA and every other algorithm are refused; ``typ`` ``at+jwt``), the
        ES256 signature against the issuer's published key with the token's
        ``kid``, then ``iss`` (equal to the issuer), ``sub``, ``exp``, ``nbf`` and
        ``iat`` (with ``leeway`` seconds of clock skew) and, when ``audience`` is
        given or ``client_id`` is configured, ``aud``.

        An offline check cannot see a session revoked a moment ago: access
        tokens expire within five minutes. Call ``get_session`` when the action
        needs an instant revocation check.

        Raises :class:`TokenVerificationError` with a machine-readable ``reason``.
        """
        expected = self._audience(audience, required=False)
        parsed = parse_token(token, "access")
        key_set = await self._key_set_for(parsed.kid)
        return self._finish(
            parsed, key_set, AccessTokenClaims, kind="access", audience=expected, nonce=None
        )

    async def verify_id_token(
        self, token: str, *, nonce: str | None, audience: Audience | None = None
    ) -> IdTokenClaims:
        """See :meth:`Authentication.verify_id_token`."""
        expected = self._audience(audience, required=True)
        nonce = self._nonce(nonce)
        parsed = parse_token(token, "id")
        key_set = await self._key_set_for(parsed.kid)
        return self._finish(
            parsed, key_set, IdTokenClaims, kind="id", audience=expected, nonce=nonce
        )

    async def exchange_code(
        self, code: str, *, code_verifier: str, redirect_uri: str
    ) -> TokenResponse:
        """See :meth:`Authentication.exchange_code`. Never retried."""
        form, secrets = self._exchange_form(code, code_verifier, redirect_uri)
        call = self._token_call(await self._discovery(), form, secrets)
        return self._model(call, await self._send(call), TokenResponse)

    async def refresh(self, refresh_token: str) -> TokenResponse:
        """See :meth:`Authentication.refresh`: serialise refreshes for one session,
        because reusing a consumed refresh token revokes it. Never retried."""
        form, secrets = self._refresh_form(refresh_token)
        call = self._token_call(await self._discovery(), form, secrets)
        return self._model(call, await self._send(call), TokenResponse)

    # Sessions and step-ups --------------------------------------------------

    async def get_session(self, access_token: str) -> AuthenticationSession:
        """See :meth:`Authentication.get_session`."""
        call = self._session_call("GET", access_token)
        return self._model(call, await self._send(call), AuthenticationSession)

    async def revoke_session(self, access_token: str) -> None:
        """See :meth:`Authentication.revoke_session`."""
        call = self._session_call("DELETE", access_token)
        self._read(call, await self._send(call))

    async def create_step_up(
        self,
        access_token: str,
        *,
        action: StepUpAction | str,
        amount: Amount | None = None,
        currency: str | None = None,
        return_to: str | None = None,
    ) -> StepUp:
        """See :meth:`Authentication.create_step_up`: the issuer currently requires
        ``return_to``, and the backend acts only on status ``approved``."""
        call = self._create_step_up_call(
            access_token, action=action, amount=amount, currency=currency, return_to=return_to
        )
        return self._model(call, await self._send(call), StepUp)

    async def retrieve_step_up(self, access_token: str, step_up_id: str) -> StepUp:
        """See :meth:`Authentication.retrieve_step_up`: act only on status ``approved``."""
        call = self._retrieve_step_up_call(access_token, step_up_id)
        return self._model(call, await self._send(call), StepUp)

    # I/O ----------------------------------------------------------------------

    async def _send(self, call: _Call) -> httpx.Response:
        request = self._build(call, self._client)
        started = time.monotonic()
        try:
            response = await self._client.send(request, follow_redirects=False)
        except httpx.HTTPError as exc:
            raise self._transport_error(exc, request) from exc
        self._log(request, response, started)
        return response

    def _async_lock(self) -> asyncio.Lock:
        loop = asyncio.get_running_loop()
        lock = self._locks.get(loop)
        if lock is None:
            lock = self._locks.setdefault(loop, asyncio.Lock())
        return lock

    async def _discovery(self) -> Discovery:
        discovery = self._cache.discovery()
        if discovery is not None:
            return discovery
        async with self._async_lock():
            return await self._discovery_locked()

    async def _discovery_locked(self) -> Discovery:
        discovery = self._cache.discovery()
        if discovery is None:
            call = self._discovery_call()
            discovery = self._store_discovery(call, await self._send(call))
        return discovery

    async def _key_set_for(self, kid: str) -> KeySet:
        key_set = self._cache.key_set_with(kid)
        if key_set is not None:
            return key_set
        async with self._async_lock():
            if not self._cache.needs_key_set_fetch(kid):
                return self._cache.current_key_set()
            self._cache.start_key_set_fetch()
            call = self._jwks_call(await self._discovery_locked())
            return self._store_key_set(call, await self._send(call))
