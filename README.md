# RVTool Genesis

A containerized tool that converts customer server inventory spreadsheets into IBM RVTools-compatible output for use with the IBM Cool sizing tool.

Powered by **Ollama (phi4-mini)** — fully local AI, no API key, no cloud. Customer data never leaves your machine.

## What it does

1. **Upload** any customer-produced spreadsheet (Excel/CSV) listing desired virtual or bare metal servers — any column layout, freeform
2. **AI Normalization** — a local phi4-mini model maps freeform customer columns to the RVTools schema, fills in missing data, and documents every inference as an assumption
3. **Review** — inspect all normalized records and AI assumptions before exporting
4. **Export** — download a standards-compliant RVTools `.xlsx` file (4 tabs: vInfo, vNetwork, vPartition, vHost) ready for the IBM Cool tool, plus a separate Assumptions Report documenting every AI decision

## Prerequisites

- [OrbStack](https://orbstack.dev) (recommended) or [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- [Ollama](https://ollama.com) — installed and running on your Mac with `phi4-mini` available

  ```bash
  # Install Ollama from https://ollama.com then pull the model:
  ollama pull phi4-mini
  ```

## Quick Start

```bash
git clone <repo-url>
cd RVTool_Genesis
./setup.sh
```

The setup script handles everything:
- Checks Docker and Ollama are running
- Pulls the `gemma4:e4b` model if not already available
- Creates the `.env` configuration file automatically
- Builds and starts all containers
- Opens the app in your browser when ready

> **If the script isn't executable after cloning:** `chmod +x setup.sh`

## Stopping and Restarting

```bash
# Stop all containers
docker compose down

# Restart the app (safe to run anytime)
./setup.sh
```

## Ports

| Service | URL | Description |
|---|---|---|
| Web UI | http://localhost:3001 | React + Carbon Design System |
| API | http://localhost:8001 | FastAPI — Swagger docs at `/api/docs` |
| PostgreSQL | localhost:5433 | Local DB (for direct inspection) |

## Makefile Commands

```bash
make up        # Start all services (docker compose up --build)
make up-d      # Start all services detached (background)
make down      # Stop all services
make logs      # Tail logs from all services
make migrate   # Run database migrations manually
make test      # Run integration tests inside the api container
make shell-api # Shell into the api container
make shell-db  # psql shell into the database
```

## Environment Variables

All defaults are pre-configured and work without changes. Edit `.env` only if you need to override:

| Variable | Default | Description |
|---|---|---|
| `OLLAMA_BASE_URL` | `http://host.docker.internal:11434` | Ollama endpoint (host Mac from inside container) |
| `OLLAMA_MODEL` | `phi4-mini` | Ollama model to use for normalization |
| `DATABASE_URL` | `postgresql://rvtool:...@db:5432/rvtooldb` | PostgreSQL connection |
| `POSTGRES_DB` | `rvtooldb` | Database name |
| `POSTGRES_USER` | `rvtool` | Database user |
| `POSTGRES_PASSWORD` | `rvtool_password` | Database password |

## Architecture

```
OrbStack / Docker Compose
├── web :3001  (React + Carbon v11)
│   ├── ProjectsPage       — create/manage projects
│   ├── ProjectDetailPage  — upload, process, review, export
│   ├── RecordsTable       — review normalized server records
│   ├── AssumptionsPanel   — view AI decisions per record
│   └── ExportBar          — download RVTools + Assumptions files
│
├── api :8001  (FastAPI + Python 3.12)
│   ├── /api/projects          — project CRUD
│   ├── /api/uploads           — file upload + raw parse
│   ├── /api/process           — AI normalization (background tasks)
│   ├── /api/export            — RVTools + Assumptions .xlsx generation
│   │
│   └── services/
│       ├── spreadsheet_parser   — pandas: handles any freeform .xlsx/.csv
│       ├── ai_normalizer        — Ollama phi4-mini: maps columns, fills gaps
│       ├── network_inference    — default subnet/gateway/NIC logic
│       ├── rvtools_generator    — openpyxl: generates 4-tab RVTools file
│       ├── assumptions_generator — openpyxl: generates Assumptions Report
│       └── validator            — structural validation for generated files
│
└── db :5433  (PostgreSQL 16)
    ├── projects
    ├── uploads
    ├── server_records  (JSONB: raw_data, normalized_data)
    ├── assumptions
    ├── rvtools_exports
    └── assumptions_exports
│
[host Mac — NOT in Docker]
└── Ollama :11434
    └── phi4-mini  ← reached via host.docker.internal from containers
```

## Generated RVTools Schema

The exported file contains exactly 4 sheets consumed by the IBM Cool tool:

| Sheet | Columns | Description |
|---|---|---|
| vInfo | 14 | Core VM specs: CPU, RAM, OS, datacenter, cluster |
| vNetwork | 17 | NIC details: IP, adapter, MAC, network |
| vPartition | 13 | Disk/partition details (one row per disk per VM) |
| vHost | 28 | Physical host details: CPU model, cores, ESX version |

## AI Assumptions

Every field that the AI infers, defaults, or converts is recorded as an assumption with:
- **Field Name** — which RVTools field was inferred
- **Assumed Value** — what value was used
- **Original Value** — what the customer provided (if anything)
- **Reasoning** — why this value was chosen
- **Confidence** — High (directly mapped) / Medium (inferred) / Low (IBM default applied)

The Assumptions Report is a **separate `.xlsx` file** and does **not** appear in the RVTools export (extra tabs break IBM Cool tool parsing).

## Testing

```bash
# Run integration tests against the running stack
make test

# API docs (Swagger UI)
open http://localhost:8001/api/docs
```

## Sample File

A real RVTools export is included at `Samples/SizingWorkshop-RVTools.xlsx` as a reference for the target output schema. You can upload it directly to the app to test the full pipeline end-to-end.

## Spreadsheet Parser Notes

The parser handles real-world freeform spreadsheets automatically:

- **Any column layout** — no template required; columns are mapped by the AI
- **Phantom rows** — Excel workbooks often contain thousands of empty rows beyond the last data row (Excel's max is 1,048,576). The parser identifies real rows (≥ 2 non-null cells) *before* forward-filling merged cells, preventing ghost rows from being counted as servers
- **Merged cells** — forward-fill propagates values across visually merged cells
- **Mixed types** — all values are normalised to JSON-safe Python types (no numpy, no NaT)
- **Title/banner rows** — if row 0 has fewer than 2 non-null headers, the parser falls back to row 1 as the header row
- **Supported formats** — `.xlsx`, `.xls`, `.csv` up to 50 MB

## AI Normalization: Resilience

The normalizer is designed to **never leave a record permanently stuck**:

- **120 s timeout** — each Ollama call is limited to 120 seconds (~10× the average phi4-mini response time). If Ollama hangs, the timeout fires.
- **Automatic retry** — on timeout the call is retried once (with a 2 s pause to let Ollama clear its queue).
- **Python fallback synthesizer** — if both attempts fail or return invalid JSON, the record is synthesized directly from raw spreadsheet data using IBM defaults. It completes as `complete` (not `error`) with low-confidence assumptions noting the fallback.
- **Reset stuck endpoint** — `POST /api/projects/{id}/processing/reset-stuck` resets any records stuck in `processing` state back to `pending` (useful after container restarts mid-run).
- **UI "Reset stuck & resume" button** — appears automatically after a record takes more than 90 seconds, allowing one-click recovery without needing the terminal.

## RVTools Output: All 22 Sheets

The generated `.xlsx` contains all standard RVTools 4.x sheets required by downstream tools (IBM Cool, VCF Migration Lite, etc.):

| Sheet | Data |
|-------|------|
| `vInfo` | VM name, CPU, RAM, OS, datacenter, cluster |
| `vCPU` | CPU configuration per VM |
| `vMemory` | Memory configuration per VM |
| `vDisk` | One row per disk per VM (capacity, mode, path, thin flag) |
| `vPartition` | Partition-level disk usage |
| `vNetwork` | NIC details, IP, adapter, MAC |
| `vTools` | VMware Tools version/status |
| `vHealth` | VM health status |
| `vFileInfo` | VM config file path |
| `vHost` | Physical host details |
| `vFloppy`, `vCD`, `vSnapshot`, `vRP`, `vCluster`, `vHBA`, `vNIC`, `vSwitch`, `vPort`, `vSC+VM`, `vDatastore`, `vMultiWriter` | Header-only stubs (required for format validation) |

## Changelog

### feat/resilience-and-ux
- **Full 22-sheet RVTools output** — adds all missing tabs (`vDisk`, `vCPU`, `vMemory`, `vTools`, `vHealth`, `vFileInfo`, and 12 stub sheets). Fixes "Unrecognised source format" error from VCF Migration Lite.
- **Ollama timeout + retry** — per-record timeout reduced from 300 s to 120 s; one automatic retry; Python fallback synthesizer on failure. Records can no longer get permanently stuck.
- **Reset-stuck endpoint** — `POST /api/projects/{id}/processing/reset-stuck` resets orphaned `processing` records.
- **Per-record heartbeat UI** — Normalize page shows elapsed time on the current record with an animated pulse dot. After 90 s, a "Reset stuck & resume" button appears.
- **NormalizePage Start button** — fixed: fresh projects (all-pending) no longer enter the "in-progress" display state immediately, hiding the Start button.
- **Export filenames** — downloads now use the server-supplied `Content-Disposition` filename (e.g. `RVTools_ProjectName_20260709.xlsx`) instead of the bare UUID.

### Previous fixes
- **Parser phantom-row fix** — `ffill` was propagating last-row values into thousands of Excel phantom rows before `dropna` ran, inflating record counts (e.g. 88 servers showing as 413). Fixed by snapshotting a "real row" mask before `ffill` and filtering to it afterwards.
- **File-replace doubling** — uploading a replacement file now clears all previous records/assumptions for the project before inserting the new batch.
- **Upload count display** — the UI now correctly reads `row_count` from the upload response (was reading a non-existent field, always showing 0).
- **Model docs** — all references updated from `gemma4:e4b` to `phi4-mini` (the current production model).
