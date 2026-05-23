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

Current release: **v1.0.0** (2026-05-22). The `main` branch is the
release surface; tag `vX.Y.Z` on the release commit and push tags.
Release notes live in [README.md](./README.md#release-notes).

When cutting a new release:

1. Update `Release Notes` in README with highlights and date.
2. `git tag -a vX.Y.Z -m "..."` then `git push origin vX.Y.Z`.
3. On GitHub, draft a release from the tag and paste the README
   highlights as the body.

## Roadmap

The v1.0 plan deliberately deferred several items to v2.x; community
PRs are welcome on any of them:

### Export & integration
- PDF / HTML / PowerPoint / Markdown bundle export formats
- True eCTD M1.2 validator (current packager is demo-grade)
- SAP docx → analysis plan reverse import
- Protocol PDF → trial-design metadata extraction
- `define.xml` full ADaM metadata
- EDC system API connectors (OpenClinica / Medidata / REDCap)

### Domain templates
- Oncology (RECIST 1.1 / iRECIST / PFS / OS)
- Rare disease (small-N + historical controls)
- Vaccine (immunogenicity + efficacy)
- Pediatric (age stratification)
- Cardiovascular (MACE composite endpoints)

### AI agents
- Literature search agent (PubMed / Wanfang)
- Medical English polishing agent
- Chart-type recommendation agent
- LaTeX → DOCX formula conversion
- Vancouver / GB/T 7714 / AMA reference formatting

### Infrastructure
- Docker Compose one-command deployment
- Prometheus + Grafana dashboard bundle
- SSO / OIDC integration with `X-User-Id` middleware
- OpenAPI rate limiting
- arq + Redis full deployment guide
- Multi-tenant project worker pool
- Automatic project zip backup + import
- Hardware HSM signing (replace demo ed25519 keys)
- True OCR vision integration (currently stub)

### UX
- Mobile (< 768) responsive support
- Full Lighthouse a11y 100
- Treatment-area templates with sample data
- First-visit guided tour videos
- Operation record-and-replay

### Visualization
- Survival curves with risk table overlay
- Bland-Altman plots
- Heat maps (gene expression / biomarker)
- 3D PK profile plots
- Interactive dashboard mode

If you start work on any of these, please open an issue tagged
`v2-roadmap` so we can coordinate.
