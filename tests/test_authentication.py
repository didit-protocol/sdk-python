"""didit.authentication (docs/DESIGN.md section 10) against a stubbed issuer.

Keys are generated locally and every request goes to an httpx.MockTransport
(tests/authentication_helpers.py); nothing here touches the network.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import hmac
import json
import logging
import subprocess
import sys
import threading
import urllib.parse
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from typing import Any, TypeVar, cast

import httpx
import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

import didit
from didit import (
    APIConnectionError,
    APIResponseValidationError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    ConfigurationError,
    ConflictError,
    InternalServerError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
)
from didit.authentication import (
    AccessTokenClaims,
    ActorClaim,
    AsyncAuthentication,
    Authentication,
    AuthenticationSession,
    IdTokenClaims,
    OrganizationClaim,
    PkcePair,
    StepUp,
    TokenResponse,
    TokenVerificationError,
    VerifiedClaims,
    _crypto,
    create_nonce,
    create_pkce,
    create_state,
)
from didit.authentication._cache import cache_seconds
from didit.authentication._issuer import issuer_from_publishable_key
from didit.authentication._pkce import s256_challenge
from tests.authentication_helpers import (
    ACCESS_TOKEN,
    APPLICATION_ID,
    CODE,
    CODE_VERIFIER,
    IDENTITY_ID,
    ISSUER,
    NONCE,
    NOW,
    REDIRECT_URI,
    REFRESH_TOKEN,
    REMOVE,
    SESSION_ID,
    STEP_UP_ID,
    FakeClock,
    FakeIssuer,
    SigningKey,
    access_claims,
    b64url,
    id_claims,
    segment,
    unsigned_token,
)

AuthT = TypeVar("AuthT", Authentication, AsyncAuthentication)

DISCOVERY = "/.well-known/openid-configuration"
JWKS = "/.well-known/jwks.json"
TOKEN_RESPONSE = {
    "access_token": "synthetic.access.jwt",
    "id_token": "synthetic.id.jwt",
    "refresh_token": "synthetic-refresh-token-0002",
    "token_type": "Bearer",
    "expires_in": 300,
    "session_id": SESSION_ID,
}
SESSION_RESPONSE = {
    "sub": IDENTITY_ID,
    "sid": SESSION_ID,
    "application_id": APPLICATION_ID,
    "vendor_data": "user-42",
    "amr": ["passkey"],
    "mfa_verified": True,
    "email": "person@example.com",
    "email_verified": True,
    "phone": None,
    "verified_identity": None,
    "verified": {"level": "liveness", "liveness": True},
    "expires_at": "2027-01-15T10:00:00Z",
    "post_logout_redirect_uri": "https://app.example.com/signed-out",
    "organizations": [
        {
            "organization_id": "6f1c2d3e-0000-4000-8000-00000000e001",
            "organization__name": "Acme Treasury",
            "role": "admin",
            "custom_role": {"key": "approver", "permissions": ["payouts:approve"]},
        }
    ],
}
STEP_UP_REQUIRED = {
    "id": STEP_UP_ID,
    "rule": "payout",
    "method": "selfie",
    "status": "pending",
    "level": None,
    "amount": "1500.00",
    "currency": "EUR",
    "created_at": "2027-01-15T10:00:00Z",
    "completed_at": None,
    "expires_at": "2027-01-15T10:30:00Z",
    "required": True,
    "verification_url": f"{ISSUER}/verify/?verification=synthetic-proof",
    "expires_in": 1800,
}


def configure(auth: AuthT, clock: FakeClock) -> AuthT:
    auth._cache.clock = clock
    auth._now = lambda: float(NOW)
    return auth


def reason(call: Callable[[], object]) -> str:
    with pytest.raises(TokenVerificationError) as info:
        call()
    return info.value.reason


def form_of(request: httpx.Request) -> dict[str, str]:
    return dict(urllib.parse.parse_qsl(request.content.decode("ascii"), strict_parsing=True))


@pytest.fixture
def key() -> SigningKey:
    return SigningKey.generate("k_synthetic_key_1")


@pytest.fixture
def issuer(key: SigningKey) -> FakeIssuer:
    return FakeIssuer([key])


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def auth(issuer: FakeIssuer, clock: FakeClock) -> Iterator[Authentication]:
    with issuer.client() as http:
        yield configure(Authentication(ISSUER, http_client=http), clock)


@pytest.fixture(scope="module")
def rsa_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


# Access tokens -----------------------------------------------------------------


def test_verifies_an_access_token(
    auth: Authentication, issuer: FakeIssuer, key: SigningKey
) -> None:
    token = key.sign(access_claims(custom_claim="kept"))
    claims = auth.verify_access_token(token)
    assert isinstance(claims, AccessTokenClaims)
    assert (claims.iss, claims.sub, claims.sid, claims.aud) == (
        ISSUER,
        IDENTITY_ID,
        SESSION_ID,
        APPLICATION_ID,
    )
    assert claims.client_id == APPLICATION_ID
    assert (claims.iat, claims.exp, claims.jti) == (NOW, NOW + 300, "synthetic-jti-0001")
    assert claims.vendor_data == "user-42"
    assert claims.amr == ["passkey"]
    assert isinstance(claims.org, OrganizationClaim)
    assert (claims.org.id, claims.org.role) == ("6f1c2d3e-0000-4000-8000-00000000e001", "admin")
    assert isinstance(claims.verified, VerifiedClaims)
    assert (claims.verified.level, claims.verified.over_18) == ("full_id", True)
    assert claims.act is None
    assert claims.model_extra == {"custom_claim": "kept"}
    assert [r.url.path for r in issuer.requests] == [DISCOVERY, JWKS]


def test_agent_access_token_carries_the_actor(auth: Authentication, key: SigningKey) -> None:
    act = {"sub": "agent-0001", "agent": "Synthetic Agent", "scopes": ["payouts:read"]}
    claims = auth.verify_access_token(key.sign(access_claims(act=act, amr=[], verified={})))
    assert isinstance(claims.act, ActorClaim)
    assert (claims.act.sub, claims.act.agent, claims.act.scopes) == (
        "agent-0001",
        "Synthetic Agent",
        ["payouts:read"],
    )
    assert claims.verified is not None
    assert claims.verified.level is None


@pytest.mark.parametrize("typ", ["at+jwt", "AT+JWT", "application/at+jwt"])
def test_access_token_type_is_case_insensitive(
    auth: Authentication, key: SigningKey, typ: str
) -> None:
    assert auth.verify_access_token(key.sign(access_claims(), typ=typ)).sub == IDENTITY_ID


@pytest.mark.parametrize("typ", [None, "JWT", "jwt", "id+jwt", "at+jwe"])
def test_rejects_a_token_that_is_not_an_access_token(
    auth: Authentication, key: SigningKey, typ: str | None
) -> None:
    assert reason(lambda: auth.verify_access_token(key.sign(access_claims(), typ=typ))) == (
        "invalid_type"
    )


def test_audience_is_checked_when_given(auth: Authentication, key: SigningKey) -> None:
    token = key.sign(access_claims())
    assert auth.verify_access_token(token, APPLICATION_ID).aud == APPLICATION_ID
    assert auth.verify_access_token(token, ["other", APPLICATION_ID]).sub == IDENTITY_ID
    assert reason(lambda: auth.verify_access_token(token, "other-application")) == (
        "invalid_audience"
    )
    listed = key.sign(access_claims(aud=["other", APPLICATION_ID]))
    assert auth.verify_access_token(listed, APPLICATION_ID).aud == ["other", APPLICATION_ID]
    for odd in (7, {"aud": APPLICATION_ID}, [7, None]):
        with pytest.raises(TokenVerificationError) as info:
            auth.verify_access_token(key.sign(access_claims(aud=odd)), APPLICATION_ID)
        assert info.value.reason == "invalid_audience"
    no_aud = key.sign(access_claims(aud=REMOVE))
    assert auth.verify_access_token(no_aud).sub == IDENTITY_ID
    assert reason(lambda: auth.verify_access_token(no_aud, APPLICATION_ID)) == "missing_claim"
    with pytest.raises(ValueError, match="audience"):
        auth.verify_access_token(token, [])


def test_client_id_is_the_default_audience(
    issuer: FakeIssuer, clock: FakeClock, key: SigningKey
) -> None:
    with issuer.client() as http:
        auth = configure(Authentication(ISSUER, client_id=APPLICATION_ID, http_client=http), clock)
        assert auth.verify_access_token(key.sign(access_claims())).sub == IDENTITY_ID
        other = key.sign(access_claims(aud="another-application"))
        assert reason(lambda: auth.verify_access_token(other)) == "invalid_audience"
        assert auth.verify_access_token(other, "another-application").sub == IDENTITY_ID


@pytest.mark.parametrize("alg", ["HS256", "HS512", "RS256", "PS256", "EdDSA", "ES384", "es256"])
def test_rejects_every_algorithm_but_es256(
    auth: Authentication, issuer: FakeIssuer, key: SigningKey, alg: str
) -> None:
    header = {"alg": alg, "typ": "at+jwt", "kid": key.kid}
    token = unsigned_token(header, access_claims(), b"\x01" * 64)
    assert reason(lambda: auth.verify_access_token(token)) == "unsupported_algorithm"
    assert issuer.requests == []


@pytest.mark.parametrize("header", [{"alg": "none", "kid": "k_synthetic_key_1"}, {}])
def test_rejects_alg_none(auth: Authentication, issuer: FakeIssuer, header: dict[str, str]) -> None:
    token = unsigned_token({**header, "typ": "at+jwt"}, access_claims())
    assert token.endswith(".")
    assert reason(lambda: auth.verify_access_token(token)) == "unsupported_algorithm"
    assert issuer.requests == []


def test_rejects_hs256_signed_with_the_public_key(auth: Authentication, key: SigningKey) -> None:
    # The classic key-confusion attack: an HMAC keyed with the published public key.
    header = {"alg": "HS256", "typ": "at+jwt", "kid": key.kid}
    signing_input = f"{segment(header)}.{segment(access_claims())}"
    secret = json.dumps(key.jwk()).encode()
    mac = hmac.new(secret, signing_input.encode(), hashlib.sha256).digest()
    token = f"{signing_input}.{b64url(mac)}"
    assert reason(lambda: auth.verify_access_token(token)) == "unsupported_algorithm"


def test_rejects_a_real_rs256_token(
    auth: Authentication, key: SigningKey, rsa_key: rsa.RSAPrivateKey
) -> None:
    header = {"alg": "RS256", "typ": "at+jwt", "kid": key.kid}
    signing_input = f"{segment(header)}.{segment(access_claims())}"
    signature = rsa_key.sign(signing_input.encode(), padding.PKCS1v15(), hashes.SHA256())
    token = f"{signing_input}.{b64url(signature)}"
    assert reason(lambda: auth.verify_access_token(token)) == "unsupported_algorithm"


def test_rejects_a_token_signed_by_another_key(auth: Authentication, key: SigningKey) -> None:
    impostor = SigningKey.generate(key.kid)
    token = impostor.sign(access_claims())
    with pytest.raises(TokenVerificationError) as info:
        auth.verify_access_token(token)
    assert info.value.reason == "invalid_signature"
    assert token not in str(info.value)


def test_rejects_tampered_claims_and_bad_signature_bytes(
    auth: Authentication, key: SigningKey
) -> None:
    header_b64, _, signature_b64 = key.sign(access_claims()).split(".")
    forged = f"{header_b64}.{segment(access_claims(sub='someone-else'))}.{signature_b64}"
    assert reason(lambda: auth.verify_access_token(forged)) == "invalid_signature"
    short = f"{header_b64}.{segment(access_claims())}.{b64url(b'x' * 63)}"
    assert reason(lambda: auth.verify_access_token(short)) == "invalid_signature"
    empty = f"{header_b64}.{segment(access_claims())}."
    assert reason(lambda: auth.verify_access_token(empty)) == "invalid_signature"


def test_rejects_the_wrong_issuer(auth: Authentication, key: SigningKey) -> None:
    other = key.sign(access_claims(iss="https://other-0001.auth.didit.me"))
    assert reason(lambda: auth.verify_access_token(other)) == "invalid_issuer"
    slash = key.sign(access_claims(iss=ISSUER + "/"))
    assert reason(lambda: auth.verify_access_token(slash)) == "invalid_issuer"
    missing = key.sign(access_claims(iss=REMOVE))
    assert reason(lambda: auth.verify_access_token(missing)) == "missing_claim"


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"exp": NOW - 61}, "expired"),
        ({"exp": NOW - 60}, "expired"),
        ({"nbf": NOW + 120}, "not_yet_valid"),
        ({"iat": NOW + 120}, "invalid_issued_at"),
        ({"exp": REMOVE}, "missing_claim"),
        ({"iat": REMOVE}, "missing_claim"),
        ({"sub": REMOVE}, "missing_claim"),
        ({"sub": ""}, "missing_claim"),
        ({"exp": "soon"}, "malformed"),
        ({"exp": True}, "malformed"),
        ({"iat": [NOW]}, "malformed"),
        ({"nbf": None}, "malformed"),
    ],
)
def test_time_and_required_claims(
    auth: Authentication, key: SigningKey, overrides: dict[str, Any], expected: str
) -> None:
    assert (
        reason(lambda: auth.verify_access_token(key.sign(access_claims(**overrides)))) == expected
    )


@pytest.mark.parametrize(
    "overrides",
    [
        {"exp": NOW - 59},
        {"exp": NOW + 1.5},
        {"nbf": NOW + 59},
        {"iat": NOW + 59},
        {"nbf": NOW - 10},
    ],
)
def test_leeway_allows_sixty_seconds_of_skew(
    auth: Authentication, key: SigningKey, overrides: dict[str, Any]
) -> None:
    assert auth.verify_access_token(key.sign(access_claims(**overrides))).sub == IDENTITY_ID


def test_leeway_is_configurable(issuer: FakeIssuer, clock: FakeClock, key: SigningKey) -> None:
    with issuer.client() as http:
        strict = configure(Authentication(ISSUER, http_client=http, leeway=0), clock)
        token = key.sign(access_claims(exp=NOW))
        assert reason(lambda: strict.verify_access_token(token)) == "expired"
        lenient = configure(Authentication(ISSUER, http_client=http, leeway=600), clock)
        old = key.sign(access_claims(exp=NOW - 500))
        assert lenient.verify_access_token(old).sub == IDENTITY_ID


def test_rejects_nan_in_a_signed_token(auth: Authentication, key: SigningKey) -> None:
    token = key.sign({**access_claims(), "exp": float("nan")})
    assert reason(lambda: auth.verify_access_token(token)) == "malformed"


def _malformed_tokens(kid: str) -> list[object]:
    good_header = segment({"alg": "ES256", "typ": "at+jwt", "kid": kid})
    payload = segment(access_claims())
    signature = b64url(b"\x00" * 64)
    duplicate = b64url(b'{"alg": "ES256", "alg": "none"}')
    not_utf8 = b64url(b"\xff\xfe")
    deep = b64url(b"[" * 5000 + b"]" * 5000)
    no_kid = segment({"alg": "ES256", "typ": "at+jwt"})
    bad_kid = segment({"alg": "ES256", "typ": "at+jwt", "kid": 7})
    critical = segment({"alg": "ES256", "typ": "at+jwt", "kid": kid, "crit": ["b64"]})
    return [
        "",
        "abc",
        "a.b",
        "a.b.c.d",
        "a.b.c.d.e",
        f"!!!.{payload}.{signature}",
        f"{good_header}=.{payload}.{signature}",
        f"{b64url(b'not json')}.{payload}.{signature}",
        f"{b64url(b'[1, 2]')}.{payload}.{signature}",
        f"{duplicate}.{payload}.{signature}",
        f"{not_utf8}.{payload}.{signature}",
        f"{good_header}.{b64url(b'not json')}.{signature}",
        f"{good_header}.{b64url(b'[]')}.{signature}",
        f"{good_header}.abcde.{signature}",
        f"{good_header}.{payload}.abc!",
        f"{no_kid}.{payload}.{signature}",
        f"{bad_kid}.{payload}.{signature}",
        f"{critical}.{payload}.{signature}",
        f"{good_header}.{deep}.{signature}",
        "x" * 20000,
        123,
        None,
        b"a.b.c",
    ]


def test_rejects_malformed_tokens(
    auth: Authentication, issuer: FakeIssuer, key: SigningKey
) -> None:
    for token in _malformed_tokens(key.kid):
        with pytest.raises(TokenVerificationError) as info:
            auth.verify_access_token(cast(Any, token))
        assert info.value.reason == "malformed", token
        if isinstance(token, str) and len(token) > 10:
            assert token not in str(info.value)
    assert issuer.requests == []


# Discovery and JWKS ------------------------------------------------------------


def test_discovery_and_keys_are_fetched_lazily_and_cached(
    auth: Authentication, issuer: FakeIssuer, key: SigningKey, clock: FakeClock
) -> None:
    assert issuer.requests == []
    token = key.sign(access_claims())
    auth.verify_access_token(token)
    auth.verify_access_token(token)
    clock.advance(299)
    auth.verify_access_token(token)
    assert (issuer.count(DISCOVERY), issuer.count(JWKS)) == (1, 1)
    clock.advance(2)
    auth.verify_access_token(token)
    assert (issuer.count(DISCOVERY), issuer.count(JWKS)) == (2, 2)
    jwks_request = issuer.last(JWKS)
    assert jwks_request.headers["accept"] == "application/json"
    assert jwks_request.headers["user-agent"].startswith(f"didit-python/{didit.__version__} ")
    assert jwks_request.headers["x-didit-client"] == f"python/{didit.__version__}"
    assert "authorization" not in jwks_request.headers
    assert "x-api-key" not in jwks_request.headers


@pytest.mark.parametrize(
    ("cache_control", "fresh_for"),
    [("public, max-age=10", 60), (None, 300), ("public, max-age=3600", 3600), ("no-store", 60)],
)
def test_key_set_is_cached_for_max_age_with_a_floor(
    auth: Authentication,
    issuer: FakeIssuer,
    key: SigningKey,
    clock: FakeClock,
    cache_control: str | None,
    fresh_for: int,
) -> None:
    issuer.metadata_cache_control = cache_control
    token = key.sign(access_claims())
    auth.verify_access_token(token)
    clock.advance(fresh_for - 1)
    auth.verify_access_token(token)
    assert issuer.count(JWKS) == 1
    clock.advance(1)
    auth.verify_access_token(token)
    assert issuer.count(JWKS) == 2


@pytest.mark.parametrize(
    ("headers", "seconds"),
    [
        ({}, 300),
        ({"cache-control": "public, max-age=300"}, 300),
        ({"cache-control": "max-age=120"}, 120),
        ({"cache-control": 'MAX-AGE="900", public'}, 900),
        ({"cache-control": "max-age=1"}, 60),
        ({"cache-control": "max-age=0"}, 60),
        ({"cache-control": "max-age=999999999"}, 86400),
        ({"cache-control": "max-age=soon"}, 300),
        ({"cache-control": "public, max-age=300", "age": "100"}, 200),
        ({"cache-control": "public, max-age=300", "age": "290"}, 60),
        ({"cache-control": "public, max-age=300", "age": "old"}, 300),
        ({"cache-control": "max-age=300, no-cache"}, 60),
        ({"cache-control": "no-store"}, 60),
    ],
)
def test_cache_seconds(headers: dict[str, str], seconds: float) -> None:
    assert cache_seconds(httpx.Headers(headers)) == seconds


def test_unknown_kid_refetches_at_most_once_a_minute(
    auth: Authentication, issuer: FakeIssuer, key: SigningKey, clock: FakeClock
) -> None:
    auth.verify_access_token(key.sign(access_claims()))
    assert issuer.count(JWKS) == 1
    rotated = SigningKey.generate("k_synthetic_key_2")
    rotated_token = rotated.sign(access_claims())
    clock.advance(1)
    # The new key is not published yet: the refetch is refused for a minute after the last fetch.
    assert reason(lambda: auth.verify_access_token(rotated_token)) == "unknown_key"
    issuer.keys.append(rotated)
    clock.advance(30)
    assert reason(lambda: auth.verify_access_token(rotated_token)) == "unknown_key"
    assert issuer.count(JWKS) == 1
    clock.advance(29)
    assert auth.verify_access_token(rotated_token).sub == IDENTITY_ID
    assert issuer.count(JWKS) == 2
    stranger = SigningKey.generate("k_never_published").sign(access_claims())
    for _ in range(5):
        clock.advance(10)
        assert reason(lambda: auth.verify_access_token(stranger)) == "unknown_key"
    assert issuer.count(JWKS) == 2
    clock.advance(10)
    assert reason(lambda: auth.verify_access_token(stranger)) == "unknown_key"
    assert issuer.count(JWKS) == 3
    # Known keys keep verifying from the cache meanwhile.
    auth.verify_access_token(key.sign(access_claims()))
    assert issuer.count(JWKS) == 3


@pytest.mark.parametrize(
    "jwk_change",
    [
        {"kty": "RSA"},
        {"crv": "P-384"},
        {"alg": "ES384"},
        {"use": "enc"},
        {"x": b64url(b"\x01" * 31)},
        {"y": 42},
        {"x": b64url(b"\x00" * 32), "y": b64url(b"\x00" * 32)},
    ],
)
def test_unusable_published_key_is_an_unknown_key(
    auth: Authentication, issuer: FakeIssuer, key: SigningKey, jwk_change: dict[str, Any]
) -> None:
    class Odd(SigningKey):
        def jwk(self) -> dict[str, str]:
            return {**super().jwk(), **jwk_change}

    issuer.keys[:] = [Odd(key.kid, key.private_key)]
    assert reason(lambda: auth.verify_access_token(key.sign(access_claims()))) == "unknown_key"


def test_jwks_ignores_entries_without_a_kid(
    auth: Authentication, issuer: FakeIssuer, key: SigningKey
) -> None:
    issuer.route(
        "GET",
        "/keys/custom.json",
        lambda _: httpx.Response(
            200, json={"keys": [{"kty": "EC"}, "junk", {**key.jwk(), "kid": ""}, key.jwk()]}
        ),
    )
    issuer.discovery["jwks_uri"] = f"{ISSUER}/keys/custom.json"
    assert auth.verify_access_token(key.sign(access_claims())).sub == IDENTITY_ID
    assert issuer.count("/keys/custom.json") == 1
    assert issuer.count(JWKS) == 0


def test_documented_paths_are_used_when_discovery_omits_them(
    auth: Authentication, issuer: FakeIssuer, key: SigningKey
) -> None:
    issuer.discovery["jwks_uri"] = "https://[::1"
    issuer.discovery["token_endpoint"] = 42
    issuer.reply("POST", "/token/", 200, TOKEN_RESPONSE)
    assert auth.verify_access_token(key.sign(access_claims())).sub == IDENTITY_ID
    assert auth.refresh(REFRESH_TOKEN).token_type == "Bearer"
    assert [r.url.path for r in issuer.requests] == [DISCOVERY, JWKS, "/token/"]


def test_discovery_must_name_the_configured_issuer(
    auth: Authentication, issuer: FakeIssuer, key: SigningKey
) -> None:
    issuer.discovery["issuer"] = "https://login.example.com"
    with pytest.raises(ConfigurationError, match=r"names the issuer 'https://login\.example\.com'"):
        auth.verify_access_token(key.sign(access_claims()))
    del issuer.discovery["issuer"]
    assert auth.verify_access_token(key.sign(access_claims())).sub == IDENTITY_ID


@pytest.mark.parametrize(
    ("path", "response"),
    [
        (DISCOVERY, httpx.Response(200, text="<html>", headers={"content-type": "text/html"})),
        (DISCOVERY, httpx.Response(200, json=["not", "an", "object"])),
        (DISCOVERY, httpx.Response(200)),
        (JWKS, httpx.Response(200, json={"keys": "none"})),
        (JWKS, httpx.Response(200, json=[])),
    ],
)
def test_unreadable_metadata_is_a_response_validation_error(
    clock: FakeClock, key: SigningKey, path: str, response: httpx.Response
) -> None:
    issuer = FakeIssuer([key])

    def handle(request: httpx.Request) -> httpx.Response:
        return response if request.url.path == path else issuer.handle(request)

    with httpx.Client(transport=httpx.MockTransport(handle)) as http:
        auth = configure(Authentication(ISSUER, http_client=http), clock)
        with pytest.raises(APIResponseValidationError):
            auth.verify_access_token(key.sign(access_claims()))


def test_metadata_http_errors(clock: FakeClock, key: SigningKey) -> None:
    requests: list[httpx.Request] = []

    def failing(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(503, text="upstream unavailable")

    with httpx.Client(transport=httpx.MockTransport(failing)) as http:
        auth = configure(Authentication(ISSUER, http_client=http), clock)
        with pytest.raises(InternalServerError) as info:
            auth.verify_access_token(key.sign(access_claims()))
        assert info.value.status == 503
        assert [r.url.path for r in requests] == [DISCOVERY]
        assert str(info.value) == "HTTP 503: upstream unavailable"


def test_concurrent_threads_fetch_the_keys_once(
    auth: Authentication, issuer: FakeIssuer, key: SigningKey
) -> None:
    issuer.jwks_delay = 0.05
    tokens = [key.sign(access_claims(jti=f"jti-{n}")) for n in range(8)]
    start = threading.Barrier(8, timeout=10)

    def verify(token: str) -> str:
        start.wait()
        return auth.verify_access_token(token).sub

    with ThreadPoolExecutor(max_workers=8) as pool:
        subjects = list(pool.map(verify, tokens))
    assert subjects == [IDENTITY_ID] * 8
    assert (issuer.count(DISCOVERY), issuer.count(JWKS)) == (1, 1)


def test_import_error_without_cryptography(
    auth: Authentication, key: SigningKey, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in (
        "cryptography.exceptions",
        "cryptography.hazmat.primitives",
        "cryptography.hazmat.primitives.asymmetric",
        "cryptography.hazmat.primitives.asymmetric.ec",
        "cryptography.hazmat.primitives.asymmetric.utils",
    ):
        monkeypatch.setitem(sys.modules, name, None)
    with pytest.raises(ImportError, match=r"pip install 'didit-sdk\[auth\]'"):
        auth.verify_access_token(key.sign(access_claims()))
    with pytest.raises(ImportError, match=r"didit-sdk\[auth\]"):
        _crypto.verify_es256(cast(Any, None), b"", b"")


def test_module_imports_without_cryptography() -> None:
    code = (
        "import sys\n"
        "sys.modules['cryptography'] = None\n"
        "import didit.authentication as a\n"
        "pair = a.create_pkce()\n"
        "auth = a.Authentication('https://acme.auth.didit.me')\n"
        "auth.close()\n"
        "print(pair.method, 'cryptography' in sys.modules and sys.modules['cryptography'] is None)\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=False, timeout=120
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "S256 True"


# ID tokens ---------------------------------------------------------------------


def test_verifies_an_id_token(auth: Authentication, key: SigningKey) -> None:
    token = key.sign(id_claims(), typ="JWT")
    claims = auth.verify_id_token(token, nonce=NONCE, audience=APPLICATION_ID)
    assert isinstance(claims, IdTokenClaims)
    assert (claims.sub, claims.sid, claims.nonce) == (IDENTITY_ID, SESSION_ID, NONCE)
    assert (claims.email, claims.email_verified, claims.name) == (
        "person@example.com",
        True,
        "Synthetic Person",
    )
    assert claims.auth_time == NOW - 10
    assert claims.phone_number is None
    assert claims.org is None


@pytest.mark.parametrize("typ", ["JWT", "jwt", "application/jwt", None])
def test_id_token_type(auth: Authentication, key: SigningKey, typ: str | None) -> None:
    token = key.sign(id_claims(), typ=typ)
    assert auth.verify_id_token(token, nonce=NONCE, audience=APPLICATION_ID).sub == IDENTITY_ID


@pytest.mark.parametrize("typ", ["at+jwt", "application/at+jwt", "dpop+jwt", 1])
def test_an_access_token_is_never_an_id_token(
    auth: Authentication, key: SigningKey, typ: Any
) -> None:
    token = key.sign(id_claims(), header={"typ": typ})
    assert reason(lambda: auth.verify_id_token(token, nonce=NONCE, audience=APPLICATION_ID)) == (
        "invalid_type"
    )


def test_id_token_nonce(auth: Authentication, key: SigningKey) -> None:
    token = key.sign(id_claims(), typ="JWT")
    assert reason(
        lambda: auth.verify_id_token(token, nonce="another-sign-in", audience=APPLICATION_ID)
    ) == ("invalid_nonce")
    no_nonce = key.sign(id_claims(nonce=REMOVE), typ="JWT")
    assert reason(lambda: auth.verify_id_token(no_nonce, nonce=NONCE, audience=APPLICATION_ID)) == (
        "invalid_nonce"
    )
    # An ID token from refresh() carries no nonce; the caller opts out explicitly.
    refreshed = auth.verify_id_token(no_nonce, nonce=None, audience=APPLICATION_ID)
    assert refreshed.nonce is None
    with pytest.raises(ValueError, match="nonce"):
        auth.verify_id_token(token, nonce="", audience=APPLICATION_ID)


def test_id_token_audience_is_required(
    auth: Authentication, issuer: FakeIssuer, clock: FakeClock, key: SigningKey
) -> None:
    token = key.sign(id_claims(), typ="JWT")
    with pytest.raises(ConfigurationError, match="audience"):
        auth.verify_id_token(token, nonce=NONCE)
    assert issuer.requests == []
    assert reason(lambda: auth.verify_id_token(token, nonce=NONCE, audience="other")) == (
        "invalid_audience"
    )
    no_aud = key.sign(id_claims(aud=REMOVE), typ="JWT")
    assert reason(lambda: auth.verify_id_token(no_aud, nonce=NONCE, audience=APPLICATION_ID)) == (
        "missing_claim"
    )
    with issuer.client() as http:
        configured = configure(
            Authentication(ISSUER, client_id=APPLICATION_ID, http_client=http), clock
        )
        assert configured.verify_id_token(token, nonce=NONCE).aud == APPLICATION_ID


def test_id_token_time_checks(auth: Authentication, key: SigningKey) -> None:
    expired = key.sign(id_claims(exp=NOW - 120), typ="JWT")
    assert reason(lambda: auth.verify_id_token(expired, nonce=NONCE, audience=APPLICATION_ID)) == (
        "expired"
    )
    other = SigningKey.generate(key.kid).sign(id_claims(), typ="JWT")
    assert reason(lambda: auth.verify_id_token(other, nonce=NONCE, audience=APPLICATION_ID)) == (
        "invalid_signature"
    )


# Publishable keys and configuration ---------------------------------------------


def _pk(prefix: str, issuer: str) -> str:
    return prefix + b64url(issuer.encode())


def test_publishable_keys_carry_the_issuer(issuer: FakeIssuer) -> None:
    assert issuer_from_publishable_key(_pk("pk_live_", ISSUER)) == ISSUER
    sandbox = "https://acme-0001.sandbox.auth.didit.me"
    assert issuer_from_publishable_key(_pk("pk_test_", sandbox)) == sandbox
    assert issuer_from_publishable_key("  " + _pk("pk_live_", ISSUER + "/") + "\n") == ISSUER
    assert issuer_from_publishable_key(_pk("pk_test_", "http://acme.auth.localhost:8000")) == (
        "http://acme.auth.localhost:8000"
    )
    with issuer.client() as http:
        auth = Authentication.from_publishable_key(
            _pk("pk_live_", ISSUER), client_id=APPLICATION_ID, http_client=http, leeway=5
        )
        assert (auth.issuer, auth.client_id, auth.leeway) == (ISSUER, APPLICATION_ID, 5.0)


@pytest.mark.parametrize(
    "publishable_key",
    [
        "",
        "pk_live_",
        "pk_",
        "sk_live_" + b64url(ISSUER.encode()),
        "PK_LIVE_" + b64url(ISSUER.encode()),
        "pk_live_!!!notbase64",
        "pk_live_" + b64url(ISSUER.encode()) + "=",
        "pk_live_a",
        "pk_live_" + b64url(b"\xff\xfe\xfd"),
        "pk_live_" + b64url(b"http://acme.auth.didit.me"),
        "pk_test_" + b64url(b"http://acme.auth.didit.me"),
        "pk_live_" + b64url(b"http://localhost:8000"),
        "pk_live_" + b64url(b"acme.auth.didit.me"),
        "pk_live_" + b64url(b"https://acme.auth.didit.me?x=1"),
        cast(Any, None),
        cast(Any, 42),
    ],
)
def test_invalid_publishable_keys(publishable_key: str) -> None:
    with pytest.raises(ConfigurationError):
        issuer_from_publishable_key(publishable_key)
    with pytest.raises(ConfigurationError):
        AsyncAuthentication.from_publishable_key(publishable_key)


@pytest.mark.parametrize(
    "value",
    [
        "",
        "   ",
        "acme.auth.didit.me",
        "http://acme.auth.didit.me",
        "ftp://acme.auth.didit.me",
        "https://",
        "https://user:secret@acme.auth.didit.me",
        "https://acme.auth.didit.me/?x=1",
        "https://acme.auth.didit.me#top",
        "https://acme.auth.didit.me:99999",
        "https://acme.auth.didit.me/a b",
        "https://[::1",
        cast(Any, None),
    ],
)
def test_invalid_issuers(value: str) -> None:
    with pytest.raises(ConfigurationError):
        Authentication(value)


def test_issuer_normalisation_and_options() -> None:
    with Authentication(ISSUER + "/") as auth:
        assert auth.issuer == ISSUER
        assert repr(auth) == f"Authentication(issuer={ISSUER!r}, client_id=None)"
        assert auth.leeway == 60.0
    with Authentication("http://localhost:8000", client_id=f" {APPLICATION_ID} ") as local:
        assert (local.issuer, local.client_id) == ("http://localhost:8000", APPLICATION_ID)
    for bad in ("", "  "):
        with pytest.raises(ConfigurationError, match="client_id"):
            Authentication(ISSUER, client_id=bad)
    for leeway in (-1, cast(Any, True), cast(Any, "60"), float("nan")):
        with pytest.raises(ConfigurationError, match="leeway"):
            Authentication(ISSUER, leeway=leeway)
    async_http = httpx.AsyncClient()
    with pytest.raises(ConfigurationError, match=r"httpx\.Client"):
        Authentication(ISSUER, http_client=cast(Any, async_http))
    asyncio.run(async_http.aclose())
    with (
        httpx.Client() as sync_http,
        pytest.raises(ConfigurationError, match=r"httpx\.AsyncClient"),
    ):
        AsyncAuthentication(ISSUER, http_client=cast(Any, sync_http))


def test_does_not_close_a_client_it_did_not_create(issuer: FakeIssuer) -> None:
    with issuer.client() as http:
        Authentication(ISSUER, http_client=http).close()
        assert not http.is_closed
    owned = Authentication(ISSUER)
    owned.close()
    assert owned._client.is_closed


# PKCE, state and nonce -----------------------------------------------------------


def test_pkce_rfc7636_appendix_b() -> None:
    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    assert s256_challenge(verifier) == "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"


def test_create_pkce() -> None:
    pairs = [create_pkce() for _ in range(20)]
    for pair in pairs:
        assert isinstance(pair, PkcePair)
        assert pair.method == "S256"
        assert 43 <= len(pair.verifier) <= 128
        assert set(pair.verifier) <= set(
            "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~"
        )
        assert pair.challenge == s256_challenge(pair.verifier)
        assert len(pair.challenge) == 43
        assert pair.verifier not in repr(pair)
    assert len({pair.verifier for pair in pairs}) == 20


def test_state_and_nonce() -> None:
    values = [create_state() for _ in range(10)] + [create_nonce() for _ in range(10)]
    assert len(set(values)) == 20
    for value in values:
        assert len(value) >= 43
        assert set(value) <= set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")


def test_helpers_are_static_methods_too() -> None:
    assert Authentication.create_pkce().method == "S256"
    assert len(AsyncAuthentication.create_state()) >= 43
    with Authentication(ISSUER) as auth:
        assert len(auth.create_nonce()) >= 43


# Token, session and step-up requests ---------------------------------------------


def test_exchange_code(auth: Authentication, issuer: FakeIssuer) -> None:
    issuer.reply("POST", "/token/", 200, TOKEN_RESPONSE)
    tokens = auth.exchange_code(CODE, code_verifier=CODE_VERIFIER, redirect_uri=REDIRECT_URI)
    assert isinstance(tokens, TokenResponse)
    assert tokens.access_token == "synthetic.access.jwt"
    assert tokens.id_token == "synthetic.id.jwt"
    assert tokens.refresh_token == "synthetic-refresh-token-0002"
    assert (tokens.token_type, tokens.expires_in, tokens.session_id) == ("Bearer", 300, SESSION_ID)
    for secret in ("synthetic.access.jwt", "synthetic.id.jwt", "synthetic-refresh-token-0002"):
        assert secret not in repr(tokens)
    assert [(r.method, r.url.path) for r in issuer.requests] == [
        ("GET", DISCOVERY),
        ("POST", "/token/"),
    ]
    request = issuer.last("/token/")
    assert str(request.url) == f"{ISSUER}/token/"
    assert request.headers["content-type"] == "application/x-www-form-urlencoded"
    assert request.headers["accept"] == "application/json"
    assert request.headers["x-didit-client"] == f"python/{didit.__version__}"
    assert "authorization" not in request.headers
    assert "x-api-key" not in request.headers
    assert form_of(request) == {
        "grant_type": "authorization_code",
        "code": CODE,
        "code_verifier": CODE_VERIFIER,
        "redirect_uri": REDIRECT_URI,
    }


def test_token_requests_send_the_client_id_when_configured(
    issuer: FakeIssuer, clock: FakeClock
) -> None:
    issuer.reply("POST", "/token/", 200, TOKEN_RESPONSE)
    with issuer.client() as http:
        auth = configure(Authentication(ISSUER, client_id=APPLICATION_ID, http_client=http), clock)
        auth.exchange_code(CODE, code_verifier=CODE_VERIFIER, redirect_uri=REDIRECT_URI)
        assert form_of(issuer.last("/token/"))["client_id"] == APPLICATION_ID
        auth.refresh(REFRESH_TOKEN)
        assert form_of(issuer.last("/token/")) == {
            "grant_type": "refresh_token",
            "refresh_token": REFRESH_TOKEN,
            "client_id": APPLICATION_ID,
        }
    assert issuer.count(DISCOVERY) == 1


def test_refresh_uses_the_discovered_token_endpoint(
    auth: Authentication, issuer: FakeIssuer
) -> None:
    issuer.discovery["token_endpoint"] = f"{ISSUER}/oauth/token/"
    issuer.reply("POST", "/oauth/token/", 200, TOKEN_RESPONSE)
    tokens = auth.refresh(REFRESH_TOKEN)
    assert tokens.refresh_token == "synthetic-refresh-token-0002"
    assert form_of(issuer.last("/oauth/token/")) == {
        "grant_type": "refresh_token",
        "refresh_token": REFRESH_TOKEN,
    }


def test_token_request_arguments_are_required(auth: Authentication, issuer: FakeIssuer) -> None:
    with pytest.raises(ValueError, match="code is empty"):
        auth.exchange_code("", code_verifier=CODE_VERIFIER, redirect_uri=REDIRECT_URI)
    with pytest.raises(ValueError, match="code_verifier"):
        auth.exchange_code(CODE, code_verifier=" ", redirect_uri=REDIRECT_URI)
    with pytest.raises(ValueError, match="redirect_uri"):
        auth.exchange_code(CODE, code_verifier=CODE_VERIFIER, redirect_uri=cast(Any, None))
    with pytest.raises(ValueError, match="refresh_token"):
        auth.refresh("")
    with pytest.raises(ValueError, match="access_token"):
        auth.get_session("")
    assert issuer.requests == []


def test_get_session(auth: Authentication, issuer: FakeIssuer) -> None:
    issuer.reply("GET", "/session/", 200, SESSION_RESPONSE)
    session = auth.get_session(ACCESS_TOKEN)
    assert isinstance(session, AuthenticationSession)
    assert (session.sub, session.sid, session.application_id) == (
        IDENTITY_ID,
        SESSION_ID,
        APPLICATION_ID,
    )
    assert session.expires_at == dt.datetime(2027, 1, 15, 10, 0, tzinfo=dt.timezone.utc)
    assert session.verified is not None
    assert session.verified.level == "liveness"
    assert session.organizations is not None
    organization = session.organizations[0]
    assert (organization.organization_name, organization.role) == ("Acme Treasury", "admin")
    assert organization.custom_role is not None
    assert organization.custom_role.permissions == ["payouts:approve"]
    assert session.to_dict()["organizations"][0]["organization__name"] == "Acme Treasury"
    request = issuer.last("/session/")
    assert (request.method, str(request.url)) == ("GET", f"{ISSUER}/session/")
    assert request.headers["authorization"] == f"Bearer {ACCESS_TOKEN}"
    assert request.headers["accept"] == "application/json"
    assert request.content == b""
    assert issuer.count(DISCOVERY) == 0


def test_revoke_session(auth: Authentication, issuer: FakeIssuer) -> None:
    issuer.reply("DELETE", "/session/", 204)
    auth.revoke_session(ACCESS_TOKEN)
    request = issuer.last("/session/")
    assert request.method == "DELETE"
    assert request.headers["authorization"] == f"Bearer {ACCESS_TOKEN}"


def test_create_step_up(auth: Authentication, issuer: FakeIssuer) -> None:
    issuer.reply("POST", "/step-up/", 201, STEP_UP_REQUIRED)
    step_up = auth.create_step_up(
        ACCESS_TOKEN,
        action="payout",
        amount=Decimal("1500.00"),
        currency="EUR",
        return_to="https://app.example.com/payouts",
    )
    assert isinstance(step_up, StepUp)
    assert (step_up.required, step_up.id, step_up.status, step_up.approved) == (
        True,
        STEP_UP_ID,
        "pending",
        False,
    )
    assert step_up.verification_url == f"{ISSUER}/verify/?verification=synthetic-proof"
    assert (step_up.expires_in, step_up.amount, step_up.rule, step_up.method) == (
        1800,
        "1500.00",
        "payout",
        "selfie",
    )
    assert step_up.expires_at == dt.datetime(2027, 1, 15, 10, 30, tzinfo=dt.timezone.utc)
    request = issuer.last("/step-up/")
    assert request.headers["authorization"] == f"Bearer {ACCESS_TOKEN}"
    assert request.headers["content-type"] == "application/json"
    assert json.loads(request.content) == {
        "action": "payout",
        "amount": "1500.00",
        "currency": "EUR",
        "return_to": "https://app.example.com/payouts",
    }


def test_create_step_up_not_required(auth: Authentication, issuer: FakeIssuer) -> None:
    issuer.reply("POST", "/step-up/", 200, {"required": False})
    step_up = auth.create_step_up(
        ACCESS_TOKEN, action="contact", return_to="https://app.example.com/profile"
    )
    assert (step_up.required, step_up.id, step_up.approved) == (False, None, False)
    assert json.loads(issuer.last("/step-up/").content) == {
        "action": "contact",
        "return_to": "https://app.example.com/profile",
    }
    auth.create_step_up(ACCESS_TOKEN, action="bank")
    assert json.loads(issuer.last("/step-up/").content) == {"action": "bank"}


@pytest.mark.parametrize(
    ("amount", "sent"),
    [
        ("1500.00", "1500.00"),
        (1500, "1500"),
        (1500.5, "1500.5"),
        (0.1, "0.1"),
        (Decimal("1E+3"), "1000"),
        (Decimal("12.30"), "12.30"),
    ],
)
def test_step_up_amounts_are_decimal_strings(
    auth: Authentication, issuer: FakeIssuer, amount: Any, sent: str
) -> None:
    issuer.reply("POST", "/step-up/", 200, {"required": False})
    auth.create_step_up(ACCESS_TOKEN, action="payout", amount=amount, return_to=REDIRECT_URI)
    assert json.loads(issuer.last("/step-up/").content)["amount"] == sent


def test_step_up_argument_errors(auth: Authentication, issuer: FakeIssuer) -> None:
    for amount in (True, [1], object()):
        with pytest.raises(TypeError, match="amount"):
            auth.create_step_up(ACCESS_TOKEN, action="payout", amount=cast(Any, amount))
    with pytest.raises(ValueError, match="action"):
        auth.create_step_up(ACCESS_TOKEN, action="")
    with pytest.raises(ValueError, match="step_up_id"):
        auth.retrieve_step_up(ACCESS_TOKEN, "")
    with pytest.raises(ValueError, match="step_up_id"):
        auth.retrieve_step_up(ACCESS_TOKEN, "..")
    assert issuer.requests == []


@pytest.mark.parametrize(
    ("status", "approved"),
    [
        ("approved", True),
        ("pending", False),
        ("review", False),
        ("declined", False),
        ("expired", False),
        ("superseded", False),
        ("some_future_status", False),
    ],
)
def test_retrieve_step_up(
    auth: Authentication, issuer: FakeIssuer, status: str, approved: bool
) -> None:
    body = {
        key: value
        for key, value in STEP_UP_REQUIRED.items()
        if key not in ("required", "verification_url", "expires_in")
    }
    body.update(status=status, level="liveness_face_match" if approved else None)
    issuer.reply("GET", f"/step-up/{STEP_UP_ID}/", 200, body)
    step_up = auth.retrieve_step_up(ACCESS_TOKEN, STEP_UP_ID)
    assert (step_up.status, step_up.approved, step_up.required) == (status, approved, None)
    request = issuer.last(f"/step-up/{STEP_UP_ID}/")
    assert request.method == "GET"
    assert request.headers["authorization"] == f"Bearer {ACCESS_TOKEN}"


def test_step_up_id_is_percent_encoded(auth: Authentication, issuer: FakeIssuer) -> None:
    with pytest.raises(NotFoundError):
        auth.retrieve_step_up(ACCESS_TOKEN, "a/b")
    assert issuer.requests[-1].url.raw_path == b"/step-up/a%2Fb/"


# Errors --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "body", "error", "message"),
    [
        (400, {"error": "invalid_grant"}, BadRequestError, "HTTP 400: invalid_grant"),
        (400, {"non_field_errors": ["invalid_request"]}, BadRequestError, "HTTP 400"),
        (401, {"detail": "invalid_token"}, AuthenticationError, "HTTP 401: invalid_token"),
        (
            403,
            {"detail": "origin_not_allowed"},
            PermissionDeniedError,
            "HTTP 403: origin_not_allowed",
        ),
        (404, {"detail": "Not found."}, NotFoundError, "HTTP 404: Not found."),
        (409, {"detail": "conflict"}, ConflictError, "HTTP 409: conflict"),
        (429, {"detail": "Too many requests."}, RateLimitError, "HTTP 429: Too many requests."),
        (500, None, InternalServerError, "HTTP 500"),
        (503, {"detail": "unavailable"}, InternalServerError, "HTTP 503: unavailable"),
        (418, {"detail": "teapot"}, APIStatusError, "HTTP 418: teapot"),
    ],
)
def test_status_errors(
    auth: Authentication,
    issuer: FakeIssuer,
    status: int,
    body: object,
    error: type[APIStatusError],
    message: str,
) -> None:
    issuer.reply("POST", "/token/", status, body)
    with pytest.raises(error) as info:
        auth.refresh(REFRESH_TOKEN)
    assert type(info.value) is error
    assert info.value.status == status
    assert info.value.body == body
    assert info.value.message.startswith(message)
    assert REFRESH_TOKEN not in str(info.value)
    if body is not None:
        assert info.value.request_id == "req_synthetic"
    # Token requests are never retried.
    assert issuer.count("/token/") == 1


def test_echoed_secrets_are_redacted(auth: Authentication, issuer: FakeIssuer) -> None:
    issuer.reply("POST", "/token/", 400, {"detail": f"bad token {REFRESH_TOKEN}"})
    with pytest.raises(BadRequestError) as info:
        auth.refresh(REFRESH_TOKEN)
    assert str(info.value) == "HTTP 400: bad token [redacted] (request id req_synthetic)"
    issuer.reply("GET", "/session/", 401, {"detail": f"{ACCESS_TOKEN} is not valid"})
    with pytest.raises(AuthenticationError) as session_info:
        auth.get_session(ACCESS_TOKEN)
    assert ACCESS_TOKEN not in str(session_info.value)
    issuer.reply("POST", "/token/", 400, {"detail": f"{CODE} / {CODE_VERIFIER}"})
    with pytest.raises(BadRequestError) as code_info:
        auth.exchange_code(CODE, code_verifier=CODE_VERIFIER, redirect_uri=REDIRECT_URI)
    assert CODE not in str(code_info.value)
    assert CODE_VERIFIER not in str(code_info.value)


def test_session_errors_are_not_retried(auth: Authentication, issuer: FakeIssuer) -> None:
    issuer.reply("GET", "/session/", 503, {"detail": "unavailable"})
    with pytest.raises(InternalServerError):
        auth.get_session(ACCESS_TOKEN)
    assert issuer.count("/session/") == 1


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, text="<html>", headers={"content-type": "text/html"}),
        httpx.Response(200, json=["not", "an", "object"]),
        httpx.Response(204),
    ],
)
def test_unexpected_success_bodies(
    auth: Authentication, issuer: FakeIssuer, response: httpx.Response
) -> None:
    issuer.route("GET", "/session/", lambda _: response)
    with pytest.raises(APIResponseValidationError) as info:
        auth.get_session(ACCESS_TOKEN)
    assert "/session/" in str(info.value)


@pytest.mark.parametrize(
    ("exc", "error"),
    [
        (httpx.ConnectError("refused"), APIConnectionError),
        (httpx.ReadError("reset"), APIConnectionError),
        (httpx.ConnectTimeout("slow"), APITimeoutError),
        (httpx.ReadTimeout("slow"), APITimeoutError),
    ],
)
def test_transport_errors(
    clock: FakeClock, key: SigningKey, exc: httpx.HTTPError, error: type[APIConnectionError]
) -> None:
    issuer = FakeIssuer([key])
    attempts: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/token/":
            attempts.append(request.method)
            raise exc
        return issuer.handle(request)

    with httpx.Client(transport=httpx.MockTransport(handle)) as http:
        auth = configure(Authentication(ISSUER, http_client=http), clock)
        with pytest.raises(error) as info:
            auth.exchange_code(CODE, code_verifier=CODE_VERIFIER, redirect_uri=REDIRECT_URI)
    assert type(info.value) is error
    assert CODE not in str(info.value)
    assert attempts == ["POST"]


def test_logs_never_contain_tokens(
    auth: Authentication, issuer: FakeIssuer, caplog: pytest.LogCaptureFixture
) -> None:
    issuer.reply("GET", "/session/", 200, SESSION_RESPONSE)
    issuer.reply("POST", "/token/", 200, TOKEN_RESPONSE)
    with caplog.at_level(logging.DEBUG, logger="didit"):
        auth.get_session(ACCESS_TOKEN)
        auth.refresh(REFRESH_TOKEN)
    assert "GET /session/ -> 200" in caplog.text
    assert "POST /token/ -> 200" in caplog.text
    for secret in (ACCESS_TOKEN, REFRESH_TOKEN, "synthetic.access.jwt"):
        assert secret not in caplog.text


# Async ---------------------------------------------------------------------------


def test_async_verifies_tokens(issuer: FakeIssuer, key: SigningKey, clock: FakeClock) -> None:
    async def main() -> None:
        async with issuer.async_client() as http:
            auth = configure(AsyncAuthentication(ISSUER, http_client=http), clock)
            claims = await auth.verify_access_token(key.sign(access_claims()), APPLICATION_ID)
            assert isinstance(claims, AccessTokenClaims)
            assert claims.sub == IDENTITY_ID
            id_token = key.sign(id_claims(), typ="JWT")
            id_claims_ = await auth.verify_id_token(id_token, nonce=NONCE, audience=APPLICATION_ID)
            assert id_claims_.email == "person@example.com"
            with pytest.raises(TokenVerificationError) as info:
                await auth.verify_id_token(id_token, nonce="other", audience=APPLICATION_ID)
            assert info.value.reason == "invalid_nonce"
            with pytest.raises(TokenVerificationError) as alg:
                await auth.verify_access_token(
                    unsigned_token({"alg": "none", "typ": "at+jwt"}, access_claims())
                )
            assert alg.value.reason == "unsupported_algorithm"
            assert (issuer.count(DISCOVERY), issuer.count(JWKS)) == (1, 1)

    asyncio.run(main())


def test_async_unknown_kid_and_caching(
    issuer: FakeIssuer, key: SigningKey, clock: FakeClock
) -> None:
    async def main() -> None:
        async with issuer.async_client() as http:
            auth = configure(AsyncAuthentication(ISSUER, http_client=http), clock)
            await auth.verify_access_token(key.sign(access_claims()))
            rotated = SigningKey.generate("k_synthetic_key_2")
            issuer.keys.append(rotated)
            clock.advance(10)
            with pytest.raises(TokenVerificationError) as info:
                await auth.verify_access_token(rotated.sign(access_claims()))
            assert info.value.reason == "unknown_key"
            clock.advance(50)
            assert (
                await auth.verify_access_token(rotated.sign(access_claims()))
            ).sub == IDENTITY_ID
            assert issuer.count(JWKS) == 2
            clock.advance(300)
            await auth.verify_access_token(key.sign(access_claims()))
            assert (issuer.count(DISCOVERY), issuer.count(JWKS)) == (2, 3)

    asyncio.run(main())


def test_async_concurrent_verifications_fetch_once(
    issuer: FakeIssuer, key: SigningKey, clock: FakeClock
) -> None:
    issuer.jwks_delay = 0.02

    async def main() -> None:
        async with issuer.async_client() as http:
            auth = configure(AsyncAuthentication(ISSUER, http_client=http), clock)
            tokens = [key.sign(access_claims(jti=f"jti-{n}")) for n in range(10)]
            results = await asyncio.gather(*(auth.verify_access_token(t) for t in tokens))
            assert [claims.sub for claims in results] == [IDENTITY_ID] * 10
            assert (issuer.count(DISCOVERY), issuer.count(JWKS)) == (1, 1)

    asyncio.run(main())


def test_async_requests(issuer: FakeIssuer, clock: FakeClock) -> None:
    issuer.reply("POST", "/token/", 200, TOKEN_RESPONSE)
    issuer.reply("GET", "/session/", 200, SESSION_RESPONSE)
    issuer.reply("DELETE", "/session/", 204)
    issuer.reply("POST", "/step-up/", 201, STEP_UP_REQUIRED)
    issuer.reply("GET", f"/step-up/{STEP_UP_ID}/", 200, {**STEP_UP_REQUIRED, "status": "approved"})

    async def main() -> None:
        async with issuer.async_client() as http:
            auth = configure(
                AsyncAuthentication(ISSUER, client_id=APPLICATION_ID, http_client=http), clock
            )
            tokens = await auth.exchange_code(
                CODE, code_verifier=CODE_VERIFIER, redirect_uri=REDIRECT_URI
            )
            assert tokens.session_id == SESSION_ID
            assert form_of(issuer.last("/token/")) == {
                "grant_type": "authorization_code",
                "code": CODE,
                "code_verifier": CODE_VERIFIER,
                "redirect_uri": REDIRECT_URI,
                "client_id": APPLICATION_ID,
            }
            refreshed = await auth.refresh(REFRESH_TOKEN)
            assert refreshed.access_token == "synthetic.access.jwt"
            assert form_of(issuer.last("/token/"))["grant_type"] == "refresh_token"
            session = await auth.get_session(ACCESS_TOKEN)
            assert session.sid == SESSION_ID
            await auth.revoke_session(ACCESS_TOKEN)
            assert issuer.requests[-1].method == "DELETE"
            step_up = await auth.create_step_up(
                ACCESS_TOKEN, action="payout", amount="1500.00", return_to=REDIRECT_URI
            )
            assert step_up.required is True
            assert json.loads(issuer.last("/step-up/").content) == {
                "action": "payout",
                "amount": "1500.00",
                "return_to": REDIRECT_URI,
            }
            retrieved = await auth.retrieve_step_up(ACCESS_TOKEN, STEP_UP_ID)
            assert retrieved.approved
            for request in issuer.requests:
                assert request.headers["x-didit-client"] == f"python/{didit.__version__}"
                assert "x-api-key" not in request.headers
            assert issuer.count(DISCOVERY) == 1

    asyncio.run(main())


def test_async_errors(key: SigningKey, clock: FakeClock) -> None:
    issuer = FakeIssuer([key])
    issuer.reply("POST", "/token/", 400, {"error": "invalid_grant"})

    async def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/session/":
            raise httpx.ReadTimeout("slow", request=request)
        if request.url.path == f"/step-up/{STEP_UP_ID}/":
            raise httpx.ConnectError("refused", request=request)
        return issuer.handle(request)

    async def main() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
            auth = configure(AsyncAuthentication(ISSUER, http_client=http), clock)
            with pytest.raises(BadRequestError, match="invalid_grant"):
                await auth.refresh(REFRESH_TOKEN)
            assert issuer.count("/token/") == 1
            with pytest.raises(APITimeoutError):
                await auth.get_session(ACCESS_TOKEN)
            with pytest.raises(APIConnectionError):
                await auth.retrieve_step_up(ACCESS_TOKEN, STEP_UP_ID)
            with pytest.raises(ConfigurationError, match="audience"):
                await auth.verify_id_token("a.b.c", nonce=NONCE)

    asyncio.run(main())


def test_async_lifecycle(issuer: FakeIssuer) -> None:
    async def main() -> None:
        async with AsyncAuthentication.from_publishable_key(_pk("pk_test_", ISSUER)) as owned:
            assert owned.issuer == ISSUER
            assert repr(owned) == f"AsyncAuthentication(issuer={ISSUER!r}, client_id=None)"
        assert owned._client.is_closed
        async with issuer.async_client() as http:
            await AsyncAuthentication(ISSUER, http_client=http).close()
            assert not http.is_closed

    asyncio.run(main())
