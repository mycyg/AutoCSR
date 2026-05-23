"""Audit trail + electronic signature (M15).

21 CFR Part 11-style append-only event log with SHA256 hash chain plus
project-scoped ed25519 electronic signatures. Pluggable backend
(:class:`AuditBackend`) so community deployments can swap the default
monthly-sharded JSONL files for S3 Object Lock / IPFS without touching
callers.

Public surface (re-exports):
    AuditEvent, JSONLBackend, get_backend, append_event, verify_chain
    sign, verify, list_signatures
"""
from __future__ import annotations

from app.audit.schemas import AuditEvent, Signature  # noqa: F401
from app.audit.trail import (  # noqa: F401
    AuditBackend, JSONLBackend, append_event, get_backend, read_events,
    verify_chain,
)
from app.audit.signature import (  # noqa: F401
    SignatureError, list_signatures, load_signature, sign, verify,
)
