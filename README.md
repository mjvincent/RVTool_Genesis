# RVTool Genesis

A containerized tool that converts customer server inventory spreadsheets into IBM sizing outputs for IBM Cloud migration proposals — with zero manual data entry.

Powered by a **pluggable LLM backend** — use IBM watsonx.ai for IBM engagement work, or run fully local with Ollama (no API key, no cloud). Configure your preferred provider in the Settings page.

📖 [User Guide](docs/USER_GUIDE.md) · ⚙️ [Operations Guide](docs/OPERATIONS_GUIDE.md) · 📝 [Changelog](CHANGELOG.md) · 🤝 [Contributing](CONTRIBUTING.md)

---

## Why this tool exists

Producing an IBM Cloud cost estimate for a customer migration requires populating the **IBM Cloud Cost Estimator** with every server in scope — one entry per virtual machine or bare metal server. For a typical mid-size engagement this means hundreds to thousands of individual form entries, each requiring CPU count, RAM, OS, disk size, IOPS tier, region, and billing type.

The table below shows what that looks like at 1,454 servers (a real engagement dataset):

| Pace Per Entry | Total Active Time |
| :--- | :--- |
| 1 min — best case | **24 hours** |
| 1.5 min — realistic average | **36.5 hours** |
| 2 min — complex entries / slow forms | **48.5 hours** |

Three real-world variables push that number even higher:

- **System latency** — pricing forms often require a page refresh or database lookup per entry. A 3-second load lag alone adds over an hour of dead time across 1,454 entries.
- **Cognitive fatigue** — high-precision data entry slows down as eye strain sets in. Errors in pricing are costly.
- **Data retrieval** — time spent looking up the correct value on the source spreadsheet before typing it.

With standard workday constraints (lunch, hourly breaks, daily distractions), a person can sustain roughly **5.5–6 hours of focused data entry per day**. At 1,454 entries that translates to:

> - **Optimistic (1.5 min/entry):** 6–6.5 full workdays dedicated entirely to this task
> - **Conservative (2.0 min/entry):** 8–8.5 full workdays

**RVTool Genesis eliminates this entirely.** Upload the customer's server inventory spreadsheet, let the AI normalize and map every record to IBM Cloud profiles, review the output in minutes, and download a ready-to-upload Cloud Solution Export — with every AI decision documented as an auditable assumption.

---

## What it does

1. **Upload** any customer-produced spreadsheet (Excel/CSV) listing servers — any column layout, freeform
2. **AI Normalization** — maps freeform customer columns to IBM VPC / PowerVS fields, fills in missing data (OS images, disk sizes, storage tiers, regions), and documents every inference as an assumption. IBM VPC boot-disk constraints (100 GB min / 250 GB max) apply to x86 records only — PowerVS disk sizes pass through unchanged.
3. **Review** — inspect all normalized records and AI assumptions; exclude servers, edit fields inline, bulk-replace OS values, fix unsupported Flex-Nano profiles
4. **Export** — download output files for your IBM pricing tool of choice (see All Exports below)

x86 / VPC records and PowerVS (AIX / IBM i) records are **automatically separated** into independent export sets.

---

## All Exports

| Output | Format | Filename pattern | IBM tool | Notes |
|---|---|---|---|---|
| **Cloud Solution Export** | 3-sheet .xlsx | `CloudSolution_<name>_<date>.xlsx` | IBM Cloud Cost Estimator | ⭐ Primary x86 deliverable |
| **RVTools Export (x86)** | 22-sheet .xlsx | `RVTools_<name>_<date>.xlsx` | VCF Migration Lite / IBM Cool | Full 22-tab format |
| **AI Assumptions Report (x86)** | .xlsx | `Assumptions_<name>_<date>.xlsx` | Customer review | Every AI inference documented |
| **PowerVS Cloud Solution Export** | 3-sheet .xlsx | `CloudSolution_PowerVS_<name>_<date>.xlsx` | IBM PowerVS Cost Estimator | ⭐ Primary PowerVS deliverable |
| **PowerVS Cool Tool Export** | 4-sheet .xlsx | `COOL_PowerVS_<name>_<date>.xlsx` | IBM Cool (PowerVS input) | Upload separately from x86 |
| **PowerVS RVTools Export** | 22-sheet .xlsx | `RVTools_PowerVS_<name>_<date>.xlsx` | VCF Migration Lite (PowerVS) | Full 22-tab format |
| **PowerVS AI Assumptions Report** | .xlsx | `Assumptions_PowerVS_<name>_<date>.xlsx` | Customer review | PowerVS records only |
| **IBM Price Estimator (populated)** | .xlsx | `PowerVS_PriceEstimator_<name>_<date>.xlsx` | Excel | Per-LPAR PowerVS pricing |

---

## Prerequisites

- [OrbStack](https://orbstack.dev) (recommended) or [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- [Ollama](https://ollama.com) *(only if using the Ollama provider — the default)* — installed and running on your Mac with `phi4-mini` available

  ```bash
  # Install Ollama from https://ollama.com then pull the model:
  ollama pull phi4-mini
  ```

---

## Quick Start

```bash
git clone <repo-url>
cd RVTool_Genesis
./setup.sh
```

The setup script handles everything:
- Checks Docker and Ollama are running
- Pulls the `phi4-mini` model if not already available
- Creates the `.env` configuration file with an **auto-generated `SECRET_KEY`** — no manual step required
- Builds and starts all containers
- Opens the app in your browser when ready

> **If the script isn't executable after cloning:** `chmod +x setup.sh`

> **SECRET_KEY** — A strong encryption key is generated automatically into `.env` on first run (using `openssl` or `python3`). Keep `.env` private — it is already in `.gitignore`. To rotate the key at any time (e.g. before sharing a deployment), run `make generate-secret`, paste the output into `.env`, and restart the API: `docker compose up --build -d api`. See [Security hardening](docs/OPERATIONS_GUIDE.md) for full details.

---

## Stopping and Restarting

```bash
# Stop all containers
docker compose down

# Restart the app (safe to run anytime)
./setup.sh
```

---

## Ports

| Service | URL | Description |
|---|---|---|
| Web UI | http://localhost:3001 | React + Carbon Design System |
| API | http://localhost:8001 | FastAPI — Swagger docs at `/api/docs` |
| PostgreSQL | internal only | No host port — only reachable within Docker bridge network |

---

## Makefile Commands

```bash
make generate-secret  # Generate a strong SECRET_KEY value
make up               # Start all services (docker compose up --build)
make up-d             # Start all services detached (background)
make down             # Stop all services
make logs             # Tail logs from all services
make migrate          # Run database migrations manually
make test             # Run tests inside the api container
make typecheck        # Run TypeScript typecheck
make lint             # Run Ruff Python linter
make shell-api        # Shell into the api container
make shell-db         # psql shell into the database
```

---

## Environment Variables

All defaults are pre-configured and work without changes. Edit `.env` only if you need to override:

| Variable | Required | Description |
|---|---|---|
| `SECRET_KEY` | **Yes** | AES-256 key for encrypting cloud API keys in PostgreSQL. **The API will not start if this is left at the default.** Generate with `make generate-secret`. |
| `OLLAMA_BASE_URL` | No | Ollama endpoint reached from inside containers. Default: `http://host.docker.internal:11434` |
| `OLLAMA_MODEL` | No | Ollama model for normalization. Default: `phi4-mini` |
| `DMR_BASE_URL` | No | Docker Model Runner endpoint. Default: `http://host.docker.internal:9545` |
| `DMR_MODEL` | No | Model name for Docker Model Runner, e.g. `ai/phi4-mini` |
| `HF_TOKEN` | No | HuggingFace token — higher rate limits for GGUF resolver |
| `API_TOKEN` | No | Bearer token for API auth. Leave blank for home-network use. When set, all requests require `Authorization: Bearer <token>`. |
| `ALLOWED_ORIGINS` | No | Comma-separated CORS origins. Default: `http://localhost:3001`. Add your machine's IP for network demos. |
| `DATABASE_URL` | No | PostgreSQL connection string. Default: `postgresql://rvtool:rvtool_password@db:5432/rvtooldb` |
| `POSTGRES_DB` | No | Database name. Default: `rvtooldb` |
| `POSTGRES_USER` | No | Database user. Default: `rvtool` |
| `POSTGRES_PASSWORD` | No | Database password. Default: `rvtool_password` |

Generate a strong `SECRET_KEY` (required on first run):
```bash
make generate-secret
```

---

## Architecture

```
OrbStack / Docker Compose
├── web :3001  (React + Carbon v11)
│   ├── ProjectsPage       — create/manage projects, folder hierarchy
│   ├── UploadPage         — file upload
│   ├── NormalizePage      — AI normalization progress
│   ├── ReviewPage         — review records + assumptions
│   │   ├── BulkOSModal        — bulk OS replace across all matching records
│   │   ├── BulkNxfModal       — upgrade unsupported nxf-1x* profiles
│   │   └── EditRecordModal    — inline vinfo field editing
│   ├── ExportPage         — download all 8 output files + IBM Price Estimator
│   └── SettingsPage       — LLM provider configuration + model recommendations
│
├── api :8001  (FastAPI + Python 3.12)
│   ├── /api/projects          — project CRUD + region settings
│   ├── /api/folders           — folder CRUD + project move
│   ├── /api/uploads           — file upload + raw parse + record edit
│   │                            bulk-os-replace, bulk-nxf-replace, nxf-count
│   ├── /api/process           — AI normalization (background tasks)
│   ├── /api/process/{id}/readiness-summary  — Migration Readiness Summary stats
│   ├── /api/process/{id}/audit-log          — append-only project event log
│   ├── /api/export            — 7 RVTools + Assumptions export endpoints
│   ├── /api/projects/{id}/pricing-template  — IBM Price Estimator upload + populate
│   ├── /api/settings          — LLM provider settings + model recommendations
│   ├── /api/projects/{id}/backup  — single-project JSON backup
│   ├── /api/backup/all            — full system .zip backup
│   └── /api/restore               — restore from .json or .zip
│
│   services/
│       ├── spreadsheet_parser        — pandas: handles any freeform .xlsx/.csv
│       ├── ai_normalizer             — LLM dispatcher + cloud/Ollama/DMR adapters
│       ├── crypto                    — AES-256 Fernet encryption for API keys
│       ├── network_inference         — default subnet/gateway/NIC logic
│       ├── rvtools_generator         — openpyxl: generates 22-sheet RVTools file
│       ├── assumptions_generator     — openpyxl: generates Assumptions Report
│       ├── vpc_calculator_generator  — openpyxl: generates 3-sheet VPC Cloud Solution Export
│       ├── powervs_calculator_generator — generates 3-sheet PowerVS Cloud Solution Export
│       ├── pricing_template_filler   — zip-level XML surgery: fills IBM Price Estimator
│       ├── model_catalog             — curated LLM catalog + advisor + GGUF resolver
│       ├── model_benchmarker         — 8-case benchmark corpus + composite scoring (50% accuracy + 50% speed)
│       └── validator                 — structural validation for generated files
│
└── db  (PostgreSQL 16 — internal network only, no host port)
    ├── projects          (vpc_region, vpc_datacenter, pvs_region, pvs_datacenter)
    ├── folders           (hierarchical project organisation — max depth 2)
    ├── uploads
    ├── server_records    (JSONB: raw_data, normalized_data, server_type, is_excluded)
    ├── assumptions
    ├── rvtools_exports
    ├── assumptions_exports
    ├── pricing_templates (raw IBM Price Estimator .xlsx per project)
    └── llm_settings      (single-row: active provider + encrypted keys,
                           previous_model, recommendation_snoozed_until)

[host Mac — NOT in Docker, only when using Ollama or Docker Model Runner]
├── Ollama :11434          — reached via host.docker.internal from containers
└── Docker Model Runner :9545 — built into Docker Desktop ≥ 4.25; OpenAI-compatible
```

---

## Generated RVTools Schema

The tool generates two RVTools formats:

**4-sheet format** (IBM Cool input — `COOL_*.xlsx`):

| Sheet | Columns | Description |
|---|---|---|
| vInfo | 14 | Core VM specs: CPU, RAM, OS, datacenter, cluster |
| vNetwork | 17 | NIC details: IP, adapter, MAC, network |
| vPartition | 13 | Disk/partition details (one row per disk per VM) |
| vHost | 28 | Physical host details: CPU model, cores, ESX version |

**22-sheet format** (VCF Migration Lite / full RVTools 4.x):

All 4 sheets above plus `vCPU`, `vMemory`, `vDisk`, `vTools`, `vHealth`, `vFileInfo`,
and 12 header-only stub sheets required for format validation.

---

## AI Assumptions

Every field that the AI infers, defaults, or converts is recorded as an assumption with:
- **Field Name** — which RVTools field was inferred
- **Assumed Value** — what value was used
- **Original Value** — what the customer provided (if anything)
- **Reasoning** — why this value was chosen
- **Confidence** — High (directly mapped) / Medium (inferred) / Low (IBM default applied)

The Assumptions Report is a **separate `.xlsx` file** and does **not** appear in the RVTools export (extra tabs break IBM Cool tool parsing).

---

## Bulk Operations

### Bulk OS Replace

Replaces the OS family on all records matching a chosen value in a single operation.
Useful for generating alternative pricing scenarios (e.g. replacing paid Windows or
RHEL licences with a free Linux variant) without manually editing every record.

- Open the Review page → click **Bulk OS Replace**
- Choose the source OS and the replacement OS
- All matching non-excluded records are updated atomically
- Every change is logged as an assumption in the AI Assumptions Report

### Fix Nano Profiles (Flex-Nano upgrade)

The IBM Cloud Solutioning Tool only recognizes `nxf-2x1` and `nxf-2x2` in its
Data Domains sheet. Servers with `nxf-1x1`, `nxf-1x2`, or `nxf-1x4` profiles will
silently fail to populate when the Cloud Solution Export is imported.

When unsupported profiles are detected, a **warning banner** appears on the Review page.
Click **Fix Nano Profiles** to upgrade all affected servers to `nxf-2x1` or `nxf-2x2`
in one action. The change is logged as an assumption.

---

## IBM Price Estimator

The IBM Power Virtual Server Price Estimator is an IBM-provided Excel workbook that
calculates per-LPAR pricing. RVTool Genesis populates its yellow input cells automatically.

**Workflow (per project):**
1. Upload the IBM Price Estimator `.xlsx` once via the Export page
2. Click **Populate & Download** — the tool writes all PowerVS server data into the
   yellow input area (LPAR name, system type, cores, memory, OS, storage)
3. Open the downloaded file in **Excel** — pricing formulas recalculate automatically

**Machine selection logic:**

| Criteria | Assigned system |
|---|---|
| ≤ 51 cores AND ≤ 1,904 GB RAM | S1022 (Power10 scale-out) |
| ≤ 120 cores | E1050 (Power10 enterprise) |
| > 120 cores | E1080 (Power10 enterprise, largest) |

The template is stored per-project. Replace it at any time by re-uploading.

---

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
3. In the Export page, PowerVS records are **routed to a separate set of exports** (all four listed in the All Exports table above)
4. Standard x86 exports **exclude** PowerVS records
5. Both export sets are generated independently and uploaded to IBM Cool separately

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
- An optional reason text field appears — enter text and the reason is saved automatically
- Excluded records are **omitted from all RVTools exports** (x86 and PowerVS)
- Excluded records appear in an **"Excluded Servers" audit sheet** in the Assumptions
  Report `.xlsx`, showing the server name, OS, type, reason, and timestamp

---

## Folder Organization

Projects can be grouped into a two-level folder hierarchy for engagement-level
organization: **Root → Customer → Engagement**.

From the Projects page:
- **New folder** — creates a folder at the current level (root or inside another folder)
- **⋮ menu on a folder** — rename or delete the folder
- **⋮ menu on a project → Move to folder** — move the project into any folder

Deleting a folder moves its projects to root; it does not delete the projects.

---

## Backup & Restore

Projects can be exported to portable JSON bundles and restored on any machine running
RVTool Genesis — useful for off-machine backups, sharing with colleagues, and archiving
completed engagements.

### What's in a backup

| Included | Not Included |
|---|---|
| All normalized server records | Generated `.xlsx` exports |
| All AI assumptions | LLM provider settings / API keys |
| Server type, exclusion flags + reasons | Nothing sensitive |
| Project name and description | — |
| Original spreadsheet *(optional)* | — |

Generated exports are intentionally excluded — they can be regenerated from the Export
page in seconds.

### Backing up a single project

1. Open the **Projects** page
2. Click the ⋮ overflow menu on any project row
3. Select **Backup project**
4. Optionally check **"Include original spreadsheet file"** (increases file size)
5. Click **Download backup** → saves `rvtg-<project-name>-<date>.json`

### Backing up all projects

Click the **Backup all** button in the Projects page header. Downloads
`rvtoolgenesis-backup-<date>.zip` containing one JSON bundle per project.

### Restoring from backup

1. Click **Restore from backup** (ghost button in the Projects page header)
2. Pick a `.json` (single project) or `.zip` (multi-project) backup file
3. Restored project(s) appear immediately in the list with a
   `(restored YYYY-MM-DD)` suffix so they're distinguishable from originals
4. Navigate straight to **Review → Export** — no re-normalization needed

### Docker volume durability

The PostgreSQL data lives in a **named Docker volume** (`postgres_data`) that survives
container restarts, `docker compose down`, and OrbStack crashes. You do **not** need a
backup for crash recovery — only use backup/restore for off-machine portability or
archiving.

---

## Testing

```bash
# Run integration tests against the running stack
make test

# API docs (Swagger UI)
open http://localhost:8001/api/docs
```

---

## Spreadsheet Parser Notes

The parser handles real-world freeform spreadsheets automatically:

- **Any column layout** — no template required; columns are mapped by the AI
- **Phantom rows** — Excel workbooks often contain thousands of empty rows beyond the last data row (Excel's max is 1,048,576). The parser identifies real rows (≥ 2 non-null cells) *before* forward-filling merged cells, preventing ghost rows from being counted as servers
- **Merged cells** — forward-fill propagates values across visually merged cells
- **Mixed types** — all values are normalised to JSON-safe Python types (no numpy, no NaT)
- **Title/banner rows** — if row 0 has fewer than 2 non-null headers, the parser falls back to row 1 as the header row
- **Supported formats** — `.xlsx`, `.xls`, `.csv` up to 50 MB

---

## AI Normalization: Resilience

The normalizer is designed to **never leave a record permanently stuck**:

- **120 s timeout** — each Ollama call is limited to 120 seconds (~10× the average phi4-mini response time). If Ollama hangs, the timeout fires.
- **Automatic retry** — on timeout the call is retried once (with a 2 s pause to let Ollama clear its queue).
- **Python fallback synthesizer** — if both attempts fail or return invalid JSON, the record is synthesized directly from raw spreadsheet data using IBM defaults. It completes as `complete` (not `error`) with low-confidence assumptions noting the fallback.
- **Reset stuck endpoint** — `POST /api/projects/{id}/processing/reset-stuck` resets any records stuck in `processing` state back to `pending` (useful after container restarts mid-run).
- **UI "Reset stuck & resume" button** — appears automatically after a record takes more than 90 seconds, allowing one-click recovery without needing the terminal.

---

## LLM Providers

The active LLM provider is configured in the **Settings** page (`/settings`) and
persisted to the database — no container restart needed after switching.

| Provider | API Key Required | Notes |
|---|---|---|
| **Ollama (local)** | No | Default. Requires Ollama running on your Mac. `ollama pull phi4-mini` |
| **IBM watsonx.ai** ⭐ | IBM Cloud API key + Project ID | Recommended for IBM engagement work. Use `ibm/granite-3-8b-instruct` |
| **OpenAI-compatible** | API key | Works with OpenAI, Azure OpenAI, local vLLM, LM Studio |
| **Anthropic** | API key | Claude models (Haiku recommended for speed/cost) |
| **Docker Model Runner** | No | Built into Docker Desktop ≥ 4.25. `docker model pull ai/phi4-mini` |

### Getting an IBM watsonx.ai API key

1. Log in to [cloud.ibm.com](https://cloud.ibm.com)
2. Go to **Manage → Access (IAM) → API keys** → Create
3. Open your watsonx.ai project → **Manage → General** → copy the Project ID
4. Enter both in the Settings page and click **Test connection**

### IBM IAM token caching

For watsonx.ai, an IBM IAM Bearer token is obtained once and cached for 50 minutes
(tokens expire at 60 min). This means IAM is only called once per processing run, not
once per server record.

### Local AI Advisor

When Ollama is the active provider, the Settings page shows a **Local AI Advisor** card
that reads your machine's CPU/RAM, checks installed Ollama models, and ranks them by
task-fit score (1–10) and RAM fit. It recommends the best model and suggests an
`ollama pull` command if a better one is available.

**Model scoring tiers:**
- **9–10** — Excellent for structured JSON extraction (`phi4`, `phi4-mini`, `qwen2.5:14b`)
- **7–8** — Capable generalists (`llama3.3`, `mistral-nemo`)
- **5** — Unknown/neutral models (default for anything not in the catalog)
- **3–4** — Code-specialised models (`qwen2.5-coder`, `codellama`, `deepseek-coder`) — not suited for this task
- **1–2** — Embedding models (`nomic-embed-text`, `mxbai-embed`) — cannot generate text

### Compare Models (benchmark)

The "Compare Models" section (inside the Local AI Advisor card) runs **8 synthetic
server records** through two models and scores them equally on accuracy and speed:

```
Composite score = (accuracy_pct × 0.5) + (speed_score × 0.5)
Speed score     = clamp(1 − avg_latency_ms / 30 000, 0, 1) × 100
```

A model that takes 15 s per record and gets everything right scores **50 + 50 = 75**.
One that takes 3 s and gets everything right scores **50 + 90 = 95**.

Both Model A and Model B can use either **Ollama** or **Docker Model Runner** as their
backend — enabling pure runtime speed comparisons for the same model across runtimes.

When Docker Model Runner is selected as Model B's backend, a **"🔍 Find on HuggingFace"**
link queries the HuggingFace Hub API live and shows the exact `docker model pull` command.

### Model recommendations

When a newer or more capable model is available for your configured provider, a
**recommendation banner** appears at the top of the Settings page with three options:
- **Apply** — upgrades immediately; previous model is saved for rollback
- **Roll back** — returns to the model used before the last apply
- **Snooze for 7 days** — dismisses the banner until next week

### Security

- API keys are encrypted with AES-256 (Fernet) before being stored in PostgreSQL
- Keys are never logged or returned in plaintext from any API endpoint
- Only a masked hint (`••••••••abcd`) is displayed in the UI
- Set a strong `SECRET_KEY` in `.env` before using cloud providers

### Switching providers

Changes take effect immediately on the next `POST /process` call. No container restart
is needed. The Python fallback synthesizer remains active as a last resort if the cloud
provider fails.

---

## Changelog

> Full history with linked diffs: [CHANGELOG.md](CHANGELOG.md)

### v2.3.1

- **Settings page timeout** — No longer hangs if Ollama is unreachable; renders within 4 seconds with a clear error message.
- **Cancel normalization** — New Cancel button on the Normalize page; wires up the v2.3.0 backend cancel endpoint.
- **MappingPreview empty states** — Clear warning/info notices when a file has no records or no sample data, instead of a blank table.
- **ProjectsPage status failures** — Failed per-project status fetches now show "—" instead of nothing.

### v2.3.0

- **Durable job queue** — Processing now uses a PostgreSQL-backed `processing_jobs` table. Jobs survive API restarts; concurrent start requests are safely deduplicated; a new Cancel endpoint stops processing after the current record.
- **Ruff lint gate** — CI now checks the full `api/` directory; all pre-existing violations resolved.
- **Accessible Exclude checkbox** — Screen readers now hear the server name when the Exclude control is focused.
- **Upload safety guards** — XLSX zip-bomb (decompression-ratio > 100×, uncompressed > 500 MB) and row-count (> 100,000) checks added before pandas touches the file.

### v2.2.0

- **Audit History** — Bulk OS Replace, Bulk Flex-Nano Fix, Bulk Exclude, and Cloud Solution Export now write to a persistent audit log. A collapsible "Activity" panel at the bottom of the Export page shows all entries with operation badge, summary, record count, and timestamp.

### v2.1.0

- **Migration Readiness Summary Banner** — Export page now shows a colour-coded banner with six stat tiles (Total, x86 ready, PowerVS ready, Pending, Errors, Excluded) and a single "Ready to export" / "N errors need attention" decision line before any export button is pressed.

### v2.0.0

- **Exception-first Review Queue** — Review page defaults to "Needs attention" — errors first, then low-confidence AI results, then records missing key fields. Four filter preset buttons with count badges. Silently falls back to "All" when everything looks good.
- **Upload Mapping Confirmation** — After upload, a column preview panel shows detected column names and 5 sample rows before normalization begins. "Looks good" proceeds; "Re-upload" clears for a fresh file.

### v1.9.0

- **`billing_type` allowlist** — Invalid billing type values now return HTTP 422 instead of silently writing bad data into the Excel export.
- **Non-root containers** — Both API and web containers now run as a dedicated non-root `appuser`. Passes IBM container security checks.
- **Dependency audit in CI** — `pip-audit` and `npm audit` run on every push to catch vulnerable packages before they merge.
- **Python dependencies updated** — All packages bumped to latest stable; cryptography 43 → 44, fastapi 0.115.0 → 0.115.14, uvicorn 0.30.6 → 0.34.3, sqlalchemy 2.0.35 → 2.0.41, and more.

### v1.8.0

- **Billing type on Cloud Solution Export** — A modal now prompts for billing type before generating the IBM Cloud Cost Estimator workbook: `PAYG` (default), `1 Yr Reserved`, or `3 Yr Reserved`. The chosen value is written to every Billing Type cell in the Project Settings sheet.
- **`setup.sh` auto-generates `SECRET_KEY`** — Fresh installs no longer crash on startup. `setup.sh` generates a strong key automatically using `openssl` (macOS/Linux/Git Bash/WSL) or `python3` (Windows fallback).

### v1.7.0 — IBM Presentation Readiness hardening

- **SECRET\_KEY enforcement** — API refuses to start if `SECRET_KEY` is the default value or shorter than 32 characters. Use `make generate-secret`.
- **PostgreSQL off the host network** — `5433:5432` port mapping removed; DB is only reachable within the Docker bridge network.
- **LLM endpoint allowlist** — Settings test endpoint validates the provider URL against an approved domain list; stored credentials cannot be forwarded to arbitrary URLs.
- **Spreadsheet formula injection prevented** — All four Excel generators sanitize user-supplied values so `=1+1` is written as literal text, not an active formula. 18 regression tests added.
- **Optional API bearer-token auth** — Set `API_TOKEN` in `.env` to require `Authorization: Bearer <token>` on every request. Unset = no change for home-network use.
- **Stuck-record auto-recovery** — Records left in `processing` state after a crash are automatically reset to `pending` on API startup.
- **Production web container** — `web/Dockerfile` now builds compiled assets (`vite build`) and serves them via `vite preview` instead of the dev server.
- **TypeScript zero-error build** — All 10 pre-existing TS errors resolved; `npm run build` is clean.
- **Centralized `apiFetch` wrapper** — All frontend API calls now throw a typed `ApiError` on non-2xx responses instead of silently treating errors as data.
- **Configurable CORS** — `ALLOWED_ORIGINS` env var replaces hardcoded `localhost:3001`; prevents demo-day failures on non-localhost networks.
- **CI gates** — GitHub Actions runs Ruff lint, pytest, and `tsc --noEmit` on every push/PR to `main`.

### v1.6.2

- **Benchmark scorer fix** — `phi4-mini` and other small models no longer produce artificially low accuracy scores. Three previously unhandled but correct output variations now accepted: flattened JSON keys, `num_cpus` alias, and GB-as-MB memory values.

### v1.6.1

- **Pull from Discovery** — Discovered model cards have a **↓ Pull** button that streams `ollama pull` progress live (SSE) and refreshes the installed models list on completion.
- **Benchmark shortcut** — Each discovered model card has a **⚖ Benchmark** button that pre-fills the Compare Models panel with that candidate vs. the current active model.
- **Current model reference row** — Discover Models shows the active model as a pinned row; candidates scoring higher are highlighted with a green ▲ better badge.
- **Discovery scoring fix** — HuggingFace compound names (`qwen3.6-27b-mtp-gguf`, `deepseek-v4-gguf`) now score correctly via a prefix-match table instead of defaulting to 5/10.
- **Static catalog fallback** — 14 curated models shown when `ollama.com` is unreachable inside Docker.

### v1.6.0

- **Model Discovery** — "🔭 Check for New Models" button in the Local AI Advisor queries the Ollama library and HuggingFace Hub, filters to RAM-compatible structured-JSON models, and presents a ranked list with size, task-fit score, and a ready-to-copy pull command. Results cached 6 hours; Refresh bypasses cache.

### v1.5.0

- **Docker Model Runner** — 6th LLM provider. Built into Docker Desktop ≥ 4.25, OpenAI-compatible, no API key required.
- **Model benchmark** — Compare any two models (Ollama or Docker Model Runner) on 8 synthetic cases; composite score = 50 % accuracy + 50 % speed. Inline scorecard in Settings.
- **HuggingFace GGUF resolver** — `GET /api/settings/resolve-gguf?model=<name>` finds the best quantization on HF Hub and returns the `docker model pull` command.
- **Model catalog fix** — `qwen2.5-coder` and other specialised models now score correctly (≤ 4); `phi4-mini` stays recommended.
- **Validator fix** — Extra sheets in generated RVTools files are now warnings, not errors. All 3 previously failing tests resolved; test suite 120/120.

### v1.4.0
- **Local AI Advisor** — Settings page ranks your installed Ollama models by task-fit and RAM fit; suggests `ollama pull` for better models.
- **Notes field** — Annotate individual server records with free-text practitioner notes (saved to DB, shown in expanded row).
- **Re-normalize single record** — Re-run AI on one record from the Edit modal without resetting the whole project.
- **Bulk op no-op → 422** — Bulk OS Replace / Exclude / Fix Nano Profiles now return a clear error instead of a misleading success banner when nothing matched.
- **LLM empty-response guard** — Records where the AI returns `vinfo: {}` are now marked `error` instead of silently completing with blank export rows.

### v1.3.0

- **PowerVS disk clamping bypass** — IBM VPC boot-volume constraints (100 GB min / 250 GB max) no longer apply to PowerVS records (AIX / IBM i / Linux-on-Power). Customer disk sizes pass through unchanged to the IBM Price Estimator and PowerVS exports. x86 behaviour unchanged.
- **14 new unit tests** — `tests/test_normalizer_disk_clamping.py` covers both x86 clamping and PowerVS pass-through paths.

### v1.2.2

- **UX polish (5 improvements)** — Stale banners cleared on navigation; empty Review state before normalization; bulk modals show expandable accordion with first 10 affected server names; Normalize polling exponential backoff; "Currently processing: `<vm-name>`" shown during normalization.

### v1.2.1

- **Export summary** — Machine-type breakdown (S1022 / E1050 / E1080) shown after IBM Price Estimator populate.
- **Duplicate project** — One-click copy from ⋮ overflow menu.
- **Processing status badge** — Green/amber pill on project cards.
- **Bulk Exclude by filter** — Exclude all matching servers by name substring or OS family.

### v1.2.0

- **Data Domains fix** — `_DATA_DOMAINS_ROWS` expanded from 75 to 174 rows; resolves blank rows in the IBM Cloud Cost Estimator after import.
- **nxf-2x1 and nxf-2x2 added to Data Domains** — Flex-Nano profiles now recognized by the IBM Cloud Solutioning Tool.
- **Flex-Nano profile warning + bulk replace** — Review page detects `nxf-1x*` profiles; "Fix Nano Profiles" upgrades all affected servers in one action.
- **Edit record modal** — Inline editing of 11 vinfo fields with severity indicators; failed records recoverable from raw data.
- **Bulk OS Replace** — Replace OS family on all matching records; logged as assumptions.
- **Folder organization** — Two-level folder hierarchy for project grouping.

### v1.1.0

- **PowerVS Cloud Solution Export**, **PowerVS Cool Tool Export**, **PowerVS RVTools (22-sheet)**, **PowerVS AI Assumptions Report** — Full PowerVS export set.
- **IBM Price Estimator template filler** — Surgical zip-level XML surgery; formulas and named ranges preserved; S1022 / E1050 / E1080 auto-selected.
- **Backup & Restore** — Portable `.json` project bundles; full system `.zip` backup.
- **Multi-provider LLM support** — Ollama (local), IBM watsonx.ai, OpenAI-compatible, Anthropic Claude. AES-256 key encryption.
- **Model recommendations** — One-click apply, rollback, or 7-day snooze.
- **PowerVS region/datacenter per project** — Independent from VPC region.

### v1.0.0 — First stable release

- **Cloud Solution Export** (x86), **RVTools Export (22-sheet)**, **AI Assumptions Report**.
- **IBM VPC boot disk sizing** — 100 GB min / 250 GB max for x86 VSIs; overflow as Data Volume; both cases as documented assumptions.
- **GB → MB unit mismatch detection** — Auto-corrects and logs as assumption.
- **PowerVS auto-detection**, **server exclusion**, **per-project VPC region/zone**.
- **Ollama timeout + retry + Python fallback synthesizer** — records never permanently stuck.
- **Reset stuck endpoint + UI button**.
