## Summary

(One paragraph: what does this PR do, and why?)

## Type

- [ ] Bug fix
- [ ] New feature
- [ ] Refactor (no functional change)
- [ ] Docs only
- [ ] CI / tooling

## Areas touched

- [ ] ingest
- [ ] cleansing
- [ ] analysis
- [ ] outline
- [ ] writer / orchestrator
- [ ] chat editor
- [ ] export
- [ ] frontend
- [ ] config / infra
- [ ] docs

## Test plan

- [ ] `python scripts/m2_e2e_test.py` — pass
- [ ] `python scripts/m3_e2e_test.py` — pass
- [ ] `python scripts/m4_e2e_test.py` — pass
- [ ] `python scripts/m5_e2e_test.py` — pass
- [ ] `cd frontend && npm run build` — pass
- [ ] Additional manual checks (describe):

## Privacy / data handling

- [ ] No change to what the LLM sees
- [ ] Changes LLM payload — explained below
- [ ] Touches PII redaction — reviewed `pipeline.pii_strip` / `llm_data_redaction`

## Screenshots / output

(Drop screenshots, sample DOCX, or e2e tail output here when useful.)
