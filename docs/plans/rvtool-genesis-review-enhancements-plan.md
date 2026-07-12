# RVTool Genesis — Review Page Enhancements Plan

## Top-Level Overview

Four related improvements to the Review step and AI normalization workflow:

1. **OS Swap** — Individual and bulk replacement of OS values, tracked as assumptions
2. **Failed Records Panel** — Pinned section at the top of Review showing all failed records with error reasons, row numbers, and inline retry
3. **Row Number Tracking** — Preserve original spreadsheet row number through parsing so errors can be traced back to the source file
4. **Missing Field Highlighting** — Visual indicators in EditRecordModal for empty critical and advisory fields

All changes are data-safe: existing records are unaffected until a user explicitly acts. OS swaps are permanent but documented via assumptions. Row numbers are additive metadata stored in `raw_data._row_number`.

---

## Sub-Tasks

---

### Sub-Task 1: Row Number Tracking

**Intent:** Preserve the original Excel/CSV row number (absolute, matching what Excel shows in the row gutter) through the parsing pipeline so that failed records and the Edit modal can display "Row 7 in your spreadsheet" to help users locate and fix problems in the source file.

**Expected Outcomes:**
- `raw_data` for every new record contains `_row_number` (int, absolute Excel row — header row = 1, first data row = 2 or later)
- Existing records without `_row_number` degrade gracefully (UI shows "Row unknown")
- Row number is displayed in the failed-records panel and in the EditRecordModal header

**Todo List:**
1. In `api/services/spreadsheet_parser.py` `parse_spreadsheet()`, track the absolute row index during `df.iterrows()`. The absolute row = the header row offset + 1 (for header) + the pandas positional row index. Store as `_row_number` key in each row dict before appending to `rows`.
2. No DB migration needed — `raw_data` is already JSONB and stores arbitrary dicts. The new key is purely additive.
3. In `web/src/components/EditRecordModal.tsx`, read `record.raw_data._row_number` and display "Source: Row {n} in your spreadsheet" in the modal subheading (below the server name). If absent, display nothing.
4. Propagate `_row_number` into the failed-records panel (Sub-Task 2 consumes it).

**Relevant Context:**
- `api/services/spreadsheet_parser.py` lines 140-148: `for _, row in df.iterrows()` — change `_` to `row_idx` and add `record['_row_number'] = row_idx + 2` (+ 1 for 0-based, + 1 again for the header row itself). This gives the correct absolute Excel row.
- For CSV with `header=0`, the first data row has pandas index 0, so Excel row = 0 + 2 = 2. This is correct.
- If the parser re-reads with `header=1` (title row skip), the pandas index still starts at 0 for the first data row but the actual Excel row is 3 (title=1, header=2, data starts=3). The offset becomes `row_idx + 3`. The header detection path (lines 101-116) needs to track the header row offset (0 or 1) and pass it to the row-number calculation.

**Status:** `[ ] pending`

---

### Sub-Task 2: Failed Records Panel

**Intent:** Pin a collapsible "Failed Records" section at the top of the Review page that shows all records where `processing_status === 'error'`. Each entry shows the server name (or "Unknown server"), the original spreadsheet row number, the error message from the AI, and a Retry button. On successful retry the record is immediately removed from the failed panel and the main table refreshes to show it in the correct position.

**Expected Outcomes:**
- Failed panel appears above the RecordsTable when any records have `processing_status === 'error'`
- Panel is collapsed by default if there are more than 3 failures (prevent overwhelming the page), expanded by default if 1-3 failures
- Each row in the panel shows: server name | Row N | error reason | Retry button
- Retry success: record removed from failed panel in real-time, main table reloaded
- Retry failure: error message updated inline on that row
- `error_message` is now returned by the GET `/records` API (currently missing from `ServerRecordResponse`)
- "Retry all failed" button at panel header retries all failed records serially

**Todo List:**
1. **API schema fix:** Add `error_message: str | None` to `ServerRecordResponse` in `api/schemas/upload.py`. This is the only backend change needed — the field already exists on the model and is already set by the processing router.
2. **Frontend type fix:** Add `error_message: string | null` to the `ServerRecord` interface in `web/src/api/client.ts`.
3. **Create `FailedRecordsPanel` component** (`web/src/components/FailedRecordsPanel.tsx`):
   - Props: `records: ServerRecord[]`, `projectId: string`, `onRecordFixed: (recordId: string, updated: ServerRecord) => void`
   - State: retrying set, per-record retry errors, collapsed bool (default collapsed if count > 3)
   - Calls `api.processing.retryRecord()` per record; on success calls `onRecordFixed`
   - Carbon `Accordion` or simple toggle div for collapse
   - Each row: server name (from `raw_data` or `normalized_data`), row number from `raw_data._row_number`, error_message truncated to 120 chars with expand toggle, Retry button (InlineLoading when retrying)
   - "Retry all" button calls each retry sequentially
4. **Update ReviewPage** to render `FailedRecordsPanel` above `RecordsTable`, wired to `onRecordFixed` callback that re-fetches the updated record and merges it into the records list.
5. **Update RecordsTable**: Remove the existing `InlineNotification` warning banner for failed records (it's superseded by the new panel). Keep the pink row highlight and inline retry on the row itself as a secondary affordance.

**Relevant Context:**
- `api/schemas/upload.py` lines 20-32: Add `error_message: str | None` field
- `api/routers/uploads.py` `ServerRecordResponse.model_validate(record)` — will auto-include the new field since `from_attributes=True`
- `web/src/components/RecordsTable.tsx` lines 161-169: existing banner to remove
- `web/src/pages/ReviewPage.tsx` lines 60-67: RecordsTable usage — add FailedRecordsPanel above it
- `web/src/api/client.ts` `ServerRecord` interface (lines 41-54)

**Status:** `[ ] pending`

---

### Sub-Task 3: Missing Field Highlighting in EditRecordModal

**Intent:** When a user opens the Edit modal for a record that has empty/null/zero values in important fields, highlight those fields so the user knows to fill them in before exporting. Critical fields (vm_name, cpus, memory_mb, provisioned_mb, os_config) get a red warning border. Advisory fields (datacenter, cluster, nics, disks) get a yellow border. in_use_mb is always advisory. A banner at the top of the modal counts how many fields need attention.

**Expected Outcomes:**
- Edit modal shows "X field(s) need attention" banner when any required/advisory fields are empty
- Critical empty fields have red left-border indicator and red label text
- Advisory empty fields have yellow left-border indicator
- `in_use_mb` is always yellow-advisory if zero (since 60% of 0 is still 0)
- Fields with values show no extra styling
- Row number shown in the modal subheading

**Todo List:**
1. In `VINFO_FIELDS` array in `web/src/components/EditRecordModal.tsx`, add a `required: true` property to the critical fields: `vm_name`, `cpus`, `memory_mb`, `provisioned_mb`, `os_config`.
2. Add a helper function `isFieldEmpty(field, value)` that returns `'critical' | 'advisory' | null`:
   - Returns `'critical'` if field is in the critical set AND value is null/empty/0
   - Returns `'advisory'` if field is advisory AND value is null/empty/0
   - Returns `null` if the field has a value
3. Compute `warningCount` = count of fields where `isFieldEmpty` returns non-null.
4. Render an `InlineNotification` warning banner at the top of the modal body if `warningCount > 0`: "N field(s) need attention — check fields highlighted below before exporting."
5. Wrap each field in a `div` with conditional border-left styling based on `isFieldEmpty` result:
   - Critical: `borderLeft: '3px solid #da1e28'` (Carbon red-60)
   - Advisory: `borderLeft: '3px solid #f1c21b'` (Carbon yellow-30)
6. Show the source row reference in the modal: read `record.raw_data._row_number`, render "Source: Row {n} in your spreadsheet" as a small grey subheading below the server name. If absent, omit.

**Relevant Context:**
- `web/src/components/EditRecordModal.tsx` lines 14-30: `VINFO_FIELDS` array
- `web/src/components/EditRecordModal.tsx` lines 88-149: modal body render
- Carbon color tokens: `#da1e28` = red-60 (critical), `#f1c21b` = yellow-30 (advisory)

**Status:** `[ ] pending`

---

### Sub-Task 4: OS Swap — Individual and Bulk

**Intent:** Allow users to change the OS of individual records (via EditRecordModal) or replace all records matching a given OS with a different OS (bulk). The purpose is pricing — e.g. replace all Windows Server 2019 with CentOS Linux (free) to produce a lower-cost estimate. Changes are permanent updates to `os_config` (and `os_vmware_tools`) in `normalized_data`, documented as a new assumption entry so the Assumptions Report records the swap.

**Expected Outcomes:**
- EditRecordModal `os_config` field becomes a dropdown of all 40+ IBM-standard OS strings (instead of free text)
- OS column is added to the RecordsTable so users can see OS at a glance without opening each record
- A "Bulk OS Replace" button appears on the Review page header
- BulkOSModal: select source OS (dropdown of distinct OS values present in the project), select target OS (dropdown of all IBM-standard OS values), confirmation count, Apply button
- Bulk replace calls a new API endpoint `POST /projects/{id}/bulk-os-replace` with `{from_os, to_os}` body; returns count of updated records
- The API endpoint updates `os_config` + `os_vmware_tools` on all matching non-excluded records and inserts a new `Assumption` row per record documenting the swap with `confidence: 'medium'`
- After bulk replace, the Review table refreshes showing the new OS values

**Todo List:**
1. **Backend — bulk OS replace endpoint** in `api/routers/uploads.py`:
   - `POST /projects/{project_id}/bulk-os-replace` accepts `{ from_os: str, to_os: str }`
   - Queries all non-excluded `ServerRecord` rows for the project where `normalized_data->'vinfo'->>'os_config' = from_os`
   - Updates `os_config` and `os_vmware_tools` in `normalized_data.vinfo`
   - Creates one `Assumption` record per affected server: `field_name='vinfo/os_config'`, `assumed_value=to_os`, `original_value=from_os`, `reasoning='User-initiated bulk OS replacement for pricing purposes.'`, `confidence='medium'`
   - Returns `{ updated_count: int, from_os: str, to_os: str }`
2. **Frontend type** — add `bulkOsReplace` method to `api.uploads` in `web/src/api/client.ts`
3. **OS constants** — create `web/src/constants/osOptions.ts` exporting `IBM_OS_OPTIONS: string[]` — the full list of 40+ IBM-standard OS strings (mirrors `_OS_NORMALIZATION` output values from the Python normalizer, deduplicated). This is the single source of truth for the OS dropdown in both EditRecordModal and BulkOSModal.
4. **EditRecordModal** — change `os_config` field from `TextInput` to `Select` using `IBM_OS_OPTIONS`. Keep a "Custom / other" option at the bottom that falls back to a `TextInput` for edge cases.
5. **RecordsTable** — add `OS` column between `storage_gb` and `exclude_col`. Truncate long OS strings to ~30 chars with a tooltip. This column is sortable.
6. **Create `BulkOSModal` component** (`web/src/components/BulkOSModal.tsx`):
   - Props: `projectId: string`, `records: ServerRecord[]`, `onClose: () => void`, `onApplied: () => void`
   - "Replace OS" dropdown: distinct OS values currently present in the project's records (computed from props)
   - "With OS" dropdown: full `IBM_OS_OPTIONS` list
   - Preview: "This will update N records"
   - Calls `api.uploads.bulkOsReplace()` on submit
   - On success: calls `onApplied()` which triggers a record reload in ReviewPage
7. **ReviewPage** — add "Bulk OS Replace" button in the page header actions area. Opens BulkOSModal. On applied, reload records.

**Relevant Context:**
- `api/services/ai_normalizer.py` lines 283-334: `_OS_NORMALIZATION` list — the target values (right side of tuples) are the IBM-standard strings to use in `IBM_OS_OPTIONS`
- `api/routers/uploads.py`: Add new endpoint following existing patterns (select, update, commit)
- `api/db/models.py` `Assumption` model: fields `field_name`, `assumed_value`, `original_value`, `reasoning`, `confidence`, `server_record_id`, `project_id`
- `web/src/components/EditRecordModal.tsx` lines 20-21: `os_config` field currently `type: 'text'`
- `web/src/components/RecordsTable.tsx` lines 17-26: `headers` array — add OS column
- Carbon JSONB update pattern: use SQLAlchemy `func.jsonb_set` or Python-side merge on `normalized_data` dict

**Status:** `[ ] pending`

---

## Implementation Notes

### Order of Sub-Tasks
Sub-Tasks should be implemented in order: 1 → 2 → 3 → 4. Row numbers (1) are consumed by Failed Panel (2) and Edit Modal (3). Sub-Task 4 (OS Swap) is fully independent and can be done last.

### No New DB Migrations Needed for Sub-Tasks 1-3
- Sub-Task 1: `raw_data` is JSONB — additive key only affects new uploads
- Sub-Task 2: `error_message` is already in the DB; schema change is API response only
- Sub-Task 3: UI-only change
- Sub-Task 4: Uses existing `Assumption` table for tracking; new API endpoint only

### Existing Records (pre-feature)
- Records uploaded before Sub-Task 1 will have no `_row_number` in `raw_data` — UI shows nothing for row reference (not an error)
- Records processed before Sub-Task 2 already have `error_message` in the DB — it will be returned once the schema is updated
