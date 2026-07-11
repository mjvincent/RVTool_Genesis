# RVTool Genesis — Project Plan

## Top-Level Overview

Build a containerized, full-stack web application that:
1. Accepts a **freeform customer-produced spreadsheet** (virtual or bare metal server inventory)
2. Uses **Ollama (local LLM, gemma4)** running natively on the host Mac to parse, normalize, and fill in missing data — **no API key required, no cloud, data never leaves the machine**
3. Generates a **standards-compliant RVTools `.xlsx` export** (4 tabs: vInfo, vNetwork, vPartition, vHost) consumable by the IBM Cool tool
4. Produces a separate **Assumptions document** capturing every AI-inferred decision
5. Persists all projects and work sessions in a **local PostgreSQL database**
6. Presents a **Carbon Design System** React UI
7. Runs entirely via **Docker Compose on OrbStack**

### Target RVTools Schema (from sample: `SizingWorkshop-RVTools.xlsx`)

| Tab | Key Columns |
|---|---|
| vInfo | VM, Powerstate, Template, CPUs, Memory (MB), NICs, Disks, Provisioned MB, In Use MB, Datacenter, Cluster, Host, OS (config), OS (VMware Tools) |
| vNetwork | VM, Powerstate, Template, SRM Placeholder, NIC label, Adapter, Network, Switch, Connected, Starts Connected, Mac Address, Type, IPv4 Address, IPv6 Address, Direct Path IO, Internal Sort Column, Annotation |
| vPartition | VM, Powerstate, Template, Disk, Capacity MB, Consumed MB, Free MB, Free %, Datacenter, Cluster, Host, OS (config), OS (VMware Tools) |
| vHost | Host, Datacenter, Cluster, Config status, CPU Model, Speed, HT Available, HT Active, # CPU, Cores per CPU, # Cores, CPU usage %, # Memory, Memory usage %, Console, # NICs, # HBAs, # VMs, VMs per Core, # vCPUs, vCPUs per Core, vRAM, VM Used memory, VM Memory Swapped, VM Memory Ballooned, ESX Version, Vendor, Model |

### Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React 18 + IBM Carbon Design System v11 |
| Backend API | Python 3.12 + FastAPI |
| AI Layer | Ollama (gemma4, native macOS service) via `httpx` HTTP calls to `host.docker.internal:11434` |
| Spreadsheet I/O | `pandas` + `openpyxl` |
| Database | PostgreSQL 16 |
| ORM + Migrations | SQLAlchemy 2.x + Alembic |
| Container Runtime | Docker Compose on OrbStack |
| API Docs | FastAPI auto-generated Swagger at `/api/docs` |

---

## Sub-Task 1 — Project Scaffolding and Docker Compose Stack

**Status:** [x] complete

### Intent
Establish the repository structure, Docker Compose configuration, and all service skeletons so every subsequent sub-task has a working local dev environment to build into.

### Expected Outcomes
- `docker compose up` starts three services: `db` (PostgreSQL 16), `api` (FastAPI), `web` (React + Carbon)
- Hot-reload works for both frontend and backend in development mode
- A `.env.example` file documents all required environment variables
- The PostgreSQL data volume persists across container restarts
- The API health endpoint `GET /api/health` returns `{"status": "ok"}`
- The React app renders a Carbon shell at `http://localhost:3000`

### Todo List
1. Create top-level directory structure: `api/`, `web/`, `db/`, `samples/`
2. Create `docker-compose.yml` with three services: `db`, `api`, `web`
3. Create `docker-compose.override.yml` for development mounts and hot-reload
4. Create `api/Dockerfile` (Python 3.12 slim, installs requirements)
5. Create `web/Dockerfile` (Node 20 slim, React dev server)
6. Create `db/init.sql` for any initial DB setup beyond Alembic migrations
7. Create `.env.example` with: `ANTHROPIC_API_KEY`, `DATABASE_URL`, `POSTGRES_*` vars
8. Create `.gitignore` excluding `.env`, `__pycache__`, `node_modules`, `*.pyc`
9. Scaffold `api/main.py` with FastAPI app, CORS config, and `/api/health` route
10. Scaffold `web/` with `create-react-app` or Vite + TypeScript template
11. Install Carbon Design System: `@carbon/react`, `@carbon/icons-react`
12. Verify `docker compose up` starts all three services cleanly

### Relevant Context
- OrbStack is the Docker runtime — standard Docker Compose syntax applies
- Use named volume `postgres_data` for DB persistence
- Backend port: 8000, Frontend port: 3000, DB port: 5432
- ANTHROPIC_API_KEY must never be committed — enforce via `.gitignore`

---

## Sub-Task 2 — Database Schema and Migrations

**Status:** [x] complete

### Intent
Define the PostgreSQL data model that stores projects, uploaded spreadsheets, parsed server records, generated outputs, and assumptions. Use Alembic for versioned migrations.

### Expected Outcomes
- Running `alembic upgrade head` inside the `api` container creates all tables
- All tables are created with correct types, foreign keys, and indexes
- The schema supports re-runs: uploading a new file to an existing project replaces/appends records

### Todo List
1. Install SQLAlchemy 2.x + Alembic + `psycopg2-binary` in `api/requirements.txt`
2. Create `api/db/models.py` with the following tables:
   - **`projects`**: `id`, `name`, `description`, `created_at`, `updated_at`
   - **`uploads`**: `id`, `project_id` (FK), `filename`, `raw_file` (bytea), `uploaded_at`, `status` (enum: pending/processing/complete/error)
   - **`server_records`**: `id`, `upload_id` (FK), `project_id` (FK), `raw_data` (JSONB), `normalized_data` (JSONB), `server_type` (vm/bare_metal), `created_at`
   - **`assumptions`**: `id`, `server_record_id` (FK), `project_id` (FK), `field_name`, `assumed_value`, `reasoning`, `confidence` (low/medium/high), `created_at`
   - **`rvtools_exports`**: `id`, `project_id` (FK), `generated_at`, `file_data` (bytea), `status`
3. Create `api/db/database.py` with SQLAlchemy engine and session factory
4. Initialize Alembic: `alembic init alembic`
5. Configure `alembic/env.py` to use models metadata and `DATABASE_URL` from env
6. Generate and run first migration: `alembic revision --autogenerate -m "initial schema"`
7. Add migration step to Docker Compose entrypoint so migrations run on startup

### Relevant Context
- `raw_data` (JSONB) stores the original unparsed row from the customer spreadsheet
- `normalized_data` (JSONB) stores the Claude-mapped RVTools-compatible record
- `assumptions` are 1:many per server_record — one row per inferred field
- PostgreSQL JSONB allows querying into freeform customer data without schema changes

---

## Sub-Task 3 — Spreadsheet Upload and Raw Parsing API

**Status:** [x] complete

### Intent
Build the backend API endpoints for project management and spreadsheet file upload. Parse the uploaded `.xlsx` or `.csv` file into raw row objects stored as JSONB in the database — no AI yet, just structural parsing.

### Expected Outcomes
- `POST /api/projects` creates a new project
- `GET /api/projects` lists all projects
- `GET /api/projects/{id}` returns project detail with upload history
- `POST /api/projects/{id}/uploads` accepts a multipart file upload (`.xlsx`, `.csv`, `.xls`)
- The uploaded file is parsed into rows and each row is stored as a `server_record` with `raw_data` populated
- `GET /api/projects/{id}/records` returns all raw server records for a project

### Todo List
1. Create `api/routers/projects.py` with CRUD endpoints for projects
2. Create `api/routers/uploads.py` with file upload endpoint
3. Create `api/services/spreadsheet_parser.py` using `pandas` + `openpyxl` to:
   - Detect file type (.xlsx, .xls, .csv)
   - Auto-detect header row (handle files where row 1 may be a title, not headers)
   - Return a list of dicts (one per row) with original column names preserved
4. Store each parsed row as a `server_record` with `raw_data` = original dict, `normalized_data` = null, `status` = pending
5. Create `api/schemas/` with Pydantic models for request/response validation
6. Add file size limit (50MB max) and type validation
7. Write basic integration tests for upload and parse flow

### Relevant Context
- Customer spreadsheets are freeform — column names will vary widely
- The parser must handle merged cells, blank rows, and multi-sheet workbooks gracefully
- Use pandas `read_excel` with `header='infer'` and fallback logic for messy files
- Store the raw file bytes in `uploads.raw_file` for re-processing without re-upload

---

## Sub-Task 4 — Claude AI Normalization and Assumption Engine

**Status:** [x] complete

### Intent
Build the core AI processing pipeline. For each `server_record` with raw data, call the Claude API to map customer columns to RVTools schema fields, fill in missing values using intelligent defaults, and generate structured assumptions for every inferred decision.

### Expected Outcomes
- `POST /api/projects/{id}/uploads/{upload_id}/process` triggers AI normalization as a background task
- Each `server_record.normalized_data` is populated with a complete RVTools-compatible object
- Every AI-inferred or defaulted field generates a corresponding `assumption` row
- The endpoint returns immediately with `{"status": "processing"}` — results poll via `GET /api/projects/{id}/records`
- Network config assumptions (subnet, gateway, security groups) are generated at the project level

### Todo List
1. Install `anthropic` SDK in `api/requirements.txt`
2. Create `api/services/ai_normalizer.py` with:
   - A structured prompt that provides Claude with: the raw row data, the target RVTools schema, and instructions to return a strict JSON object with two keys: `normalized` (the mapped record) and `assumptions` (list of {field, value, reasoning, confidence})
   - Field mapping logic: CPU count, memory (convert GB/TB to MB), disk size (convert to MB), OS normalization, power state inference
   - Network inference: if IP is provided map it; if not, generate a placeholder with assumption; infer subnet mask, gateway from IP range patterns
   - Bare metal vs VM detection based on keywords in server name or type column
3. Create `api/services/network_inference.py` for standard network config defaults:
   - Default subnet: /24 unless specified
   - Gateway: first host in subnet (.1) as assumption
   - NIC adapter type: Vmxnet3 for VMs, E1000e for bare metal (assumption)
   - Security group: "default" with assumption noted
4. Create FastAPI background task that processes all pending records for an upload
5. Store assumptions with confidence levels: high (directly mapped), medium (inferred from context), low (pure default)
6. Add `GET /api/projects/{id}/assumptions` endpoint returning all assumptions for a project

### Relevant Context
- Claude model: `claude-3-5-sonnet-20241022` (best balance of speed and accuracy)
- The prompt must include the exact RVTools column names from the sample file as the target schema
- Memory values in RVTools are in MB — customer data may use GB, TB, or unitless numbers; Claude must normalize
- Provisioned MB vs In Use MB: if only total storage is given, assume In Use = 80% of Provisioned (document as assumption)
- vHost tab: for VMs, synthesize a representative host record; for bare metal, the server IS the host

---

## Sub-Task 5 — RVTools XLSX Export Generation

**Status:** [x] complete

### Intent
Build the export service that takes all normalized server records for a project and generates a standards-compliant RVTools `.xlsx` file with the exact 4-tab structure (vInfo, vNetwork, vPartition, vHost) that the IBM Cool tool expects.

### Expected Outcomes
- `POST /api/projects/{id}/export` generates an RVTools `.xlsx` and stores it in `rvtools_exports`
- `GET /api/projects/{id}/exports/{export_id}/download` streams the file for download
- The generated file matches the column structure of `SizingWorkshop-RVTools.xlsx` exactly
- Multi-disk servers generate multiple rows in `vPartition` (one per disk/partition)
- Multi-NIC servers generate multiple rows in `vNetwork` (one per NIC)

### Todo List
1. Create `api/services/rvtools_generator.py` using `openpyxl` to:
   - Create a workbook with 4 sheets in order: vInfo, vNetwork, vPartition, vHost
   - Write exact headers matching the sample file schema for each sheet
   - Map normalized_data fields to correct columns for each sheet
   - Handle 1:many expansion: one server with 3 disks = 3 vPartition rows
   - Handle 1:many expansion: one server with 2 NICs = 2 vNetwork rows
   - Apply basic formatting: header row bold, column widths auto-sized
2. Create `POST /api/projects/{id}/export` endpoint that:
   - Fetches all complete normalized records for the project
   - Calls the generator service
   - Stores the resulting bytes in `rvtools_exports.file_data`
3. Create `GET /api/projects/{id}/exports/{export_id}/download` streaming download endpoint
4. Add export history to `GET /api/projects/{id}` response
5. Validate generated file structure matches expected column count per sheet

### Relevant Context
- vInfo: 14 columns (see schema table above)
- vNetwork: 17 columns (see schema table above)
- vPartition: 13 columns (see schema table above)
- vHost: 28 columns (see schema table above)
- Memory in RVTools is always in MB (integers)
- Disk/Partition sizes are always in MB
- Powerstate values: "poweredOn" or "poweredOff" (lowercase camelCase)
- Template column: "False" (string) for real VMs

---

## Sub-Task 6 — Assumptions Export (Separate Document)

**Status:** [x] complete

### Intent
Generate a clean, human-readable Assumptions Report as a separate `.xlsx` file (or an additional tab in the RVTools export that does NOT interfere with Cool tool processing). This documents every AI decision for client review and audit trail.

### Expected Outcomes
- Assumptions are available as a standalone `.xlsx` download (separate from RVTools output)
- The assumptions sheet is clearly labeled and formatted for human review
- Each assumption row identifies: VM name, field that was inferred, the assumed value, the reasoning, and the confidence level
- `GET /api/projects/{id}/assumptions/download` returns the assumptions `.xlsx`

### Todo List
1. Create `api/services/assumptions_generator.py` using `openpyxl` to produce a spreadsheet with columns:
   - VM / Server Name
   - Field Name
   - Assumed Value
   - Original Customer Value (if any)
   - Reasoning
   - Confidence (High / Medium / Low)
   - Timestamp
2. Add a summary sheet tab: total assumptions by confidence level, list of VMs with most assumptions
3. Create `GET /api/projects/{id}/assumptions/download` endpoint
4. Ensure this file is stored separately from the RVTools export in the DB
5. Note: this file is intentionally separate from the RVTools `.xlsx` to avoid interfering with IBM Cool tool parsing

### Relevant Context
- The RVTools file must contain ONLY the 4 canonical tabs (vInfo, vNetwork, vPartition, vHost)
- Adding an extra tab to the RVTools file risks breaking Cool tool parsing — assumptions MUST be a separate document
- Confidence levels map to: High = directly sourced from customer data, Medium = inferred from context/patterns, Low = IBM/industry default applied

---

## Sub-Task 7 — Carbon Design System Frontend

**Status:** [x] complete

### Intent
Build the complete React + Carbon Design System UI that provides the full user workflow: project management, file upload, AI processing status, record review/editing, and export download.

### Expected Outcomes
- Users can create, name, and manage multiple projects
- Drag-and-drop or file picker uploads a customer spreadsheet
- A real-time progress indicator shows AI processing status per record
- A data table shows all normalized server records with inline editing capability
- Assumptions are viewable in a side panel or modal per server record
- Export buttons trigger RVTools and Assumptions downloads
- All UI components use IBM Carbon Design System v11

### Todo List
1. Set up Carbon Design System in the React app:
   - Install `@carbon/react`, `@carbon/icons-react`, `@carbon/styles`
   - Configure Carbon theme (White theme as default)
2. Create page/route structure:
   - `/` — Projects list (Carbon DataTable of projects)
   - `/projects/new` — New project form
   - `/projects/:id` — Project detail page (main workspace)
   - `/projects/:id/review` — Record review and editing table
3. Build `ProjectsPage` component with Carbon DataTable listing all projects
4. Build `ProjectDetailPage` as the main workspace:
   - FileUploader (Carbon FileUploader component) for spreadsheet intake
   - InlineLoading / ProgressIndicator for AI processing status
   - Summary statistics (total VMs, assumptions count, export readiness)
5. Build `RecordsReviewTable` component:
   - Carbon DataTable with sortable/filterable columns
   - Inline edit support for key fields (VM name, CPU, memory, OS)
   - Expandable row showing raw customer data vs normalized data side-by-side
   - Assumption badge per row showing count of assumptions
6. Build `AssumptionsPanel` — right-side panel (Carbon SidePanel) listing all assumptions for selected VM
7. Build `ExportBar` — sticky bottom bar with two action buttons: "Download RVTools (.xlsx)" and "Download Assumptions (.xlsx)"
8. Wire all components to backend API using React Query or SWR for data fetching
9. Add polling logic for processing status (poll every 2s while status = "processing")

### Relevant Context
- Carbon Design System v11 docs: https://carbondesignsystem.com
- Use Carbon's `@carbon/react` package — not the older `carbon-components-react`
- The FileUploader component supports drag-and-drop natively
- DataTable with inline editing requires the `TableToolbar` + `TableBatchActions` pattern
- Use Carbon's `InlineLoading` component for per-record AI processing status

---

## Sub-Task 8 — Integration, End-to-End Testing, and README

**Status:** [x] complete

### Intent
Wire the full pipeline together, validate the end-to-end flow with the sample RVTools file as a reference, and write the developer README so anyone can run the project from scratch.

### Expected Outcomes
- Full flow works: upload customer spreadsheet → AI processes → review records → download RVTools `.xlsx`
- The generated RVTools file passes basic structural validation (correct tabs, correct column count)
- `docker compose up` from a clean clone is the only command needed to run the app
- README covers: prerequisites, setup, environment variables, running locally, and architecture overview

### Todo List
1. Create `tests/test_pipeline.py` with an integration test using the sample `SizingWorkshop-RVTools.xlsx` as input to validate the output structure
2. Create `api/services/validator.py` to validate generated RVTools files: checks sheet names, column counts, data types
3. Write `README.md` covering:
   - Prerequisites (OrbStack / Docker, Anthropic API key)
   - Quick start: `cp .env.example .env` → add API key → `docker compose up`
   - Architecture diagram (text-based)
   - Environment variable reference
   - How to load the sample file for testing
4. Add a `Makefile` with convenience targets: `make up`, `make down`, `make migrate`, `make test`, `make logs`
5. Move sample file to `samples/SizingWorkshop-RVTools.xlsx` in the repo
6. Final smoke test: generate a RVTools export from a simple 3-VM test input and verify all 4 tabs populate correctly

### Relevant Context
- The sample file at `Samples/SizingWorkshop-RVTools.xlsx` is the reference for output validation
- The IBM Cool tool is the downstream consumer — output fidelity to the exact column schema is critical
- The validator should check: sheet names match exactly, column headers match exactly, no extra sheets present

---

## Architecture Summary

```
OrbStack (Docker Compose)
├── web (React + Carbon, :3000)
│   ├── ProjectsPage
│   ├── ProjectDetailPage (FileUploader + ProcessingStatus)
│   ├── RecordsReviewTable (DataTable + inline edit)
│   ├── AssumptionsPanel
│   └── ExportBar
├── api (FastAPI, :8000)
│   ├── /api/projects        — CRUD
│   ├── /api/uploads         — file intake + parsing
│   ├── /api/process         — Claude AI normalization (background)
│   ├── /api/export          — RVTools .xlsx generation
│   ├── /api/assumptions     — assumption retrieval + download
│   └── services/
│       ├── spreadsheet_parser.py   (pandas + openpyxl)
│       ├── ai_normalizer.py        (Anthropic Claude API)
│       ├── network_inference.py    (subnet/gateway defaults)
│       ├── rvtools_generator.py    (openpyxl output)
│       └── assumptions_generator.py
└── db (PostgreSQL 16, :5432)
    ├── projects
    ├── uploads
    ├── server_records (JSONB: raw_data, normalized_data)
    ├── assumptions
    └── rvtools_exports
```

## Key Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| AI Provider | Anthropic Claude (claude-3-5-sonnet) | Consistent with Bob; powerful structured output |
| Assumptions output | Separate .xlsx file (not a tab in RVTools) | Extra tabs break IBM Cool tool parsing |
| Storage for files | PostgreSQL bytea | Keeps everything in one volume, no S3 needed locally |
| AI processing | FastAPI BackgroundTasks | No Redis/Celery needed for this use case |
| Memory/disk units | Always MB in RVTools output | Matches sample file schema exactly |
| vHost for VMs | Synthesized representative host record | Required by Cool tool; VMs must reference a host |

---

## Sub-Task 9 — Swap AI Provider: Anthropic → Ollama (gemma4)

**Status:** [ ] pending

### Intent
Replace the Anthropic Claude SDK with direct HTTP calls to the locally-running Ollama service. The user has Ollama installed natively on macOS with gemma4 already pulled. The Docker containers will reach the host Ollama at `host.docker.internal:11434`. No API key is required — this is the primary motivation for this change.

### Expected Outcomes
- `api/services/ai_normalizer.py` makes HTTP calls to `http://host.docker.internal:11434/api/generate` instead of the Anthropic API
- The `anthropic` Python package is removed from `requirements.txt`
- `api/core/config.py` replaces `anthropic_api_key` with `ollama_base_url` and `ollama_model`
- `.env.example` removes `ANTHROPIC_API_KEY` and adds `OLLAMA_BASE_URL` and `OLLAMA_MODEL`
- `README.md` updated to reflect Ollama as the AI provider — no API key section
- All processing behavior (batching, assumptions, confidence levels) is identical to before
- A clear error message is shown if Ollama is not reachable (connection refused)

### Todo List
1. Edit `api/services/ai_normalizer.py`:
   - Remove `import anthropic` and the `_get_client()` singleton
   - Add `import httpx`
   - Replace `normalize_record()` to POST to `{settings.ollama_base_url}/api/generate` with `{"model": settings.ollama_model, "prompt": ..., "stream": false, "options": {"temperature": 0, "num_predict": 4096}}`
   - Parse `response.json()["response"]` as the model output text
   - Keep `_strip_markdown_fences()` — add `_extract_json()` that finds the first `{` to last `}` in the response (local LLMs sometimes emit a preamble before the JSON)
   - Use `httpx.Client(timeout=120.0)` — local LLMs can be slower than API calls
   - On `httpx.ConnectError`: raise a descriptive `ValueError` telling the user Ollama is not running
   - The system prompt and JSON output format remain identical — just add a concrete example of the full expected JSON shape to help the local model stay on-format
2. Edit `api/core/config.py`:
   - Remove `anthropic_api_key` field
   - Add `ollama_base_url: str = "http://host.docker.internal:11434"`
   - Add `ollama_model: str = "gemma3:4b"` (Ollama's tag for gemma4 — verify: `ollama list` output)
3. Remove `anthropic==0.34.2` from `api/requirements.txt`
4. Update `.env.example`: remove `ANTHROPIC_API_KEY`, add `OLLAMA_BASE_URL=http://host.docker.internal:11434` and `OLLAMA_MODEL=gemma3:4b`
5. Update `README.md`: replace API key prerequisite with "Ollama running with gemma3:4b pulled (`ollama pull gemma3:4b`)"
6. Rebuild containers: `docker compose up --build`
7. Test: process a single record and verify `normalized_data` is populated

### Relevant Context
- Ollama runs at `http://localhost:11434` on the Mac host
- From inside Docker containers on OrbStack/Docker Desktop, the host is reachable at `http://host.docker.internal:11434`
- Ollama's generate API: `POST /api/generate` with body `{"model": "...", "prompt": "...", "stream": false}`
- Response body: `{"response": "...", "done": true, ...}`
- Gemma4 on OrbStack on Apple Silicon (arm64) is fast — typically 5-15 seconds per record
- The model tag in Ollama for gemma4 may be `gemma3:4b` — confirm with `ollama list` before hardcoding

---

## Sub-Task 10 — One-Click Setup Script for End Users

**Status:** [ ] pending

### Intent
Create a `setup.sh` script at the repo root that provides a fully automated, one-click startup experience. An end user should be able to clone the repo, run `./setup.sh`, and have the app open in their browser — with no manual file editing, no terminal commands beyond the one script, and clear guidance if anything is missing.

### Expected Outcomes
- `./setup.sh` is the single command needed to start the full application
- The script validates all prerequisites and gives clear, actionable error messages if anything is missing
- `.env` is created automatically from `.env.example` — no manual editing required
- The app opens automatically in the default browser when ready
- The script is idempotent — safe to run multiple times (re-run brings app back up if it was stopped)
- `README.md` updated so "Quick Start" is a single code block: `git clone ... && cd RVTool_Genesis && ./setup.sh`

### Todo List
1. Create `setup.sh` at the project root (chmod +x):
   ```bash
   #!/usr/bin/env bash
   set -e
   ```
   The script must perform these steps in order:

   **Step 1 — Check prerequisites:**
   - Check `docker` command exists; if not, print message pointing to OrbStack/Docker Desktop and exit 1
   - Check `docker compose` (v2 plugin) works; if not, print message and exit 1
   - Check Ollama is reachable: `curl -sf http://localhost:11434` — if not, print "Ollama is not running. Start the Ollama app or run: ollama serve" and exit 1
   - Check gemma3:4b (or configured model) is available: `ollama list | grep gemma3` — if not found, print "Pulling gemma3:4b model (this is a one-time ~3GB download)..." and run `ollama pull gemma3:4b`

   **Step 2 — Environment setup:**
   - If `.env` does not exist: copy `.env.example` → `.env` and print "Created .env from .env.example"
   - If `.env` already exists: print ".env already exists — skipping (delete it to reset)"
   - No API key prompting needed — all defaults work

   **Step 3 — Start containers:**
   - Run `docker compose up --build -d`
   - Print "Starting RVTool Genesis containers..."

   **Step 4 — Wait for API health:**
   - Poll `http://localhost:8001/api/health` every 2 seconds, up to 60 seconds
   - Print a spinner/dots while waiting: "Waiting for API to be ready..."
   - If health check passes: print "✓ API is ready"
   - If timeout: print "API did not start in time. Run: docker compose logs api" and exit 1

   **Step 5 — Open browser:**
   - Run `open http://localhost:3001` (macOS `open` command)
   - Print "✓ RVTool Genesis is running at http://localhost:3001"
   - Print "  API docs available at http://localhost:8001/api/docs"
   - Print "  To stop: docker compose down"
   - Print "  To view logs: docker compose logs -f"

2. Make `setup.sh` executable in the repo: the file permission `chmod +x` needs to be set — add a note in README that if permissions are lost after clone, run `chmod +x setup.sh`

3. Update `README.md`:
   - Change **Quick Start** section to:
     ```bash
     git clone <repo-url>
     cd RVTool_Genesis
     ./setup.sh
     ```
   - Remove the multi-step manual setup (cp .env.example, editing API key, docker compose up)
   - Keep the "Prerequisites" section but simplify to: OrbStack or Docker Desktop + Ollama with gemma3:4b
   - Add a "Stopping the app" section: `docker compose down`
   - Add a "Restarting" section: just run `./setup.sh` again

4. Update `Makefile` — add a `setup` target:
   ```makefile
   setup:
       ./setup.sh
   ```

### Relevant Context
- macOS `open` command opens URLs in the default browser
- OrbStack on macOS makes `host.docker.internal` available automatically — no extra config needed
- The script must use `#!/usr/bin/env bash` not `#!/bin/bash` for maximum macOS compatibility
- `curl -sf` returns exit code 0 on success, non-zero on failure — use this for health checks
- Docker Compose v2 is invoked as `docker compose` (space, not hyphen) — v1's `docker-compose` is deprecated

