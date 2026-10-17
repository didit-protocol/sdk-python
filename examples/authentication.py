"""Didit Authentication in your backend: verify the access token on every API call,
and gate a sensitive action behind a step-up.

    pip install "didit-sdk[auth]"
    export DIDIT_PUBLISHABLE_KEY=pk_test_...     # from the Authentication settings
    export DIDIT_APPLICATION_ID=...              # your application id (the OAuth client_id)
    python examples/authentication.py <access token>
"""

from __future__ import annotations

import os
import sys

from didit.authentication import AccessTokenClaims, Authentication, TokenVerificationError

# One instance per process: it caches the issuer's discovery document and keys.
auth = Authentication.from_publishable_key(
    os.environ["DIDIT_PUBLISHABLE_KEY"],
    client_id=os.environ["DIDIT_APPLICATION_ID"],
)


def current_user(authorization_header: str) -> AccessTokenClaims:
    """What an API route of yours does with ``Authorization: Bearer <token>``."""
    scheme, _, token = authorization_header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise PermissionError("missing bearer token")
    try:
        return auth.verify_access_token(token)
    except TokenVerificationError as err:
        raise PermissionError(f"invalid token: {err.reason}") from err


def approve_payout(access_token: str, amount: str) -> str:
    """Ask Didit whether this payout needs a fresh verification first."""
    step_up = auth.create_step_up(
        access_token,
        action="payout",
        amount=amount,
        currency="EUR",
        return_to="https://example.com/payouts/confirm",
    )
    if not step_up.required:
        return "go ahead"
    # Send the person to step_up.verification_url. When they come back, read the
    # step-up again and act only on status "approved".
    return f"verify first: {step_up.verification_url}"


if __name__ == "__main__":
    claims = current_user(f"Bearer {sys.argv[1]}")
    print("user", claims.sub, "session", claims.sid, "vendor_data", claims.vendor_data)
    # get_session() asks the issuer, so it also catches sessions revoked a moment ago.
    print("session still active:", auth.get_session(sys.argv[1]).model_dump(exclude_none=True))
