"""i18n facilities for backend (M13).

Submodules:
  - ``loader``       — load named prompt templates from prompts/{lang}/{name}.txt
  - ``terminology``  — bilingual term swap utility for chinese/english CSR text
"""
from app.i18n.loader import (
    available_prompts,
    has_prompt,
    load_prompt,
    prompts_root,
    render_prompt,
)
from app.i18n.terminology import TerminologyMap, default_zh_en_map, swap_terms

__all__ = [
    "available_prompts",
    "has_prompt",
    "load_prompt",
    "prompts_root",
    "render_prompt",
    "TerminologyMap",
    "default_zh_en_map",
    "swap_terms",
]
