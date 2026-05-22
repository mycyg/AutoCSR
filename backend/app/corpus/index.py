"""Corpus index — grep-first retrieval across 4 block types.

Design notes (no third-party code reuse — this is rewritten against AutoCSR's
schema):

* Each block is one JSON file under <data>/projects/<pid>/corpus/blocks/<bid>.json
* The project's index.json holds [block_id, type, page, col, para, snippet_first_120]
  for fast in-memory scan without re-reading every block file.
* `search()` does multi-term OR scoring via rapidfuzz.partial_ratio, with a small
  exact-substring bonus. Embedding rerank is a stub that activates only when an
  `embedding` section is configured in settings.yaml.
* Ref code formats:
    literature   Ref<block_id>.P<page>.Col<col>.Para<para>
    stat         Ref<stat_id>.var<col>
    principle    Ref<principle_id>.S<section_id>
    note         Ref<block_id>
"""
from __future__ import annotations

import json
import re
import threading
import uuid
from pathlib import Path
from typing import Any, Iterable, Literal

from pydantic import BaseModel, Field
from rapidfuzz import fuzz

from app.config import data_dir

BlockType = Literal["literature", "stat", "principle", "note"]

_LOCKS: dict[str, threading.RLock] = {}
_LOCKS_GUARD = threading.Lock()


def _project_lock(pid: str) -> threading.RLock:
    with _LOCKS_GUARD:
        if pid not in _LOCKS:
            _LOCKS[pid] = threading.RLock()
        return _LOCKS[pid]


def _corpus_dir(pid: str) -> Path:
    p = data_dir() / "projects" / pid / "corpus"
    (p / "blocks").mkdir(parents=True, exist_ok=True)
    return p


def _index_path(pid: str) -> Path:
    return _corpus_dir(pid) / "index.json"


class Block(BaseModel):
    id: str = ""
    project_id: str
    type: BlockType
    page: int = 1
    col: int = 1
    para: int = 1
    text: str
    meta: dict[str, Any] = Field(default_factory=dict)


class BlockHit(BaseModel):
    block: Block
    score: float
    ref_code: str
    snippet: str


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------

def _load_index(pid: str) -> list[dict[str, Any]]:
    p = _index_path(pid)
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def _save_index(pid: str, items: list[dict[str, Any]]) -> None:
    _index_path(pid).write_text(
        json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _block_path(pid: str, bid: str) -> Path:
    return _corpus_dir(pid) / "blocks" / f"{bid}.json"


# ---------------------------------------------------------------------------
# Ref codec
# ---------------------------------------------------------------------------

_REF_LIT = re.compile(r"^Ref(?P<bid>[A-Za-z0-9_-]+)\.P(?P<page>\d+)\.Col(?P<col>\d+)\.Para(?P<para>\d+)$")
_REF_STAT = re.compile(r"^Ref(?P<bid>[A-Za-z0-9_-]+)\.var(?P<col>[A-Za-z0-9_-]+)$")
_REF_PRIN = re.compile(r"^Ref(?P<pid>[A-Za-z0-9_-]+)\.S(?P<sid>[A-Za-z0-9_.\-]+)$")
_REF_NOTE = re.compile(r"^Ref(?P<bid>[A-Za-z0-9_-]+)$")


def make_ref(block: Block) -> str:
    t = block.type
    if t == "literature":
        return f"Ref{block.id}.P{block.page}.Col{block.col}.Para{block.para}"
    if t == "stat":
        var = block.meta.get("var") or block.col
        return f"Ref{block.id}.var{var}"
    if t == "principle":
        sid = block.meta.get("section_id") or block.id
        principle_id = block.meta.get("principle_id") or block.id
        return f"Ref{principle_id}.S{sid}"
    return f"Ref{block.id}"


def parse_ref(ref_code: str) -> dict[str, Any] | None:
    for kind, regex in (
        ("literature", _REF_LIT),
        ("stat", _REF_STAT),
        ("principle", _REF_PRIN),
        ("note", _REF_NOTE),
    ):
        m = regex.match(ref_code)
        if m:
            return {"kind": kind, **m.groupdict()}
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def add_block(project_id: str, block: Block) -> str:
    if block.project_id != project_id:
        block = block.model_copy(update={"project_id": project_id})
    if not block.id:
        block = block.model_copy(update={"id": uuid.uuid4().hex[:12]})
    with _project_lock(project_id):
        _block_path(project_id, block.id).write_text(
            json.dumps(block.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        idx = _load_index(project_id)
        text = block.text or ""
        idx.append({
            "id": block.id, "type": block.type, "page": block.page,
            "col": block.col, "para": block.para,
            "snippet": text[:120],
            "meta_keys": list(block.meta.keys()),
        })
        _save_index(project_id, idx)
    return block.id


def list_blocks(project_id: str, type: BlockType | None = None) -> list[dict[str, Any]]:
    with _project_lock(project_id):
        idx = _load_index(project_id)
    if type is None:
        return idx
    return [x for x in idx if x.get("type") == type]


def drop_block(project_id: str, block_id: str) -> bool:
    with _project_lock(project_id):
        idx = _load_index(project_id)
        new = [x for x in idx if x.get("id") != block_id]
        if len(new) == len(idx):
            return False
        _save_index(project_id, new)
        p = _block_path(project_id, block_id)
        if p.exists():
            p.unlink()
        return True


def fetch_ref(project_id: str, ref_code: str) -> Block | None:
    parsed = parse_ref(ref_code)
    if not parsed:
        return None
    kind = parsed["kind"]
    bid = parsed.get("bid") or parsed.get("pid")
    if not bid:
        return None
    p = _block_path(project_id, bid)
    if p.exists():
        try:
            return Block.model_validate_json(p.read_text(encoding="utf-8"))
        except Exception:
            return None
    # principle blocks may be stored under the global "_principles" project
    if kind == "principle":
        glob_p = _block_path("_principles", bid)
        if glob_p.exists():
            try:
                return Block.model_validate_json(glob_p.read_text(encoding="utf-8"))
            except Exception:
                return None
    return None


def _load_full(project_id: str, bid: str) -> Block | None:
    p = _block_path(project_id, bid)
    if not p.exists():
        return None
    try:
        return Block.model_validate_json(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def search(
    project_id: str,
    query: str,
    types: Iterable[BlockType] | None = None,
    top_k: int = 10,
) -> list[BlockHit]:
    """Hybrid grep + (optional) embedding retrieval.

    - Tokenize query on whitespace + Chinese punctuation
    - Score each candidate block: exact substring hits * 25 + best fuzz
    - Embedding rerank is reserved for M3+ once `embedding` segment is configured.
    """
    if not query.strip():
        return []
    terms = [t for t in re.split(r"[\s，,；;、]+", query.strip()) if t]
    if not terms:
        return []
    lower_terms = [(t, t.lower()) for t in terms]
    types_filter = set(types) if types else None

    with _project_lock(project_id):
        idx = _load_index(project_id)

    hits: list[BlockHit] = []
    for entry in idx:
        if types_filter and entry.get("type") not in types_filter:
            continue
        block = _load_full(project_id, entry["id"])
        if not block:
            continue
        hay = block.text or ""
        if not hay:
            continue
        hay_l = hay.lower()
        exact = sum(1 for orig, lo in lower_terms if orig in hay or lo in hay_l)
        if exact:
            avg = sum(fuzz.partial_ratio(orig, hay) for orig, _ in lower_terms) / max(1, len(lower_terms))
            score = exact * 25 + avg
        else:
            best = 0
            for orig, _ in lower_terms:
                if len(orig) < 3:
                    continue
                best = max(best, fuzz.partial_ratio(orig.lower(), hay_l))
            if best < 65:
                continue
            score = best * 0.5
        snippet = hay if len(hay) <= 180 else hay[:180] + "…"
        hits.append(BlockHit(
            block=block, score=float(score),
            ref_code=make_ref(block), snippet=snippet,
        ))

    hits.sort(key=lambda h: h.score, reverse=True)
    return hits[:top_k]
