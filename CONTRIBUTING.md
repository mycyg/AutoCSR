# Contributing to AutoCSR

Thanks for your interest. This project moves fast, so please follow the
checklist below to keep PRs reviewable.

## Reporting Issues

When opening an issue, choose **Bug Report** or **Feature Request**
from the GitHub picker. The templates ask for:

- AutoCSR commit SHA (or "main @ <date>")
- Python + Node version, OS
- Reproduction steps (preferably an `m*_e2e_test.py` invocation or a
  minimal request payload)
- Expected vs actual

For data-handling bugs (cleansing, PII redaction), include the
`cleansing_pipeline.yaml` from the affected project — **redact any
real patient identifiers first**.

## Pull Requests

1. Fork → branch off `main`.
2. Make your change small and focused. One feature/fix per PR.
3. Touch tests:
    - Backend: extend the relevant `scripts/m*_e2e_test.py` if you add
      a new endpoint or behaviour. Unit-level tests can land under
      `backend/tests/`.
    - Frontend: run `npm run build` (which runs `vue-tsc --noEmit`) and
      fix any type errors.
4. Run the milestone e2es you touched, plus regressions. The full
    suite covers milestones M2 through M18:
    ```bash
    for m in m2 m3 m4 m5 m6 m7 m8 m9 m10 m11 m12 m13 m14 m15 m16 m17 m18; do
      python scripts/${m}_e2e_test.py
    done
    ```
    Each must finish with `[E2E] OK`. Unit tests:
    ```bash
    cd backend && .venv/Scripts/pytest tests/ -v
    ```
5. Use a clear commit message:
    ```
    <area>: <one-line summary>

    - bullet describing the change
    - bullet describing impact / risk
    ```
    `<area>` is one of `ingest` / `cleanse` / `analysis` / `outline` /
    `writer` / `chat` / `export` / `frontend` / `infra` / `docs`.

## Code Style

- **Python**: stdlib + type hints + small functions. No mandatory
  formatter, but if you use one, `ruff format`/`black` with default
  settings is the team default. Public APIs need docstrings; private
  helpers do not.
- **TypeScript / Vue**: `npm run build` must pass (which uses
  `vue-tsc --noEmit`). Prefer `<script setup lang="ts">` SFCs;
  Composition API only.
- **No new top-level dependencies** without justification in the PR
  body — small projects mean small surface area to maintain.
- **Logging over print**: use the `logging` module (`logger = logging.getLogger("autocsr.<area>")`).

## Adding a New LLM Provider

`backend/app/llm/ark_client.py` is already provider-agnostic via the
`api_format` setting. To add a provider, extend `_detect_api_format()`
and add a payload adapter; cover it with a unit test that mocks the HTTP
call.

## Releasing

Current release: **v2.0.0** (2026-05-23). The `main` branch is the
release surface; tag `vX.Y.Z` on the release commit and push tags.
Release notes live in [README.md](./README.md#release-notes).

Released versions:
- **v1.0.0** (2026-05-22) — first production-ready CSR pipeline (M1-M18)
- **v2.0.0** (2026-05-23) — production deployment + 5 therapeutic
  domains + multi-tenant accounts + advanced visualizations (M19-M22)
- **v2.1.0** (2026-05-24) — codex-contributed security middleware
  and cross-project workbench, plus Claude UI redesign (emoji-free,
  warm orange primary, Inter font, flat shadows)

When cutting a new release:

1. Update `Release Notes` in README with highlights and date.
2. `git tag -a vX.Y.Z -m "..."` then `git push origin vX.Y.Z`.
3. On GitHub, draft a release from the tag and paste the README
   highlights as the body.

## Roadmap (v3.x)

The v2.0 release delivered Docker deployment, multi-format export, 5
therapeutic-area templates, multi-tenant auth, reverse import, and
advanced visualizations. Items below were intentionally deferred to
v3.x — community PRs are welcome.

### Authentication & infrastructure
- SSO / OIDC integration (replace dev-mode + JWT-only flow)
- Hardware HSM signing (replace demo ed25519 keys)
- Multi-tenant worker pool with physical path migration
  (`data/projects/<pid>` → `data/tenants/<tid>/projects/<pid>`;
  current v2.0 is route-layer isolation, helper at
  `backend/scripts_helpers/multitenant.py:full_migrate`)
- CSRF protection + per-route rate-limit tuning

### Export & integration
- True eCTD M1.2 validator (current packager is demo-grade structure)
- EDC system API connectors (OpenClinica / Medidata / REDCap)
- LIMS integration for lab data
- Pinnacle 21 / OpenCDISC ADaM validator hook

### AI agents
- True OCR vision integration (`ark_client` needs vision support;
  M2.5 left `scan_worker` / `handwriting_worker` as stubs)
- Multi-study knowledge base (cross-project corpus learning)
- Regulatory inquiry tracker (FDA/NMPA Round 1/2/3 response workflows)
- AE causality assessment helper
- Protocol deviation tracker
- Native Anthropic tool_use streaming (currently JSON-schema action
  loop pattern)

### UX
- Lighthouse a11y 100 (v2.0 targets 95; some EP components have
  baseline issues)
- Recorded walkthrough videos (HelpMenu currently links to placeholders)
- Operation record-and-replay (rrweb integration)
- WCAG 2.2 AAA color theme variant

### Visualization
- Animated chart transitions
- Custom theme builder
- Plotly export option (alongside ECharts + matplotlib)

If you start work on any of these, please open an issue tagged
`v3-roadmap` so we can coordinate.
