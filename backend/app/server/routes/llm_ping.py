"""POST /llm/ping — proves the configured LLM endpoint is reachable.

Body: {"q": "..."}; response: {"reply": "...", "tokens": {...}, "via": "llm"}
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.llm import ark_client
from app.llm.policy import for_role

router = APIRouter()


class PingRequest(BaseModel):
    q: str = Field(..., min_length=1, max_length=4000)


@router.post("/llm/ping")
def llm_ping(req: PingRequest) -> dict:
    p = for_role("ping")
    try:
        out = ark_client.responses(
            [{"role": "user", "content": req.q}],
            timeout=p.timeout,
            max_tokens=p.max_tokens,
            temperature=p.temperature,
        )
    except ark_client.ArkError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    raw = out.get("raw") or {}
    usage = raw.get("usage") or {}
    return {
        "reply": out.get("text", ""),
        "via": out.get("via"),
        "tokens": {
            "input": usage.get("prompt_tokens") or usage.get("input_tokens"),
            "output": usage.get("completion_tokens") or usage.get("output_tokens"),
        },
    }
