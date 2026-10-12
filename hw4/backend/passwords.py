"""Password hashing for Campus Customs accounts.

Stored form: ``pbkdf2_sha256$<salt>$<hex digest>``.
The iteration count is not in the string. Signup and login both use 120,000
rounds of PBKDF2-HMAC-SHA256, which is what the seed rows were built with.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

ALGORITHM = "pbkdf2_sha256"
ITERATIONS = 120_000
DIGEST_BYTES = 32

# Used when no account exists, so a missing email still pays for one hash.
_MISSING_USER_HASH = ""


def hash_password(password: str, salt: str | None = None) -> str:
    """Hash a new password. A fresh salt is created only when none is passed."""
    if salt is None:
        salt = secrets.token_hex(8)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        ITERATIONS,
        dklen=DIGEST_BYTES,
    )
    return f"{ALGORITHM}${salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Re-hash the typed password with the salt already in ``stored``.

    The stored digest is never reversed. Comparison uses ``hmac.compare_digest``.
    """
    try:
        algorithm, salt, digest_hex = stored.split("$")
        stored_digest = bytes.fromhex(digest_hex)
    except (ValueError, TypeError):
        return False
    if algorithm != ALGORITHM or not salt or len(stored_digest) != DIGEST_BYTES:
        return False
    check = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        ITERATIONS,
        dklen=DIGEST_BYTES,
    )
    return hmac.compare_digest(check, stored_digest)


_MISSING_USER_HASH = hash_password("missing-account", salt="missing-user-salt")


def verify_against_account(password: str, stored: str | None) -> bool:
    """Check a login. A missing account is hashed against a fixed dummy row."""
    return verify_password(password, stored if stored else _MISSING_USER_HASH)
