"""Sample-project bootstrapping (M20 v2.2).

Provides ``create_from_sample(domain)`` which:

  1. Materialises a fresh Project row pointing at the domain principle/template
  2. Copies the pre-generated ADaM parquets from
     ``data/sample_projects/<domain>/`` into the project's ``processed/`` dir
     (so the analyst agent can run against them with zero ingest cost)
  3. Marks the ingest store as "already cleansed" via a single ingest entry
     per parquet so downstream state-machine and UI badges populate
  4. Kicks off an outline build using the domain principle in the background

The 5 sample domains mirror M20 templates:
  oncology / rare_disease / vaccine / pediatric / cardiovascular

If the parquet files are missing on disk we fall back to running the
``scripts/generate_sample_data.py`` builders inline so the endpoint never
fails on a fresh checkout.
"""
from __future__ import annotations

import asyncio
import json
import shutil
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import data_dir
from app.observability.logger import get_logger
from app.projects.templates import get_template

logger = get_logger("autocsr.sample_projects")


_SAMPLE_DOMAINS: dict[str, dict[str, Any]] = {
    "oncology": {
        "template_id": "oncology",
        "principle_id": "oncology",
        "blurb": "肿瘤试验 demo：50 例患者，含 RECIST 反应、PFS/OS、PD-L1 亚组。",
    },
    "rare_disease": {
        "template_id": "rare_disease",
        "principle_id": "rare_disease",
        "blurb": "罕见病 demo：25 例患者，含基因突变、生物标志物应答、小样本统计。",
    },
    "vaccine": {
        "template_id": "vaccine",
        "principle_id": "vaccine",
        "blurb": "疫苗 demo：50 例，含 GMT pre/post、SCR、反应原性日记。",
    },
    "pediatric": {
        "template_id": "pediatric",
        "principle_id": "pediatric",
        "blurb": "儿科 demo：40 例横跨 4 个年龄段，含生长 z-score、适口性、Tanner 分期。",
    },
    "cardiovascular": {
        "template_id": "cardiovascular",
        "principle_id": "cardiovascular",
        "blurb": "心血管 demo：60 例，含 MACE 复合终点、LVEF、CV 风险亚组。",
    },
}


_LOCK = threading.RLock()
_SUBDIRS = ("raw", "processed", "corpus", "chapters", "exports", "chats")


def list_sample_domains() -> list[dict[str, Any]]:
    """Return UI-friendly metadata for the 5 domains (no project creation)."""
    out: list[dict[str, Any]] = []
    for domain, info in _SAMPLE_DOMAINS.items():
        tpl = get_template(info["template_id"])
        out.append({
            "domain": domain,
            "template_id": info["template_id"],
            "principle_id": info["principle_id"],
            "name": (tpl.name if tpl else domain.replace("_", " ").title()),
            "description": (tpl.description if tpl else info["blurb"]),
            "blurb": info["blurb"],
            "tags": list((tpl.tags if tpl else []) + ["sample"]),
        })
    return out


def _sample_data_dir(domain: str) -> Path:
    return Path(__file__).resolve().parents[3] / "data" / "sample_projects" / domain


def _ensure_sample_parquets(domain: str) -> list[Path]:
    """Return parquet paths for ``domain``, generating them inline if missing."""
    src = _sample_data_dir(domain)
    src.mkdir(parents=True, exist_ok=True)
    parquets = sorted(src.glob("*.parquet"))
    if parquets:
        return parquets
    # On-the-fly fallback — import the generator script and run the builder
    import importlib.util
    gen_path = Path(__file__).resolve().parents[3] / "scripts" / "generate_sample_data.py"
    if not gen_path.exists():
        return []
    spec = importlib.util.spec_from_file_location("gen_sample_data", gen_path)
    if not spec or not spec.loader:
        return []
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    try:
        mod.generate_all()    # writes all 5 domains in one pass
    except Exception as e:    # noqa: BLE001
        logger.warning("sample_data_generate_failed: %s", e)
        return []
    return sorted(src.glob("*.parquet"))


def _projects_json() -> Path:
    return data_dir() / "projects.json"


def _load_projects() -> list[dict[str, Any]]:
    p = _projects_json()
    if not p.exists():
        return []
    try:
        items = json.loads(p.read_text(encoding="utf-8"))
        return items if isinstance(items, list) else []
    except Exception:
        return []


def _save_projects(items: list[dict[str, Any]]) -> None:
    p = _projects_json()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(items, ensure_ascii=False, indent=2, default=str),
                  encoding="utf-8")


def _project_dir(pid: str) -> Path:
    return data_dir() / "projects" / pid


def _seed_ingest_entries(project_id: str, parquets: list[Path]) -> None:
    """Pre-populate the ingest index so the UI shows the sample files as
    already-cleansed (no upload required)."""
    try:
        from app.ingestion.orchestrator import save_entries
        from app.schemas.ingest import FileEntry
    except Exception as e:        # noqa: BLE001
        logger.warning("ingest_module_unavailable: %s", e)
        return
    entries: list[FileEntry] = []
    now = datetime.now(timezone.utc)
    for p in parquets:
        entries.append(FileEntry(
            file_id=f"sample_{p.stem.lower()}_{uuid.uuid4().hex[:6]}",
            project_id=project_id,
            filename=p.name,
            stored_path=str(p),
            mime="application/parquet",
            size_bytes=p.stat().st_size,
            uploaded_at=now,
            # Sample parquets ship in ADaM-shaped form so we mark the ingest
            # step "done" — the cleansing workbench will treat them as
            # already-clean structured data.
            ingest_type="structured_data",
            ingest_confidence=1.0,
            status="done",
        ))
    try:
        save_entries(project_id, entries)
    except Exception as e:        # noqa: BLE001
        logger.warning("seed_ingest_entries_failed: %s", e)


async def _kick_outline_build(project_id: str, principle_id: str) -> None:
    """Background outline build; failures are logged but never raised so the
    HTTP response stays 200 OK."""
    try:
        from app.outline.builder import build as build_outline
        await build_outline(project_id, principle_id, use_llm=False)
    except Exception as e:        # noqa: BLE001
        logger.warning("sample_outline_build_failed pid=%s err=%s",
                        project_id, e)


def create_from_sample(domain: str, *, name: str | None = None,
                         schedule_outline: bool = True) -> dict[str, Any]:
    """Create a project, copy sample parquets, seed ingest entries.

    Returns a dict with the persisted project row plus ``parquet_count``.

    Raises ``ValueError`` for an unknown domain.
    """
    if domain not in _SAMPLE_DOMAINS:
        raise ValueError(f"unknown sample domain: {domain}")
    info = _SAMPLE_DOMAINS[domain]
    tpl = get_template(info["template_id"])
    parquets = _ensure_sample_parquets(domain)

    pid = uuid.uuid4().hex[:12]
    now = datetime.now(timezone.utc)
    proj = {
        "id": pid,
        "name": (name or f"{(tpl.name if tpl else domain)} Demo").strip(),
        "principle_id": info["principle_id"],
        "created_at": now.isoformat(timespec="seconds"),
        "status": "intake",
        "tags": list((tpl.tags if tpl else []) + ["sample", "demo"]),
        "archived": False,
        "last_opened_at": None,
        "language": (tpl.language if tpl else "zh"),
        "notes": f"[sample] {info['blurb']}",
        "template_id": info["template_id"],
    }
    with _LOCK:
        items = _load_projects()
        items.append(proj)
        _save_projects(items)
    pdir = _project_dir(pid)
    pdir.mkdir(parents=True, exist_ok=True)
    for sub in _SUBDIRS:
        (pdir / sub).mkdir(exist_ok=True)

    # Copy parquets into processed/ so analyst_agent + cleansing UI see them
    copied: list[Path] = []
    for src in parquets:
        dst = pdir / "processed" / src.name
        try:
            shutil.copyfile(src, dst)
            copied.append(dst)
        except Exception as e:        # noqa: BLE001
            logger.warning("sample_copy_failed src=%s err=%s", src, e)

    _seed_ingest_entries(pid, copied)

    # Initialise state machine record so badges show the right step.
    # Step through uploaded -> cleansed (sample parquets ship ADaM-clean).
    try:
        from app.state import default_machine, ProjectState
        default_machine.get_record(pid)
        for tgt in (ProjectState.uploaded, ProjectState.cleansed):
            try:
                default_machine.try_transition(pid, tgt,
                                                reason="sample bootstrap")
            except Exception:
                pass
    except Exception:
        pass

    # Background outline build (best effort; fire-and-forget)
    if schedule_outline:
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_kick_outline_build(pid, info["principle_id"]))
        except RuntimeError:
            # Called from a sync context (e.g. CLI / test) — run inline.
            try:
                asyncio.run(_kick_outline_build(pid, info["principle_id"]))
            except Exception:
                pass

    return {
        **proj,
        "parquet_count": len(copied),
        "parquet_files": [p.name for p in copied],
    }


__all__ = [
    "list_sample_domains",
    "create_from_sample",
]
