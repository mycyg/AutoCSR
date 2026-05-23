# AutoCSR

[![Release](https://img.shields.io/github/v/release/mycyg/AutoCSR)](https://github.com/mycyg/AutoCSR/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Tests](https://img.shields.io/badge/e2e-22%20passing-brightgreen)](./scripts)
[![Backend](https://img.shields.io/badge/Python-3.11+-blue)](./backend)
[![Frontend](https://img.shields.io/badge/Vue-3.5-42b883)](./frontend)

**Turn raw clinical data — including messy real-world inputs — into an
ICH E3 / NMPA-aligned Clinical Study Report (CSR) in Word.**

<!-- TODO: screenshot of three-pane workbench -->

AutoCSR is an open-source, end-to-end pipeline: upload → router →
cleansing → analysis → outline → multi-agent writing → conversational
editing → DOCX / TLF / eCTD export. Every step keeps an audit trail;
nothing leaves the cleansing stage without a human-readable rule yaml;
every LLM call is logged; every reference is validated against the
corpus.

---

## Features

### 🧪 Data → Statistics
- **Heterogeneous ingest router** — six typed workers (SDTM/ADaM,
  messy Excel, PDF forms, scanned CRFs, handwritten notes, literature)
  routed by mime + content heuristics + LLM tiebreaker.
- **Cleansing workbench** — 10 proposal types (rename, cast, unit
  convert, normalize, **map_to_cdisc**, impute, outlier flag, PII hash,
  split, merge, derive) with mandatory `hash_pii`; user accepts /
  edits / rejects each rule; exportable `cleansing_pipeline.yaml`
  re-applicable to new batches.
- **Medical coding** — bundled CC0 dictionaries (ICD-10 / ATC /
  LOINC, ~1500 codes) plus configurable paths for commercial
  dictionaries (MedDRA, WHODrug, SNOMED-CT).
- **Clinical analysis** — basics (descriptive, inferential
  t/Wilcoxon/chi-square/Fisher, survival KM+Cox via lifelines,
  safety AE × SOC × severity) + advanced (multitest Bonferroni/FDR,
  subgroup forest plots, sensitivity ITT/PP/LOCF/MMRM, CONSORT flow
  diagram, SMD baseline balance).

### 🤖 Multi-agent Writing
- **Plan-first mode** — outline points editable before full draft.
- **Writer tool loop** — autonomous calls to `sandbox_python` /
  `search_corpus` / `call_analyst` / `fetch_ref` / etc., with `respond`
  terminator, capped at 5 turns, JSON schema constrained.
- **Three-phase orchestrator** — background → results → discussion;
  `asyncio.gather` with bounded parallelism; `AnalystFuturePool`
  dedupes identical queries across parallel writers.
- **Harmonizer** — pairwise tone + terminology unification; rejects
  LLM output that drops `Ref<…>` codes or changes paragraph length
  beyond a threshold.
- **Data Ask** — natural-language query → analyst writes Python →
  sandbox runs → returns `StatBlock` with both markdown table and
  ECharts JSON.

### 📝 Editing & Collaboration
- **Conversational editor** — 4 atomic patch ops (`replace_section` /
  `insert_paragraph` / `replace_paragraph` / `patch_field`), automatic
  version snapshots, one-click rollback.
- **Comments + apply batch** — collect inline comments, then one call
  applies all unresolved comments via editor LLM.
- **Markers** — 4 colored tags (important / todo / question / risk)
  with character-range anchoring.
- **Multi-version diff** — paragraph-level structured diff between
  any two SectionDraft revisions.
- **Multi-user tasks** — Kanban (open / in_progress / resolved /
  wont_fix), from-issue / from-comment promotion, per-task assignee.
- **Cross-project compare** — outline + draft diff across two projects
  for protocol-amendment impact analysis.

### 🔬 Reviewers & Quality
- **Four parallel checkers** (M10): structure (ICH E3 coverage),
  consistency (sandbox cross-checks numbers vs StatBlock), citation
  (every `Ref<…>` resolves), completeness (outline required + bound
  stat_refs + non-empty markdown).
- **Three expert reviewer agents** (M16): statistician (assumptions,
  CI/p-value reporting, subgroup interpretation), medical
  (dose / regimen / AE causality / drug interactions), regulatory
  (ICH E3 / FDA / NMPA jurisdiction-specific compliance).
- **Hallucination guard** — every `Ref<…>` produced by writer or
  editor is validated against the corpus; unresolved refs flag the
  paragraph and surface in DOCX export.

### 🛡 Compliance & AI Safety
- **21 CFR Part 11 audit trail** — append-only JSONL with SHA-256
  chain; pluggable `AuditBackend` for S3 Object Lock / IPFS upgrade;
  monthly file rotation with gzip.
- **ed25519 e-signatures** — per-project keypair (HSM-ready
  interface); demo signing for unblind / database-lock / final
  approval.
- **Sequential sign chain** — `statistician → medical → regulatory →
  approver`; out-of-order advance returns 403.
- **PII pre-check** — regex + optional LLM second-pass scans every
  LLM payload (ID / phone / email / MRN / names / address); four
  modes: strict / auto_redact / warn / off.
- **LLM call logging** — full prompt / response / tokens / latency
  per call, hash-only mode available.
- **AI provenance markers** — every paragraph tracks `source:
  ai|human|hybrid`; optional grey shading in DOCX export.
- **Blinding mode** — arm names masked in LLM context until
  unblind-with-signature.
- **Database lock** — mutations 403 unless `X-Addendum: true`.

### 📦 Export
- **DOCX** — programmatic ICH E3 template, cover with cleansing
  pipeline reference, auto TOC field, real Word tables (not images),
  References + Appendix A (cleansing) + Appendix B (analyses);
  4 presets (standard / pharma / academic / regulatory) + user
  `.docx` template upload with placeholder injection; configurable
  fonts / sizes / margins / header / footer / watermark.
- **TLF zip** — per-StatBlock RTF + CSV + minimal define.xml.
- **eCTD M5.3.5 package** — `m1/cover` + `m5/53-clin-stud-rep/...`
  directory with CSR docx, TLF zip, define.xml, signed sign_chain
  manifest.
- **CSR reverse import** — parse existing `.docx` CSR back into
  outline + drafts via Heading-style detection.

### 🌐 UX
- **Bilingual UI** (zh / en) — vue-i18n with ja stub for future.
- **Multi-language prompts** — writer / harmonizer / proposer /
  analyst / reviewer prompt libraries per project language.
- **Dark mode** — design tokens + Element Plus dark + md-editor-v3
  dark + ECharts dark theme.
- **Responsive** — ≥ 1280 three-pane; < 1280 drawer + bottom sheet;
  < 1024 card stack (mobile not supported below 768).
- **Onboarding tour** — first-visit walkthrough + inline tooltips
  for advanced features.
- **Keyboard shortcuts** — j/k tree navigation, ⌘+S save, ⌘+K
  search, Esc close, Tab pane cycle.
- **Accessibility** — aria-labels, focus indicators, role semantics,
  WCAG-AA contrast.

### 🔌 Developer Experience
- **OpenAPI 3.0** — `/openapi.json`, Swagger UI `/docs`, ReDoc
  `/redoc`; routes tagged into 14 logical groups.
- **SDK generation** — `scripts/generate_sdk.py` produces TypeScript
  (`sdk/ts/`) and Python (`sdk/py/`) SDKs from the live OpenAPI spec.
- **Prometheus `/metrics`** — agent runs, LLM tokens, queue depth,
  active projects, request latency histograms.
- **Error sink hooks** — `register_error_sink(callable)` for Sentry
  / Webhook / custom error reporting; no SaaS dependency by default.
- **Checkpoint resume** — long tasks (report generation, cleansing
  apply) can resume from disk after SIGTERM.
- **Pluggable LLM backend** — DeepSeek / OpenAI / Ark / Anthropic-
  compatible endpoints; mock mode (`CSR_*_MOCK=1`) for all agents.

---

## Architecture

```
                upload                                                export
                  │                                                      ▲
                  ▼                                                      │
            ┌──────────┐    ┌──────────┐   ┌─────────┐   ┌─────────┐  ┌──┴──┐
            │  Router  │──▶ │ Workers  │──▶│ Cleanse │──▶│ Analyze │─▶│Write│
            └──────────┘    └──────────┘   └─────────┘   └─────────┘  └──┬──┘
                                              │                          │
                            audit + yaml ◀────┘                          │
                                                                         ▼
                                                                  ┌───────────┐
                                                                  │   Chat    │
                                                                  │  Editor   │
                                                                  └─────┬─────┘
                                                                        ▼
                                                                  ┌───────────┐
                                                                  │   DOCX    │
                                                                  └───────────┘
```

Every node persists to `data/projects/<pid>/` so any failure is
recoverable and any output is auditable.

---

## Quick Start

Requires **Python 3.11+** and **Node 18+**.

```bash
git clone https://github.com/<you>/AutoCSR.git
cd AutoCSR

# 1. backend
cd backend
python -m venv .venv && source .venv/Scripts/activate   # Windows: .venv\Scripts\activate
pip install -e .
cp app/config/settings.example.yaml app/config/settings.yaml
# Edit settings.yaml or `export LLM_API_KEY=sk-...`
python -m uvicorn app.server.main:app --port 8766 --reload

# 2. frontend (new shell)
cd ../frontend
npm install
npm run dev
```

Open `http://127.0.0.1:5174`, create a project, follow the top nav:
**上传 → 清洗 → 分析 → 大纲 → 撰写 → 导出**.

---

## Configuration

`backend/app/config/settings.yaml` (gitignored — copy from
`settings.example.yaml`):

| Section | Key | Notes |
| --- | --- | --- |
| `llm` | `base_url` / `api_key` / `model` | Defaults to DeepSeek; OpenAI / Ark / Anthropic-compatible endpoints work as drop-ins. Override `api_key` with `LLM_API_KEY` env var to keep it out of disk. |
| `server` | `host` / `port` / `data_dir` | Default `127.0.0.1:8766`. `data_dir` is relative to the repo root. |
| `pipeline` | `pii_strip` | Mandatory PII hashing on every cleansing run. Default `true` and cannot be silently skipped. |
| `pipeline` | `max_parallel_writers` | Caps writer-agent concurrency (default 4). |
| `pipeline` | `max_parallel_ingest_workers` | Caps router worker concurrency (default 4). |
| `pipeline` | `llm_data_redaction` | `strict` / `mild` / `off`. Strict (default) sends only column profiles and ≤5 sample rows to the LLM during cleansing proposals. |

Environment variables `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL`
always override `settings.yaml`.

---

## Tutorial

Reproduce the full demo against synthetic ADaM data — no real patients,
no LLM key required (mock mode):

```bash
# Each script is self-contained: spins up uvicorn on a private port,
# runs one milestone's checks, tears down.
python scripts/m2_e2e_test.py     # ingest + cleansing + corpus
python scripts/m3_e2e_test.py     # analysis + outline
python scripts/m4_e2e_test.py     # multi-agent writers
python scripts/m5_e2e_test.py     # chat editor + DOCX export
```

`m5_e2e_test.py` prints the produced docx path on success; open it in
Word to inspect cover, TOC (press F9 to refresh), chapters, and
appendices.

To exercise a real DeepSeek call instead of the deterministic mock:

```bash
export LLM_API_KEY=sk-...
REAL_LLM=1 python scripts/m4_e2e_test.py     # 5-leaf real writer pass
```

---

## Module Map

| Path | What lives there |
| --- | --- |
| `backend/app/llm/` | Provider-agnostic LLM client + 4-tier policy table (`outline_llm` / `writer_llm` / `editor_llm` / `analyst_llm`). |
| `backend/app/ingestion/` | Router + 6 typed workers (`structured`, `messy_tabular`, `pdf_form`, `scan_crf`, `handwriting`, `literature`). |
| `backend/app/cleansing/` | Profiler → proposer → transformer → auditor + `pipeline_io` (yaml export/import). |
| `backend/app/analysis/` | `descriptive` / `inferential` / `survival` / `safety` → `StatBlock`. |
| `backend/app/corpus/` | Unified grep + fuzzy index over four block types (`literature`, `stat`, `principle`, `note`). |
| `backend/app/outline/` | Builder that grafts project StatBlock refs onto a hard-coded principle yaml. |
| `backend/app/report/` | `writer_agent`, parallel `orchestrator`, style-unifying `harmonizer`, conversational `chat_editor`. |
| `backend/app/export/` | `docx_builder` + programmatic ICH E3 template. |
| `backend/app/server/` | FastAPI :8766, REST routes, per-project WebSocket. |
| `frontend/src/` | Vue 3 + Element Plus + md-editor-v3 SPA. |

---

## Contributing

Issues and pull requests are welcome. See [CONTRIBUTING.md](./CONTRIBUTING.md)
for the issue templates, code style, and the e2e check you must run
before submitting.

---

## License

Released under the **MIT License** — see [LICENSE](./LICENSE).

---

## Acknowledgments

This project relies on excellent open-source work:
[lifelines](https://lifelines.readthedocs.io) (survival),
[python-docx](https://python-docx.readthedocs.io) (Word output),
[python-markdown](https://python-markdown.github.io) (md → html),
[rapidfuzz](https://github.com/maxbachmann/RapidFuzz) (corpus search),
[FastAPI](https://fastapi.tiangolo.com),
[Vue.js](https://vuejs.org),
[Element Plus](https://element-plus.org),
[md-editor-v3](https://imzbf.github.io/md-editor-v3/).

---

## Data Privacy

AutoCSR is designed so **patient identifiers never leave your machine**:

- The cleansing pipeline applies `hash_pii` by default and refuses to
  proceed without it; PII columns are detected from semantic heuristics
  and the user must explicitly opt out.
- When the cleansing LLM proposes rules, it sees only column names,
  dtypes, missing-rate, top frequencies, and at most five sample rows
  with PII columns masked. `pipeline.llm_data_redaction=strict` is the
  default.
- Writer / editor LLM calls operate on `StatBlock` aggregates and
  literature snippets, never on row-level patient data.

Audit the redaction yourself: every LLM payload is logged at
`DEBUG` level in `backend/app/llm/ark_client.py`.

---

## Release Notes

### v1.0.0 — 2026-05-22

The first production-ready release. 18 milestones, 14 commits since
init, ~50K lines net added across 302 tracked files. 17 e2e scripts
(`scripts/m2_e2e_test.py` … `m18_e2e_test.py`) and 64 unit tests all
passing.

**Highlights**

- Full ICH E3 pipeline from raw clinical data to signed DOCX +
  TLF + eCTD M5.3.5.
- Six typed ingest workers, ten cleansing proposal types with
  mandatory PII hashing, four basic + five advanced statistical
  modules, multi-agent writer with autonomous tool loop.
- Eight reviewer perspectives (structure / consistency / citation /
  completeness / statistician / medical / regulatory / hallucination).
- 21 CFR Part 11 audit trail, ed25519 e-signatures, sequential
  sign chain, blinding mode, database lock, AI provenance markers.
- Bilingual UI (zh/en), dark mode, responsive ≥ 1024px, onboarding
  tour, keyboard navigation, full a11y pass.
- OpenAPI 3.0 + Swagger UI + auto-generated TypeScript / Python
  SDKs, Prometheus `/metrics`, pluggable error sinks, checkpoint
  resume for long tasks.

See [CONTRIBUTING.md](./CONTRIBUTING.md#roadmap) for the v2.x
roadmap (PDF/HTML/PPT export, real OCR vision, treatment-area
templates, Docker compose, multi-study knowledge base, regulatory
inquiry tracker, and more).

### v2.0.0 — 2026-05-23

The production deployment + therapeutic depth + multi-tenant release.
22 milestones total (M1-M22), 19 commits since init, ~70K lines net
across 435 tracked files. 22 e2e scripts (`m2_e2e_test.py` …
`m22_e2e_test.py`) and 78 unit tests all passing. New `docs/` folder
with 6 guides.

**Major increments since v1.0.0**

- **Infrastructure & deployment** — `docker-compose.yml` (backend +
  frontend + redis + optional prometheus profile), multi-stage
  `Dockerfile`s, nginx SPA + API/WS reverse proxy; full **arq +
  Redis** task queue (inmemory mode preserved); rate-limit middleware
  (token-bucket); project zip backup + restore; GitHub Actions CI
  with pytest/lint/build/e2e-mock/docker-config jobs.
- **Multi-format export** — PDF (reportlab), HTML (jinja2 + ECharts
  interactive), PowerPoint (python-pptx 16:9), Markdown bundle (zip).
- **Therapeutic area templates** — oncology (RECIST 1.1 / iRECIST,
  PFS/OS/DOR), rare disease (Bayesian + external control + propensity
  score), vaccine (GMT/SCR + VE), pediatric (ICH E11(R1) age strata +
  PopPK + growth z-score), cardiovascular (MACE composite + CEC
  adjudication + LVEF). 5 sample projects with synthetic ADaM data
  for one-click hands-on.
- **5 new AI agents** — literature search (PubMed E-utilities,
  Wanfang stub), medical English polishing (3 modes with diff), chart
  selector (StatBlock → ECharts type), reference formatter (Vancouver
  / GB/T 7714 / AMA), LaTeX → DOCX formula render.
- **Multi-tenant accounts** — `User` + `Tenant` + `ProjectMember`
  models, bcrypt password hashing, JWT (python-jose) with access +
  refresh tokens, dev_mode `X-User-Id` fallback for backward
  compatibility. Four-role ACL: owner / editor / reviewer / viewer.
  Login + Register + TenantSettings frontend views.
- **Reverse import suite** — Protocol PDF → 8 trial-design fields,
  SAP docx → outline stat_hints injection, define.xml → ItemDef notes.
- **Advanced visualizations** — KM with risk table (dual-panel +
  median + log-rank p), Bland-Altman with LoA, heatmap (long → pivot
  → imshow + ECharts), PK profile 3D (matplotlib 3D + ECharts-GL with
  2D fallback), composable dashboard (grid layout persistence).
- **Mobile < 768 full support** — `useResponsive` composable, panes
  stack into el-tabs, simplified ChapterReader toolbar, native touch
  gestures (swipe chapters + long-press context menu); skip-to-content
  link, ARIA semantics, contrast bumps targeting Lighthouse a11y ≥ 95.
- **Onboarding upgrade** — ProjectList Hero 5-domain card grid with
  icons; OnboardingTour gains "5 demo projects" step; HelpMenu gains
  video tutorial modal + 10-question FAQ.
- **Documentation** — `docs/quickstart.md` (5-min walkthrough),
  `architecture.md` (data flow + module map), `compliance.md`
  (21 CFR Part 11 / NMPA reviewer checklist), `api.md` (OpenAPI +
  curl/Python/TS/WS examples), `deployment.md` (Docker Compose +
  Nginx TLS + backup), `contributing.md` (recipes for adding
  templates / agents / export formats / locales).

See [CONTRIBUTING.md](./CONTRIBUTING.md#roadmap) for the remaining
v3.x backlog (SSO/OIDC, real HSM signing, true OCR vision, recording
replay, multi-study knowledge base, regulatory inquiry tracking).
