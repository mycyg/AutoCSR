# AutoCSR — 5-minute quickstart

> Target audience: a clinical data scientist or RA reviewer who wants
> to evaluate AutoCSR end-to-end without reading a single line of code.

## What you'll have at the end

A complete Clinical Study Report (CSR) `.docx` for an oncology study,
generated from synthetic ADaM data via the AI pipeline, exportable to
PDF / HTML / PPTX / Markdown bundle / eCTD M5 zip. Total wall time on
a modest workstation: **~5 minutes**.

---

## Step 1 — Clone and bootstrap

```bash
git clone https://github.com/your-org/AutoCSR.git
cd AutoCSR

# Backend (Python ≥ 3.11)
python -m venv backend/.venv
source backend/.venv/bin/activate          # Windows: backend\.venv\Scripts\activate
pip install -r backend/requirements.txt

# Frontend (Node ≥ 18)
cd frontend && npm install && npm run build && cd ..
```

Create `backend/app/config/settings.yaml` with at least an LLM key:

```yaml
llm:
  primary:
    provider: deepseek          # or openai / anthropic / ollama
    model: deepseek-chat
    api_key: sk-...              # your own key
```

The repo's `settings.example.yaml` lists every knob with sane defaults.

<!-- TODO: screenshot — settings.yaml editor pane -->

## Step 2 — Launch and create a demo project

```bash
# Backend
cd backend && uvicorn app.server.main:app --host 0.0.0.0 --port 8765

# Frontend (separate shell, repo root)
cd frontend && npm run preview -- --port 5174
```

Open <http://localhost:5174>. The empty Project List shows the hero
plus the **5 domain demo cards** (oncology / rare disease / vaccine /
pediatric / cardiovascular). Click **Oncology**.

What happens behind the scenes:

1. The backend stages real-shape fake ADaM parquets (ADSL / ADAE /
   ADEFF / ADTTE) into `data/projects/<pid>/raw/`.
2. The intake worker classifies each file and routes it to the
   cleansing pipeline.
3. The auto-analysis agent produces 8–12 StatBlocks (descriptive,
   survival, safety, subgroup) and the outline builder lays out an
   ICH E3-shaped tree with RECIST-aware sections.

<!-- TODO: screenshot — domain card grid -->
<!-- TODO: screenshot — auto-staged project landing -->

## Step 3 — Generate the report

Navigate to **撰写 / Report**. Click **Start writing** and confirm
"all sections". Watch the StepNavigator badges flip from `pending` →
`done` as the writer agent fans out across leaves (default concurrency
= 4).

The right pane streams plan / WriterStatus / Hallucination panel in
real time. Long sections take 10–20 s each on a Sonnet-class model.

<!-- TODO: screenshot — Report view mid-flight -->

## Step 4 — Export DOCX

When the StepNavigator's `report` chip turns green, head to **Export**.
Pick a preset (`standard` / `pharma` / `academic` / `regulatory`),
verify fonts and watermark in the live preview, then click
**Generate DOCX**. The file lands in the history table — click ⬇ to
download.

Tip: tick **附录 A · 清洗** + **附录 B · 分析** for the full
reproducibility bundle (DOCX-embedded audit + StatBlock JSON).

<!-- TODO: screenshot — Export view + advanced collapse -->

## Step 5 — Try the conversational editor

Open any section in **Report**, click **+ 指令** in the toolbar and
type "tone down the conclusion to neutral phrasing; cite ADAE rather
than overall". The writer re-runs only that section, preserves the
previous version (rollback from the dropdown), and writes an audit
event for the change.

For more advanced flows see:

- `docs/architecture.md` — module map + data flow
- `docs/compliance.md` — 21 CFR Part 11 / NMPA notes
- `docs/api.md` — REST examples
- `docs/deployment.md` — Docker Compose + Nginx
- `docs/contributing.md` — extending templates / agents / locales

---

## Video script (5 minutes)

The placeholder card under **? → Video tutorial** will eventually
embed the recorded walkthrough. The script for that recording lives
here:

| Time | Action | Note |
|---|---|---|
| 0:00 | Title card — "AutoCSR in 5 minutes" | Logo + version |
| 0:10 | Show empty project list + domain grid | Mention 5 demo cards |
| 0:25 | Click Oncology card | "One click, real-shape fake data" |
| 0:45 | Walk through Cleanse view briefly | Highlight PII scan + provenance |
| 1:15 | Walk through Analyze view | Show KM + forest + bland-altman |
| 1:50 | Open Outline view; show RECIST tree | Mention the 5 domain principles |
| 2:20 | Open Report view; hit Start writing | Watch streaming +badges |
| 3:00 | Pick a section; demo `+ 指令` edit | Show diff + rollback |
| 3:50 | Open Export; pick preset; generate | Show preview pane |
| 4:20 | Show eCTD M5 dialog | Mention cover letter + ICF upload |
| 4:40 | Quick mobile shot — same flow on phone | Three tabs replace three panes |
| 4:55 | "Star us on GitHub" closing card | Link in description |

Recommended tooling: OBS (full-screen capture), iPhone simulator for
mobile shot, ffmpeg for trim/concat. Upload to YouTube + Bilibili in
parallel; update `VIDEO_URLS` in `frontend/src/components/global/HelpMenu.vue`.
