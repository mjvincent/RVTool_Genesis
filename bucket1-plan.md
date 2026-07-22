# Bucket 1 — IBM Demo Polish Feature Plan

## Overview

Four features from the original IBM Presentation Readiness Assessment "Phase 3" that have not yet been implemented. All four make the tool more credible and trustworthy in an IBM executive or technical-buyer demonstration.

**Constraints:**
- No new database schema migrations for features 1–3. Feature 4 (audit) adds one new table.
- No changes to existing export formats or workflow logic.
- Each sub-task is independently shippable.
- All work on `main`; each sub-task gets its own commit.

---

## Sub-Task 1 — Migration Readiness Summary Dashboard

**Intent:**
Replace the current per-section counts scattered across the Export page with a single summary banner that shows the complete migration health at a glance. An IBM stakeholder should be able to look at one panel and know: how many servers total, how many are export-ready, how many need attention, and whether the project is ready to export. This is the single highest-impact demo moment called out in the IBM assessment.

**Expected Outcomes:**
- A new API endpoint `GET /projects/{project_id}/readiness-summary` returns all counts in one call:
  - `total` — all server records (any status, any type)
  - `complete_x86` — complete, non-excluded, non-PowerVS records (export-ready for VPC)
  - `complete_powervs` — complete, non-excluded PowerVS records (export-ready for PowerVS)
  - `excluded` — is_excluded=True records
  - `error` — processing_status='error' records
  - `pending` — not yet processed
  - `export_ready` — boolean: complete_x86 > 0 and error == 0
- A summary banner appears at the top of the Export page (above the export cards) showing these counts as Carbon `Tile` stats with coloured indicators (green = good, amber = needs attention, red = blocked).
- The banner shows a clear "Export ready" or "X records need attention" decision line.
- No change to any existing export functionality.

**Todo List:**
1. Add `GET /projects/{project_id}/readiness-summary` endpoint to `api/routers/processing.py`. Compute all counts via a single SQL query using `func.count()` with `FILTER` clauses grouped on `processing_status`, `is_excluded`, and `server_type`. No new DB model required.
2. Add `ReadinessSummary` Pydantic response model with the fields listed above.
3. Add `api.processing.getReadinessSummary(projectId)` to `web/src/api/client.ts` with a matching `ReadinessSummary` TypeScript interface.
4. Add a `ReadinessBanner` component to `web/src/pages/ExportPage.tsx` (or a new `web/src/components/ReadinessBanner.tsx`) that renders the counts as Carbon stat tiles with color-coded status indicators. Use Carbon `Tag` components for the status line (green "Ready to export" / amber "Review needed" / red "Errors blocking export").
5. Fetch the summary on ExportPage load (alongside existing status fetch) and render the banner above the export cards section.

**Relevant Context:**
- `api/routers/processing.py` lines 217–268: existing `getStatus` endpoint — use same DB session pattern.
- `api/db/models.py` lines 113–143: `ServerRecord` fields — `processing_status`, `is_excluded`, `server_type`.
- `web/src/pages/ExportPage.tsx` lines 60–145: existing status fetch and x86/PowerVS count logic — the new summary replaces the ad-hoc count math.
- `web/src/api/client.ts` lines 97–105: `ProcessingStatus` interface — add `ReadinessSummary` alongside it.
- Carbon `Tile` and `Tag` components are already used elsewhere in the codebase.

**Status:** [x] complete

---

## Sub-Task 2 — Upload Mapping Confirmation ✅

**Intent:**
After a spreadsheet is uploaded and parsed, show the user a confirmation step before processing begins: display 5–10 sample rows from the source file alongside the detected column names. This makes "any spreadsheet layout" credible — the user can verify that VM name, CPU, RAM, OS, disk, and cluster columns were correctly detected before committing to the AI normalization run. Currently the user sees only a row count with no visibility into what was detected.

**Expected Outcomes:**
- The upload API response includes two new fields: `columns` (list of detected column names) and `sample_rows` (first 5 rows of raw data as a list of dicts).
- After a successful upload, the Upload page shows a confirmation panel (not a blocker modal — the user can still proceed or cancel) displaying a scrollable preview table of the sample rows.
- Column headers in the preview are the raw detected column names from the source file.
- A "Looks good — proceed to normalize" button takes the user to the Normalize page. A "Re-upload" link clears the state and allows a different file to be chosen.
- No change to how parsing or record storage works — this is metadata only.

**Todo List:**
1. In `api/services/spreadsheet_parser.py`, after parsing, capture `columns` (list of cleaned column names from the header row) and `sample_rows` (first 5 row dicts, excluding `_row_number`). Return these alongside the existing rows list.
2. Update the `UploadResponse` schema (`api/schemas/` or inline in `api/routers/uploads.py`) to include `columns: list[str]` and `sample_rows: list[dict]`.
3. In `api/routers/uploads.py`, pass the parser metadata through to the response.
4. In `web/src/api/client.ts`, update the `UploadResponse` interface to include `columns` and `sample_rows`.
5. In `web/src/pages/UploadPage.tsx`, after a successful upload (currently shows row count + navigate button), render a `MappingPreview` component showing the sample rows table and the "Looks good" / "Re-upload" action buttons.
6. Create `web/src/components/MappingPreview.tsx` — a Carbon `DataTable` (or simple styled table) showing `sample_rows` with `columns` as headers. Keep it lightweight; no editing capability required.

**Relevant Context:**
- `api/services/spreadsheet_parser.py` lines 82–155: parser function — extend return value here.
- `api/routers/uploads.py` lines 28–131: upload handler — modify response model and pass metadata.
- `web/src/pages/UploadPage.tsx` lines 43–58: post-upload state — currently shows row_count and navigates; add preview step here.
- `web/src/api/client.ts` lines around 335–365: upload functions — update `UploadResponse` type.
- The parser already returns a list of cleaned row dicts — the columns are just the keys of the first row dict.

**Status:** [x] complete

---

## Sub-Task 3 — Exception-first Review Queue ✅

**Intent:**
The Review page currently shows all complete non-excluded records by default. For a migration project of any size, the reviewer's attention should go to problems first — failed records, records that used AI fallback synthesis, low-confidence assumptions, and records missing key fields. The happy path (AI normalized successfully with high confidence) should be quiet and easy to get through. This mirrors how IBM migration practitioners actually work.

**Expected Outcomes:**
- A filter/sort bar above the records table has four preset filter buttons: **All**, **Needs attention** (default), **Errors**, **Excluded**.
- "Needs attention" preset shows: error records first, then complete records with any low-confidence assumption or fallback synthesis indicator, then complete records with missing OS/disk/CPU fields.
- "Errors" shows only `processing_status='error'` records.
- "Excluded" shows only `is_excluded=true` records.
- "All" shows every record (current default behaviour preserved).
- The existing search/filter input and sort controls are unchanged.
- A small count badge on each preset button shows how many records match (e.g., "Needs attention (4)").
- The default on page load is **Needs attention** — if zero records need attention, it silently falls back to **All**.

**Todo List:**
1. In `web/src/pages/ReviewPage.tsx`, add a `filterPreset` state (`'attention' | 'errors' | 'excluded' | 'all'`), defaulting to `'attention'`.
2. Define `attentionRecords`: records where `processing_status === 'error'` OR any assumption has `confidence === 'low'` OR `normalized_data` is missing key fields (cpu_count, ram_mb, os_name). Sort within this group: errors first, then low-confidence, then missing fields.
3. Compute `filteredRecords` by applying the active preset to the full record list before the existing search filter is applied.
4. Render four Carbon `Button` (kind="ghost" / kind="primary" for active) filter preset buttons above the records table, each with a count badge using Carbon `Tag`.
5. If `filterPreset === 'attention'` and `attentionRecords.length === 0`, auto-switch to `'all'` and show a green "All records look good" inline notification.
6. The "fallback" indicator: check `r.assumptions` for any entry whose `reasoning` includes the string `"Python synthesizer"` or `"fallback"` — these are the existing fallback markers written by `ai_normalizer.py`.

**Relevant Context:**
- `web/src/pages/ReviewPage.tsx` lines 82–87: existing `failedRecords` / `normalRecords` derived lists — replace with the new preset system.
- `web/src/api/client.ts` lines 107–132: `ServerRecord` and `Assumption` interfaces — `confidence`, `reasoning` fields already present.
- `api/services/ai_normalizer.py` lines 1254–1258: fallback synthesizer writes `"Python synthesizer used"` into assumption reasoning — use this as the fallback detection string.
- No backend changes required — all filtering is client-side on already-fetched records.

**Status:** [x] complete

---

## Sub-Task 4 — Recovery and Audit History

**Intent:**
Add a visible, persistent audit trail for the most consequential user actions: bulk OS replace, bulk exclude, bulk Flex-Nano fix, individual record exclusion/restore, and export generation. The goal is not a full event-sourcing system — it is a simple append-only log table that makes the tool feel governed and traceable, which is exactly what an IBM reviewer expects to see. The log is displayed as a timeline panel on the project's Export page.

**Expected Outcomes:**
- A new `AuditLog` database table stores: `project_id`, `operation` (string enum), `summary` (human-readable description), `record_count` (affected rows), `created_at`.
- The following operations write an audit entry:
  - Bulk OS Replace (N records updated: 'old' → 'new')
  - Bulk Exclude (N records excluded, filter: type=value)
  - Bulk Flex-Nano Fix (N records updated → target profile)
  - Individual record exclusion / restore
  - Export generated (export type, N records, filename)
  - Processing started / completed / failed summary
- A new `GET /projects/{project_id}/audit-log` endpoint returns the log entries for a project, most recent first, capped at 50 entries.
- An **Activity** collapsible panel at the bottom of the Export page displays the audit log as a simple timestamped list (operation + summary + time ago). Uses Carbon `Accordion` to keep it out of the way.
- No undo capability in this sub-task — that is a future feature. The log is read-only.

**Todo List:**
1. Add `AuditLog` model to `api/db/models.py`:
   ```
   id (UUID PK), project_id (FK → projects.id, CASCADE DELETE),
   operation (String, indexed), summary (String), record_count (Integer, nullable),
   created_at (DateTime, server_default=now())
   ```
2. Generate an Alembic migration for the new table: `alembic revision --autogenerate -m "add audit_log table"`.
3. Add a helper function `log_audit(db, project_id, operation, summary, record_count=None)` to a new `api/services/audit.py` — a simple async insert, fire-and-forget (catch and log exceptions, never raise).
4. Call `log_audit()` at the end of each bulk operation handler in `api/routers/uploads.py` and `api/routers/processing.py`, and at export generation in `api/routers/exports.py`.
5. Add `GET /projects/{project_id}/audit-log` endpoint to `api/routers/processing.py` (or a new `api/routers/audit.py`). Returns list of `AuditLogEntry` (id, operation, summary, record_count, created_at), most-recent-first, limit 50.
6. Add `api.processing.getAuditLog(projectId)` to `web/src/api/client.ts` with `AuditLogEntry` interface.
7. Add an `ActivityPanel` collapsible section at the bottom of `web/src/pages/ExportPage.tsx` using Carbon `Accordion`. Each entry renders as: `[operation badge] [summary] — [N records] — [time ago]`.

**Relevant Context:**
- `api/db/models.py` line 284 (end of file): add new model here.
- `api/routers/uploads.py` lines 402–751: bulk operation handlers — add `log_audit()` call at end of each.
- `api/routers/processing.py` lines 271–350: single-record reset/restore — add audit call here too.
- `api/routers/exports.py` lines 409–413: export generation log line — pair with `log_audit()`.
- `web/src/pages/ExportPage.tsx` lines 674–676: bottom of page before closing tag — add Activity panel here.
- Carbon `Accordion` already used in `BulkNxfModal.tsx` — reuse the same import pattern.
- Alembic migration pattern: see `api/alembic/versions/` for existing examples.

**Status:** [ ] pending

---

## Implementation Order

Sub-tasks are independent and can be shipped one at a time. Recommended order:

1. **Sub-Task 3** first — entirely client-side, zero backend changes, immediately visible
2. **Sub-Task 2** — small backend extension + new UI component
3. **Sub-Task 1** — new API endpoint + new UI banner component
4. **Sub-Task 4** last — requires DB migration, most touch points

---

## Validation Checklist

- [ ] Readiness banner shows correct counts for a project with mixed statuses
- [ ] "Export ready" indicator is green when all records are complete and no errors
- [ ] "X errors blocking export" indicator is red when error records exist
- [ ] Upload confirmation preview shows correct column names from source spreadsheet
- [ ] Upload preview shows 5 sample rows matching the source file content
- [ ] "Re-upload" clears state; "Looks good" navigates to Normalize page
- [ ] Review page defaults to "Needs attention" filter on load
- [ ] "Needs attention" shows error records first, then low-confidence, then missing fields
- [ ] If zero attention records, page silently shows all records with a green notice
- [ ] Each filter preset button shows correct count badge
- [ ] Audit log entries appear after each bulk operation
- [ ] Audit log entries appear after export generation
- [ ] Activity panel on Export page shows entries most-recent-first
- [ ] All existing tests still pass
- [ ] TypeScript typecheck: 0 errors
