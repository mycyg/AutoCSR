"""Structured diff between two SectionDraft versions (M11).

Uses ``difflib.SequenceMatcher`` over the markdown source so the result
travels back to the frontend as a list of typed blocks. The frontend can
render them as inline highlights or as a unified-style two-pane view.

Block shape:

    {
      "op":  "equal" | "insert" | "delete" | "replace",
      "v1_range": [i1, i2],
      "v2_range": [j1, j2],
      "v1_text":  str,
      "v2_text":  str,
    }

The text excerpts are clipped to 2 KB per block so very long sections do
not blow up the WS payload.
"""
from __future__ import annotations

import difflib
from typing import Any


_MAX_BLOCK_CHARS = 2000


def diff_markdown(v1_md: str, v2_md: str) -> list[dict[str, Any]]:
    """Return a list of difflib opcode-derived blocks.

    Operates at the character level so insert/delete of tokens (numbers,
    Ref codes, punctuation) show up as their own blocks rather than
    being smeared across whole paragraphs.
    """
    matcher = difflib.SequenceMatcher(a=v1_md, b=v2_md, autojunk=False)
    blocks: list[dict[str, Any]] = []
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        v1_text = v1_md[i1:i2]
        v2_text = v2_md[j1:j2]
        if len(v1_text) > _MAX_BLOCK_CHARS:
            v1_text = v1_text[:_MAX_BLOCK_CHARS] + f"…(+{len(v1_md[i1:i2]) - _MAX_BLOCK_CHARS} chars)"
        if len(v2_text) > _MAX_BLOCK_CHARS:
            v2_text = v2_text[:_MAX_BLOCK_CHARS] + f"…(+{len(v2_md[j1:j2]) - _MAX_BLOCK_CHARS} chars)"
        blocks.append({
            "op": op,
            "v1_range": [i1, i2],
            "v2_range": [j1, j2],
            "v1_text": v1_text,
            "v2_text": v2_text,
        })
    return blocks


def diff_summary(blocks: list[dict[str, Any]]) -> dict[str, int]:
    """Counts per op for a quick badge in the UI."""
    out = {"equal": 0, "insert": 0, "delete": 0, "replace": 0}
    for b in blocks:
        op = b.get("op", "equal")
        if op in out:
            out[op] += 1
    return out
