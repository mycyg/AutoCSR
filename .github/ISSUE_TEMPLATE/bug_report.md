---
name: Bug report
about: Report a reproducible issue in AutoCSR
title: "[bug] "
labels: bug
---

## Environment

- AutoCSR commit / branch:
- Python version (`python --version`):
- Node version (`node --version`):
- OS:
- LLM provider (DeepSeek / OpenAI / Ark / other):

## Steps to reproduce

1.
2.
3.

If possible, paste the request you sent and a minimal `curl` that
triggers the bug. For ingest / cleansing issues, attach the input file
(redact any real patient identifiers).

## Expected behaviour

## Actual behaviour

Logs / stack traces (please use code fences):

```
<paste here>
```

## Optional context

- Did one of the `scripts/m*_e2e_test.py` scripts reproduce it?
- Any custom `settings.yaml` fields involved?
