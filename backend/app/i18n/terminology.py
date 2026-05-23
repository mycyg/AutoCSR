"""Bilingual CSR terminology helper (M13).

The :class:`TerminologyMap` wraps a dict of ``src -> tgt`` term pairs plus
an optional ``categories`` map (term -> category like ``drug``,
``adverse_event``). ``swap_terms()`` substitutes the source terms with
their targets, longest-first to avoid partial-overlap collisions.

The default ``zh-en`` map ships ~40 high-frequency CSR terms across
drugs / AE / statistics / trial-design.
"""
from __future__ import annotations

import re
from typing import Iterable

from pydantic import BaseModel, Field


class TerminologyMap(BaseModel):
    language_pair: str = Field(..., description='e.g. "zh-en" or "en-zh"')
    terms: dict[str, str] = Field(default_factory=dict)
    categories: dict[str, str] = Field(default_factory=dict)

    def add(self, src: str, tgt: str, category: str | None = None) -> None:
        self.terms[src] = tgt
        if category:
            self.categories[src] = category

    def merge(self, other: "TerminologyMap") -> None:
        self.terms.update(other.terms)
        self.categories.update(other.categories)


def swap_terms(text: str, mapping: TerminologyMap | dict[str, str]) -> str:
    """Replace each source term with its target in ``text``.

    Sorted longest-first so ``placebo group`` is matched before ``placebo``
    when both happen to be keys. For CJK-only mappings we still do a
    plain :py:meth:`str.replace`; for ASCII keys we anchor on word
    boundaries when possible to avoid sub-token corruption.
    """
    if isinstance(mapping, TerminologyMap):
        items = list(mapping.terms.items())
    else:
        items = list(mapping.items())
    if not items:
        return text
    items.sort(key=lambda kv: -len(kv[0]))
    out = text
    for src, tgt in items:
        if not src:
            continue
        if _is_ascii_token(src):
            out = re.sub(rf"\b{re.escape(src)}\b", tgt, out, flags=re.IGNORECASE)
        else:
            out = out.replace(src, tgt)
    return out


def _is_ascii_token(s: str) -> bool:
    return all(ord(c) < 128 and (c.isalnum() or c in " -_") for c in s)


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------


def default_zh_en_map() -> TerminologyMap:
    """A starter zh→en terminology map covering core CSR vocabulary.

    Curated by category. ~40 entries — enough to demo the swap; users
    augment via the cleansing-workbench terminology UI."""
    pairs: list[tuple[str, str, str]] = [
        # --- drug / treatment ---------------------------------------
        ("安慰剂", "placebo", "drug"),
        ("试验药", "investigational drug", "drug"),
        ("研究药物", "study drug", "drug"),
        ("阳性对照", "active control", "drug"),
        ("剂量", "dose", "drug"),
        ("给药", "dosing", "drug"),
        ("不良事件", "adverse event", "adverse_event"),
        ("严重不良事件", "serious adverse event", "adverse_event"),
        ("可疑非预期严重不良反应", "SUSAR", "adverse_event"),
        ("死亡", "death", "adverse_event"),
        ("停药", "drug discontinuation", "adverse_event"),
        ("剂量限制性毒性", "dose-limiting toxicity", "adverse_event"),
        ("最大耐受剂量", "maximum tolerated dose", "adverse_event"),
        # --- statistics ---------------------------------------------
        ("置信区间", "confidence interval", "stat"),
        ("p 值", "p-value", "stat"),
        ("均值", "mean", "stat"),
        ("中位数", "median", "stat"),
        ("标准差", "standard deviation", "stat"),
        ("四分位距", "interquartile range", "stat"),
        ("协变量", "covariate", "stat"),
        ("假设检验", "hypothesis test", "stat"),
        ("意向性治疗", "intention-to-treat", "stat"),
        ("符合方案集", "per-protocol set", "stat"),
        ("敏感性分析", "sensitivity analysis", "stat"),
        ("亚组分析", "subgroup analysis", "stat"),
        ("生存分析", "survival analysis", "stat"),
        ("风险比", "hazard ratio", "stat"),
        ("相对风险", "relative risk", "stat"),
        # --- trial design -------------------------------------------
        ("随机化", "randomization", "design"),
        ("分层", "stratification", "design"),
        ("双盲", "double-blind", "design"),
        ("单盲", "single-blind", "design"),
        ("交叉设计", "crossover design", "design"),
        ("平行设计", "parallel design", "design"),
        ("洗脱期", "washout period", "design"),
        ("筛选", "screening", "design"),
        ("入选标准", "inclusion criteria", "design"),
        ("排除标准", "exclusion criteria", "design"),
        ("主要终点", "primary endpoint", "design"),
        ("次要终点", "secondary endpoint", "design"),
        ("方案", "protocol", "design"),
        ("知情同意", "informed consent", "design"),
        ("研究者", "investigator", "design"),
        ("中心", "site", "design"),
    ]
    tm = TerminologyMap(language_pair="zh-en")
    for src, tgt, cat in pairs:
        tm.add(src, tgt, cat)
    return tm


def default_en_zh_map() -> TerminologyMap:
    zh_en = default_zh_en_map()
    tm = TerminologyMap(language_pair="en-zh")
    for src, tgt in zh_en.terms.items():
        # reverse — note this loses ordering hints for ambiguous English
        # heteronyms; acceptable for the first cut.
        tm.add(tgt, src, zh_en.categories.get(src, ""))
    return tm


def default_map(language_pair: str) -> TerminologyMap | None:
    """Return a starter map for the given pair, or None if unsupported."""
    lp = language_pair.lower()
    if lp in ("zh-en", "zh_cn-en", "zh-en_us"):
        return default_zh_en_map()
    if lp in ("en-zh", "en-zh_cn"):
        return default_en_zh_map()
    return None


def iter_supported_pairs() -> Iterable[str]:
    yield "zh-en"
    yield "en-zh"
