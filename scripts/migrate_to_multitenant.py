"""Idempotent migration to the M21 multi-tenant layout.

Usage:
    python scripts/migrate_to_multitenant.py
    python scripts/migrate_to_multitenant.py --no-backup
    python scripts/migrate_to_multitenant.py --dry-run

What it does (each step is idempotent):
    1. Backup data/ → data.pre-tenant.bak/ (only if absent)
    2. Ensure the 'default' tenant exists
    3. Back-fill tenant_id='default' on every projects.json row
    4. Materialize data/tenants/default/projects/<pid>/ shells
    5. Promote dev seed admin (demo_admin) to tenant=default, role=admin
    6. Seed an 'owner' ProjectMember for every project whose member list
       is still empty

Physical artefact relocation (data/projects/<pid>/ →
data/tenants/default/projects/<pid>/) is intentionally NOT performed —
the codebase still reads the legacy path everywhere and a hard move
would be one giant blast-radius change for a v2.3 milestone.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))


def main() -> int:
    parser = argparse.ArgumentParser(description="AutoCSR M21 multi-tenant migration")
    parser.add_argument("--no-backup", action="store_true",
                        help="skip the data/ → data.pre-tenant.bak/ snapshot")
    parser.add_argument("--dry-run", action="store_true",
                        help="report what would happen without writing")
    args = parser.parse_args()

    try:
        from scripts_helpers.multitenant import (
            backfill_tenant_id, ensure_default_tenant, full_migrate,
        )
    except Exception as e:
        print(f"[migrate] cannot import backend helpers: {e}", file=sys.stderr)
        return 1

    if args.dry_run:
        # Light read-only summary path.
        try:
            from app.config import data_dir
        except Exception as e:
            print(f"[migrate] dry-run: cannot import app.config: {e}",
                  file=sys.stderr)
            return 1
        dd = data_dir()
        pj = dd / "projects.json"
        n_total = n_legacy = 0
        if pj.exists():
            for it in json.loads(pj.read_text(encoding="utf-8")):
                n_total += 1
                if "tenant_id" not in it:
                    n_legacy += 1
        print(f"[migrate-dry] data_dir={dd}")
        print(f"[migrate-dry] projects_total={n_total} legacy_without_tenant={n_legacy}")
        return 0

    report = full_migrate(backup=not args.no_backup)
    print("[migrate] result:")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
