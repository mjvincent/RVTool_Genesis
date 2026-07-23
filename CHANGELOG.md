# Changelog

All notable changes to RVTool Genesis are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) conventions.
Versions are tagged on `main`; each section maps to one or more git commits.

---

## [Unreleased]

---

## [2.3.1] — 2026-07-23

### Fixed

- **Settings page no longer hangs when Ollama is unreachable** — The mount
  `Promise.all` is now wrapped in a 4-second `Promise.race` timeout. If Ollama
  or the recommendation endpoint is slow or down, the page renders within 4
  seconds and the Ollama advisor section shows a clear "Could not reach Ollama"
  message instead of an indefinite spinner.
  (`web/src/pages/SettingsPage.tsx`)

- **Cancel normalization button** — A "Cancel normalization" button is now
  visible on the Normalize page while a job is running. Clicking it calls the
  backend cancel endpoint, stops the polling loop, and shows a confirmation
  notification. The worker finishes the current record and then stops.
  (`web/src/api/client.ts` — added `cancel()`; `web/src/pages/NormalizePage.tsx`)

- **`already_running` response handled on NormalizePage** — If a second "Start"
  click is made while a job is already running, the page silently attaches to
  the existing job via polling instead of showing confusing duplicate feedback.
  (`web/src/pages/NormalizePage.tsx`)

- **MappingPreview empty/error states** — Upload preview now shows a clear
  warning when no records are detected (wrong file or empty sheet) and an info
  notice when rows were detected but no sample data could be generated, rather
  than a blank table.
  (`web/src/components/MappingPreview.tsx`)

- **ProjectsPage silent status failures surfaced** — When a per-project status
  fetch fails, the project card now shows a subtle "—" indicator with a tooltip
  ("Status unavailable") instead of showing nothing, so coworkers don't mistake
  a network hiccup for an unnormalized project.
  (`web/src/pages/ProjectsPage.tsx`)

---

## [2.3.0] — 2026-07-21

### Added

- **PostgreSQL-backed durable job queue** — AI normalization processing now uses a
  persistent `processing_jobs` table instead of FastAPI `BackgroundTasks`. Jobs
  survive API container restarts; the worker loop polls for pending jobs using
  `SELECT … FOR UPDATE SKIP LOCKED` to prevent duplicate scheduling. Stale
  `in_progress` jobs are automatically re-queued on startup (5-minute timeout).
  A new `POST /projects/{id}/processing/cancel` endpoint requests graceful
  cancellation after the current record finishes.
  (`api/db/models.py` — `ProcessingJob` model;
  `api/alembic/versions/h2i3j4k5l6m7_add_processing_jobs_table.py` — migration;
  `api/services/job_worker.py` — worker loop, claim, re-queue logic;
  `api/routers/processing.py` — updated `start_processing`, new `cancel_processing`;
  `api/main.py` — worker task started in lifespan)

### Fixed

- **Ruff lint gate widened to full `api/`** — CI `lint-python` job now runs
  `ruff check api/` instead of 9 specific files. All pre-existing violations in
  `ai_normalizer`, `model_catalog`, `exports`, `crypto`, and other modules resolved.
- **Accessible Exclude checkbox** — The Exclude control in the records table now
  carries an `aria-label` identifying the server by name (e.g. "Exclude prod-web-01
  from exports") for screen reader users.
- **XLSX zip-bomb and row-count guards** — `parse_spreadsheet` now rejects XLSX
  files whose ZIP members have a decompression ratio > 100× or total uncompressed
  size > 500 MB, and files with more than 100,000 data rows. 7 unit tests added.
  (`api/services/spreadsheet_parser.py`;
  `tests/test_upload_guards.py`)

---

## [2.2.0] — 2026-07-21

### Added

- **Audit History — Activity panel on Export page** — Every consequential user
  action is now recorded in a persistent, project-scoped audit log. The following
  operations write an entry: Bulk OS Replace, Bulk Flex-Nano Fix, Bulk Exclude,
  and Cloud Solution Export generation. A collapsible "Activity (N)" panel at
  the bottom of the Export page shows all entries most-recent-first with an
  operation badge, summary text, record count, and timestamp. The panel is
  hidden when no entries exist.
  A new `GET /projects/{project_id}/audit-log` endpoint returns the 50 most
  recent entries. A new `AuditLog` database table stores all entries; the
  corresponding Alembic migration (`g1h2i3j4k5l6`) creates the table with a
  composite index on `(project_id, created_at)`.
  (`api/db/models.py` — `AuditLog` model;
  `api/alembic/versions/g1h2i3j4k5l6_add_audit_log_table.py` — migration;
  `api/services/audit.py` — `log_audit()` fire-and-forget helper;
  `api/routers/processing.py` — `GET /audit-log` endpoint;
  `api/routers/uploads.py` — audit calls on bulk OS/NXF/exclude;
  `api/routers/exports.py` — audit call on VPC Calculator export;
  `web/src/api/client.ts` — `AuditLogEntry` interface + `getAuditLog()`;
  `web/src/pages/ExportPage.tsx` — Activity panel)

---

## [2.1.0] — 2026-07-21

### Added

- **Migration Readiness Summary Banner** — A summary banner now appears at the
  top of the Export page showing the full migration health at a glance before
  any export is attempted. The banner displays six stat tiles (Total servers,
  x86 ready, PowerVS ready, Pending, Errors, Excluded) with colour-coded
  values, and a single decision line: green "✓ Ready to export", amber warning
  when processing is incomplete, or red "✗ N records need attention" when errors
  exist. The banner is green only when at least one x86 record is complete and
  zero error records exist.
  A new `GET /projects/{project_id}/readiness-summary` endpoint computes all
  counts in a single SQL query grouped by processing_status, is_excluded, and
  server_type — no additional database schema changes required.
  (`api/routers/processing.py` — `ReadinessSummary` model + endpoint;
  `web/src/api/client.ts` — `ReadinessSummary` interface + `getReadinessSummary()`;
  `web/src/pages/ExportPage.tsx` — readiness banner)

---

## [2.0.0] — 2026-07-21

### Added

- **Exception-first Review Queue** — The Review page now defaults to a
  "Needs attention" filter preset that surfaces problem records first: error
  records appear at the top, followed by complete records with low-confidence
  AI assumptions or fallback synthesis, then records missing key fields (CPU,
  RAM, OS). Four preset filter buttons with count badges — **Needs attention**
  (default), **Errors**, **Excluded**, **All** — sit above the records table.
  If zero records need attention on load, the page silently shows all records
  with a green "All records look good" notification. Existing search, sort, and
  bulk operation controls are unchanged.
  (`web/src/pages/ReviewPage.tsx`, `web/src/components/RecordsTable.tsx`)

- **Upload Mapping Confirmation** — After a spreadsheet is uploaded, a column
  preview panel appears before the user proceeds to normalize. The panel shows
  the detected column names and up to 5 sample rows from the source file,
  allowing the user to verify that VM name, CPU, RAM, OS, disk, and cluster
  columns were correctly detected. "Looks good — proceed to normalize" continues
  the workflow; "Re-upload different file" clears state for a fresh upload.
  The backend now returns `columns` and `sample_rows` on every upload response.
  (`api/services/spreadsheet_parser.py`, `api/schemas/upload.py`,
  `api/routers/uploads.py`, `web/src/api/client.ts`,
  `web/src/pages/UploadPage.tsx`, `web/src/components/MappingPreview.tsx`)

---

## [1.9.0] — 2026-07-21

### Security

- **`billing_type` allowlist enforced** — `VPCCalculatorRequest.billing_type` is now typed as
  `Literal["PAYG", "1 Yr Reserved", "3 Yr Reserved"]`. Previously accepted any string and
  silently wrote it to the Excel workbook. Invalid values now return HTTP 422 with a clear
  validation error from Pydantic.
  (`api/routers/exports.py`)

- **Containers run as non-root** — Both `api/Dockerfile` and `web/Dockerfile` now create a
  dedicated `appuser` system account and switch to it before running the process. Previously
  both containers ran as root, which violates container security best practices and is flagged
  by IBM security tooling.
  (`api/Dockerfile`, `web/Dockerfile`)

- **Dependency audit in CI** — Two new GitHub Actions jobs run on every push/PR:
  `pip-audit` scans Python dependencies for known CVEs; `npm audit --audit-level=moderate`
  scans frontend dependencies. Vulnerable dependency versions will now block merges.
  (`.github/workflows/ci.yml`)

### Dependencies

- **Python dependencies updated** — All pinned versions bumped to latest stable:
  `fastapi` 0.115.0 → 0.115.14, `uvicorn` 0.30.6 → 0.34.3, `sqlalchemy` 2.0.35 → 2.0.41,
  `alembic` 1.13.3 → 1.15.2, `asyncpg` 0.29.0 → 0.31.0, `psycopg2-binary` 2.9.9 → 2.9.12,
  `python-multipart` 0.0.12 → 0.0.32, `python-dotenv` 1.0.1 → 1.2.2,
  `pydantic-settings` 2.5.2 → 2.14.2, `httpx` 0.27.2 → 0.28.1,
  `cryptography` 43.0.3 → 44.0.3, `pytest` 8.3.3 → 9.1.1,
  `pytest-asyncio` 0.24.0 → 1.4.0.
  `pandas` and `openpyxl` held at current versions (2.2.3 / 3.1.5) — pandas 3.x is a
  major version bump requiring validation against all export generators.
  (`api/requirements.txt`)

---

## [1.8.0] — 2026-07-21

### Added

- **Billing type selection on Cloud Solution Export** — Clicking "Download Cloud Solution export"
  now opens a modal with three radio button options before generating the workbook:
  `PAYG` (default), `1 Yr Reserved`, and `3 Yr Reserved`. The chosen value is written
  to every Billing Type cell in the Project Settings sheet of the IBM Cloud Cost Estimator
  workbook. Previously hardcoded to `PAYG`.
  (`web/src/pages/ExportPage.tsx` — billing type modal;
  `web/src/api/client.ts` — `generateVPCCalculator()` body;
  `api/routers/exports.py` — `VPCCalculatorRequest` body model;
  `api/services/vpc_calculator_generator.py` — `billing_type` parameter)

### Fixed

- **`setup.sh` auto-generates `SECRET_KEY` on first run** — Previously `setup.sh` copied
  `.env.example` verbatim, leaving the known-insecure default key. Since v1.7.0 the API
  hard-fails on that default, causing a crash on every fresh install. `setup.sh` now
  generates a strong 64-character hex key automatically after creating `.env`, using
  `openssl rand -hex 32` (macOS/Linux/Git Bash/WSL) with a `python3 secrets` fallback
  for Windows environments where `openssl` is unavailable. Users with an existing `.env`
  are unaffected.
  (`setup.sh`)

- **README Quick Start updated** — Documents the auto-generated `SECRET_KEY` and explains
  how to rotate it (`make generate-secret`) for users who need to share or redeploy.
  (`README.md`)

---

## [1.7.0] — 2026-07-21

### Security

- **SECRET\_KEY enforcement** — The API now refuses to start if `SECRET_KEY` is set to
  the known default value or is shorter than 32 characters. Previously this was a logged
  warning only. Use `make generate-secret` to generate a compliant key.
  (`api/main.py`)

- **PostgreSQL not exposed to host network** — Removed the `5433:5432` port mapping from
  `docker-compose.yml`. The database is now only reachable within the internal Docker
  bridge network (`api → db:5432`). Direct external connections to the DB are no longer
  possible.

- **LLM settings test endpoint — endpoint allowlist** — `POST /api/settings/test` now
  validates the provider URL against an approved domain list before making any outbound
  connection. Stored credentials cannot be forwarded to arbitrary URLs supplied in the
  request body. Approved domains: `localhost`, `host.docker.internal`, `api.openai.com`,
  `api.anthropic.com`, IBM WatsonX regional endpoints.
  (`api/routers/settings.py` — `_APPROVED_ENDPOINT_HOSTS`, `_assert_approved_endpoint()`)

- **Spreadsheet formula injection prevented** — All four Excel export generators now pass
  user-supplied string values through a `sanitize_cell()` helper that prefixes
  formula-trigger characters (`=`, `+`, `-`, `@`) with a single-quote, preventing
  formula execution when exported workbooks are opened in Excel or LibreOffice Calc.
  18 regression tests added.
  (`api/services/export_utils.py`; `rvtools_generator.py`, `assumptions_generator.py`,
  `vpc_calculator_generator.py`, `powervs_calculator_generator.py`)

- **Optional API bearer-token authentication** — A `require_token` FastAPI dependency is
  now applied to all routers. When `API_TOKEN` is not set (the default for home-network
  use), the dependency is a no-op and behaviour is unchanged. When set, every request
  must include `Authorization: Bearer <token>`. The health endpoint is excluded.
  (`api/core/auth.py`, `api/core/config.py`, `api/main.py`)

### Reliability

- **Stuck-record auto-recovery on startup** — On API startup, any `ServerRecord` rows
  left in `processing_status = 'processing'` from a previous container crash are
  automatically reset to `'pending'`. Previously these required a manual reset API call.
  (`api/main.py` lifespan function)

### Build and tooling

- **Production web container** — `web/Dockerfile` now builds a production asset bundle
  (`tsc && vite build`) and serves it via `vite preview`. Previously the container ran
  the Vite development server (`vite --host`) with HMR, source maps, and dev overlays.
  The `docker-compose.override.yml` dev workflow (`npm run dev`) is unchanged for local
  development.

- **TypeScript zero-error build** — Fixed 10 TypeScript errors: `BulkNxfModal.tsx`
  missing `previewNames` destructure, `NormalizePage.tsx` unbound `err` variable in
  catch block. `npm run build` (`tsc && vite build`) now completes with zero errors.

- **Centralized API fetch wrapper** — All 41 frontend API calls now use a shared
  `apiFetch()` helper that throws a typed `ApiError` on any non-2xx response. Previously
  37 of 41 calls parsed the JSON body without checking HTTP status, causing server errors
  to silently appear as malformed data.
  (`web/src/api/client.ts`)

- **Configurable CORS origins** — `ALLOWED_ORIGINS` env var (comma-separated list)
  replaces the hardcoded `http://localhost:3001`. Prevents demo-day failures when
  the app is accessed from a non-localhost address on the same network.
  (`api/core/config.py`, `api/main.py`)

- **Vite and esbuild upgraded** — Vite upgraded from 5.4.8 to 8.x and
  `@vitejs/plugin-react` upgraded to v6. Resolves 2 moderate/high CVEs in the esbuild
  development server. `npm audit` reports zero vulnerabilities.

- **CI gates** — GitHub Actions workflow (`.github/workflows/ci.yml`) added with three
  jobs: Python lint (Ruff), Python unit tests (pytest), and TypeScript typecheck
  (`tsc --noEmit`). Runs on push and PR to `main`. Matching `make lint`, `make typecheck`
  Makefile targets added.

- **`make generate-secret` target** — Generates a strong `SECRET_KEY` value and prints
  the `.env` line ready to paste. Replaces the previous manual `python3 -c "import
  secrets..."` instruction.

---

## [1.6.2] — 2025-07-21

### Fixed
- **Benchmark scorer false negatives** — Small models produced artificially low accuracy
  scores (e.g. phi4-mini at 35.7%) due to three legitimate-but-unhandled output variations:
  (1) flattened JSON — model emits top-level `cpus`/`memory_mb` instead of `vinfo.cpus`/
  `vinfo.memory_mb`; (2) key aliasing — model emits `num_cpus` instead of `cpus`;
  (3) GB-as-MB — model returns `memory_mb: 32` (GB) instead of `memory_mb: 32768` (MB)
  despite the prompt instruction. All three are now accepted as correct. Wrong values
  (e.g. cpus=4 when expected=8) are still rejected.
  (`api/services/model_benchmarker.py` — `_FIELD_ALIASES`, `_resolve_field()`,
  `score_response()` numeric tolerance)

---

## [1.6.1] — 2025-07-21

### Added
- **Ollama Pull from Discovery** — Each discovered model card now has a **↓ Pull** button
  (Ollama-source models only). Clicking it streams the Ollama `/api/pull` response as
  Server-Sent Events, displaying a live progress bar (`↓ 42%`) and status line. On
  completion the Installed Models list and discovery results refresh automatically.
  (`api/routers/settings.py` — `POST /api/settings/pull-model`;
  `web/src/pages/SettingsPage.tsx` — `pullOllamaModel()`)

- **Benchmark shortcut from Discovery** — Every discovered model card has an
  **⚖ Benchmark vs phi4-mini** button that pre-fills the Compare Models selectors with
  the current active model as Model A and the candidate as Model B, opens the Compare
  Models panel, and scrolls to it.
  (`web/src/pages/SettingsPage.tsx`)

- **Current model reference row** — The Discover Models section now shows the active
  Ollama model (e.g. `phi4-mini`) as a pinned reference row with its task-fit score, so
  discovered candidates can be compared at a glance. Candidates scoring higher are
  highlighted with a green `▲ better` badge and green border.
  (`api/routers/settings.py` — `current_model` + `current_task_fit` added to response;
  `web/src/api/client.ts` — `DiscoveryResponse` updated;
  `web/src/pages/SettingsPage.tsx`)

### Fixed
- **Discovery scoring always 5/10** — `_score_model_name()` was missing a prefix-match
  step for HuggingFace compound names. `qwen3.6-27b-mtp-gguf` now scores 9,
  `deepseek-v4-gguf` scores 9, `gemma-4-26b-it-gguf` scores 8 (was all 5).
  Added `_FAMILY_PREFIX_SCORES` ordered prefix table and rewrote the three-step lookup.
  (`api/services/model_catalog.py`)

- **Discovery empty when Ollama.com unreachable** — Docker containers cannot route to
  `ollama.com` by default, leaving the discovery list empty. Added
  `_OLLAMA_STATIC_CATALOG` (14 curated entries: phi4, qwen3:8b, qwen3:14b, qwen2.5:7b,
  qwen2.5:14b, llama3.2:3b, llama3.3, mistral-small, mistral-nemo, gemma3:4b, gemma3:12b,
  deepseek-r1:7b, etc.) used as fallback when the live API is unreachable. Changed sort
  from `newest` → `popular` so live results surface well-known models first.
  (`api/services/model_catalog.py`)

- **Missing model families in task-fit table** — Added `qwen3`, `qwen3.6`, `llama3/4`,
  `gemma4`, `deepseek-v3/v4/r1/r2`, `mistral-small`, `command-r` and `gemma-4`/`gemma-3`
  hyphenated HuggingFace prefix variants to `_OLLAMA_TASK_FIT` and `_FAMILY_PREFIX_SCORES`.
  (`api/services/model_catalog.py`)

---

## [1.6.0] — 2025-07-21

### Added
- **Model Discovery — "Check for New Models"** — The Local AI Advisor card on the Settings
  page now contains a **"🔭 Check for New Models"** button. Clicking it queries two live
  model registries — the **Ollama library** (`ollama.com/api/search`) and **HuggingFace Hub**
  (`huggingface.co/api/models?filter=gguf`) — and presents a ranked list of not-yet-installed
  models filtered to those that fit in the host's available RAM and are suited for structured
  JSON extraction. Results include the model name, source badge (ollama / huggingface), size,
  task-fit score (1–10), pull count, a one-line description, and a ready-to-copy
  `ollama pull` / `docker model pull` command. Registry reachability warnings are shown if
  either source is offline. Results are cached 6 hours in-process; a "↻ Refresh" button
  bypasses the cache. The feature is best-effort — if both registries are unreachable the
  page degrades gracefully with an empty list and an informational message.
  (`api/services/model_catalog.py` — `discover_models()`, `DiscoveredModel`, helpers;
  `api/routers/settings.py` — `GET /api/settings/discover-models`;
  `web/src/api/client.ts` — `DiscoveredModel`, `DiscoveryResponse`, `discoverModels()`;
  `web/src/pages/SettingsPage.tsx` — Discover Models section in Local AI Advisor card)

---

## [1.5.0] — 2025-07-20

### Added
- **Docker Model Runner provider** — Docker Model Runner (Docker Desktop ≥ 4.25) is now
  a full 6th LLM provider. No API key required. Configure via the Settings page with the
  base URL (`http://host.docker.internal:9545`) and model name (e.g. `ai/phi4-mini` or
  `hf.co/<org>/<model>-GGUF`). Uses the OpenAI-compatible `/v1/chat/completions` API.
  DB migration `49d19351b26a` adds `dmr_base_url` and `dmr_model` to `llm_settings`.
  (`api/db/models.py`, `api/schemas/settings.py`, `api/services/ai_normalizer.py`,
  `api/routers/settings.py`, `web/src/pages/SettingsPage.tsx`)

- **Model benchmark feature** — New `POST /api/settings/benchmark-models` endpoint runs
  8 synthetic server records through two LLM models and returns a scored comparison
  report. Scoring is 50 % accuracy + 50 % speed (latency ceiling 30 s). Both models
  can use any backend independently (Ollama or Docker Model Runner), enabling
  same-model-different-runtime comparisons. A "Compare Models" inline section is now
  available in the Local AI Advisor card on the Settings page: select two models, choose
  backends, run, and get a side-by-side scorecard with winner badge and recommendation
  sentence.
  (`api/services/model_benchmarker.py`, `api/routers/settings.py`,
  `api/schemas/settings.py`, `web/src/pages/SettingsPage.tsx`, `web/src/api/client.ts`)

- **HuggingFace Hub GGUF resolver** — New `GET /api/settings/resolve-gguf?model=<name>`
  endpoint queries the HuggingFace Hub API to find the best GGUF quantization
  (Q4_K_M → Q5_K_M → Q4_0 → Q8_0 in priority) for any model name. Returns the
  `docker model pull hf.co/...` command ready to copy. Results cached 1 hour in-process.
  Optional `HF_TOKEN` env var for higher rate limits. When the benchmark "Compare Models"
  section has Docker Model Runner selected as Model B's backend, a "🔍 Find on
  HuggingFace" link appears that calls this endpoint and shows the pull command inline.
  (`api/services/model_catalog.py`, `api/routers/settings.py`, `web/src/api/client.ts`)

### Fixed
- **Model catalog misranking bug** — `qwen2.5-coder:1.5b` and other code-specialised
  models (`codellama`, `deepseek-coder`, `starcoder`, `codegemma`) were inheriting high
  task-fit scores (9/10) from their parent `qwen2.5` family via a broken prefix-match
  fallback. They now score ≤ 4 explicitly. Embedding models (`nomic-embed-text`,
  `mxbai-embed`, `all-minilm`) score 1–2. Unknown models default to 5 (neutral) instead
  of 1 (worst). A runtime suffix-cap guard (`_SPECIALISED_SUFFIXES`) catches any future
  `*-coder`, `*-embed`, `*-vision`, `*-vl`, `*-math`, `*-ocr` model not yet in the table.
  (`api/services/model_catalog.py`)

- **RVTools validator over-strict on extra sheets** — The validator was rejecting generated
  files as `valid: False` if they contained any sheets beyond the 4 IBM-required ones
  (`vInfo`, `vNetwork`, `vPartition`, `vHost`). Real RVTools exports always contain 20+
  sheets; the IBM import tool ignores all but the 4 required. Extra sheets are now a
  `warnings` entry, not an `errors` entry, so `valid` correctly reflects whether the
  required structure is present.
  (`api/services/validator.py`)

- **3 previously failing tests resolved** — `test_generator_and_validator`,
  `test_export_before_processing_fails`, and `test_delete_project` all now pass.
  Root cause: the validator's extra-sheet hard error caused the first test to fail,
  which polluted fixture state and cascaded to the others. Test suite: 120/120 passing.

### Tests
- **14 new unit tests** — `tests/test_model_catalog.py` covers: coder model ranking,
  embedding model ranking, `phi4-mini` recommended when installed alongside coder models,
  pull suggestion suppression when a good model is installed, unknown model neutral default.

---

## [1.4.0] — 2025-07-17

### Added
- **Local AI Advisor** — Settings page now shows a "Local AI Advisor" card when Ollama
  is the active provider. On load it reads Docker container CPU/RAM, checks Ollama
  `/api/tags` for installed models, ranks them by task-fit score and RAM fit, and
  recommends the best model for structured JSON extraction. Shows a `ollama pull`
  command when a better model is available. 24-hour cache with a manual Refresh button.
  (`api/routers/settings.py`, `api/services/model_catalog.py`,
  `web/src/pages/SettingsPage.tsx`)
- **Notes field on server records** — Practitioners can now add free-text annotations
  to individual server records (e.g. "confirmed decommissioned", "dependency on X").
  Notes are editable in the Edit Record modal and displayed in the expanded row on the
  Review page. DB migration `a2b3c4d5e6f7` adds `notes TEXT NULL` to `server_records`.
  (`api/db/models.py`, `api/schemas/upload.py`, `api/routers/uploads.py`,
  `web/src/components/EditRecordModal.tsx`, `web/src/components/RecordsTable.tsx`)
- **Re-normalize single record** — Edit Record modal now has a "Re-normalize this
  record with AI" link at the bottom of any completed record. Clicking it shows an
  inline confirmation, then resets and re-runs AI normalization for just that one
  record without affecting any others.
  (`web/src/components/EditRecordModal.tsx`)

### Fixed
- **Bulk operation no-op now returns HTTP 422** — Bulk OS Replace, Fix Nano Profiles,
  and Bulk Exclude previously returned HTTP 200 with `updated_count: 0` when no
  records matched the filter, showing a misleading green success banner. They now
  return HTTP 422 with a descriptive error message; the existing error banner in each
  modal handles it automatically.
  (`api/routers/uploads.py`)
- **Empty LLM response marked as error** — When the AI normalizer returns an empty
  `vinfo: {}` or a response missing all three anchor fields (`vm_name`, `cpus`,
  `memory_mb`), the record is now marked `processing_status = "error"` instead of
  silently completing. The error message directs the user to Edit & fix manually.
  (`api/routers/processing.py`)

---

## [1.3.0] — 2025-07-17

### Fixed
- **PowerVS disk clamping bypass** — IBM Cloud VPC boot-volume constraints
  (100 GB minimum / 250 GB maximum) no longer apply to PowerVS (AIX / IBM i /
  Linux-on-Power) records. The customer's raw disk size is passed through unchanged
  to the IBM Price Estimator and all PowerVS exports. x86 VPC clamping behaviour
  is unaffected. Detection uses both the LLM `server_type` field and `_is_powervs_os()`
  on `os_config` as a belt-and-suspenders guard.
  (`api/services/ai_normalizer.py` — `_sanitize_numeric_fields`)

### Added
- **14 new unit tests** for disk-clamping behaviour
  (`tests/test_normalizer_disk_clamping.py`) — 6 x86 tests confirming clamping
  still fires, 8 PowerVS tests confirming raw pass-through for AIX, IBM i,
  Linux-on-Power (SAP), and the `os_config` guard path.

---

## [1.2.2] — 2025-07-17

### Added
- **UX polish — 5 improvements** across the Review, Normalize, and bulk-operation flows:
  - Stale error/success banners now clear on page navigation (ReviewPage, UploadPage,
    NormalizePage unmount cleanup).
  - Review page shows an info banner instead of a blank table when no records have been
    normalized yet.
  - All three bulk-operation modals (Bulk OS Replace, Fix Nano Profiles, Bulk Exclude)
    now display a collapsible Carbon Accordion section listing the first 10 affected
    server names before confirmation, with an "…and N more" overflow label.
  - Normalize polling adds exponential backoff after 3 consecutive API failures
    (interval doubles up to a 30 s cap, resets to 2 s on success).
  - Normalize page shows "Currently processing: `<vm-name>`" below the progress bar
    while a record is in-flight (backend: `current_record_name` added to
    `ProcessingStatusResponse`).

---

## [1.2.1] — 2025-07-16

### Added
- **Export summary panel** — After populating the IBM Price Estimator, the Export
  page displays a machine-type breakdown card (S1022 / E1050 / E1080 counts).
  Response headers `X-Written-Count`, `X-Skipped-Count`, and `X-Machine-Counts`
  added to the pricing template endpoint.
- **Duplicate project** — One-click project copy from the ⋮ overflow menu. Copies
  name, description, folder, VPC and PowerVS region/datacenter settings, and the
  stored pricing template if one exists.
- **Processing status badge** — Project cards on the Projects page show a green
  "✓ Complete" pill or an amber "N / M normalized" pill based on parallel
  `Promise.allSettled()` status fetches.
- **Bulk Exclude by filter** — New "Bulk Exclude" button on the Review page.
  Filter by server name substring or OS family; all matching active records are
  excluded atomically with a documented assumption per record. Live preview count
  updates as you type.

---

## [1.2.0] — 2025-07-15

### Added
- **Flex-Nano profile warning + bulk replace** — Review page shows a warning
  banner when any x86 server resolves to an `nxf-1x1`, `nxf-1x2`, or `nxf-1x4`
  profile not recognized by the IBM Cloud Solutioning Tool. "Fix Nano Profiles"
  button upgrades all affected servers to `nxf-2x1` or `nxf-2x2` in one action;
  change is logged as an assumption.
- **Edit record modal** — Any normalized record can be edited inline from the
  Review table. 11 editable vinfo fields with critical (red) and advisory (yellow)
  severity indicators. Failed records can be pre-filled from raw spreadsheet data
  and promoted to `complete` on manual edit.
- **Bulk OS Replace** — Replace the OS family on all records matching a chosen
  value in one operation; changes are logged as assumptions.
- **Folder organization** — Two-level folder hierarchy (Root → Customer →
  Engagement). Create, rename, delete folders; move projects between folders.

### Fixed
- **Data Domains coverage** — `_DATA_DOMAINS_ROWS` expanded from 75 to 174 rows
  covering all non-Flex IBM VPC profile families (`bx2-*`, `cx2-*`, `mx2-*`,
  `bx3d-*`, `cx3d-*`, `mx3d-*`, `ux2d-*`, `gx2-*`, `gx3-*`, `vx2d-*`, `ox2-*`).
  Resolves blank rows in the IBM Cloud Cost Estimator after import.
- **nxf-2x1 / nxf-2x2 added to Data Domains** — Flex-Nano profiles now recognized
  by the IBM Cloud Solutioning Tool.

---

## [1.1.0] — 2025-07-14

### Added
- **PowerVS Cloud Solution Export** — 3-sheet IBM PowerVS Calculator workbook
  (Project Settings, Exceptions, Data Domains). PowerVS equivalent of the x86
  Cloud Solution Export; direct upload to IBM PowerVS Cost Estimator.
- **PowerVS Cool Tool Export** — 4-sheet RVTools workbook for IBM Cool PowerVS
  pricing. Must be uploaded to IBM Cool separately from the x86 export.
- **PowerVS RVTools Export (22-sheet)** — Full 22-sheet format for VCF
  Migration Lite.
- **PowerVS AI Assumptions Report** — Assumptions for PowerVS records only.
- **IBM Price Estimator template filler** — Upload the IBM Power Virtual Server
  Price Estimator `.xlsx` once per project. Click "Populate & Download" to fill
  the yellow input cells from PowerVS records using surgical zip-level XML surgery
  (preserves all formulas, named ranges, and VML drawings). Machine type
  auto-selected: S1022 / E1050 / E1080.
- **Backup & Restore** — Download any project as a portable `.json` bundle; full
  system `.zip` backup; restore on any instance without re-normalization.
- **Multi-provider LLM support** — Settings page: Ollama (local, default),
  IBM watsonx.ai, OpenAI-compatible, Anthropic Claude. AES-256 Fernet encryption
  for all cloud API keys at rest.
- **Model recommendations** — Auto-detect available model upgrades per provider;
  one-click apply, rollback, or 7-day snooze.
- **PowerVS region/datacenter per project** — Independent from VPC region; set
  at project creation; editable on the Export page.

---

## [1.0.0] — 2025-07-10 — First stable release

### Added
- **Cloud Solution Export** — 3-sheet IBM Cloud Cost Estimator workbook (Project
  Settings, Exceptions, Data Domains). Profiles x86 servers onto IBM VPC Flex
  instances. Eliminates the need for the `rvtools2vpc` web tool.
- **RVTools Export (22-sheet)** — Full 22-tab format required by VCF Migration
  Lite and IBM Cool.
- **AI Assumptions Report** — Every AI inference documented with field, assumed
  value, original value, reasoning, and confidence.
- **IBM VPC profile selection** — Flex-Compute (`cxf`), Flex-Balanced (`bxf`),
  Flex-Memory (`mxf`) selected automatically from CPU/RAM ratio.
- **IBM VPC boot disk sizing** — Boot disk clamped to 100 GB minimum / 250 GB
  maximum per IBM VPC rules (x86 VSIs only). Overflow written as a separate Data
  Volume row. Both cases recorded as documented assumptions.
- **`total_disk_mb` field** — Full original disk size preserved before boot cap
  so the Data Volume is never lost when the boot disk is clamped.
- **GB → MB unit mismatch detection** — Auto-corrects raw GB values in MB fields;
  cross-checked against raw column names; fix logged as assumption.
- **PowerVS OS families** — Eight IBM Cool PowerVS OS families (`AIX`, `IBM i`,
  `IBM i MOL`, `Linux BYOL`, `SAP SUSE`, `SAP Red Hat`, `Red Hat GP`, `SUSE GP`)
  mapped at normalize time and written to the RVTools exports.
- **`Operating System VS` column** — Cloud Solution Export populates the IBM VPC
  stock image name for every x86 row including SAP and SQL Server variants.
- **PowerVS auto-detection** — AIX and IBM i OS designate records as
  `server_type = "powervs"` automatically, enforced in both LLM and fallback paths.
- **Server exclusion** — Exclude checkbox in Review table; optional reason stored
  in DB; Excluded Servers audit sheet in AI Assumptions Report.
- **Per-project VPC region/zone** — 15 regions, all standard zones.
- **Ollama timeout + retry + Python fallback synthesizer** — Records never get
  permanently stuck. 120 s timeout, one retry, then Python synthesizer using 64
  column-name synonyms.
- **Reset stuck endpoint + UI button** — One-click recovery from stuck
  normalization without needing the terminal.
- **VERSION file** — Single source of truth at repo root.

---

[Unreleased]: https://github.com/mjvincent/RVTool_Genesis/compare/v1.3.0...HEAD
[1.3.0]: https://github.com/mjvincent/RVTool_Genesis/compare/v1.2.2...v1.3.0
[1.2.2]: https://github.com/mjvincent/RVTool_Genesis/compare/v1.2.1...v1.2.2
[1.2.1]: https://github.com/mjvincent/RVTool_Genesis/compare/v1.2.0...v1.2.1
[1.2.0]: https://github.com/mjvincent/RVTool_Genesis/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/mjvincent/RVTool_Genesis/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/mjvincent/RVTool_Genesis/releases/tag/v1.0.0
