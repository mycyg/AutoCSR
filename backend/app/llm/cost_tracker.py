"""Thread-safe token / cost accumulator.

Pricing constants are crude estimates — the goal is relative comparison
across calls within one CSR build, not invoice accounting.
"""
from __future__ import annotations

import json
import threading
import time
from collections import defaultdict
from pathlib import Path
from typing import Any


_PRICE_PER_M_INPUT = 0.30
_PRICE_PER_M_INPUT_CACHED = 0.03
_PRICE_PER_M_OUTPUT = 1.20


_LOCK = threading.Lock()
_RECORDS: list[dict[str, Any]] = []
_TOTALS: dict[str, float] = defaultdict(float)


def record(
    endpoint: str,
    *,
    usage: dict | None,
    via: str = "llm",
    latency_ms: int = 0,
    model: str = "",
) -> None:
    """Record one LLM call. `usage` is the raw `data["usage"]` block.

    OpenAI shape:    {prompt_tokens, completion_tokens, total_tokens,
                      prompt_tokens_details: {cached_tokens}}
    Anthropic shape: {input_tokens, output_tokens, cache_creation_input_tokens,
                      cache_read_input_tokens}
    """
    if not usage:
        return
    u = usage
    in_tok = int(u.get("input_tokens") or u.get("prompt_tokens") or 0)
    out_tok = int(u.get("output_tokens") or u.get("completion_tokens") or 0)
    cached = int(
        u.get("cache_read_input_tokens")
        or (u.get("prompt_tokens_details") or {}).get("cached_tokens")
        or 0
    )
    # Anthropic counts cache reads SEPARATELY from input_tokens; don't double-deduct.
    paid_input = max(in_tok - (cached if "prompt_tokens_details" in u else 0), 0)
    usd = (
        paid_input / 1_000_000 * _PRICE_PER_M_INPUT
        + cached / 1_000_000 * _PRICE_PER_M_INPUT_CACHED
        + out_tok / 1_000_000 * _PRICE_PER_M_OUTPUT
    )
    rec = {
        "ts": time.time(),
        "endpoint": endpoint,
        "via": via,
        "model": model,
        "input_tokens": in_tok,
        "output_tokens": out_tok,
        "cached_tokens": cached,
        "latency_ms": latency_ms,
        "usd_est": round(usd, 6),
    }
    with _LOCK:
        _RECORDS.append(rec)
        _TOTALS["calls"] += 1
        _TOTALS["input_tokens"] += in_tok
        _TOTALS["output_tokens"] += out_tok
        _TOTALS["cached_tokens"] += cached
        _TOTALS["usd_est"] += usd


def snapshot() -> dict[str, Any]:
    with _LOCK:
        per_ep: dict[str, dict[str, Any]] = defaultdict(lambda: {
            "calls": 0, "input_tokens": 0, "output_tokens": 0,
            "cached_tokens": 0, "usd_est": 0.0,
        })
        for r in _RECORDS:
            ep = r["endpoint"]
            per_ep[ep]["calls"] += 1
            per_ep[ep]["input_tokens"] += r["input_tokens"]
            per_ep[ep]["output_tokens"] += r["output_tokens"]
            per_ep[ep]["cached_tokens"] += r["cached_tokens"]
            per_ep[ep]["usd_est"] += r["usd_est"]
        return {
            "totals": dict(_TOTALS),
            "by_endpoint": {k: v for k, v in per_ep.items()},
            "n_records": len(_RECORDS),
        }


def dump_to(path: Path) -> None:
    path.write_text(json.dumps(snapshot(), ensure_ascii=False, indent=2), encoding="utf-8")


def reset() -> None:
    with _LOCK:
        _RECORDS.clear()
        _TOTALS.clear()
