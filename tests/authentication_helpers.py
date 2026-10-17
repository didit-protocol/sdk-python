"""A stub Didit Authentication issuer for tests/test_authentication.py.

Signing keys are generated locally with ``cryptography`` and tokens are signed
here; the issuer is an ``httpx.MockTransport``, so nothing touches the network.
Every id, token and secret below is synthetic.
"""

from __future__ import annotations

import asyncio
import base64
import json
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

import httpx
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

ISSUER = "https://acme-0a1b2c3d4e5f60718293a4b5c6d7e8f9.auth.didit.me"
APPLICATION_ID = "6f1c2d3e-0000-4000-8000-00000000a001"
IDENTITY_ID = "6f1c2d3e-0000-4000-8000-00000000b001"
SESSION_ID = "6f1c2d3e-0000-4000-8000-00000000c001"
STEP_UP_ID = "6f1c2d3e-0000-4000-8000-00000000d001"
ACCESS_TOKEN = "synthetic-access-token-0001"
REFRESH_TOKEN = "synthetic-refresh-token-0001"
CODE = "synthetic-authorization-code-0001"
CODE_VERIFIER = "synthetic-code-verifier-000000000000000000000001"
REDIRECT_URI = "https://app.example.com/callback"
NONCE = "synthetic-nonce-0001"
NOW = 1_800_000_000

REMOVE: Any = object()
"""Pass as a claim override to leave the claim out."""

Handler = Callable[[httpx.Request], httpx.Response]


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def segment(value: object) -> str:
    return b64url(json.dumps(value).encode("utf-8"))


def unsigned_token(header: Mapping[str, Any], claims: Mapping[str, Any], signature: bytes = b"") -> str:
    """A token with any header and signature bytes, for the rejection tests."""
    return f"{segment(dict(header))}.{segment(dict(claims))}.{b64url(signature)}"


@dataclass
class SigningKey:
    kid: str
    private_key: ec.EllipticCurvePrivateKey

    @classmethod
    def generate(cls, kid: str) -> SigningKey:
        return cls(kid, ec.generate_private_key(ec.SECP256R1()))

    def jwk(self) -> dict[str, str]:
        numbers = self.private_key.public_key().public_numbers()
        return {
            "kty": "EC",
            "crv": "P-256",
            "x": b64url(numbers.x.to_bytes(32, "big")),
            "y": b64url(numbers.y.to_bytes(32, "big")),
            "kid": self.kid,
            "use": "sig",
            "alg": "ES256",
        }

    def sign(
        self,
        claims: Mapping[str, Any],
        *,
        typ: str | None = "at+jwt",
        kid: str | None = None,
        header: Mapping[str, Any] | None = None,
    ) -> str:
        """An ES256 JWS as the Didit issuer signs it (raw r||s signature)."""
        head: dict[str, Any] = {"alg": "ES256", "kid": self.kid if kid is None else kid}
        if typ is not None:
            head["typ"] = typ
        head.update(header or {})
        signing_input = f"{segment(head)}.{segment(dict(claims))}"
        der = self.private_key.sign(signing_input.encode("ascii"), ec.ECDSA(hashes.SHA256()))
        r, s = decode_dss_signature(der)
        return f"{signing_input}.{b64url(r.to_bytes(32, 'big') + s.to_bytes(32, 'big'))}"


def _claims(base: dict[str, Any], overrides: Mapping[str, Any]) -> dict[str, Any]:
    base.update(overrides)
    return {name: value for name, value in base.items() if value is not REMOVE}


def access_claims(now: int = NOW, **overrides: Any) -> dict[str, Any]:
    """The claims of a person's access token (issuer.session_tokens)."""
    return _claims(
        {
            "iss": ISSUER,
            "aud": APPLICATION_ID,
            "sub": IDENTITY_ID,
            "sid": SESSION_ID,
            "jti": "synthetic-jti-0001",
            "iat": now,
            "exp": now + 300,
            "vendor_data": "user-42",
            "org": {"id": "6f1c2d3e-0000-4000-8000-00000000e001", "role": "admin"},
            "verified": {"level": "full_id", "over_18": True, "country": "ES"},
            "amr": ["passkey"],
            "act": None,
            "client_id": APPLICATION_ID,
        },
        overrides,
    )


def id_claims(now: int = NOW, **overrides: Any) -> dict[str, Any]:
    """The claims of an ID token (issuer.session_tokens): no client_id, plus profile claims."""
    return _claims(
        {
            "iss": ISSUER,
            "aud": APPLICATION_ID,
            "sub": IDENTITY_ID,
            "sid": SESSION_ID,
            "jti": "synthetic-jti-0002",
            "iat": now,
            "exp": now + 300,
            "vendor_data": "user-42",
            "org": None,
            "verified": {},
            "amr": ["password"],
            "act": None,
            "auth_time": now - 10,
            "email_verified": True,
            "email": "person@example.com",
            "name": "Synthetic Person",
            "nonce": NONCE,
        },
        overrides,
    )


class FakeClock:
    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class FakeIssuer:
    """The issuer's HTTP side: discovery and JWKS built in, other routes per test."""

    def __init__(self, keys: list[SigningKey], *, issuer: str = ISSUER) -> None:
        self.issuer = issuer
        self.keys = keys
        self.metadata_cache_control: str | None = "public, max-age=300"
        self.discovery: dict[str, Any] = {
            "issuer": issuer,
            "authorization_endpoint": f"{issuer}/sign-in/",
            "token_endpoint": f"{issuer}/token/",
            "jwks_uri": f"{issuer}/.well-known/jwks.json",
            "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code", "refresh_token"],
            "id_token_signing_alg_values_supported": ["ES256"],
            "token_endpoint_auth_methods_supported": ["none"],
            "code_challenge_methods_supported": ["S256"],
        }
        self.routes: dict[tuple[str, str], Handler] = {}
        self.requests: list[httpx.Request] = []
        self.jwks_delay = 0.0

    def route(self, method: str, path: str, handler: Handler) -> None:
        self.routes[(method, path)] = handler

    def reply(self, method: str, path: str, status: int, body: object = None) -> None:
        """Answer ``method path`` with ``status`` and a JSON ``body`` (no body when ``None``)."""

        def handler(_: httpx.Request) -> httpx.Response:
            if body is None:
                return httpx.Response(status)
            return httpx.Response(status, json=body, headers={"x-request-id": "req_synthetic"})

        self.route(method, path, handler)

    def _metadata(self, body: object) -> httpx.Response:
        headers = {"content-type": "application/json"}
        if self.metadata_cache_control is not None:
            headers["cache-control"] = self.metadata_cache_control
        return httpx.Response(200, content=json.dumps(body).encode(), headers=headers)

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if request.method == "GET" and path == "/.well-known/openid-configuration":
            return self._metadata(self.discovery)
        if request.method == "GET" and path == "/.well-known/jwks.json":
            if self.jwks_delay:
                time.sleep(self.jwks_delay)
            return self._metadata({"keys": [key.jwk() for key in self.keys]})
        handler = self.routes.get((request.method, path))
        if handler is None:
            return httpx.Response(404, json={"detail": "Not found."})
        return handler(request)

    async def handle_async(self, request: httpx.Request) -> httpx.Response:
        if self.jwks_delay and request.url.path == "/.well-known/jwks.json":
            await asyncio.sleep(self.jwks_delay)
            delay, self.jwks_delay = self.jwks_delay, 0.0
            try:
                return self.handle(request)
            finally:
                self.jwks_delay = delay
        return self.handle(request)

    def count(self, path: str) -> int:
        return sum(1 for request in self.requests if request.url.path == path)

    def last(self, path: str) -> httpx.Request:
        return [request for request in self.requests if request.url.path == path][-1]

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self.handle))

    def async_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(self.handle_async))
