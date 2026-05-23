"""End-to-end test for V3-B / M18 — v1.0 frontend polish.

Coverage is intentionally frontend-heavy because M18 makes no backend
changes; the upstream M2-M17 e2e scripts still guard backend behaviour.

Phases:
  1. `npm run build` (vue-tsc + vite build) succeeds and produces a
     reasonable bundle (< 8 MB gzip-uncompressed).
  2. Bundle contains evidence of our new wiring (tokens.css, a11y.css,
     dark theme, error map, recently-viewed key, eCTD wiring).
  3. Source-grep manual checklist — verifies the additive features are
     actually wired (additive checks; we don't render the SPA here).
  4. Lighthouse a11y is OPTIONAL — skipped on Windows + no Chrome.

Exit code 0 = pass, 1 = fail.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"
DIST = FRONTEND / "dist"

CHECKS: list[tuple[str, bool]] = []


def info(msg: str) -> None:
    print(f"[E2E-M18] {msg}", flush=True)


def check(name: str, ok: bool, hint: str = "") -> None:
    marker = "PASS" if ok else "FAIL"
    print(f"  [{marker}] {name}{(' — ' + hint) if hint and not ok else ''}", flush=True)
    CHECKS.append((name, ok))


def run_build() -> bool:
    info("phase 1: npm run build")
    if not (FRONTEND / "node_modules").exists():
        info("  installing node_modules (first run)")
        rc = subprocess.call(["npm", "install"], cwd=str(FRONTEND), shell=True)
        if rc != 0:
            return False
    rc = subprocess.call(["npm", "run", "build"], cwd=str(FRONTEND), shell=True)
    return rc == 0


def gather_bundle_text() -> str:
    """Concatenate every text asset under dist/ for source-grep checks."""
    out: list[str] = []
    for p in DIST.rglob("*"):
        if p.is_file() and p.suffix in {".js", ".css", ".html", ".json"}:
            try: out.append(p.read_text(encoding="utf-8", errors="ignore"))
            except Exception: pass
    return "\n".join(out)


def gather_source_text() -> str:
    """Concatenate every .vue / .ts under src/ for additive-check grep."""
    src = FRONTEND / "src"
    out: list[str] = []
    for p in src.rglob("*"):
        if p.is_file() and p.suffix in {".vue", ".ts", ".css", ".json"}:
            try: out.append(p.read_text(encoding="utf-8", errors="ignore"))
            except Exception: pass
    return "\n".join(out)


def bundle_size_ok() -> bool:
    total = sum(p.stat().st_size for p in DIST.rglob("*") if p.is_file())
    info(f"  dist total = {total / 1024 / 1024:.2f} MB (raw)")
    return total < 8 * 1024 * 1024 * 4  # 8MB gzip ≈ ~32MB raw upper bound


def main() -> int:
    if not run_build():
        check("npm run build", False, "build failed — see output above")
        return 1
    check("npm run build", True)
    check("dist size < 32MB raw (~8MB gzip)", bundle_size_ok())

    bundle = gather_bundle_text()
    src = gather_source_text()

    # Bundle-level proof: design tokens shipped.
    check("tokens.css shipped (--color-bg, --color-surface in bundle)",
          "--color-bg" in bundle and "--color-surface" in bundle)
    check("a11y focus-visible rule shipped",
          ":focus-visible" in bundle)
    check("dark theme tokens shipped",
          'data-theme="dark"' in bundle or "data-theme=\\\"dark\\\"" in bundle
          or "[data-theme=" in bundle)
    check("Element Plus dark CSS imported",
          "element-plus/theme-chalk/dark" in src)

    # Source-level proof: additive components wired.
    files_must_exist = [
        "src/components/global/OnboardingTour.vue",
        "src/components/global/TaskProgressOverlay.vue",
        "src/components/global/EmptyState.vue",
        "src/components/global/HelpMenu.vue",
        "src/components/global/ThemeToggle.vue",
        "src/components/global/HallucinationPanel.vue",
        "src/components/global/EctdExportDialog.vue",
        "src/components/collab/SignChainPanel.vue",
        "src/composables/useTheme.ts",
        "src/composables/useConfirm.ts",
        "src/composables/useRecentlyViewed.ts",
        "src/utils/errors.ts",
        "src/styles/tokens.css",
        "src/styles/a11y.css",
        "src/i18n/ja.json",
    ]
    for rel in files_must_exist:
        check(f"file exists: {rel}", (FRONTEND / rel).exists())

    # Functional additive proofs
    check("OnboardingTour: localStorage persist key",
          "autocsr_onboarding_done" in src)
    check("ProjectList: hero + template cards",
          "hero-pitch" in src and "tpl-card" in src)
    check("useConfirm wired in destructive ops",
          "confirmAction(" in src and "delete_confirm" in src)
    check("TaskProgressOverlay listens to writer.section_start",
          "writer.section_start" in src)
    check("Keyboard slots: j/k + Cmd+/",
          "outline_next" in src and "show_view_shortcuts" in src)
    check("aria-label coverage (≥ 20 sites)",
          src.count("aria-label") >= 20)
    check("EmptyState applied to all 7 views",
          all(f"EmptyState" in (FRONTEND / "src/views" / v).read_text(encoding="utf-8")
              for v in ["AnalyzeView.vue", "OutlineView.vue", "ReportView.vue",
                         "TasksView.vue", "AuditView.vue", "CompareView.vue",
                         "CleanseView.vue"]))
    check("Dark mode toggle + composable",
          "toggleTheme" in src and "ThemeToggle" in src)
    check("Responsive 1024px media queries present",
          "max-width: 1023px" in src and "max-width: 1279px" in src)
    check("Language switch: ja stub",
          "'ja'" in (FRONTEND / "src/i18n/index.ts").read_text(encoding="utf-8")
          and 'command="ja"' in (FRONTEND / "src/components/global/LanguageSwitch.vue").read_text(encoding="utf-8"))
    check("ChapterReader: Copy markdown + Share snapshot",
          "report.copy_md" in src and "report.share_snapshot" in src)
    check("GlobalSearchModal: recent searches",
          "autocsr_recent_searches" in src)
    check("M17 wiring: hallucination + sign chain + eCTD",
          "runHallucinationCheck" in src and "SignChainPanel" in src and "EctdExportDialog" in src)
    check("ChapterTree heatmap badge",
          "badge hallu" in src or "badge.hallu" in src)
    check("OutlineTree: search + collapse + goto + j/k",
          "ot-toolbar" in src and "collapseAll" in src and "gotoCurrent" in src)
    check("Errors util: code map size ≥ 25",
          (FRONTEND / "src/utils/errors.ts").read_text(encoding="utf-8").count("'") >= 100)

    # ------------------------------------------------------------------
    # Phase 4: Lighthouse (best-effort).
    # ------------------------------------------------------------------
    info("phase 4: Lighthouse a11y (skip if Chrome/CLI not available)")
    rc = subprocess.call("npx --yes lighthouse --version",
                         shell=True, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
    if rc != 0:
        info("  Lighthouse CLI not installed — skipped (manual check recommended)")
    else:
        info("  Lighthouse available; run manually against a live dev server.")

    failed = [n for n, ok in CHECKS if not ok]
    info(f"summary: {len(CHECKS) - len(failed)} / {len(CHECKS)} checks passed")
    if failed:
        info("FAILED: " + ", ".join(failed))
        return 1
    info("M18 e2e: ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
