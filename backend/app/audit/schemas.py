"""Audit + signature schemas (M15)."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class AuditEvent(BaseModel):
    """One entry in the per-project append-only audit log.

    The chain anchors each event to the previous one via SHA-256 so any
    tampering inside the JSONL file breaks ``verify_chain``.
    """
    id: str
    ts: datetime
    actor: str = ""
    action: str = ""              # e.g. "POST /projects/{pid}/cleansing/apply"
    resource_type: str = ""       # e.g. "draft" | "stat" | "project"
    resource_id: str = ""
    before_hash: str | None = None
    after_hash: str | None = None
    reason: str | None = None
    ip: str | None = None
    extra: dict = Field(default_factory=dict)
    prev_event_hash: str = ""     # SHA256 of previous event_hash (or "" for genesis)
    curr_event_hash: str = ""     # SHA256 of canonical_json(payload-with-prev-hash)


class Signature(BaseModel):
    """Project-scoped ed25519 signature over an artefact's content hash."""
    id: str
    ts: datetime
    signer: str = ""
    reason: str = ""
    signed_artifact_type: str = ""    # "docx" | "draft" | "review" | "blinding_change" | ...
    signed_artifact_id: str = ""
    signed_artifact_hash: str = ""    # SHA-256 hex of the artefact bytes / canonical json
    public_key_id: str = ""
    signature: str = ""               # base64-encoded ed25519 signature
    algorithm: Literal["ed25519", "fallback-hmac"] = "ed25519"


class ChainVerifyResult(BaseModel):
    verified: bool
    total: int = 0
    broken_at: str | None = None      # event id where the chain broke
    error: str | None = None
