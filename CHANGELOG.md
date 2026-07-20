# Changelog

All notable changes to RVTool Genesis are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) conventions.
Versions are tagged on `main`; each section maps to one or more git commits.

---

## [Unreleased]

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
