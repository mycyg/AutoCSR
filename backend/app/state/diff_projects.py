"""Cross-project outline / drafts diff (M16).

Two modes:

  * ``outline``  — align both projects' outlines by ``node.id``, return
    ``added`` / ``removed`` / ``modified`` (title or notes changed).
  * ``drafts``   — for nodes that exist in both outlines, run a line-level
    diff over the section markdown.
"""
from __future__ import annotations

import difflib
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.outline.store import load as load_outline
from app.report.store import load_draft


class DiffNodeEntry(BaseModel):
    node_id: str
    title: str = ""
    kind: Literal["added", "removed", "modified", "unchanged"] = "unchanged"
    notes: str = ""


class DraftDiffEntry(BaseModel):
    node_id: str
    title: str = ""
    n_added: int = 0
    n_removed: int = 0
    diff: str = ""    # unified diff (truncated)


class DiffResult(BaseModel):
    pid_a: str
    pid_b: str
    mode: Literal["outline", "drafts"]
    outline: list[DiffNodeEntry] = Field(default_factory=list)
    drafts: list[DraftDiffEntry] = Field(default_factory=list)
    summary: dict[str, int] = Field(default_factory=dict)


def diff_projects(pid_a: str, pid_b: str, *, by: str = "outline") -> DiffResult:
    by_norm = by if by in ("outline", "drafts") else "outline"
    result = DiffResult(pid_a=pid_a, pid_b=pid_b, mode=by_norm)  # type: ignore[arg-type]

    out_a = load_outline(pid_a)
    out_b = load_outline(pid_b)
    nodes_a = {n.id: n for n in (out_a.walk() if out_a else [])}
    nodes_b = {n.id: n for n in (out_b.walk() if out_b else [])}

    common = sorted(set(nodes_a) & set(nodes_b))
    added = sorted(set(nodes_b) - set(nodes_a))
    removed = sorted(set(nodes_a) - set(nodes_b))

    for nid in added:
        n = nodes_b[nid]
        result.outline.append(DiffNodeEntry(
            node_id=nid, title=n.title, kind="added", notes=n.notes or "",
        ))
    for nid in removed:
        n = nodes_a[nid]
        result.outline.append(DiffNodeEntry(
            node_id=nid, title=n.title, kind="removed", notes=n.notes or "",
        ))
    for nid in common:
        a = nodes_a[nid]
        b = nodes_b[nid]
        if a.title != b.title or (a.notes or "") != (b.notes or ""):
            result.outline.append(DiffNodeEntry(
                node_id=nid, title=b.title, kind="modified",
                notes=f"title: {a.title!r} → {b.title!r}",
            ))
        else:
            result.outline.append(DiffNodeEntry(
                node_id=nid, title=a.title, kind="unchanged",
            ))

    if by_norm == "drafts":
        for nid in common:
            da = load_draft(pid_a, nid)
            db = load_draft(pid_b, nid)
            md_a = (da.markdown if da else "") or ""
            md_b = (db.markdown if db else "") or ""
            if md_a == md_b:
                continue
            udiff = list(difflib.unified_diff(
                md_a.splitlines(), md_b.splitlines(),
                fromfile=f"{pid_a}:{nid}", tofile=f"{pid_b}:{nid}", lineterm="",
            ))
            n_added = sum(1 for l in udiff if l.startswith("+") and not l.startswith("+++"))
            n_removed = sum(1 for l in udiff if l.startswith("-") and not l.startswith("---"))
            text = "\n".join(udiff[:200])
            if len(udiff) > 200:
                text += f"\n... (+{len(udiff) - 200} more lines truncated)"
            result.drafts.append(DraftDiffEntry(
                node_id=nid,
                title=nodes_a[nid].title,
                n_added=n_added, n_removed=n_removed,
                diff=text,
            ))

    result.summary = {
        "n_added": len(added),
        "n_removed": len(removed),
        "n_modified": sum(1 for e in result.outline if e.kind == "modified"),
        "n_unchanged": sum(1 for e in result.outline if e.kind == "unchanged"),
        "n_draft_diffs": len(result.drafts),
    }
    return result
