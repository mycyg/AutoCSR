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
4. Run the milestone e2es you touched:
    ```bash
    python scripts/m2_e2e_test.py
    python scripts/m3_e2e_test.py
    python scripts/m4_e2e_test.py
    python scripts/m5_e2e_test.py
    ```
    All four must finish with `[E2E] OK`.
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

This project does not cut formal releases yet. The `main` branch is the
release surface; tag `vX.Y.Z` when we settle on a public version.
