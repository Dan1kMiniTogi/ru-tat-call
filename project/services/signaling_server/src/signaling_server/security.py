"""Password hashing and opaque session tokens."""

import hashlib
import hmac
import secrets

_PBKDF2_ROUNDS = 120_000


def hash_password(password: str) -> str:
    """Hash a password with PBKDF2-HMAC-SHA256.

    Args:
        password: Plain text password.

    Returns:
        Stored form `salt$hexdigest`.

    Example:
        stored = hash_password("family")
        assert verify_password("family", stored)
    """
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), _PBKDF2_ROUNDS
    )
    return f"{salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Check a password against `hash_password` output.

    Args:
        password: Candidate plain text.
        stored: Value from the database.
    """
    try:
        salt, digest_hex = stored.split("$", 1)
    except ValueError:
        return False
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), _PBKDF2_ROUNDS
    )
    return hmac.compare_digest(digest.hex(), digest_hex)


def new_token() -> str:
    """URL-safe random token for access/refresh/group ids."""
    return secrets.token_urlsafe(32)
