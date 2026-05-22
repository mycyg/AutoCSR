"""Corpus subsystem — unified block index over 4 types.

types: literature | stat | principle | note

Blocks live on disk under <data>/projects/<pid>/corpus/blocks/<id>.json with a
project-level index at <data>/projects/<pid>/corpus/index.json. Retrieval is
grep-first (rapidfuzz) with optional embedding rerank when configured.
"""
from app.corpus.index import (
    Block, BlockHit, add_block, search, fetch_ref, parse_ref,
    list_blocks, drop_block,
)

__all__ = [
    "Block", "BlockHit",
    "add_block", "search", "fetch_ref", "parse_ref",
    "list_blocks", "drop_block",
]
