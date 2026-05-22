# AutoCSR

**Turn raw clinical data — including messy real-world inputs — into an
ICH E3 / NMPA-aligned Clinical Study Report (CSR) in Word.**

<!-- TODO: screenshot of three-pane workbench -->

AutoCSR is an open-source, end-to-end pipeline: upload → router →
cleansing → analysis → outline → multi-agent writing → conversational
editing → DOCX export. Every step keeps an audit trail; nothing leaves
the cleansing stage without a human-readable rule yaml.

---

## Features

- **Heterogeneous ingest router** — auto-classifies six input types
  (SDTM/ADaM, messy Excel, PDF forms, scanned CRFs, handwritten notes,
  literature) and dispatches them to parallel workers.
- **Cleansing workbench** — LLM proposes rules (rename, cast, unit
  convert, normalize, CDISC map, impute, outlier flag, PII hash, derive…);
  user accepts/edits/rejects each one. Output is an exportable
  `cleansing_pipeline.yaml` that can be re-applied to a new batch.
- **Clinical analysis modules** — descriptive baseline tables,
  inferential tests (t / Wilcoxon / chi-square / Fisher), survival
  (Kaplan–Meier + Cox via lifelines), safety (AE × SOC × severity).
  Each output is a `StatBlock` that becomes a corpus citation.
- **Outline builder** — hard-coded ICH E3 / CDE skeleton plus
  project-specific binding of `StatBlock` refs to leaves.
- **Multi-agent writer** — `asyncio.gather` over leaves with a
  `Semaphore`-bounded parallelism cap, three-phase DAG
  (background → results → discussion), then a harmonizer pass to
  unify tone.
- **Conversational editor** — per-section chat with 4 atomic patch ops
  (`replace_section` / `insert_paragraph` / `replace_paragraph` /
  `patch_field`), automatic version snapshots, and one-click rollback.
- **DOCX export** — programmatic ICH E3 template with cover page,
  automatic TOC field, header/footer with page numbering, real Word
  tables (not images), References chapter, and appendices documenting
  the cleansing pipeline + analysis methods.
- **Privacy by default** — `hash_pii` is a mandatory cleansing rule;
  LLM calls never see raw patient identifiers. Configurable via
  `pipeline.pii_strip` and `pipeline.llm_data_redaction` in
  `settings.yaml`.

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
