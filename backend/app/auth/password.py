"""Password hashing — bcrypt with passlib sha256_crypt fallback.

We prefer bcrypt (cost 12) for production strength; on stripped-down
environments where the wheel isn't present, fall back to passlib's
sha256_crypt so the auth layer still functions for tests / dev.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("autocsr.auth.password")

_BCRYPT_OK = False
_PASSLIB_OK = False

try:
    import bcrypt  # type: ignore

    _BCRYPT_OK = True
except Exception:  # noqa: BLE001
    bcrypt = None  # type: ignore

if not _BCRYPT_OK:
    try:
        from passlib.hash import sha256_crypt  # type: ignore

        _PASSLIB_OK = True
    except Exception:  # noqa: BLE001
        sha256_crypt = None  # type: ignore


def hash_password(password: str) -> str:
    """Hash a password using the strongest available algorithm.

    Empty / None passwords are rejected so dev accounts can never end up
    with a usable login by mistake.
    """
    if not password:
        raise ValueError("password must be non-empty")
    if _BCRYPT_OK:
        salt = bcrypt.gensalt(rounds=12)  # type: ignore[union-attr]
        return "bcrypt$" + bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")  # type: ignore[union-attr]
    if _PASSLIB_OK:
        return "sha256$" + sha256_crypt.hash(password)  # type: ignore[union-attr]
    raise RuntimeError(
        "no password hashing backend available; install bcrypt or passlib"
    )


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a plaintext password against the stored hash.

    Tolerates legacy / cross-backend hashes:
        bcrypt$<hash>          — preferred
        sha256$<hash>          — passlib fallback
        $2b$... (raw bcrypt)   — historical
        $5$...   (raw sha256)  — historical
    """
    if not password or not password_hash:
        return False
    try:
        if password_hash.startswith("bcrypt$"):
            if not _BCRYPT_OK:
                logger.warning("bcrypt_hash_no_backend")
                return False
            return bcrypt.checkpw(  # type: ignore[union-attr]
                password.encode("utf-8"), password_hash[len("bcrypt$"):].encode("utf-8")
            )
        if password_hash.startswith("sha256$"):
            if not _PASSLIB_OK:
                return False
            return sha256_crypt.verify(password, password_hash[len("sha256$"):])  # type: ignore[union-attr]
        if password_hash.startswith("$2"):
            if not _BCRYPT_OK:
                return False
            return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))  # type: ignore[union-attr]
        if password_hash.startswith("$5$"):
            if not _PASSLIB_OK:
                return False
            return sha256_crypt.verify(password, password_hash)  # type: ignore[union-attr]
    except Exception as e:  # noqa: BLE001
        logger.warning("verify_password_error: %s", e)
        return False
    return False


def backend_info() -> dict[str, bool]:
    return {"bcrypt": _BCRYPT_OK, "passlib": _PASSLIB_OK}
