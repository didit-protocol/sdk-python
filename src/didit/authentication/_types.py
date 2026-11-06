"""Token claims and issuer responses of Didit Authentication (docs/DESIGN.md section 10).

Shapes follow ``service-didit-auth`` (``authentication/services/issuer.py``,
``services/tokens.py``, ``services/step_ups.py`` and ``views/runtime.py``).
Every model keeps fields and claims this version does not know (``model_extra``).
"""

from __future__ import annotations

import datetime as _dt
from typing import Any, Literal

from pydantic import Field

from .._models import BaseModel

__all__ = [
    "AccessTokenClaims",
    "ActorClaim",
    "AuthenticationSession",
    "IdTokenClaims",
    "OrganizationClaim",
    "OrganizationRole",
    "SessionCustomRole",
    "SessionOrganization",
    "StepUp",
    "StepUpAction",
    "StepUpMethod",
    "StepUpRule",
    "StepUpStatus",
    "TokenResponse",
    "VerificationLevel",
    "VerifiedClaims",
]

OrganizationRole = Literal["admin", "member", "billing"]
VerificationLevel = Literal["liveness", "liveness_face_match", "full_id"]
StepUpAction = Literal["payout", "bank", "contact"]
StepUpRule = Literal["payout", "device", "bank", "contact"]
StepUpMethod = Literal["liveness", "selfie", "full_id"]
StepUpStatus = Literal["pending", "review", "approved", "declined", "expired", "superseded"]


class OrganizationClaim(BaseModel):
    """``org``: the person's earliest organization membership, when customer organizations are on."""

    id: str
    role: OrganizationRole | str | None = None


class ActorClaim(BaseModel):
    """``act``: the agent acting for the person. Only agent access tokens carry it."""

    sub: str
    """The agent id."""
    agent: str | None = None
    """The agent's name."""
    scopes: list[str] | None = None
    """What the person allowed the agent to do; never act beyond these."""


class VerifiedClaims(BaseModel):
    """``verified``: the highest approved verification level and the claims the
    application selected. Empty when the person has not been verified."""

    level: VerificationLevel | str | None = None
    over_18: bool | None = None
    over_21: bool | None = None
    given_name: str | None = None
    family_name: str | None = None
    birthdate: str | None = None
    nationality: str | None = None
    country: str | None = None
    document_verified: bool | None = None
    liveness: bool | None = None


class _TokenClaims(BaseModel):
    iss: str
    """The issuer."""
    sub: str
    """The identity id."""
    aud: str | list[str] | None = None
    """The application id."""
    sid: str | None = None
    """The session id (the grant id on an agent token)."""
    jti: str | None = None
    iat: int
    exp: int
    nbf: int | None = None
    vendor_data: str | None = None
    """The person's reference across Didit products (verification sessions, monitoring)."""
    amr: list[str] | None = None
    """How the person signed in, for example ``["passkey"]``; empty on an agent token."""
    org: OrganizationClaim | None = None
    verified: VerifiedClaims | None = None
    act: ActorClaim | None = None
    """``None`` for a person; the agent on an agent access token."""


class AccessTokenClaims(_TokenClaims):
    """The verified claims of an access token (header ``typ: at+jwt``)."""

    client_id: str | None = None
    """The application id."""


class IdTokenClaims(_TokenClaims):
    """The verified claims of an ID token (header ``typ: JWT``)."""

    auth_time: int | None = None
    nonce: str | None = None
    email: str | None = None
    email_verified: bool | None = None
    name: str | None = None
    phone_number: str | None = None


class TokenResponse(BaseModel):
    """``POST token/``: new tokens. The tokens are left out of ``repr``; never log them."""

    access_token: str = Field(repr=False)
    """A JWT access token that expires within five minutes."""
    token_type: str
    expires_in: int
    """Seconds until ``access_token`` expires."""
    refresh_token: str | None = Field(default=None, repr=False)
    """Opaque and single use: every refresh returns a new one."""
    id_token: str | None = Field(default=None, repr=False)
    session_id: str | None = None


class SessionCustomRole(BaseModel):
    key: str | None = None
    permissions: list[str] | None = None


class SessionOrganization(BaseModel):
    organization_id: str | None = None
    organization_name: str | None = Field(default=None, alias="organization__name")
    """Sent by the API as ``organization__name``."""
    role: OrganizationRole | str | None = None
    custom_role: SessionCustomRole | None = None


class AuthenticationSession(BaseModel):
    """``GET session/``: the live session behind an access token."""

    sub: str
    """The identity id."""
    sid: str
    """The session id."""
    application_id: str | None = None
    vendor_data: str | None = None
    amr: list[str] | None = None
    mfa_verified: bool | None = None
    email: str | None = None
    email_verified: bool | None = None
    phone: str | None = None
    verified_identity: dict[str, Any] | None = None
    verified: VerifiedClaims | None = None
    expires_at: _dt.datetime | None = None
    post_logout_redirect_uri: str | None = None
    organizations: list[SessionOrganization] | None = None


class StepUp(BaseModel):
    """A step-up: ``POST step-up/`` and ``GET step-up/{id}/``.

    When ``POST step-up/`` finds no rule that applies it answers only
    ``required=False``: the action may go ahead. Otherwise send the person to
    ``verification_url``, then read the step-up again with ``retrieve_step_up``
    and act only when :attr:`approved` is true.
    """

    required: bool | None = None
    """``POST step-up/`` only: whether the person must verify before the action."""
    id: str | None = None
    rule: StepUpRule | str | None = None
    method: StepUpMethod | str | None = None
    status: StepUpStatus | str | None = None
    level: VerificationLevel | str | None = None
    amount: str | None = None
    currency: str | None = None
    created_at: _dt.datetime | None = None
    completed_at: _dt.datetime | None = None
    expires_at: _dt.datetime | None = None
    verification_url: str | None = None
    """``POST step-up/`` only: where to send the person to verify."""
    expires_in: int | None = None
    """``POST step-up/`` only: seconds the person has to verify."""

    @property
    def approved(self) -> bool:
        """``True`` only for status ``approved``: the one status to act on."""
        return self.status == "approved"
