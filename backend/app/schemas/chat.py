"""Chat-editor schemas — per-section conversational edits.

Each `ChatMessage` belongs to one outline section (node_id). The editor LLM
may emit zero or more `Patch` objects per turn; each patch represents one
atomic mutation that has already been applied to the section markdown.

Patch ops (4):
  * replace_section        — overwrite the whole markdown body
  * insert_paragraph       — insert a new paragraph after `target` (int index)
  * replace_paragraph      — replace paragraph at `target` (int index)
  * patch_field            — regex / literal substitution; ``target`` is a regex
                              pattern (or the literal `before` string) and
                              ``after`` is the replacement.

`Patch.before` / `Patch.after` carry the exact strings so the frontend can
diff them; `applied=True` means the editor already wrote `after` to disk.
A patch can later be reversed via the `rollback` endpoint by restoring an
older `SectionDraft` version snapshot.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

PatchOp = Literal[
    "replace_section",
    "insert_paragraph",
    "replace_paragraph",
    "patch_field",
]

ChatRole = Literal["user", "assistant", "system"]


class Patch(BaseModel):
    op: PatchOp
    target: int | str | None = None   # paragraph index or regex/literal anchor
    before: str = ""
    after: str = ""
    applied: bool = False
    note: str = ""                    # optional commentary from the editor


class ChatMessage(BaseModel):
    id: str
    role: ChatRole
    content: str
    patches: list[Patch] = Field(default_factory=list)
    ts: datetime
    meta: dict[str, Any] = Field(default_factory=dict)   # tool calls, tokens, etc.


class ChatTurnResult(BaseModel):
    assistant_message: ChatMessage
    patches: list[Patch] = Field(default_factory=list)
    new_version: int | None = None      # SectionDraft version after edits (None if no edit)
    new_warnings: list[str] = Field(default_factory=list)
