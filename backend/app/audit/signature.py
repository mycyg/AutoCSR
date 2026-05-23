"""Electronic signature (M15).

Per-project ed25519 keypair generated lazily on first ``sign`` call and
persisted as ``data/projects/<pid>/keys/<key_id>.{pub,priv}``. Signatures
land in ``data/projects/<pid>/signatures/<sig_id>.json``.

If the ``cryptography`` package is unavailable (Windows wheel fail) we
fall back to a deterministic HMAC-SHA256 ``algorithm='fallback-hmac'``
so the demo still works; production callers can swap this for HSM.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.audit.schemas import Signature
from app.config import data_dir

logger = logging.getLogger("autocsr.audit.signature")


class SignatureError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Backend detection — prefer cryptography ed25519, fallback HMAC
# ---------------------------------------------------------------------------

try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey, Ed25519PublicKey,
    )
    from cryptography.hazmat.primitives.serialization import (
        Encoding, NoEncryption, PrivateFormat, PublicFormat,
        load_pem_private_key, load_pem_public_key,
    )
    _HAS_CRYPTO = True
except Exception:  # noqa: BLE001
    _HAS_CRYPTO = False


_LOCK_GUARD = threading.Lock()
_LOCKS: dict[str, threading.RLock] = {}


def _plock(pid: str) -> threading.RLock:
    with _LOCK_GUARD:
        lk = _LOCKS.get(pid)
        if lk is None:
            lk = threading.RLock()
            _LOCKS[pid] = lk
        return lk


def _keys_dir(pid: str) -> Path:
    p = data_dir() / "projects" / pid / "keys"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _signatures_dir(pid: str) -> Path:
    p = data_dir() / "projects" / pid / "signatures"
    p.mkdir(parents=True, exist_ok=True)
    return p


# ---------------------------------------------------------------------------
# Key management
# ---------------------------------------------------------------------------

def _ensure_keypair(pid: str) -> str:
    """Return the active key id; generate one on first call."""
    keys = _keys_dir(pid)
    # Active key is the lexicographically largest .pub
    existing = sorted(keys.glob("*.pub"))
    if existing:
        return existing[-1].stem
    key_id = "k_" + uuid.uuid4().hex[:10]
    if _HAS_CRYPTO:
        priv = Ed25519PrivateKey.generate()
        pub = priv.public_key()
        priv_pem = priv.private_bytes(
            encoding=Encoding.PEM,
            format=PrivateFormat.PKCS8,
            encryption_algorithm=NoEncryption(),
        )
        pub_pem = pub.public_bytes(
            encoding=Encoding.PEM,
            format=PublicFormat.SubjectPublicKeyInfo,
        )
        (keys / f"{key_id}.priv").write_bytes(priv_pem)
        (keys / f"{key_id}.pub").write_bytes(pub_pem)
    else:
        # HMAC-fallback "keypair": pub == priv == 32 random bytes b64
        secret = secrets.token_bytes(32)
        material = base64.b64encode(secret).decode("ascii")
        (keys / f"{key_id}.priv").write_text(material, encoding="utf-8")
        (keys / f"{key_id}.pub").write_text(material, encoding="utf-8")
    try:
        os.chmod(keys / f"{key_id}.priv", 0o600)
    except Exception:
        pass
    return key_id


def _load_private(pid: str, key_id: str) -> Any:
    p = _keys_dir(pid) / f"{key_id}.priv"
    if not p.exists():
        raise SignatureError(f"private key {key_id} missing for project {pid}")
    if _HAS_CRYPTO:
        return load_pem_private_key(p.read_bytes(), password=None)
    return base64.b64decode(p.read_text(encoding="utf-8"))


def _load_public(pid: str, key_id: str) -> Any:
    p = _keys_dir(pid) / f"{key_id}.pub"
    if not p.exists():
        raise SignatureError(f"public key {key_id} missing for project {pid}")
    if _HAS_CRYPTO:
        return load_pem_public_key(p.read_bytes())
    return base64.b64decode(p.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Artefact hashing
# ---------------------------------------------------------------------------

def _hash_artifact(pid: str, artifact_type: str, artifact_id: str) -> str:
    """Resolve the bytes the signature is anchored on.

    For an opaque artefact (the e2e signs a docx filename) we hash the
    file content; for in-store records (draft, review) we hash the
    canonical JSON.
    """
    pdir = data_dir() / "projects" / pid
    if artifact_type == "docx":
        for sub in ("exports", "exports/docx"):
            cand = pdir / sub / artifact_id
            if cand.exists():
                return hashlib.sha256(cand.read_bytes()).hexdigest()
    if artifact_type == "draft":
        # Hash the JSON payload via report.store
        try:
            from app.report.store import load_draft
            d = load_draft(pid, artifact_id)
            if d is not None:
                return hashlib.sha256(
                    d.model_dump_json().encode("utf-8")
                ).hexdigest()
        except Exception:
            pass
    if artifact_type == "blinding_change" or artifact_type == "lock":
        # Hash a canonical marker representing the policy change
        return hashlib.sha256(
            f"{artifact_type}:{artifact_id}".encode("utf-8")
        ).hexdigest()
    # Fallback: hash the artifact_id string so signatures are reproducible
    return hashlib.sha256(artifact_id.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------

def sign(
    project_id: str,
    artifact_type: str,
    artifact_id: str,
    signer: str,
    reason: str = "",
) -> Signature:
    if not signer:
        raise SignatureError("signer required")
    with _plock(project_id):
        key_id = _ensure_keypair(project_id)
        priv = _load_private(project_id, key_id)
        h = _hash_artifact(project_id, artifact_type, artifact_id)
        message = h.encode("utf-8")
        if _HAS_CRYPTO:
            sig_bytes = priv.sign(message)
            algo = "ed25519"
        else:
            sig_bytes = hmac.new(priv, message, hashlib.sha256).digest()
            algo = "fallback-hmac"
        sig = Signature(
            id="sig_" + uuid.uuid4().hex[:12],
            ts=datetime.now(timezone.utc),
            signer=signer,
            reason=reason,
            signed_artifact_type=artifact_type,
            signed_artifact_id=artifact_id,
            signed_artifact_hash=h,
            public_key_id=key_id,
            signature=base64.b64encode(sig_bytes).decode("ascii"),
            algorithm=algo,  # type: ignore[arg-type]
        )
        path = _signatures_dir(project_id) / f"{sig.id}.json"
        path.write_text(
            json.dumps(json.loads(sig.model_dump_json()),
                       ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    # WS notify
    try:
        from app.server.ws import publish_sync
        publish_sync(project_id, "audit.signature_added", {
            "id": sig.id, "signer": signer, "reason": reason,
            "artifact_type": artifact_type, "artifact_id": artifact_id,
        })
    except Exception:
        pass
    # Mirror into audit chain
    try:
        from app.audit.trail import append_event, make_event
        append_event(project_id, make_event(
            actor=signer, action="audit.sign",
            resource_type=artifact_type, resource_id=artifact_id,
            after_hash=h, reason=reason,
            extra={"signature_id": sig.id, "key_id": key_id, "algorithm": algo},
        ))
    except Exception:
        pass
    return sig


def verify(project_id: str, sig_id: str) -> bool:
    sig = load_signature(project_id, sig_id)
    if sig is None:
        return False
    try:
        h = _hash_artifact(project_id, sig.signed_artifact_type, sig.signed_artifact_id)
    except Exception:
        return False
    if h != sig.signed_artifact_hash:
        return False
    try:
        sig_bytes = base64.b64decode(sig.signature)
        message = sig.signed_artifact_hash.encode("utf-8")
        if sig.algorithm == "ed25519" and _HAS_CRYPTO:
            pub = _load_public(project_id, sig.public_key_id)
            try:
                pub.verify(sig_bytes, message)
                return True
            except Exception:
                return False
        if sig.algorithm == "fallback-hmac":
            secret = _load_public(project_id, sig.public_key_id)
            expected = hmac.new(secret, message, hashlib.sha256).digest()
            return hmac.compare_digest(expected, sig_bytes)
    except Exception:
        return False
    return False


def load_signature(project_id: str, sig_id: str) -> Signature | None:
    p = _signatures_dir(project_id) / f"{sig_id}.json"
    if not p.exists():
        return None
    try:
        return Signature.model_validate_json(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def list_signatures(project_id: str) -> list[Signature]:
    out: list[Signature] = []
    for p in sorted(_signatures_dir(project_id).glob("sig_*.json")):
        try:
            out.append(Signature.model_validate_json(p.read_text(encoding="utf-8")))
        except Exception:
            continue
    return sorted(out, key=lambda s: s.ts, reverse=True)
