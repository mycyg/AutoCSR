# AutoCSR — deployment guide

This guide covers the supported topologies:

- **Single-node Docker Compose** (most installs)
- **Local venv + npm** (dev / debugging)
- **Behind Nginx with TLS**
- **Backup & restore**

## 1. Single-node Docker Compose

The repo ships a `docker-compose.yml` that stands up:

| Service | Image | Port |
|---|---|---|
| `backend` | `autocsr-backend:v2.x` (multi-stage Python 3.11 slim) | 8765 |
| `worker` | same image, runs `python -m app.queue.arq_app` | — |
| `frontend` | `autocsr-frontend:v2.x` (nginx + Vite build) | 5174 |
| `redis` | `redis:7-alpine` | 6379 |
| `prometheus` (optional) | `prom/prometheus:latest` | 9090 |

```bash
# clone + cd
git clone https://github.com/your-org/AutoCSR.git
cd AutoCSR

# Put your LLM key + auth secret in env (or a .env file next to compose).
export AUTOCSR_LLM_API_KEY="sk-..."
export AUTOCSR_JWT_SECRET="$(openssl rand -hex 32)"
export AUTOCSR_TZ="Asia/Shanghai"

docker compose up -d --build
```

The first build is slow (~5 minutes) because the backend image carries
pyreadstat / lifelines / matplotlib / reportlab. Subsequent rebuilds
hit the layer cache.

Open <http://localhost:5174>. Register a new user — the first user in
a fresh DB is auto-elevated to `admin` of a brand-new tenant.

### Volumes

| Path inside container | Host mount | Holds |
|---|---|---|
| `/app/data` | `./data` | project data, audit, signatures |
| `/app/backend/app/config` | `./backend/app/config` | `settings.yaml` |

The redis container has no volume by default — the queue is for
transient task state. Add one if you want zero loss on restart.

## 2. Local dev (venv + npm)

```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.server.main:app --reload --port 8765

# Frontend (separate shell)
cd frontend && npm install
npm run dev          # vite hot-reload on :5173
# or for production-like preview:
npm run build && npm run preview -- --port 5174
```

Set `settings.queue.backend=inmemory` to skip Redis during dev. Set
`settings.auth.dev_mode=true` to use `X-User-Id` instead of JWT.

## 3. Nginx + TLS

A minimal reverse-proxy config that fronts both backend and frontend
on the same domain:

```nginx
upstream autocsr_backend  { server 127.0.0.1:8765; }
upstream autocsr_frontend { server 127.0.0.1:5174; }

server {
    listen 80;
    server_name csr.example.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name csr.example.com;

    ssl_certificate     /etc/letsencrypt/live/csr.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/csr.example.com/privkey.pem;

    client_max_body_size 200M;       # SAS / Excel uploads
    proxy_read_timeout   600s;       # long export jobs

    # Frontend static assets
    location / {
        proxy_pass http://autocsr_frontend;
        proxy_set_header Host $host;
    }

    # Backend REST + OpenAPI
    location /api/ {
        proxy_pass http://autocsr_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-Proto https;
    }

    # WebSocket upgrade
    location /ws/ {
        proxy_pass http://autocsr_backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 24h;
    }

    # Prometheus (lock down with allow/deny if exposed)
    location = /metrics {
        proxy_pass http://autocsr_backend/metrics;
        allow 10.0.0.0/8;
        deny all;
    }
}
```

## 4. Environment variables

All variables read by the backend bootstrap:

| Var | Default | Purpose |
|---|---|---|
| `AUTOCSR_DATA_DIR` | `./data` | base path for project files |
| `AUTOCSR_LLM_API_KEY` | — | overrides `settings.llm.primary.api_key` |
| `AUTOCSR_JWT_SECRET` | random ephemeral | **set in production** — invalidates all sessions if changed |
| `AUTOCSR_TZ` | `Asia/Shanghai` | default project timezone |
| `AUTOCSR_REDIS_URL` | `redis://redis:6379/0` | arq backend |
| `AUTOCSR_LOG_LEVEL` | `INFO` | uvicorn + structlog |
| `AUTOCSR_RATE_LIMIT_RPM` | `30` | per-tenant RPM ceiling |
| `AUTOCSR_AUDIT_ROTATE_MB` | `100` | per-file rotation threshold |

## 5. Backup & restore

Project-level zip backups (data + audit + signatures) are first-class:

```bash
# Trigger a backup over REST
curl -X POST http://localhost:8765/api/projects/$PID/backup \
  -H "Authorization: Bearer $TOKEN" -o my_csr_backup.zip

# Restore into a new project
curl -X POST http://localhost:8765/api/projects/restore \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@my_csr_backup.zip"
```

For full disaster recovery also snapshot:

- `data/` — all tenants
- `backend/app/config/settings.yaml` — auth secret, LLM keys
- `data/auth/users.json` — user accounts
- Redis dump (optional; only needed if you can't tolerate in-flight task loss)

A `cron` example for nightly tar snapshots:

```cron
0 2 * * * cd /opt/AutoCSR && \
  tar -czf /backups/autocsr-$(date +\%F).tgz \
  data backend/app/config/settings.yaml >> /var/log/autocsr-backup.log 2>&1
```

## 6. Production Redis note

`docker-compose.yml`'s redis is a stock alpine image with no AOF.
For real deployment:

- Pin a version (`redis:7.2.4-alpine`).
- Enable `--appendonly yes` and mount `/data`.
- Set `requirepass` and update `AUTOCSR_REDIS_URL` to
  `redis://:password@host:6379/0`.
- Place redis on the same VPC as backend; latency dominates queue
  throughput.

## 7. Health checks

| Path | Purpose |
|---|---|
| `GET /api/health` | liveness — returns `{"status":"ok"}` |
| `GET /api/health/deps` | dependencies — checks redis, disk, LLM probe |
| `GET /metrics` | Prometheus text |

A trivial uptime probe:

```bash
curl -fsS http://localhost:8765/api/health || systemctl restart autocsr-backend
```
