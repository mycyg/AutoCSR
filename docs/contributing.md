# AutoCSR — contributing guide

This is the **v2.x extension recipe book**. For the licence terms, PR
checklist and dev-env walkthrough, see the repo's top-level
[`CONTRIBUTING.md`](../CONTRIBUTING.md).

If you want to add a feature that does not fit the four recipes below,
please open an issue first so we can sketch the right surface (a new
agent class, a new export format, a new analysis kind…). Most v2.x
additions live in a single file plus a registry entry.

---

## 1. Add a new therapeutic-area template

A "template" is **one principle YAML** + **one project template JSON**
(+ optional sample data).

1. Create `backend/app/principles/<area>.yaml` shaped like
   `backend/app/principles/oncology.yaml`:
   - top-level: `principle_id`, `display_name`, `language_default`
   - `sections: []` — recursive `{id, title, depth, requirements,
     stat_hints, children}` tree
2. Register it in `backend/app/principles/__init__.py` (`PRINCIPLES`
   dict) so the outline builder discovers it.
3. Create `data/templates/<area>.json`:
   ```json
   {"id":"<area>_csr","name":"<Area> CSR template",
    "principle_id":"<area>","description":"..."}
   ```
4. (Optional) drop a sample project under `data/sample_projects/<area>/`
   following the layout already used by `oncology/`.
5. Add a row to `scripts/generate_sample_data.py`'s `DOMAINS` list so
   `python scripts/generate_sample_data.py` regenerates the parquets
   reproducibly.
6. Add `<area>` to the `DOMAIN_ICONS` map in
   `frontend/src/views/ProjectList.vue` and an `i18n.projects` blurb
   key if you want a custom card label.

Test: `python scripts/m20_e2e_test.py` (covers the 5 existing domains)
should be extended with one assertion per new domain.

---

## 2. Add a new AI agent (writer / reviewer / tool)

Agents inherit `app.agents.base.BaseAgent` and live in
`backend/app/agents/<name>.py`. A minimal skeleton:

```python
from app.agents.base import BaseAgent, AgentResult

class MyHelper(BaseAgent):
    name = "my_helper"
    default_model = "primary"

    async def run(self, *, project_id: str, payload: dict) -> AgentResult:
        # 1. Pull whatever context you need from app.context.gather(...)
        # 2. Build a prompt
        # 3. await self.llm.complete(...)  -- caches + tracks tokens
        # 4. Optionally tool_loop(...) for tool calls
        return AgentResult(
            markdown=text,
            provenance=self.make_provenance(),
        )
```

Then:

1. Add a route in `backend/app/server/routes/<area>.py` that wires the
   payload → agent.run → response.
2. If it is a "tool-use" callable from other agents (e.g.
   `search_literature`), also register it in
   `backend/app/agents/tools/__init__.py`.
3. Add unit tests under `backend/tests/agents/test_my_helper.py`
   mocking the LLM via `app.llm.testing.fake_client`.
4. If user-visible, add a button in the relevant frontend view (often
   `ReportView.vue` toolbar or `AnalyzeView.vue` action bar) plus an
   i18n key.

Provenance + metrics + audit logging are inherited from `BaseAgent`;
you do not need to write them yourself.

---

## 3. Add a new export format

Each format is one module under `backend/app/export/<fmt>_builder.py`
exposing a single async function:

```python
async def build_<fmt>(project_id: str,
                      options: ExportOptions) -> ExportResult:
    ...
```

Steps:

1. Implement the builder. Reuse `app.export.common.load_drafts`,
   `load_outline`, `load_stat_blocks` — they handle the canonical
   `tenant/project` paths.
2. Register the format in `backend/app/server/routes/export.py`'s
   `MULTI_BUILDERS` dict — that's all that's needed for
   `POST /api/projects/{pid}/export/{fmt}` to start routing.
3. Emit `export.<fmt>.start | progress | done | error` over the WS so
   `TaskProgressOverlay` can show progress.
4. Frontend: bump the `MultiExportFormat` union in
   `frontend/src/api/rest.ts` and add a card to the multi-grid in
   `ExportView.vue`.
5. Add an assertion to `scripts/m19_e2e_test.py` verifying the file is
   produced and well-formed (open + sanity check size > N bytes).

---

## 4. Add a new locale

UI strings live in `frontend/src/i18n/<locale>.json`.

1. Copy `zh.json` to `<locale>.json` and translate (top-down — every
   key has an equivalent in `en.json`).
2. Import it in `frontend/src/i18n/index.ts`:
   ```ts
   import xx from './xx.json'
   ...
   export type Locale = 'zh' | 'en' | 'ja' | 'xx'
   ...
   messages: { zh, en, ja, xx },
   ```
3. Add a row to `LanguageSwitch.vue` and document.lang mapping in
   `setLocale()`.
4. Backend prompts: if you want translated agent prompts, add a
   `<lang>.yaml` next to `backend/app/prompts/zh.yaml` /
   `en.yaml`. Agents pick the right prompt via `project.language`.
5. Date / number formatting: confirm `app.i18n.format` covers your
   locale (it uses Babel under the hood — most BCP47 tags work).

---

## Local quality bar

Before opening a PR:

```bash
# Backend
cd backend && .venv/Scripts/pytest tests/ -v   # all green
ruff check app                                  # 0 errors

# Frontend
cd frontend && npm run build                    # 0 errors
                                                # bundle delta < 100 KB

# E2E
python scripts/m22_e2e_test.py                  # 0 fails
python scripts/m21_e2e_test.py                  # regression
```

CI replays the same suite (without LLM key — mock mode). Anything
green locally will be green in CI; nothing is gated on a fast network.

---

## What lives where (cheat sheet)

| You changed… | Open this test |
|---|---|
| an agent prompt | `scripts/m17_e2e_test.py` |
| a route under `/api/projects/...` | the milestone that introduced it (m2–m21 trace in CONTRIBUTING) |
| a frontend view | `npm run build` + a manual mobile checklist (`docs/quickstart.md`) |
| a principle YAML | `scripts/m20_e2e_test.py` |
| an export format | `scripts/m19_e2e_test.py` |
| an auth path | `scripts/m21_e2e_test.py` |
| a11y CSS | `scripts/m22_a11y_check.py` |
