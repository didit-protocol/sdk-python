"""Didit Authentication for your backend (docs/DESIGN.md section 10).

    from didit.authentication import Authentication, TokenVerificationError

    auth = Authentication.from_publishable_key("pk_live_...", client_id=APPLICATION_ID)
    try:
        claims = auth.verify_access_token(access_token)
    except TokenVerificationError as exc:
        ...  # exc.reason is machine readable, for example "expired"

Each application has its own OpenID Connect issuer (``https://<slug>.auth.didit.me``
or its custom domain). This module verifies the ES256 tokens it signs, exchanges
and refreshes codes, checks and revokes sessions and runs step-ups. It never
uses your Didit API key. Token verification needs ``pip install 'didit-sdk[auth]'``.
"""

from ._client import (
    DEFAULT_LEEWAY,
    DEFAULT_TIMEOUT,
    Amount,
    AsyncAuthentication,
    Audience,
    Authentication,
)
from ._errors import TokenVerificationError, TokenVerificationReason
from ._pkce import PkcePair, create_nonce, create_pkce, create_state
from ._types import (
    AccessTokenClaims,
    ActorClaim,
    AuthenticationSession,
    IdTokenClaims,
    OrganizationClaim,
    OrganizationRole,
    SessionCustomRole,
    SessionOrganization,
    StepUp,
    StepUpAction,
    StepUpMethod,
    StepUpRule,
    StepUpStatus,
    TokenResponse,
    VerificationLevel,
    VerifiedClaims,
)

__all__ = [
    "DEFAULT_LEEWAY",
    "DEFAULT_TIMEOUT",
    "AccessTokenClaims",
    "ActorClaim",
    "Amount",
    "AsyncAuthentication",
    "Audience",
    "Authentication",
    "AuthenticationSession",
    "IdTokenClaims",
    "OrganizationClaim",
    "OrganizationRole",
    "PkcePair",
    "SessionCustomRole",
    "SessionOrganization",
    "StepUp",
    "StepUpAction",
    "StepUpMethod",
    "StepUpRule",
    "StepUpStatus",
    "TokenResponse",
    "TokenVerificationError",
    "TokenVerificationReason",
    "VerificationLevel",
    "VerifiedClaims",
    "create_nonce",
    "create_pkce",
    "create_state",
]
