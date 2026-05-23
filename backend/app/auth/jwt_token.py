"""JWT helpers — python-jose with PyJWT fallback.

Secrets:
    settings.auth.jwt_secret   — long random string; auto-generated on
                                  first boot if missing and persisted via
                                  app.config.save(...) so all subsequent
                                  processes share the same secret.

Token shape:
    {
        "sub": user_id,
        "tid": tenant_id,
        "typ": "access" | "refresh",
        "iat": int,
        "exp": int,
    }
"""
from __future__ import annotations

import logging
import secrets
import threading
from datetime import datetime, timedelta, timezone
from typing import Any

from app.config import settings, save as save_settings

logger = logging.getLogger("autocsr.auth.jwt")

_BACKEND = "none"
_jose_jwt = None
_pyjwt = None

try:
    from jose import jwt as _jose_jwt  # type: ignore
    from jose import JWTError as _JoseJWTError  # type: ignore

    _BACKEND = "jose"
except Exception:  # noqa: BLE001
    try:
        import jwt as _pyjwt  # type: ignore

        _BACKEND = "pyjwt"
    except Exception:  # noqa: BLE001
        pass


_SECRET_LOCK = threading.Lock()
_ALGORITHM = "HS256"
ACCESS_EXPIRES = timedelta(hours=24)
REFRESH_EXPIRES = timedelta(days=30)


def _get_secret() -> str:
    """Return the JWT secret, generating + persisting one if absent."""
    with _SECRET_LOCK:
        s = settings()
        auth_seg = dict(s.get("auth") or {})
        secret = auth_seg.get("jwt_secret")
        if isinstance(secret, str) and len(secret) >= 32:
            return secret
        # Generate + persist.
        secret = secrets.token_urlsafe(48)
        auth_seg["jwt_secret"] = secret
        # Preserve dev_mode default to True for backwards-compat with the
        # M2-M20 e2e suite when the user hasn't pinned a value yet.
        auth_seg.setdefault("dev_mode", True)
        merged = dict(s)
        merged["auth"] = auth_seg
        try:
            save_settings(merged)
            logger.info("auth.jwt_secret.generated_and_persisted")
        except Exception as e:  # noqa: BLE001
            logger.warning("auth.jwt_secret.persist_failed: %s", e)
        return secret


def _encode(claims: dict[str, Any]) -> str:
    secret = _get_secret()
    if _BACKEND == "jose":
        return _jose_jwt.encode(claims, secret, algorithm=_ALGORITHM)  # type: ignore[union-attr]
    if _BACKEND == "pyjwt":
        return _pyjwt.encode(claims, secret, algorithm=_ALGORITHM)  # type: ignore[union-attr]
    raise RuntimeError("no JWT backend available; install python-jose or PyJWT")


def _decode(token: str) -> dict[str, Any]:
    secret = _get_secret()
    if _BACKEND == "jose":
        return _jose_jwt.decode(token, secret, algorithms=[_ALGORITHM])  # type: ignore[union-attr]
    if _BACKEND == "pyjwt":
        return _pyjwt.decode(token, secret, algorithms=[_ALGORITHM])  # type: ignore[union-attr]
    raise RuntimeError("no JWT backend available")


def create_access_token(user_id: str, tenant_id: str,
                          expires: timedelta = ACCESS_EXPIRES) -> str:
    now = datetime.now(timezone.utc)
    claims = {
        "sub": user_id,
        "tid": tenant_id,
        "typ": "access",
        "iat": int(now.timestamp()),
        "exp": int((now + expires).timestamp()),
    }
    return _encode(claims)


def create_refresh_token(user_id: str, tenant_id: str = "default",
                          expires: timedelta = REFRESH_EXPIRES) -> str:
    now = datetime.now(timezone.utc)
    claims = {
        "sub": user_id,
        "tid": tenant_id,
        "typ": "refresh",
        "iat": int(now.timestamp()),
        "exp": int((now + expires).timestamp()),
    }
    return _encode(claims)


def decode_token(token: str) -> dict[str, Any]:
    """Raises ValueError on any decode / expiry error."""
    try:
        claims = _decode(token)
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"invalid_token: {e}")
    return claims


def backend_info() -> dict[str, str]:
    return {"backend": _BACKEND, "algorithm": _ALGORITHM}
