# RVTool Genesis — Operations Guide

> **Who this is for:** The person who installs, configures, and maintains
> the RVTool Genesis instance on their Mac.
>
> **Related guides:** [User Guide](USER_GUIDE.md) · [README](../README.md)

---

## Table of Contents

1. [System requirements](#1-system-requirements)
2. [Installation](#2-installation)
3. [Environment variables](#3-environment-variables)
4. [Docker services](#4-docker-services)
5. [Makefile reference](#5-makefile-reference)
6. [LLM provider configuration](#6-llm-provider-configuration)
7. [Security hardening](#7-security-hardening)
8. [Upgrading](#8-upgrading)
9. [Database operations](#9-database-operations)
10. [API documentation](#10-api-documentation)

---

## 1. System requirements

| Component | Requirement | Notes |
|---|---|---|
| **OS** | macOS (Apple Silicon or Intel) | Tested on macOS 13+. Linux should work but is not tested. |
| **Container runtime** | OrbStack (recommended) or Docker Desktop 4.x+ | OrbStack is faster and uses less memory. Free for personal use. |
| **Ollama** | Required only for Ollama LLM provider | Not needed if using watsonx.ai, OpenAI, or Anthropic. |
| **RAM** | 8 GB minimum | 16 GB recommended if running Ollama alongside containers. |
| **Disk** | 5 GB minimum free | PostgreSQL data volume + container images. phi4-mini model adds ~2.5 GB. |
| **Network** | Internet for cloud LLM providers | Ollama works fully offline. |

---

## 2. Installation

### Clone and run

```bash
git clone <repo-url>
cd RVTool_Genesis
chmod +x setup.sh       # only needed once after cloning
./setup.sh
```

### What `setup.sh` does

1. Checks that Docker (or OrbStack) is running
2. Checks that Ollama is running (if Ollama is the configured provider)
3. Pulls the `phi4-mini` model if not already available locally
4. Creates a `.env` file from `.env.example` if one doesn't exist
5. Runs `docker compose up --build -d` to build and start all containers
6. Waits for the health check on the database container to pass
7. Runs `alembic upgrade head` to apply any pending database migrations
8. Opens `http://localhost:3001` in your browser when all services are ready

> **Subsequent starts:** `./setup.sh` is safe to run at any time. It is idempotent —
> running it again will rebuild containers if image files changed and apply any
> new migrations, but will not wipe data.

---

## 3. Environment variables

All variables live in `.env` at the repo root. The file is created automatically
by `setup.sh` from `.env.example`. You only need to edit it to override defaults.

| Variable | Required | Default | Description | Security note |
|---|---|---|---|---|
| `SECRET_KEY` | **Yes** | *(weak default — blocked)* | AES-256 Fernet key for encrypting cloud LLM API keys in PostgreSQL. **The API refuses to start if this is set to the default or is shorter than 32 characters.** | Generate with `make generate-secret`. Rotate by re-entering cloud keys in Settings after changing. |
| `OLLAMA_BASE_URL` | No | `http://host.docker.internal:11434` | Ollama endpoint reached from inside containers. | — |
| `OLLAMA_MODEL` | No | `phi4-mini` | Ollama model for normalization. | — |
| `DMR_BASE_URL` | No | `http://host.docker.internal:9545` | Docker Model Runner endpoint (Docker Desktop ≥ 4.25). | — |
| `DMR_MODEL` | No | *(empty)* | Docker Model Runner model name, e.g. `ai/phi4-mini`. | — |
| `HF_TOKEN` | No | *(empty)* | HuggingFace token — higher rate limits for GGUF resolver. | — |
| `API_TOKEN` | No | *(empty — enforcement disabled)* | Bearer token for API authentication. When empty, all endpoints are open (home-network default). When set, every request must include `Authorization: Bearer <token>`. | Generate with `openssl rand -hex 32`. Also set `VITE_API_TOKEN` when rebuilding the frontend. |
| `ALLOWED_ORIGINS` | No | `http://localhost:3001` | Comma-separated list of CORS origins the browser may request from. Add your machine's IP for non-localhost demos: `http://localhost:3001,http://192.168.1.x:3001`. | — |
| `DATABASE_URL` | No | `postgresql://rvtool:rvtool_password@db:5432/rvtooldb` | PostgreSQL connection string used by the API container. | Internal only — DB port is not exposed to host network. |
| `POSTGRES_DB` | No | `rvtooldb` | PostgreSQL database name. | — |
| `POSTGRES_USER` | No | `rvtool` | PostgreSQL user. | — |
| `POSTGRES_PASSWORD` | No | `rvtool_password` | PostgreSQL password. | Change before any network-accessible deployment. |

### Generating a strong SECRET_KEY

```bash
make generate-secret
```

This prints a ready-to-paste `.env` line:
```
SECRET_KEY=af65ef2e010953cc...
```

Paste that line into your `.env` file, then rebuild the API container:
```bash
docker compose up --build -d api
```

> **Warning:** Changing `SECRET_KEY` after cloud API keys have been stored in the
> database will make those keys unreadable. Re-enter them in the Settings page after
> any key rotation.

---

## 4. Docker services

The application is three containers managed by Docker Compose.

### Services

| Service | Container name | Host port | Container port | Description |
|---|---|---|---|---|
| `web` | `rvtool_genesis-web-1` | **3001** | 3000 | React + Carbon Design System UI |
| `api` | `rvtool_genesis-api-1` | **8001** | 8000 | FastAPI (Python 3.12) + Alembic |
| `db` | `rvtool_genesis-db-1` | *(none — internal only)* | 5432 | PostgreSQL 16 |

### Startup order

`db` must be healthy before `api` starts (enforced by `depends_on` with
`condition: service_healthy`). `web` starts after `api` is up.

The `api` container runs `alembic upgrade head` on every startup before launching
uvicorn. This means schema migrations apply automatically on restart.

### Restart policy

All services have `restart: unless-stopped`. They will automatically restart after
a crash or OrbStack/Docker restart, but not after a `docker compose down`.

### Volume durability

The PostgreSQL data lives in a **named Docker volume** `postgres_data`:
```
/var/lib/postgresql/data → postgres_data volume
```

This volume persists across:
- Container restarts
- `docker compose down` / `docker compose up`
- OrbStack crashes or version upgrades
- Mac reboots

The volume is **only destroyed** by `docker compose down -v`. Do not run this
unless you intend to wipe all project data.

### Health check

The `db` service exposes a `pg_isready` health check:
- Interval: 5 s
- Timeout: 5 s
- Retries: 10 (50 s maximum wait)
- Start period: 10 s

If the health check fails, `docker compose ps` will show `db` as `unhealthy`.
Check `docker compose logs db` for PostgreSQL startup errors.

---

## 5. Makefile reference

Run any make target from the repo root.

| Command | What it does |
|---|---|
| `make generate-secret` | Generates a strong `SECRET_KEY` and prints the `.env` line |
| `make setup` | Runs `./setup.sh` (full startup with health checks) |
| `make up` | `docker compose up --build` — builds and starts all services in foreground |
| `make up-d` | `docker compose up --build -d` — builds and starts in background (detached) |
| `make down` | `docker compose down` — stops and removes containers (data volume preserved) |
| `make logs` | `docker compose logs -f` — tails logs from all services |
| `make migrate` | Runs `alembic upgrade head` inside the running API container |
| `make test` | Runs the full test suite inside the API container (`pytest /tests/ -v`) |
| `make typecheck` | Runs TypeScript typecheck (`tsc --noEmit`) in the `web/` directory |
| `make lint` | Runs Ruff Python linter against API source files |
| `make shell-api` | Opens a bash shell inside the API container |
| `make shell-db` | Opens a `psql` shell in the database container |

---

## 6. LLM provider configuration

All four providers are configured in the Settings page (`http://localhost:3001/settings`).
API keys are encrypted with AES-256 Fernet before being stored in PostgreSQL.

### Ollama (local — default)

No API key required. Ollama must be installed and running on your Mac.

```bash
# Install Ollama from https://ollama.com then:
ollama pull phi4-mini          # ~2.5 GB download
ollama serve                   # ensure Ollama is running
```

Verify from inside the API container:
```bash
make shell-api
curl http://host.docker.internal:11434/api/tags
```

**Model recommendations:** The default `phi4-mini` is recommended for a balance
of speed and accuracy. Larger models (`phi4`, `llama3.1:8b`) improve accuracy
for complex OS mappings but are slower.

---

### IBM watsonx.ai ⭐ (recommended for IBM engagement work)

1. Log in to [cloud.ibm.com](https://cloud.ibm.com)
2. **Manage → Access (IAM) → API keys** → Create an API key with `ML Platform` scope
3. Open your watsonx.ai project → **Manage → General** → copy the **Project ID**
4. In Settings, select **IBM watsonx.ai**, enter the API key and Project ID
5. Set the endpoint URL (default: `https://us-south.ml.cloud.ibm.com`)
6. Click **Test connection** to verify credentials before saving

**IAM token caching:** A Bearer token is obtained once and cached for 50 minutes.
IAM is called once per normalization run, not once per server record.

**Recommended models:**
- `ibm/granite-3-8b-instruct` — default, fast and accurate
- `ibm/granite-3-2b-instruct` — faster, slightly less accurate
- `meta-llama/llama-3-3-70b-instruct` — highest accuracy, slower

---

### OpenAI-compatible

Works with OpenAI, Azure OpenAI, local vLLM, and LM Studio.

1. In Settings, select **OpenAI-compatible**
2. Enter your API key
3. Set the base URL:
   - OpenAI: `https://api.openai.com` (default)
   - Azure OpenAI: your Azure endpoint
   - Local vLLM / LM Studio: `http://host.docker.internal:PORT`
4. Set the model name (default: `gpt-4o-mini`)
5. Click **Test connection**

---

### Anthropic

1. In Settings, select **Anthropic**
2. Enter your Anthropic API key from [console.anthropic.com](https://console.anthropic.com)
3. Set the model (default: `claude-3-haiku-20240307` — fastest and cheapest)
4. Click **Test connection**

---

## 7. Security hardening

### Before using cloud LLM providers

1. **Generate a strong `SECRET_KEY`** — run `make generate-secret`, paste the output
   into `.env`, then rebuild: `docker compose up --build -d api`
2. Re-enter cloud API keys in the Settings page

### Network exposure

By default, all services bind to `127.0.0.1` (localhost only). The PostgreSQL
database has **no host-network port** — it is only reachable within the internal
Docker bridge network. **Do not expose ports 3001 or 8001 to external networks**
without enabling API authentication.

#### Optional bearer-token authentication (`API_TOKEN`)

Set `API_TOKEN` in `.env` to a strong random value to require bearer-token
authentication on every API request:

```bash
# Generate a token (same tool as SECRET_KEY):
make generate-secret

# Add to .env:
API_TOKEN=<generated-value>

# Restart the API:
docker compose up --build -d api
```

Once set, every request must include the header:

```
Authorization: Bearer <API_TOKEN>
```

Leave `API_TOKEN` unset (the default) for home-network use — the API runs open,
identical to the previous behaviour.

#### Remote access from other machines

For network-accessible demos where `API_TOKEN` is set:

- Set `ALLOWED_ORIGINS` in `.env` to the origin of the accessing machine, e.g.
  `ALLOWED_ORIGINS=http://192.168.1.42:3001`
- Multiple origins: comma-separated, e.g.
  `ALLOWED_ORIGINS=http://localhost:3001,http://192.168.1.42:3001`
- For stricter perimeter control, add a reverse proxy (Nginx/Caddy) with TLS
  in front of the web container

### API key storage

- Cloud provider API keys (watsonx, OpenAI, Anthropic) are encrypted with
  AES-256 Fernet before storage in PostgreSQL
- Keys are **never logged** at any log level
- Keys are **never returned** in plaintext from any API endpoint
- Only a masked hint (`••••••••abcd`) is displayed in the Settings UI

### PostgreSQL password

Change `POSTGRES_PASSWORD` in `.env` from the default `rvtool_password` before
any network-accessible deployment. The `api` container's `DATABASE_URL` must
match.

---

## 8. Upgrading

### Pull latest changes

```bash
git pull origin main
./setup.sh
```

`setup.sh` rebuilds all container images with the latest code and runs
`alembic upgrade head` automatically to apply any new database migrations.

### Manual migration only

If you need to apply migrations without rebuilding images:
```bash
make migrate
```

### Rolling back a migration

```bash
make shell-api
alembic downgrade -1      # roll back one migration
# or
alembic downgrade <revision_id>
```

List available revisions:
```bash
alembic history --verbose
```

### Checking the current migration state

```bash
make shell-api
alembic current
```

---

## 9. Database operations

### Connecting directly (psql)

```bash
make shell-db
# or equivalently:
docker compose exec db psql -U rvtool -d rvtooldb
```

### Key tables

| Table | Description |
|---|---|
| `projects` | Project names, descriptions, VPC region, PowerVS region/datacenter |
| `folders` | Hierarchical folder records (max depth 2) |
| `uploads` | Raw uploaded file bytes + parser metadata |
| `server_records` | JSONB: raw_data, normalized_data, server_type, is_excluded |
| `assumptions` | Per-record AI inference log (field, value, reasoning, confidence) |
| `rvtools_exports` | Generated RVTools .xlsx blobs + metadata |
| `assumptions_exports` | Generated Assumptions Report .xlsx blobs |
| `pricing_templates` | Stored IBM Price Estimator .xlsx per project |
| `llm_settings` | Single-row table: active provider, encrypted API keys, model names |
| `audit_log` | Append-only event log: project, action, target record, actor, timestamp, detail JSON |
| `processing_jobs` | Durable job queue: one row per normalization run; status, progress counters, cancel flag |

### Checking database size

```bash
make shell-db
SELECT pg_size_pretty(pg_database_size('rvtooldb'));
```

### Backing up the PostgreSQL volume

For a full volume-level backup (separate from the project JSON backup/restore
feature in the UI):

```bash
docker run --rm \
  -v rvtoolgenesis_postgres_data:/data \
  -v $(pwd):/backup \
  alpine tar czf /backup/postgres_backup_$(date +%Y%m%d).tar.gz /data
```

Restore by stopping the DB container, removing the volume, and extracting the archive.

---

## 10. API documentation

The FastAPI application exposes interactive Swagger documentation at:

```
http://localhost:8001/api/docs
```

ReDoc (alternative view) is at:
```
http://localhost:8001/api/redoc
```

### Key endpoint groups

| Prefix | Description |
|---|---|
| `GET/POST /api/projects` | Project CRUD, region settings |
| `GET/POST /api/folders` | Folder CRUD, move projects |
| `POST /api/projects/{id}/uploads` | File upload + parse |
| `GET /api/projects/{id}/records` | Fetch normalized records |
| `PATCH /api/projects/{id}/records/{rid}` | Edit a normalized record inline |
| `PATCH /api/records/{rid}/exclude` | Toggle exclusion + set reason |
| `POST /api/projects/{id}/bulk-os-replace` | Bulk OS replacement |
| `GET /api/projects/{id}/nxf-unsupported-count` | Count nxf-1x* records |
| `POST /api/projects/{id}/bulk-nxf-replace` | Upgrade nxf-1x* profiles |
| `POST /api/projects/{id}/process` | Start AI normalization (durable job queue) |
| `GET /api/projects/{id}/processing/status` | Normalization progress |
| `POST /api/projects/{id}/processing/cancel` | Request graceful cancellation |
| `POST /api/projects/{id}/processing/reset-stuck` | Reset orphaned records + archive stale job |
| `GET /api/projects/{id}/readiness-summary` | Migration Readiness Summary (Export page banner) |
| `GET /api/projects/{id}/audit-log` | 50 most recent audit log entries |
| `POST /api/projects/{id}/export/vpc-calculator` | Generate Cloud Solution Export (x86) |
| `POST /api/projects/{id}/export/rvtools` | Generate RVTools 22-sheet (x86) |
| `POST /api/projects/{id}/export/rvtools-pure` | Generate RVTools 4-sheet (x86) |
| `POST /api/projects/{id}/export/assumptions` | Generate AI Assumptions Report (x86) |
| `POST /api/projects/{id}/export/powervs-calculator` | Generate PowerVS Cloud Solution Export |
| `POST /api/projects/{id}/export/rvtools-powervs` | Generate PowerVS Cool Tool Export (4-sheet) |
| `POST /api/projects/{id}/export/rvtools-powervs-full` | Generate PowerVS RVTools (22-sheet) |
| `POST /api/projects/{id}/export/assumptions-powervs` | Generate PowerVS Assumptions Report |
| `POST /api/projects/{id}/pricing-template` | Upload IBM Price Estimator template |
| `GET /api/projects/{id}/pricing-template/status` | Template upload status |
| `POST /api/projects/{id}/export/pricing-estimator` | Populate + download filled template |
| `GET /api/projects/{id}/backup` | Download single-project backup |
| `GET /api/backup/all` | Download full system backup .zip |
| `POST /api/restore` | Restore from .json or .zip backup |
| `GET/POST /api/settings` | LLM provider settings |
| `POST /api/settings/test` | Test LLM connection |
| `GET /api/settings/model-recommendation` | Check for model upgrade recommendation |
| `POST /api/settings/model-recommendation/apply` | Apply recommended model |
| `POST /api/settings/model-recommendation/rollback` | Roll back to previous model |
| `POST /api/settings/model-recommendation/snooze` | Snooze recommendation for 7 days |
