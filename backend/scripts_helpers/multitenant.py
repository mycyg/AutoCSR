"""Multi-tenant migration helpers (M21).

Idempotent: safe to call on every server boot. Performs only the
non-destructive operations:

    * Ensure the 'default' tenant exists in data/tenants.json
    * Stamp tenant_id='default' on any project records in data/projects.json
      that are missing it (legacy pre-M21 records)
    * Ensure tenants/default/projects/<pid>/members.json exists for every
      project (with a best-effort 'owner' assignment to dev_admin so
      legacy dev installs keep being able to mutate them)

The destructive path (physical disk move
  data/projects/<pid>/ → data/tenants/default/projects/<pid>/)
is intentionally **not** performed here — the rest of the codebase
still reads data/projects/<pid>/ directly. It is left as a future
opt-in step; see scripts/migrate_to_multitenant.py for the dry-run /
backup machinery.
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _data_dir() -> Path:
    from app.config import data_dir
    return data_dir()


def ensure_default_tenant() -> None:
    from app.auth.models import ensure_default_tenant as _ensure
    _ensure()


def backfill_tenant_id() -> dict[str, int]:
    """Add tenant_id='default' to legacy project rows. Idempotent.

    Returns counts for the boot log.
    """
    ensure_default_tenant()
    pj = _data_dir() / "projects.json"
    n_total = 0
    n_patched = 0
    if pj.exists():
        try:
            raw = json.loads(pj.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                changed = False
                for it in raw:
                    if not isinstance(it, dict):
                        continue
                    n_total += 1
                    if "tenant_id" not in it or not it.get("tenant_id"):
                        it["tenant_id"] = "default"
                        n_patched += 1
                        changed = True
                if changed:
                    pj.write_text(
                        json.dumps(raw, ensure_ascii=False, indent=2, default=str),
                        encoding="utf-8",
                    )
        except Exception:
            pass
    # Also back-fill users so the dev seed accounts have a tenant.
    try:
        from app.auth.models import load_users, save_users
        users = load_users()
        save_users(users)  # normalize → re-save with all M21 fields populated
    except Exception:
        pass
    return {"projects_total": n_total, "patched": n_patched}


def full_migrate(backup: bool = True) -> dict[str, Any]:
    """One-shot CLI migration.

    Steps (in order, each idempotent):
        1. Backup data/ → data.pre-tenant.bak/  (only if backup=True and
           the backup dir does not yet exist)
        2. ensure_default_tenant()
        3. backfill_tenant_id()
        4. Ensure data/tenants/default/projects/<pid>/ exists for each
           project so the layout matches the M21 design even though the
           live data still lives at data/projects/<pid>/.
        5. Promote any pre-M21 dev seed user to tenant='default' + admin.
        6. Auto-seed an 'owner' member on every project for the most
           plausible user (admin > demo_admin > first user). Existing
           members are not touched.
    """
    dd = _data_dir()
    report: dict[str, Any] = {"started_at": datetime.now(timezone.utc).isoformat()}
    # 1) backup -----------------------------------------------------------
    if backup:
        bak = dd.parent / (dd.name + ".pre-tenant.bak")
        if not bak.exists() and dd.exists():
            try:
                shutil.copytree(dd, bak, dirs_exist_ok=False)
                report["backup_dir"] = str(bak)
            except Exception as e:  # noqa: BLE001
                report["backup_error"] = str(e)
        else:
            report["backup_dir"] = str(bak) + " (already present, skipped)"
    # 2 + 3 ---------------------------------------------------------------
    ensure_default_tenant()
    report["backfill"] = backfill_tenant_id()
    # 4) materialize per-tenant project shells ---------------------------
    pj = dd / "projects.json"
    materialized = 0
    if pj.exists():
        try:
            raw = json.loads(pj.read_text(encoding="utf-8"))
            for it in raw if isinstance(raw, list) else []:
                if not isinstance(it, dict):
                    continue
                tid = str(it.get("tenant_id") or "default")
                pid = str(it.get("id") or "")
                if not pid:
                    continue
                p = dd / "tenants" / tid / "projects" / pid
                if not p.exists():
                    p.mkdir(parents=True, exist_ok=True)
                    materialized += 1
        except Exception:
            pass
    report["tenant_shells_materialized"] = materialized
    # 5) promote dev seed admin ------------------------------------------
    try:
        from app.auth.models import load_users, save_users, get_user_by_id
        users = load_users()
        for u in users:
            if u.id in ("demo_admin", "admin") and u.role != "admin":
                u.role = "admin"
            if not u.tenant_id:
                u.tenant_id = "default"
        save_users(users)
    except Exception:
        pass
    # 6) seed owner members ----------------------------------------------
    seeded = 0
    try:
        from app.auth.models import (
            ProjectMember, list_members, upsert_member, load_users,
        )
        users = load_users()
        users_by_tid: dict[str, list[Any]] = {}
        for u in users:
            users_by_tid.setdefault(u.tenant_id or "default", []).append(u)

        def _pick_owner(tid: str, created_by: str | None) -> str | None:
            if created_by:
                return created_by
            pool = users_by_tid.get(tid, [])
            for cand in pool:
                if cand.id == "demo_admin":
                    return cand.id
            for cand in pool:
                if cand.role == "admin":
                    return cand.id
            if pool:
                return pool[0].id
            return None

        if pj.exists():
            raw = json.loads(pj.read_text(encoding="utf-8"))
            for it in raw if isinstance(raw, list) else []:
                if not isinstance(it, dict):
                    continue
                tid = str(it.get("tenant_id") or "default")
                pid = str(it.get("id") or "")
                if not pid:
                    continue
                existing = list_members(tid, pid)
                if existing:
                    continue
                owner = _pick_owner(tid, it.get("created_by"))
                if owner is None:
                    continue
                upsert_member(tid, pid, ProjectMember(
                    project_id=pid, user_id=owner, role="owner", granted_by=owner,
                ))
                seeded += 1
    except Exception as e:  # noqa: BLE001
        report["seed_owner_error"] = str(e)
    report["owner_members_seeded"] = seeded
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    return report
