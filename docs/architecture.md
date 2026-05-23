# AutoCSR — architecture

## High-level data flow

```
                   ┌─────────────────────────────────────────────┐
                   │              FRONTEND (Vue 3 + EP)          │
                   │   ProjectList → Intake → Cleanse → Analyze  │
                   │   → Outline → Report → Review → Export      │
                   │   pinia stores | WS bridge | i18n | a11y    │
                   └────────────────────┬────────────────────────┘
                                        │ REST + WebSocket (json)
                                        ▼
   ┌────────────────────────── BACKEND (FastAPI) ───────────────────────────┐
   │                                                                        │
   │   server/   routes/        middlewares/   ws/                          │
   │             auth pagination pii rate_limit  realtime                   │
   │                                                                        │
   │   agents/   writer  chat_editor  reviewer(s)  literature_search        │
   │             polishing  chart_selector                                  │
   │                                                                        │
   │   ingestion/ classifier protocol_importer sap_importer define_importer │
   │   cleansing/ auditor rule_engine pii sandbox snapshots                 │
   │   analysis/  basic/  advanced/  ask  dashboards                        │
   │   outline/   builder principles versioning                             │
   │   report/    writer_runner harmonizer terminology                      │
   │   collab/    sign_chain comments multi_review                          │
   │   export/    docx pdf html pptx md_bundle ectd_packager tlf            │
   │              reference_formatter formula_render                        │
   │   safety/    hallucination_guard pii_scanner                           │
   │   observability/ metrics error_hook tracing                            │
   │   queue/     arq_app  checkpoint  inmemory                             │
   │   audit/     ledger rotation hash_chain                                │
   │   auth/      models  password  jwt_token  middleware                   │
   │   i18n/      format (numbers / dates / tz)                             │
   │                                                                        │
   └──────────────┬──────────────────────────────────┬──────────────────────┘
                  │                                  │
                  ▼                                  ▼
        ┌─────────────────┐               ┌──────────────────┐
        │  data/projects  │               │   Redis (arq)    │
        │  ./tenants/...  │               │  task queue      │
        │  raw/  proc/    │               │  ws fanout       │
        │  chapters/      │               └──────────────────┘
        │  outline.json   │
        │  audit.jsonl    │
        │  signatures/    │
        └─────────────────┘
```

## Backend module map (25+ packages)

| Package | Purpose |
|---|---|
| `app.server.main` | FastAPI app, OpenAPI tags, CORS, lifespan |
| `app.server.routes.*` | One module per resource (projects / outline / report / analysis / export / auth / ingestion / dashboards / tasks / audit / ectd / hallucination …) |
| `app.server.middlewares.*` | `pagination`, `rate_limit`, `tenant_context`, error handler |
| `app.server.ws.realtime` | per-project WebSocket pub/sub with offline replay buffer |
| `app.agents.base` | `BaseAgent` — tool-loop primitive, metrics decorator, provenance tagger |
| `app.agents.writer` | per-section drafting; produces `SectionDraftDTO` |
| `app.agents.chat_editor` | in-editor refinement w/ markdown diff |
| `app.agents.reviewers.*` | `consistency`, `compliance`, `stat_alignment`, `completeness` |
| `app.agents.literature_search` | PubMed E-utilities + Wanfang stub |
| `app.agents.polishing` | medical-English polish + structural diff |
| `app.agents.chart_selector` | recommend ECharts type for a StatBlock |
| `app.ingestion.*` | classifier, parsers (xpt, sas7bdat, parquet, docx, pdf), `protocol_importer`, `sap_importer`, `define_importer` |
| `app.cleansing.*` | rule engine, PII scanner, sandbox, snapshots, auditor with `rule_provenance` |
| `app.analysis.basic.*` | descriptive, inferential, survival, safety |
| `app.analysis.advanced.*` | `km_with_risk`, `bland_altman`, `heatmap`, `pk_profile_3d`, `dashboard` |
| `app.analysis.ask` | data-question agent w/ sandboxed pandas |
| `app.outline.*` | principles loader (ICH E3 + 5 domains), tree builder, versioning |
| `app.report.*` | concurrent writer runner, terminology harmonizer, draft store |
| `app.collab.sign_chain` | sequential signature workflow on `ReviewTask` |
| `app.collab.comments` | section-anchored comments + sign-off |
| `app.export.docx_builder` | jinja2 over `python-docx`; preset palette |
| `app.export.pdf_builder` | reportlab CSR build |
| `app.export.html_builder` | jinja2 + ECharts CDN; interactive |
| `app.export.pptx_builder` | python-pptx summary deck |
| `app.export.markdown_bundle` | per-section md + assets zip |
| `app.export.ectd_packager` | M5.3.5 directory layout zip |
| `app.export.tlf` | RTF + CSV + define-XML bundle |
| `app.export.reference_formatter` | Vancouver / GB-7714 / AMA |
| `app.export.formula_render` | matplotlib mathtext → PNG |
| `app.safety.hallucination_guard` | Ref<…> validation against corpus |
| `app.safety.pii_scanner` | 4 mode scanner (regex + ML + dictionary + LLM) |
| `app.observability.metrics` | Prometheus counters / histograms / gauges |
| `app.observability.error_hook` | pluggable sink (Sentry / webhook) |
| `app.queue.arq_app` | arq + Redis (prod) |
| `app.queue.inmemory` | dev fallback queue |
| `app.queue.checkpoint` | resumable long tasks (report / cleansing) |
| `app.audit.ledger` | append-only JSONL w/ hash chain |
| `app.audit.rotation` | monthly gzip rotation |
| `app.auth.models` | User / Tenant / ProjectMember |
| `app.auth.password` | bcrypt |
| `app.auth.jwt_token` | jose access (24 h) + refresh (30 d) |
| `app.auth.middleware` | bearer dependency + dev_mode fallback |
| `app.i18n.format` | locale-aware numbers / dates / tz |

## Frontend layout

```
src/
  api/         rest.ts (typed axios)  ws.ts (per-project bus)
  stores/      pinia stores per domain (auth, project, outline,
               report, cleansing, ingest, analysis, export, tasks…)
  composables/ useShortcuts useConfirm useRecentlyViewed useTheme
               useResponsive (M22) useTouchGestures (M22)
  components/  global/ (StepNavigator, EmptyState, TaskProgressOverlay,
               OnboardingTour, HelpMenu, ThemeToggle, ProjectMembersDialog…)
               cleanse/ outline/ report/ analyze/ analysis/ collab/
  views/       per-step page (ProjectList, ProjectDetail, CleanseView,
               OutlineView, ReportView, ExportView, AnalyzeView,
               DashboardView, ReviewView, TasksView, AuditView,
               CompareView, LoginView, RegisterView,
               TenantSettingsView)
  i18n/        zh.json en.json ja.json (stub)
  styles/      tokens.css (design tokens + dark) a11y.css
```

## Key Pydantic schemas

| Schema | Where | Notable fields |
|---|---|---|
| `ProjectConfig` | `app.config.project` | id, name, tenant_id, principle_id, language, timezone, notes, blinding, lock |
| `OutlineNode` | `app.outline.models` | id, title, depth, requirements, stat_hints, children |
| `StatBlock` | `app.analysis.models` | id, title, analysis_type, source_files, result_json, image_data_uri, n_rows |
| `SectionDraft` | `app.report.models` | node_id, markdown, citations, llm_meta, warnings, status, provenance |
| `ReviewTask` | `app.collab.models` | id, project_id, status, sign_chain[], comments[] |
| `SignChainStep` | `app.collab.models` | role, signer_user_id, signed_at, signature_id, status |
| `Provenance` | `app.report.models` | agent, model, tokens, ts, hallucination?, rule_provenance? |
| `AuditEntry` | `app.audit.ledger` | ts, actor, action, resource, payload, prev_hash, hash |
| `User` / `Tenant` | `app.auth.models` | bcrypt password_hash, role, tenant_id |
| `ProjectMember` | `app.auth.models` | project_id, user_id, role ∈ {owner, editor, reviewer, viewer} |

## Synchronous vs background work

- **Synchronous (REST):** small CRUD on outline / config / comments;
  metadata reads; auth roundtrips.
- **Background (queue):** ingest, cleansing apply, analysis batches,
  report generation, all export formats. Drives WS events
  `<kind>.start | .progress | .done | .error` so the frontend can
  show TaskProgressOverlay + StepNavigator badges live.

Checkpoints (`app.queue.checkpoint`) make `report.generate` and
`cleansing.apply` SIGTERM-safe; `POST /api/tasks/{tid}/resume` picks up
the next outstanding leaf.
