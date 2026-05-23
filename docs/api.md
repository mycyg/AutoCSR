# AutoCSR — REST API quick reference

The canonical, always-up-to-date contract is FastAPI's auto-generated
documentation:

- **Swagger UI:** `http://<host>:<port>/docs`
- **ReDoc:** `http://<host>:<port>/redoc`
- **OpenAPI JSON:** `http://<host>:<port>/openapi.json`

`scripts/generate_sdk.py` consumes that JSON to emit a typed TypeScript
client into `sdk/ts/` and a Python client into `sdk/py/`.

## Authentication

JWT bearer token. Obtain via `/api/auth/login`; refresh via
`/api/auth/refresh`. All `/api/...` endpoints (except `/api/health`,
`/api/auth/*`, `/metrics`) require either a bearer token **or**, when
`settings.auth.dev_mode=true`, an `X-User-Id` header.

```http
GET /api/projects HTTP/1.1
Host: localhost:8765
Authorization: Bearer eyJhbGciOi...
```

## Common endpoints

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/auth/register` | create user + tenant |
| `POST` | `/api/auth/login` | exchange email+password for tokens |
| `POST` | `/api/auth/refresh` | rotate access token |
| `GET`  | `/api/auth/me` | current user + tenant snapshot |
| `GET`  | `/api/projects` | list projects (paginated) |
| `POST` | `/api/projects` | create new project |
| `POST` | `/api/projects/from_sample/{domain}` | one-click demo project |
| `GET`  | `/api/projects/{pid}` | project metadata |
| `POST` | `/api/projects/{pid}/upload` | upload raw data file |
| `POST` | `/api/projects/{pid}/analysis/run` | trigger auto analyses |
| `POST` | `/api/projects/{pid}/outline/build` | build outline from principle |
| `POST` | `/api/projects/{pid}/report/generate` | start writer agents |
| `POST` | `/api/projects/{pid}/report/regenerate/{node_id}` | re-run one section |
| `POST` | `/api/projects/{pid}/hallucination_check` | scan all sections |
| `POST` | `/api/projects/{pid}/export/docx` | build DOCX |
| `POST` | `/api/projects/{pid}/export/{pdf\|html\|pptx\|md_bundle}` | other formats |
| `POST` | `/api/projects/{pid}/export/ectd` | eCTD M5 zip |
| `WS`   | `/ws/projects/{pid}` | per-project event stream |
| `GET`  | `/metrics` | Prometheus text |

## Curl examples

### Login

```bash
curl -X POST http://localhost:8765/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"alice@example.com","password":"secret"}'
```

### Create a project

```bash
TOKEN="eyJ..."
curl -X POST http://localhost:8765/api/projects \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"name":"My CSR","principle_id":"ich_e3","language":"en"}'
```

### Spin up an oncology demo

```bash
curl -X POST http://localhost:8765/api/projects/from_sample/oncology \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d '{}'
```

### Generate a DOCX

```bash
curl -X POST http://localhost:8765/api/projects/$PID/export/docx \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"include_compliance_note":true,"include_toc":true,
       "include_appendix_cleansing":true,"include_appendix_analysis":true}'
```

### Trigger a literature search (PubMed)

```bash
curl -X POST http://localhost:8765/api/projects/$PID/literature_search \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"query":"pembrolizumab NSCLC overall survival","max_results":5}'
```

## Python (httpx)

```python
import httpx

base = "http://localhost:8765"
async with httpx.AsyncClient(base_url=base) as cx:
    r = await cx.post("/api/auth/login",
                      json={"email": "alice@example.com",
                            "password": "secret"})
    token = r.json()["access_token"]

    hdr = {"Authorization": f"Bearer {token}"}
    r = await cx.get("/api/projects", headers=hdr)
    print(r.json())

    r = await cx.post(f"/api/projects",
                      headers=hdr,
                      json={"name": "My CSR",
                            "principle_id": "ich_e3"})
    pid = r.json()["id"]

    r = await cx.post(f"/api/projects/{pid}/report/generate",
                      headers=hdr,
                      json={"limit": 5})
    print(r.json())
```

Or use the auto-generated SDK in `sdk/py/`:

```python
from autocsr_sdk import ApiClient, Configuration
cfg = Configuration(host="http://localhost:8765", access_token=token)
api = ApiClient(cfg)
projects = api.list_projects()
```

## TypeScript (fetch + the generated SDK)

```ts
import { OpenAPI, AuthService, ProjectsService } from '@/sdk/ts'

OpenAPI.BASE = 'http://localhost:8765'
const tokens = await AuthService.login({ requestBody: {
  email: 'alice@example.com', password: 'secret',
}})
OpenAPI.TOKEN = tokens.access_token

const projects = await ProjectsService.listProjects()
console.log(projects)

const job = await ProjectsService.exportFormat({
  pid: projects[0].id, format: 'pdf',
  requestBody: { include_compliance_note: true },
})
console.log(`Generated ${job.filename} (${job.size_bytes} B)`)
```

## WebSocket events

Subscribe to `ws://<host>:<port>/ws/projects/{pid}`. Each frame is JSON:

```json
{"type":"writer.progress","payload":{"node_id":"11.4.2","leaves_done":4,"leaves_total":12}}
{"type":"export.pdf.done","payload":{"filename":"csr_2026-05-23.pdf"}}
```

Common event types: `ingest.*`, `cleansing.*`, `analysis.*`,
`outline.*`, `writer.*`, `harmonize.*`, `export.<fmt>.*`,
`ectd.*`, `signatures.*`, `audit.append`.

## Rate limits

Heavy endpoints (`/upload`, `/ingest`, `/ask`, `/report/generate`,
`/export/*`) are rate-limited per-tenant via `app.server.middlewares.rate_limit`.
Default: 30 requests / minute / tenant. `HTTP 429` is returned with a
`Retry-After` header.

## Errors

All errors are JSON of shape:

```json
{"detail": "human readable",
 "code": "sign_chain_out_of_order",
 "params": {"required_role": "medical"}}
```

The frontend maps `code` to a localised toast via
`src/utils/errors.ts`. New codes can be added there.
