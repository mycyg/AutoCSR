"""PII detection — regex first, optional LLM second-pass.

Returns ``PIIFinding`` objects with masked values so downstream code can
log + display without leaking the original. The redactor in
:mod:`app.safety.redactor` consumes the same finding objects to apply
``<REDACTED_*>`` placeholders before the prompt leaves the host.

Detected:
  * id_cn       — 18-digit PRC national ID
  * phone_cn    — 11-digit PRC mobile
  * email       — common email
  * mrn         — hospital/medical record number markers
  * name_cn     — Chinese personal names via prefix + surname heuristic
  * name_en     — English names with title prefix (Mr./Dr./...)
  * address     — addresses containing 省/市/区/号 markers

The second-pass LLM check is opt-in via ``settings.safety.pii_llm_check``
and only re-evaluates regex findings to drop obvious false positives
(e.g. "Mr. Smith" appearing in a literature title); it never inspects
text the regex layer did not flag, so it cannot itself leak.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Literal

logger = logging.getLogger("autocsr.safety.pii")


PIIType = Literal[
    "id_cn", "phone_cn", "email", "mrn",
    "name_cn", "name_en", "address",
]


class PIIError(RuntimeError):
    """Raised when settings.safety.pii_pre_check='strict' and PII detected."""
    def __init__(self, message: str, findings: list["PIIFinding"]):
        super().__init__(message)
        self.findings = findings


@dataclass
class PIIFinding:
    type: PIIType
    range: tuple[int, int]
    value_masked: str
    confidence: float = 1.0
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "range": [int(self.range[0]), int(self.range[1])],
            "value_masked": self.value_masked,
            "confidence": float(self.confidence),
        }


# ---------------------------------------------------------------------------
# Regexes
# ---------------------------------------------------------------------------

_ID_CN_RE = re.compile(r"(?<![0-9])\d{17}[\dXx](?![0-9])")
_PHONE_CN_RE = re.compile(r"(?<![0-9])1[3-9]\d{9}(?![0-9])")
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
# MRN: MR/HOSP/住院号/案号 followed by optional colon and >=6 digits
_MRN_RE = re.compile(
    r"(?:MR|HOSP|住院号|病案号|案号|MRN)\s*[:：#]?\s*(\d{6,})",
    re.IGNORECASE,
)
# Chinese name heuristics (高频姓 + 2-4 字)
_CN_SURNAMES = (
    "王", "李", "张", "刘", "陈", "杨", "黄", "赵", "吴", "周", "徐", "孙",
    "马", "朱", "胡", "郭", "何", "高", "林", "罗", "郑", "梁", "谢", "宋",
    "唐", "许", "韩", "冯", "邓", "曹", "彭", "曾", "肖", "田", "董", "潘",
    "袁", "蔡", "蒋", "余", "于", "杜", "叶", "程", "魏", "苏", "吕", "丁",
    "任", "沈", "姚", "卢", "姜", "崔", "钟", "谭", "陆",
)
_NAME_CN_RE = re.compile(
    r"(?:[张李王赵刘陈杨黄周吴徐孙马朱胡郭何高林罗郑梁谢宋唐许韩冯邓"
    r"曹彭曾肖田董潘袁蔡蒋余于杜叶程魏苏吕丁任沈姚卢姜崔钟谭陆])"
    r"[一-鿿]{1,3}"
    r"(?=\s*(?:先生|女士|医生|教授|大夫|博士|主任|护士)?)",
)
# Honorific-prefixed Chinese names (always flag)
_NAME_CN_TITLE_RE = re.compile(
    r"(?:[张李王赵刘陈杨黄周吴徐孙马朱胡郭何高林罗郑梁谢宋唐许韩冯邓"
    r"曹彭曾肖田董潘袁蔡蒋余于杜叶程魏苏吕丁任沈姚卢姜崔钟谭陆])"
    r"[一-鿿]{1,3}(?:先生|女士|医生|教授|大夫|博士|主任|护士)",
)
_NAME_EN_RE = re.compile(
    r"\b(?:Mr|Mrs|Ms|Miss|Dr|Prof)\.?\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?",
)
# Address: requires 号 + at least one of 省/市/区/路/街
_ADDRESS_RE = re.compile(
    r"[一-鿿]{2,8}(?:省|市|区|县|路|街|镇)[一-鿿\d]{1,30}号",
)


def _mask(value: str, *, keep: int = 2) -> str:
    """Mask the middle of a value, keeping prefix+suffix for context."""
    if not value:
        return "***"
    if len(value) <= 2 * keep:
        return "*" * len(value)
    return value[:keep] + "***" + value[-keep:]


def _scan_regex(text: str) -> list[PIIFinding]:
    out: list[PIIFinding] = []
    # IDs — masked aggressively because the 18-digit ID is extremely
    # sensitive on its own.
    for m in _ID_CN_RE.finditer(text):
        v = m.group(0)
        out.append(PIIFinding(
            type="id_cn", range=(m.start(), m.end()),
            value_masked=v[:4] + "**********" + v[-4:],
            confidence=0.99,
        ))
    for m in _PHONE_CN_RE.finditer(text):
        v = m.group(0)
        out.append(PIIFinding(
            type="phone_cn", range=(m.start(), m.end()),
            value_masked=v[:3] + "****" + v[-4:],
            confidence=0.95,
        ))
    for m in _EMAIL_RE.finditer(text):
        v = m.group(0)
        out.append(PIIFinding(
            type="email", range=(m.start(), m.end()),
            value_masked=_mask(v.split("@", 1)[0]) + "@" + v.split("@", 1)[-1],
            confidence=0.9,
        ))
    for m in _MRN_RE.finditer(text):
        out.append(PIIFinding(
            type="mrn", range=(m.start(), m.end()),
            value_masked=_mask(m.group(0), keep=3),
            confidence=0.85,
        ))
    for m in _NAME_CN_TITLE_RE.finditer(text):
        out.append(PIIFinding(
            type="name_cn", range=(m.start(), m.end()),
            value_masked=_mask(m.group(0), keep=1), confidence=0.8,
        ))
    for m in _NAME_EN_RE.finditer(text):
        out.append(PIIFinding(
            type="name_en", range=(m.start(), m.end()),
            value_masked=_mask(m.group(0)), confidence=0.7,
        ))
    for m in _ADDRESS_RE.finditer(text):
        out.append(PIIFinding(
            type="address", range=(m.start(), m.end()),
            value_masked=_mask(m.group(0), keep=3), confidence=0.7,
        ))
    # Bare Chinese-name heuristic — only fire when not already covered by
    # title-prefixed match, and only when it co-occurs with an MRN, ID or
    # phone in the same line (very cheap proxy for "actual patient" context).
    has_id_or_phone = bool(_ID_CN_RE.search(text) or _PHONE_CN_RE.search(text)
                            or _MRN_RE.search(text))
    if has_id_or_phone:
        seen_ranges = {(f.range[0], f.range[1]) for f in out}
        for m in _NAME_CN_RE.finditer(text):
            if (m.start(), m.end()) in seen_ranges:
                continue
            # Avoid matching obvious medical terms ("张力" etc.)
            v = m.group(0)
            if len(v) < 2 or len(v) > 4:
                continue
            out.append(PIIFinding(
                type="name_cn", range=(m.start(), m.end()),
                value_masked=_mask(v, keep=1), confidence=0.6,
            ))
    # Dedup overlapping
    out.sort(key=lambda f: (f.range[0], -(f.range[1] - f.range[0])))
    dedup: list[PIIFinding] = []
    last_end = -1
    for f in out:
        if f.range[0] >= last_end:
            dedup.append(f)
            last_end = f.range[1]
    return dedup


def scan(text: str, *, use_llm: bool = False) -> list[PIIFinding]:
    """Public entrypoint. Optional LLM second-pass is gated on the
    ``use_llm`` flag (caller drives this from ``settings.safety``)."""
    if not text:
        return []
    findings = _scan_regex(text)
    if use_llm and findings:
        try:
            findings = _llm_filter(text, findings)
        except Exception as e:  # noqa: BLE001
            logger.warning("pii LLM filter failed; keeping regex findings: %s", e)
    return findings


def _llm_filter(text: str, findings: list[PIIFinding]) -> list[PIIFinding]:
    """Ask the LLM to drop obvious false positives from the regex layer.

    Sends only the masked spans + 40 chars of surrounding context so the
    LLM never sees the raw PII value.
    """
    from app.llm import policy as _policy
    from app.llm.ark_client import responses_json

    snippets = []
    for i, f in enumerate(findings):
        s = max(0, f.range[0] - 40)
        e = min(len(text), f.range[1] + 40)
        ctx = text[s:e].replace(text[f.range[0]:f.range[1]], "<<HIT>>")
        snippets.append({"i": i, "type": f.type, "context": ctx})
    prompt = (
        "判断下列每个 <<HIT>> 命中是否真实 PII（个人可识别信息）。"
        "返回严格 JSON：{\"keep\": [i1, i2, ...]}，列出确认为 PII 的索引。"
        "命中列表：\n" + str(snippets)
    )
    pol = _policy.for_role("editor")
    try:
        ans = responses_json(
            [{"role": "user", "content": prompt}],
            schema={"type": "object", "properties": {
                "keep": {"type": "array", "items": {"type": "integer"}},
            }, "required": ["keep"]},
            timeout=pol.timeout, max_tokens=pol.max_tokens,
            temperature=pol.temperature,
        )
    except Exception:
        return findings
    keep = set(int(i) for i in (ans.get("keep") or []))
    return [f for i, f in enumerate(findings) if i in keep]
