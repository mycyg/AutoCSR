"""Uniform pagination helper (M17).

Use it to keep list endpoints honest as projects grow:

::

    from app.server.middlewares.pagination import paginate

    items = projects_mod.list_projects(...)
    return paginate(items, offset=offset, limit=limit)

Older clients that don't pass either query param get the full list back
so we don't break the M2 → M16 e2e harnesses.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping, TypeVar

T = TypeVar("T")


def paginate(
    items: Iterable[T],
    *,
    offset: int | None = None,
    limit: int | None = None,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return ``{items, total, offset, limit}`` (and any extras).

    Semantics:

    * Both ``offset`` and ``limit`` ``None``  → no slicing; the caller
      gets the full list. This is the backwards-compatible behaviour.
    * ``offset`` defaults to 0 when ``limit`` is set.
    * ``limit`` defaults to len(items) - offset when ``offset`` is set
      but ``limit`` is not.
    * Negative offset / non-positive limit raise ``ValueError`` because
      they almost always indicate a frontend bug.
    """
    seq: list[T] = list(items)
    total = len(seq)
    if offset is None and limit is None:
        body: dict[str, Any] = {
            "items": seq, "total": total,
            "offset": 0, "limit": total,
        }
        if extra:
            body.update(extra)
        return body
    if offset is None:
        offset = 0
    if limit is None:
        limit = max(0, total - int(offset))
    if int(offset) < 0:
        raise ValueError("offset must be >= 0")
    if int(limit) <= 0:
        raise ValueError("limit must be > 0")
    sliced = seq[int(offset): int(offset) + int(limit)]
    body = {
        "items": sliced, "total": total,
        "offset": int(offset), "limit": int(limit),
    }
    if extra:
        body.update(extra)
    return body


__all__ = ["paginate"]
