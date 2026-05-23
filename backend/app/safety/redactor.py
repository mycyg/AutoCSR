"""Replace PII findings in-place with ``<REDACTED_<TYPE>>`` markers."""
from __future__ import annotations

from app.safety.pii_scanner import PIIFinding


def redact(text: str, findings: list[PIIFinding]) -> str:
    if not findings:
        return text
    # Sort by start desc so we can replace without re-computing offsets.
    parts = sorted(findings, key=lambda f: f.range[0], reverse=True)
    out = text
    for f in parts:
        s, e = f.range
        if s < 0 or e > len(out) or s >= e:
            continue
        out = out[:s] + f"<REDACTED_{f.type.upper()}>" + out[e:]
    return out
