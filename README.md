# RVTool Genesis

A containerized tool that converts customer server inventory spreadsheets into IBM RVTools-compatible output for use with the IBM Cool sizing tool.

Powered by a **pluggable LLM backend** — use IBM watsonx.ai for IBM engagement work, or run fully local with Ollama (no API key, no cloud). Configure your preferred provider in the Settings page.

## What it does

1. **Upload** any customer-produced spreadsheet (Excel/CSV) listing desired virtual or bare metal servers — any column layout, freeform
2. **AI Normalization** — a local phi4-mini model maps freeform customer columns to the RVTools schema, fills in missing data, and documents every inference as an assumption
3. **Review** — inspect all normalized records and AI assumptions before exporting
4. **Export** — download a standards-compliant RVTools `.xlsx` file (4 tabs: vInfo, vNetwork, vPartition, vHost) ready for the IBM Cool tool, plus a separate Assumptions Report documenting every AI decision

## Prerequisites

- [OrbStack](https://orbstack.dev) (recommended) or [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- [Ollama](https://ollama.com) *(only if using the Ollama provider — the default)* — installed and running on your Mac with `phi4-mini` available

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
| `SECRET_KEY` | *(weak default)* | AES-256 key for encrypting cloud API keys in DB — **change this** before using cloud providers |
| `DATABASE_URL` | `postgresql://rvtool:...@db:5432/rvtooldb` | PostgreSQL connection |
| `POSTGRES_DB` | `rvtooldb` | Database name |
| `POSTGRES_USER` | `rvtool` | Database user |
| `POSTGRES_PASSWORD` | `rvtool_password` | Database password |

Generate a strong `SECRET_KEY`:
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

## Architecture

```
OrbStack / Docker Compose
├── web :3001  (React + Carbon v11)
│   ├── ProjectsPage       — create/manage projects
│   ├── UploadPage         — file upload
│   ├── NormalizePage      — AI normalization progress
│   ├── ReviewPage         — review records + assumptions
│   ├── ExportPage         — download RVTools + Assumptions files
│   └── SettingsPage       — LLM provider configuration
│
├── api :8001  (FastAPI + Python 3.12)
│   ├── /api/projects          — project CRUD
│   ├── /api/uploads           — file upload + raw parse
│   ├── /api/process           — AI normalization (background tasks)
│   ├── /api/export            — RVTools + Assumptions .xlsx generation
│   ├── /api/settings          — LLM provider settings (GET/POST/test)
│   │
│   └── services/
│       ├── spreadsheet_parser   — pandas: handles any freeform .xlsx/.csv
│       ├── ai_normalizer        — LLM dispatcher + cloud/Ollama adapters
│       ├── crypto               — AES-256 Fernet encryption for API keys
│       ├── network_inference    — default subnet/gateway/NIC logic
│       ├── rvtools_generator    — openpyxl: generates 22-sheet RVTools file
│       ├── assumptions_generator — openpyxl: generates Assumptions Report
│       └── validator            — structural validation for generated files
│
└── db :5433  (PostgreSQL 16)
    ├── projects
    ├── uploads
    ├── server_records  (JSONB: raw_data, normalized_data)
    ├── assumptions
    ├── rvtools_exports
    ├── assumptions_exports
    └── llm_settings         (single-row: active provider + encrypted keys)
│
[host Mac — NOT in Docker, only when using Ollama provider]
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

## LLM Providers

The active LLM provider is configured in the **Settings** page (`/settings`) and
persisted to the database — no container restart needed after switching.

| Provider | API Key Required | Notes |
|---|---|---|
| **Ollama (local)** | No | Default. Requires Ollama running on your Mac. `ollama pull phi4-mini` |
| **IBM watsonx.ai** ⭐ | IBM Cloud API key + Project ID | Recommended for IBM engagement work. Use `ibm/granite-3-8b-instruct` |
| **OpenAI-compatible** | API key | Works with OpenAI, Azure OpenAI, local vLLM, LM Studio |
| **Anthropic** | API key | Claude models (Haiku recommended for speed/cost) |

### Getting an IBM watsonx.ai API key

1. Log in to [cloud.ibm.com](https://cloud.ibm.com)
2. Go to **Manage → Access (IAM) → API keys** → Create
3. Open your watsonx.ai project → **Manage → General** → copy the Project ID
4. Enter both in the Settings page and click **Test connection**

### IBM IAM token caching

For watsonx.ai, an IBM IAM Bearer token is obtained once and cached for 50 minutes
(tokens expire at 60 min). This means IAM is only called once per processing run, not
once per server record.

### Security

- API keys are encrypted with AES-256 (Fernet) before being stored in PostgreSQL
- Keys are never logged or returned in plaintext from any API endpoint
- Only a masked hint (`••••••••abcd`) is displayed in the UI
- Set a strong `SECRET_KEY` in `.env` before using cloud providers

### Switching providers

Changes take effect immediately on the next `POST /process` call. No container restart
is needed. The Python fallback synthesizer remains active as a last resort if the cloud
provider fails.


## PowerVS Auto-Detection

When a server's operating system is **AIX** or **IBM i** (any version), the AI normalizer
automatically designates it as a **PowerVS** workload. This happens in both the LLM path
and the Python fallback synthesizer, and is enforced as a guaranteed post-processing step
regardless of the LLM's response.

**Trigger patterns (case-insensitive, substring match):**
`AIX`, `IBM i`, `IBMi`, `i/OS`, `OS/400`, `IBM OS/400`

### What happens to PowerVS records

1. `server_type` is set to `"powervs"` (shown as a purple "PowerVS" tag in the Review table)
2. A high-confidence assumption is added explaining the designation
3. In the Export page, PowerVS records are **routed to a separate set of exports**:
   - **PowerVS Cloud Solutioning Tool Export** — 22-sheet IBM Cool workbook, PowerVS only
   - **PowerVS Assumptions Report** — AI decisions for PowerVS records only
4. Standard x86 exports **exclude** PowerVS records
5. Both exports are generated independently and uploaded to IBM Cool separately

### Why separate exports?

The IBM Cool / Cloud Solutioning Tool scopes its entire pricing proposal to a single uploaded
workbook. Mixing x86 Virtual Servers and PowerVS workloads in the same upload produces
incorrect results. Each pricing exercise requires its own dedicated RVTools file.

### Mixed-workload banner

When a project contains both x86 and PowerVS records, the Export page shows an
informational banner explaining the automatic separation, with the exact record counts
for each type.

### Overriding the designation

In the Review table, click "Edit this record" to change `server_type` to/from `powervs`
if the automatic detection was incorrect.

---

## Server Exclusion

Any server can be excluded from all generated reports via the **Exclude checkbox** in
the Review table.

### How it works

- Check the "Exclude" checkbox on any row → record is immediately excluded (persists to DB)
- Excluded rows display at 55% opacity with a strikethrough server name
- An optional reason text field appears in the expanded row (saves on blur or Enter)
- Excluded records are **omitted from all RVTools exports** (x86 and PowerVS)
- Excluded records appear in an **"Excluded Servers" audit sheet** in the Assumptions
  Report `.xlsx`, showing the server name, OS, type, reason, and timestamp

### Use cases

- Server already migrated
- Decommissioned / out of scope for this engagement
- Test/dev server not included in the sizing
- Customer explicitly requested exclusion

---


## Changelog

### feat/powervs-exclusion
- **PowerVS auto-detection** — AIX and IBM i operating systems are automatically designated as `server_type = "powervs"` by both the LLM and Python fallback. Enforced as a guaranteed post-processing step.
- **Separate PowerVS exports** — Export page generates two independent 22-sheet IBM Cool workbooks: one for x86/VPC records and one for PowerVS records. Each is uploaded to IBM Cool separately for independent pricing.
- **Mixed-workload banner** — When a project contains both x86 and PowerVS records, a banner on the Export page explains the automatic separation.
- **Server exclusion** — Checkbox in the Review table excludes servers from all exports. Optional reason stored in DB and surfaced in an "Excluded Servers" audit sheet in the Assumptions Report.
- **DB migration** — `is_excluded` (boolean) and `exclusion_reason` (text) columns added to `server_records`.
- **Purple "PowerVS" tag** — Type column in Review table now has three distinct tags: Virtual (blue), Bare Metal (teal), PowerVS (purple).
- **`PATCH /records/{id}/exclude`** — New endpoint to toggle exclusion and set reason, independent of the vinfo editor.

### feat/llm-providers
- **Multi-provider LLM support** — Settings page lets you switch between Ollama (local), IBM watsonx.ai, OpenAI-compatible, and Anthropic Claude
- **IBM watsonx.ai integration** — IAM token exchange + 50-min cache; defaults to `ibm/granite-3-8b-instruct`
- **AES-256 key encryption** — cloud API keys encrypted with Fernet before PostgreSQL storage; never logged or returned in plaintext
- **Test Connection button** — validates provider credentials and shows latency + model response before saving
- **Settings nav link** — "Settings" added to the top navigation bar
- **`cryptography` dependency** — added to `requirements.txt` (no vendor SDK needed)

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
