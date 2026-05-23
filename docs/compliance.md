# AutoCSR — regulatory compliance reference

> **Status:** AutoCSR provides *technical building blocks* aligned with
> 21 CFR Part 11 and NMPA Annex 11 expectations. Final regulatory
> sign-off for any submission remains the responsibility of the
> sponsor's RA team. Treat this document as a **mapping**, not a
> guarantee of compliance.

## At a glance

| Requirement (FDA 21 CFR Part 11 / NMPA Annex 11) | AutoCSR feature | Module |
|---|---|---|
| § 11.10(b) electronic records integrity | Append-only audit JSONL + SHA-256 hash chain | `app.audit.ledger` |
| § 11.10(c) record retention | Monthly rotation + gzip; configurable retention | `app.audit.rotation` |
| § 11.10(e) operational checks | Sequential sign-chain blocks out-of-order signing | `app.collab.sign_chain` |
| § 11.50 / § 11.70 signature manifestations + linkage | ed25519 signature payload includes ts + actor + reason + section hash | `app.collab.signatures` |
| § 11.200 unique user IDs + two factors | Bcrypt + JWT (24 h access / 30 d refresh); 2FA hook (see roadmap) | `app.auth.*` |
| § 11.300 e-sig revocation | `signatures/revoked.json` + sign_chain re-init | `app.collab.signatures` |
| Audit trail review | `/api/projects/{pid}/audit?since=...` + UI AuditView | `app.server.routes.audit` |
| Blinding protection | `ProjectConfig.blinding=true` blocks unmasked exports | `app.config.project` |
| Database lock | `ProjectConfig.lock=true` blocks all writes | `app.config.project` |
| PII protection | 4-mode PII scanner (regex / dictionary / ML / LLM) | `app.safety.pii_scanner` |
| AI-output provenance | Every `SectionDraft.provenance` carries agent, model, tokens, ts | `app.report.models` |
| Reference integrity | `hallucination_guard.validate_references_against_corpus` | `app.safety.hallucination_guard` |
| eCTD format | M5.3.5 directory layout zip | `app.export.ectd_packager` |

## Audit trail

Every state change writes one append-only JSON line to
`data/projects/<pid>/audit.jsonl`:

```json
{
  "ts": "2026-05-23T08:31:17Z",
  "actor": "u_alice",
  "action": "outline.patch_node",
  "resource": "node:11.4.2",
  "payload": {"old_title": "...", "new_title": "..."},
  "prev_hash": "8a4f...",
  "hash": "c91e..."
}
```

`hash = sha256(prev_hash || canonical_payload)` so any tamper is
detectable by replaying the chain. `app.audit.rotation` rolls to
`audit.YYYY-MM.jsonl.gz` once a file exceeds 100 MB.

The UI's **Audit** view shows the chain in reverse-chronological order
with action chips + actor avatars. Operators can export the full chain
or any time slice as a signed JSON bundle.

## Electronic signatures

Demo grade ed25519 keys are auto-generated on first use, written under
`data/projects/<pid>/signatures/keys/`. Each signature record stores:

```json
{
  "id": "sig_8eb1...",
  "section_hash": "sha256:...",
  "signer_user_id": "u_alice",
  "role": "statistician",
  "ts": "2026-05-23T08:33:01Z",
  "reason": "Statistical review complete.",
  "signature": "base64..."
}
```

For real submissions the keypair material lives outside the repo
under a hardware HSM — `app.collab.signatures` exposes a
`SignerBackend` interface so the demo ed25519 backend can be swapped
for `PKCS11Backend` / `KMSBackend` without touching call sites.

## Sequential sign chain

`POST /api/tasks/{tid}/sign_chain/init` seeds the default chain
**statistician → medical → regulatory → approver**.
`POST /api/tasks/{tid}/sign_chain/advance` advances exactly one step:

- Step n+1 is allowed only when step n is `status=signed`.
- Re-signing the same step is rejected with `409 conflict`.
- The DOCX cover sheet enumerates the chain with timestamps + redacted
  signature IDs.

## Blinding & database lock

`ProjectConfig.blinding=true` masks all `TRT01A`-class columns in the
cleansed parquets, the analysis results, and the exported DOCX. The
mask is reversed only when an authorised user calls
`POST /api/projects/{pid}/unblind` (which itself appends a
`blinding.lifted` audit row).

`ProjectConfig.lock=true` refuses all write endpoints; reviewers can
still read, comment and sign. Lock + unlock require an authenticated
admin and are themselves audit-logged.

## PII scanning

`app.safety.pii_scanner` operates in 4 modes simultaneously:

1. **Regex** — phone numbers, SSN-style IDs, MRN, IP addresses,
   typical Chinese / EU ID schemes.
2. **Dictionary** — name lookup against `data/dict/given_names.txt` +
   `data/dict/family_names.txt`.
3. **Lightweight ML** — `presidio-analyzer` if installed; skipped
   silently otherwise.
4. **LLM fallback** — when the prior three flag a row as ambiguous,
   the editor LLM is asked to label fields conservatively.

Any flagged field is replaced with `***` in exports and an
`audit:pii_masked` entry is appended.

## AI provenance

Every chunk of generated markdown carries a `Provenance` block:

```json
{
  "agent": "writer",
  "model": "deepseek-chat",
  "tokens_in": 1280,
  "tokens_out": 920,
  "ts": "2026-05-23T08:34:11Z",
  "hallucination": false,
  "rule_provenance": "llm_suggestion"
}
```

When `show_ai_provenance=true` (Export advanced config), the DOCX
footer of each AI-touched paragraph contains a small italic marker
`[AI · writer · 2026-05-23]`. When `false`, the provenance still lives
in the audit log but is not visible to print readers.

## Hallucination guard

After every `writer` or `chat_editor` call, the markdown is scanned
for `Ref<...>` placeholders. Each one is resolved against the project
corpus (`corpus.fetch_ref`). Unresolvable references are recorded in
`hallucinations.json` and:

- The DOCX paragraph is wrapped in a red border + footer warning.
- The eCTD packager refuses to build until all hallucinations are
  cleared OR explicitly accepted by an admin reason-coded override.

## Reviewer checklist

A pragmatic checklist if you are an external RA reviewer auditing an
AutoCSR-generated CSR:

1. Open `data/projects/<pid>/audit.jsonl` and `replay_chain.py` to
   verify `prev_hash` integrity end-to-end.
2. `GET /api/projects/{pid}/signatures` — confirm sign-chain
   completeness and step order.
3. Check `Provenance.hallucination == false` for every paragraph in
   `chapters.json`.
4. Compare `StatBlock.result_json` numbers against the rendered DOCX
   tables (the DOCX builder writes statblock IDs as run properties for
   exactly this reason).
5. Verify `blinding=true` was set during analysis if the protocol is
   blinded.
6. Confirm `ProjectConfig.lock=true` after database lock event.
7. Verify the exported eCTD zip directory layout matches your local
   eValidator profile.

> If any step fails, refuse the submission and request a remediation
> note via the `POST /api/projects/{pid}/ra_note` endpoint.
