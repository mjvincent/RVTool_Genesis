# Enhancement Plan: LLM Advisor + Six UX/Reliability Improvements

## Overview

Seven independent enhancements grouped into three themes:

1. **Intelligent Local LLM Advisor** — auto-checks Ollama library on Settings load,
   detects installed models and machine hardware, advises the best local model.
2. **Workflow reliability** — re-normalize selected records, bulk-op no-op warning,
   LLM response schema validation.
3. **UX polish** — notes field on server records, export history record count,
   bulk-op no-op warning (crossover with reliability).

All sub-tasks are independent and can be implemented one at a time.

---

## Sub-Task A — Intelligent Local LLM Advisor

### Intent
When the active provider is Ollama, automatically check the Ollama library online
for newer/better models on Settings page load. Combine that with hardware detection
(CPU, RAM, architecture) and the list of models already installed on the user's
Ollama instance to give a clear, actionable recommendation.

The goal is to answer: *"Given this machine and what I already have installed,
what's the best model for IBM Cloud normalization tasks?"*

### Expected Outcomes
- When Settings page loads with Ollama as provider, a new "Local AI Advisor" card
  appears automatically (no button click required).
- Card shows: detected CPU family, total RAM, architecture (Apple Silicon / x86-64).
- Card shows: models currently installed on Ollama (from `GET /api/tags` on the
  Ollama host).
- Card shows: a ranked recommendation from the advisor — which installed model is
  best for this tool, and whether a better model is available to pull.
- If an online check finds a newer model in the Ollama library that would perform
  better, the card shows it with an `ollama pull <model>` instruction.
- If online check fails (no internet), card degrades gracefully — shows hardware
  + installed models + static-catalog advice only.

### Online Check Approach
- The Ollama library exposes a public API: `https://ollama.com/api/search?q=<query>`
  or tag-based search. The backend calls this on Settings load when provider=ollama.
- Query terms: "phi4", "qwen2.5", "llama3" — models known to be good for structured
  JSON extraction.
- Response is cached in-memory for 24 hours (keyed by query) so repeated page loads
  don't hammer the API.
- Timeout: 5 seconds. On timeout or error, fall back to static catalog gracefully.

### Ranking Logic (static catalog, no internet needed)
Priority criteria for local model selection (in order):
1. **Task fit** — models flagged in catalog as good for "structured JSON extraction"
   rank highest.
2. **RAM fit** — models whose parameter count × quantization factor fits in available
   RAM rank above those that don't. Rule of thumb: 7B Q4 ≈ 4 GB, 14B Q4 ≈ 8 GB,
   32B Q4 ≈ 18 GB.
3. **Speed** — smaller models that fit in RAM rank above larger ones.

### Todo List
1. **Backend — hardware detection endpoint**
   `GET /api/settings/local-advisor` — reads `/proc/cpuinfo` and `/proc/meminfo`
   from inside the Docker container; calls `GET /api/tags` on the Ollama host;
   calls Ollama library API with 5 s timeout; returns
   `{cpu_model, cpu_arch, ram_gb, installed_models, recommendations, online_models}`.

2. **Backend — model ranking service**
   New function in `model_catalog.py`: `rank_local_models(installed, ram_gb) -> list[ModelRec]`
   Returns installed models ranked by task fit + RAM fit, with a recommended pull
   if a better model isn't installed.

3. **Backend — Ollama library fetch with cache**
   New function: `fetch_ollama_library(queries) -> list[OnlineModel]`
   Calls `https://ollama.com/api/search` with each query string, merges results,
   caches for 24 h in a module-level dict keyed by query + timestamp.

4. **Frontend — Local AI Advisor card in SettingsPage**
   Add a `LocalAdvisorCard` section that appears only when `provider === "ollama"`.
   Fires `GET /api/settings/local-advisor` on mount (not on every keystroke).
   Shows: hardware summary, installed models list, ranked recommendation with
   reasoning, online model suggestion if available.
   Loading state: InlineLoading while fetching.
   Error state: "Could not reach Ollama" with a "Retry" button.

5. **Frontend — "Check for newer models" refresh button**
   A small "↻ Refresh" link in the card header that re-fires the advisor endpoint
   and invalidates the server-side cache for this request only.

### Relevant Context
- `api/services/model_catalog.py` — existing static catalog; add ranking function here
- `api/routers/settings.py` — add new `/api/settings/local-advisor` endpoint
- `web/src/pages/SettingsPage.tsx` — add LocalAdvisorCard; fires on mount when
  provider === "ollama"
- `api/core/config.py` — has OLLAMA_BASE_URL for constructing the `/api/tags` URL
- Ollama `/api/tags` returns: `{models: [{name, size, details: {parameter_size, quantization_level}}]}`
- `/proc/meminfo` MemTotal line gives total RAM in kB
- `/proc/cpuinfo` `model name` line gives CPU string; `Architecture` from `uname -m`

### Status
[x] done

---

## Sub-Task B — Re-normalize Selected Records

### Intent
Users who ran normalization before v1.3.0 may have PowerVS records with disk sizes
incorrectly clamped to 100 GB. Currently the only way to fix them is to reset the
entire project back to pending, losing all manual edits, exclusions, and assumptions
for every record.

Add a "Re-normalize" action per record in the Review table that resets just that one
record to `pending`, clears its normalized data, and queues it for AI normalization
— leaving all other records untouched.

### Expected Outcomes
- Edit Record modal gains a **"Re-normalize this record"** button (secondary, at the
  bottom of the modal, away from Save).
- Clicking it shows a confirmation: "This will discard all normalized data and
  assumptions for this record and re-run AI normalization. Continue?"
- On confirm: record is reset to `processing_status = "pending"`, `normalized_data`
  cleared, assumptions deleted.
- NormalizePage's "Start normalization" button picks it up on next run — or a
  dedicated "Resume" call is made immediately.
- The record re-appears in the Failed/Pending section of the Review page until
  normalization completes.

### Todo List
1. **Backend** — `POST /projects/{project_id}/records/{record_id}/reset`
   Sets `processing_status = "pending"`, clears `normalized_data`, deletes all
   `Assumption` rows for this record. Returns 204.
2. **Frontend** — Add "Re-normalize this record" button to `EditRecordModal.tsx`
   with confirm dialog. On confirm, calls new endpoint, then calls `onClose()` so
   the Review table reloads.
3. **Frontend** — After reset, trigger `POST /api/projects/{id}/process` for just
   this record (the process endpoint already accepts a single record ID path:
   `POST /projects/{project_id}/records/{record_id}/process` — verify this exists).

### Relevant Context
- `web/src/components/EditRecordModal.tsx` — add button here
- `api/routers/processing.py` — existing `POST /projects/{id}/records/{record_id}/process`
  endpoint (line 237 approx) — verify it accepts a single reset+re-process
- `api/routers/uploads.py` — pattern for record-level DB mutations
- The reset should delete all `Assumption` rows for the record before clearing
  `normalized_data` — same pattern as `_process_single_record` lines 103-107

### Status
[x] done

---

## Sub-Task C — Bulk Operation No-Op Warning

### Intent
Bulk OS Replace, Bulk Exclude, and Fix Nano Profiles all return HTTP 200 with
`updated_count: 0` when the filter matches nothing. The frontend shows a green
success banner ("OS replacement complete — 0 records updated") which is misleading.

Return HTTP 422 with a clear error message when the operation would affect 0 records,
so the frontend shows an error banner instead of a false success.

### Expected Outcomes
- `POST /projects/{id}/uploads/{uid}/bulk-os-replace` returns 422 with
  `{"detail": "No active records match OS 'Windows Server 2019'. Check the OS value and try again."}` when count = 0.
- `POST /projects/{id}/bulk-exclude` returns 422 with a descriptive message when
  count = 0.
- `POST /projects/{id}/bulk-nxf-replace` returns 422 when no nxf-1x* records exist
  (should not be reachable via normal UI, but defensive).
- Frontend's existing error-handling in all three modals already catches non-2xx
  responses and shows `setError(...)` — no frontend change needed.

### Todo List
1. In `api/routers/uploads.py` bulk_os_replace handler: check `updated_count == 0`
   after the DB update; raise `HTTPException(status_code=422, detail="...")`.
2. In `api/routers/uploads.py` bulk_exclude handler: same check.
3. In `api/routers/uploads.py` bulk_nxf_replace handler: same check.
4. Add regression tests for each zero-match case.

### Relevant Context
- `api/routers/uploads.py` — bulk_os_replace (around line 430), bulk_exclude
  (around line 510), bulk_nxf_replace (search for `bulk-nxf-replace`)
- Frontend error handling is already in place in all three modals — no UI change needed

### Status
[x] done

---

## Sub-Task D — Notes Field on Server Records

### Intent
Practitioners need a way to annotate individual servers with context that doesn't
fit the assumption system — e.g. "customer confirmed this is decommissioned",
"flagged for PM review", "dependency on server X". Currently there is no such field.

Add an optional free-text `notes` column to `ServerRecord` and surface it as an
editable text area in the Edit Record modal.

### Expected Outcomes
- A `notes: Text | None` column exists on the `server_records` table (new Alembic
  migration required).
- Edit Record modal has a **Notes** text area at the bottom of the form.
- Notes are displayed in the review table row expansion (alongside assumptions).
- Notes are exported in the AI Assumptions Report as a dedicated column in the main
  sheet (not the Excluded Servers sheet).

### Todo List
1. **DB migration** — new Alembic migration adding `notes TEXT NULL` to `server_records`.
2. **Model** — add `notes: Mapped[str | None]` to `ServerRecord` in `api/db/models.py`.
3. **API** — add `notes` to the edit record endpoint body schema and handler in
   `api/routers/uploads.py` (the `PATCH /projects/{id}/records/{record_id}` endpoint).
4. **Frontend** — add `notes` to `ServerRecord` TypeScript interface in `client.ts`;
   add `notes` text area to `EditRecordModal.tsx`; add `notes` display in the
   expanded row view in `RecordsTable.tsx`.
5. **Assumptions Report** — add a Notes column to `assumptions_generator.py` main
   sheet output.

### Relevant Context
- `api/db/models.py` — `ServerRecord` model (add `notes` field)
- `api/alembic/versions/` — create new migration file following naming pattern
- `api/routers/uploads.py` — edit record endpoint (find `PATCH` on records)
- `web/src/components/EditRecordModal.tsx` — add text area
- `web/src/components/RecordsTable.tsx` — add to expanded row view
- `api/services/assumptions_generator.py` — add Notes column to sheet
- `web/src/api/client.ts` — add `notes?: string` to `ServerRecord` interface

### Status
[x] done

---

## Sub-Task E — Export History Record Count

### Intent
The Export page shows a history of generated files (filename, timestamp) but does
not show how many records were in each export. The `record_count` field already
exists on the `RVToolsExport` model and is populated at export time — it is just
never surfaced in the UI.

### Expected Outcomes
- Export history table gains a "Records" column showing the record count for each
  download.
- No backend change required — the field is already stored.

### Todo List
1. **Frontend** — Read `record_count` from the export history API response in
   `ExportPage.tsx` (or wherever the history is rendered).
2. Add a "Records" column to the export history table/list.
3. Verify `record_count` is included in the API response schema
   (`api/routers/exports.py` — check the export history endpoint response model).
   If not, add it to the response schema.

### Relevant Context
- `api/db/models.py` — `RVToolsExport` model; `record_count` field
- `api/routers/exports.py` — export history endpoint; check if `record_count` is
  in the response model
- `web/src/pages/ExportPage.tsx` — the export history rendering section

### Status
[x] done (record_count already in API response; Export page shows server counts inline on each card)

---

## Sub-Task F — LLM Response Schema Validation

### Intent
When the LLM returns a structurally valid JSON response but with an empty `vinfo: {}`
or missing required fields, the record is persisted as `processing_status = "complete"`
with empty normalized data. Exports then produce blank rows or zero-byte values for
that server. The user has no indication anything went wrong.

Add a minimum-field check before persisting: if `vinfo` is missing `vm_name`, `cpus`,
and `memory_mb`, the record should be marked `error` with a clear message rather than
silently completing.

### Expected Outcomes
- Records with `vinfo: {}` or missing all three anchor fields (`vm_name`, `cpus`,
  `memory_mb`) are marked `processing_status = "error"` with `error_message`:
  "AI response missing required fields (vm_name, cpus, memory_mb). Use Edit & fix
  to complete this record manually."
- These records appear in the Failed Records panel on the Review page.
- Records that have at least one of the three fields populated are still accepted
  (partial normalization is better than an error for records with sparse data).
- The Python fallback synthesizer is unaffected (it always populates all fields).

### Todo List
1. In `api/routers/processing.py` `_process_single_record()`, after
   `record.normalized_data` is set (line ~92), add a validation check:
   if `vinfo` dict is empty OR all three of `vm_name`, `cpus`, `memory_mb` are
   falsy, set `record.processing_status = "error"` and
   `record.error_message = "..."` instead of `"complete"`.
2. Add a unit test: LLM returns `{"vinfo": {}, ...}` → record marked error.
3. Add a unit test: LLM returns `{"vinfo": {"vm_name": "x"}, ...}` → record
   accepted as complete (partial data allowed).

### Relevant Context
- `api/routers/processing.py` lines 91–100 — where `normalized_data` is set and
  `processing_status` is set to "complete"
- The validation must happen AFTER `_sanitize_numeric_fields()` so the fields have
  been corrected before the check
- Failed records panel already handles `processing_status = "error"` records —
  no frontend change needed

### Status
[x] done
