"""ES256 (ECDSA P-256 with SHA-256) signature checks.

``cryptography`` is an optional extra (``pip install 'didit-sdk[auth]'``), so it is
imported here, when a signature is first checked, and never when
``didit.authentication`` is imported.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurvePublicKey

__all__ = ["INSTALL_HINT", "load_p256_key", "verify_es256"]

INSTALL_HINT = (
    "Verifying Didit Authentication tokens needs the cryptography package: "
    "pip install 'didit-sdk[auth]'."
)


def load_p256_key(x: int, y: int) -> EllipticCurvePublicKey:
    """The P-256 public key at point ``(x, y)``; :class:`ValueError` if the point is not on the curve."""
    try:
        from cryptography.hazmat.primitives.asymmetric import ec
    except ImportError as exc:
        raise ImportError(INSTALL_HINT) from exc
    return ec.EllipticCurvePublicNumbers(x, y, ec.SECP256R1()).public_key()


def verify_es256(key: EllipticCurvePublicKey, signing_input: bytes, signature: bytes) -> bool:
    """Whether ``signature`` (JWS form: the 32-byte ``r`` then the 32-byte ``s``) signs ``signing_input``."""
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
    except ImportError as exc:
        raise ImportError(INSTALL_HINT) from exc
    if len(signature) != 64:
        return False
    r = int.from_bytes(signature[:32], "big")
    s = int.from_bytes(signature[32:], "big")
    try:
        key.verify(encode_dss_signature(r, s), signing_input, ec.ECDSA(hashes.SHA256()))
    except InvalidSignature:
        return False
    return True
