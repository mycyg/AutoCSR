"""Embedding-rerank helper (M13).

Stays passive unless ``settings.embedding`` declares both
``base_url`` and ``api_key`` (in addition to a model name). When
configured, ``rerank_hits`` recomputes hit scores with
``cosine(query_vec, hit_vec)`` and returns the top-k.

The helper deliberately avoids importing ark_client at module load
time so the existing grep-only flow stays free of new transitive
dependencies. Failures degrade silently to the original hit ordering.
"""
from __future__ import annotations

import logging
from typing import Any, Iterable

from app.config import settings

logger = logging.getLogger("autocsr.corpus.embedding")


def is_enabled() -> bool:
    cfg = (settings() or {}).get("embedding") or {}
    return bool(cfg.get("base_url") and cfg.get("api_key") and cfg.get("model"))


def embed_text(text: str) -> list[float] | None:
    if not text:
        return None
    if not is_enabled():
        return None
    try:
        # Lazy import to avoid pulling httpx in cold paths.
        from app.llm import ark_client  # type: ignore
    except Exception:
        return None
    if not hasattr(ark_client, "embed_one"):
        return None
    try:
        vec = ark_client.embed_one(text)  # type: ignore[attr-defined]
        if isinstance(vec, list) and all(isinstance(x, (int, float)) for x in vec):
            return list(vec)
    except Exception as e:  # noqa: BLE001
        logger.debug("embed_text failed: %s", e)
    return None


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    import math
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def rerank_hits(hits: list[dict[str, Any]], query: str, top_k: int = 8) -> list[dict[str, Any]]:
    """If embedding is enabled, re-rank ``hits`` by cosine similarity.

    Each ``hit`` should carry ``text`` or ``snippet`` (we use whichever
    is non-empty). Hits whose embedding fails fall back to the input
    score. Returns the top ``top_k`` items."""
    if not hits:
        return hits[:top_k]
    if not is_enabled():
        return hits[:top_k]
    q_vec = embed_text(query)
    if q_vec is None:
        return hits[:top_k]
    scored: list[tuple[float, dict[str, Any]]] = []
    for h in hits:
        text = h.get("text") or h.get("snippet") or h.get("title") or ""
        v = embed_text(str(text)[:1000])
        if v is None:
            scored.append((float(h.get("score", 0.0)), h))
        else:
            scored.append((_cosine(q_vec, v), h))
    scored.sort(key=lambda x: x[0], reverse=True)
    out: list[dict[str, Any]] = []
    for s, h in scored[:top_k]:
        item = dict(h)
        item["embedding_score"] = round(s, 4)
        out.append(item)
    return out
