# RVTool Genesis — Failed Record UX & Missing Data Visibility Plan

## Top-Level Overview

Three targeted improvements to address the issues visible in the two screenshots:

1. **Human-readable error messages** — translate raw Python exception text into plain English; also fix the underlying `'str' object has no attribute 'get'` bug in the AI normalizer
2. **"Edit manually" escape hatch for failed records** — add an Edit button to each failed-record row in the Failed panel; the Edit modal pre-populates from raw_data with best-effort field mapping AND shows the original raw data alongside for reference
3. **Missing-data call-to-action in the records table** — records with empty critical fields get a visible amber warning icon and "fields need attention" prompt in the expanded row detail, directing the user to the Edit modal

---

## Sub-Tasks

---

### Sub-Task 1: Fix the normalizer bug + human-readable error messages

**Intent:** The `'str' object has no attribute 'get'` crash happens in `_sanitize_numeric_fields` when the LLM returns a `vnetwork` or `vpartition` list containing strings instead of dicts. Line 528 guards `vpartition` but the crash occurs at line 109 of `processing.py` when iterating `assumption_data.get(...)` on a string element in the assumptions list. The fix makes the code resilient; the UI translates any remaining Python exceptions into plain English.

**Expected Outcomes:**
- `'str' object has no attribute 'get'` no longer appears — the normalizer handles malformed LLM output gracefully
- Failed records show messages like "The AI returned an unexpected response format. Use Retry or Edit manually." instead of raw Python tracebacks
- A translation map converts known exception patterns to human sentences

**Todo List:**
1. In `api/routers/processing.py` line 109, add a guard: `if not isinstance(assumption_data, dict): continue` before accessing `.get()` on each assumption item. This is the direct cause of the crash.
2. In `api/services/ai_normalizer.py` `_sanitize_numeric_fields()`, add a type guard for the `assumptions` list items (line 564): ensure every element is a dict before appending.
3. In `web/src/components/FailedRecordsPanel.tsx`, add a `translateError(msg: string): string` function that maps known Python exception patterns to plain English:
   - `'str' object has no attribute 'get'` → "The AI returned data in an unexpected format. Use Retry or Edit manually to fix this record."
   - `JSONDecodeError` / `json.decoder` → "The AI response could not be parsed. Use Retry — the AI may succeed on a second attempt."
   - `timeout` / `ConnectError` / `ConnectionRefused` → "Could not reach the AI service. Check that Ollama is running and use Retry."
   - `KeyError` → "A required field was missing from the AI response. Use Retry or Edit manually."
   - Any message starting with `'` and containing `object has no attribute` → "The AI returned unexpected data types. Use Retry or Edit manually."
   - Fallback for anything else: show the message as-is but without monospace styling (treat as a human sentence)
4. Apply `translateError()` to the displayed error text in the panel rows.

**Relevant Context:**
- `api/routers/processing.py` lines 109-123: the assumption iteration loop — add dict guard at line 109
- `api/services/ai_normalizer.py` line 564: `result["assumptions"] = list(...) + new_assumptions` — ensure new_assumptions only contains dicts
- `web/src/components/FailedRecordsPanel.tsx` lines 135, 162-167: where `errMsg` is displayed

**Status:** `[ ] pending`

---

### Sub-Task 2: "Edit manually" button on failed records + raw data sidebar in Edit modal

**Intent:** When retry fails (or the user doesn't want to wait), they need a direct path to enter values manually. The Edit button opens EditRecordModal pre-populated with best-effort values mapped from raw_data. The modal shows the original raw spreadsheet data alongside the form fields so the user can cross-reference and fill in anything the auto-map missed.

**Expected Outcomes:**
- Each failed-record row in `FailedRecordsPanel` gains an "Edit manually" button alongside Retry
- `EditRecordModal` can accept an optional `prefillFromRaw: boolean` prop — when true and `normalized_data` is absent or empty, it pre-populates vinfo fields by running a client-side best-effort mapping of `raw_data` keys
- A collapsible "Original spreadsheet data" panel appears at the bottom of the Edit modal showing all `raw_data` key-value pairs (excluding `_row_number`) in a read-only table — always visible for failed records, collapsed by default for normal records
- After the user saves a manually-entered record, the record's `processing_status` stays as `complete` (the PATCH endpoint already sets this correctly via normalized_data update) — the record drops off the Failed panel and appears in the main table

**Todo List:**
1. In `web/src/components/FailedRecordsPanel.tsx`:
   - Import `EditRecordModal`
   - Add state: `editTarget: ServerRecord | null`
   - Add "Edit manually" button (kind="ghost", size="sm", renderIcon=Edit) next to each row's Retry button
   - On save: call `onRecordFixed(recordId, updated)` — same callback as retry success — which removes the record from the failed panel in real-time
2. In `web/src/components/EditRecordModal.tsx`:
   - Add helper `prefillFromRaw(rawData: Record<string, any>): Record<string, any>` that maps common raw column names to vinfo keys using a priority-ordered lookup table:
     - `vm_name`: look for `name`, `Server Name`, `VM Name`, `Hostname`, `vm_name`, `hostname`, `server`
     - `cpus`: look for `CPU`, `vCPU`, `CPUs`, `vCPUs`, `Cores`, `cpu_count`, `cpus`
     - `memory_mb`: look for `Memory`, `Memory (MB)`, `RAM`, `RAM (MB)`, `memory_mb` — if value looks like GB (< 512), multiply by 1024
     - `provisioned_mb`: look for `Disk`, `Storage`, `Provisioned`, `Disk (MB)`, `provisioned_mb`, `storage_gb` — if looks like GB multiply by 1024
     - `os_config`: look for `OS`, `Operating System`, `Guest OS`, `os`, `os_config`
     - `datacenter`: look for `Datacenter`, `DC`, `datacenter`
     - `cluster`: look for `Cluster`, `cluster`
   - When `record.normalized_data` is null/empty AND `prefillFromRaw` prop is true, use `prefillFromRaw(record.raw_data)` as the initial fields state instead of `{}`
   - Add a collapsible "Original spreadsheet data" section at the bottom of the modal:
     - Render all `raw_data` entries (excluding `_row_number`) as a 2-column read-only table (key | value)
     - Collapsed by default for normal records (with `normalized_data`), expanded by default for failed records (no `normalized_data`)
     - Title: "Original data from Row {n} in your spreadsheet" or "Original spreadsheet data" if no row number
3. In `web/src/components/RecordsTable.tsx`, in the inline Retry button (AI Decisions column for failed rows), also add a small "Edit" icon button next to Retry that opens EditRecordModal for that record directly from the table row.

**Relevant Context:**
- `web/src/components/FailedRecordsPanel.tsx` lines 129-199: row render — add Edit button after Retry
- `web/src/components/EditRecordModal.tsx` lines 68-90: `useEffect` that sets initial fields — add prefill logic here
- `web/src/components/EditRecordModal.tsx` lines 95+: modal body — add raw data panel at bottom
- `web/src/components/RecordsTable.tsx` lines 282-300: AI Decisions column for failed rows

**Status:** `[ ] pending`

---

### Sub-Task 3: Missing-data call-to-action in the records table

**Intent:** Records that normalized successfully but are missing critical field values (empty RAM, empty OS, etc.) currently show `—` with no call to action. The user needs a visual signal and a direct path to fix the problem.

**Expected Outcomes:**
- Records with any empty critical vinfo fields (vm_name, cpus, memory_mb, provisioned_mb, os_config) show an amber warning badge in the "AI Decisions" column: "⚠ N fields missing"
- The expanded row detail for incomplete records shows a banner: "Some fields could not be determined. Click 'Edit this record' to fill them in manually — refer to Row N in your spreadsheet."
- The "Edit this record" link in the expanded row (already present) becomes more prominent (Button kind="primary" size="sm") when the record has missing fields, normal styling otherwise
- Row number is shown in the expanded detail: "Source: Row N in your spreadsheet" — displayed for all records that have `_row_number`, not just failed ones

**Todo List:**
1. In `web/src/components/RecordsTable.tsx`:
   - Add a `getMissingCriticalFields(r: ServerRecord): string[]` helper that checks `normalized_data.vinfo` for null/empty/zero values in `['vm_name', 'cpus', 'memory_mb', 'provisioned_mb', 'os_config']` and returns the list of missing field names
   - In the row data mapping (lines 125-150), compute `missingCount` and add it as `_missingCount` to the row object
   - In the AI Decisions column render (lines 282-317): for non-failed rows with `missingCount > 0`, show an amber `⚠ {n} missing` badge (instead of or alongside the assumptions count)
   - In the expanded row detail for non-failed records (lines 338-390): add a banner at the top when `missingCount > 0`: "⚠ {n} field(s) could not be determined. Refer to Row {n} in your spreadsheet and click 'Edit this record' to fill them in."
   - In the expanded detail, always show "Source: Row N in your spreadsheet" when `raw_data._row_number` is present
   - Make the "Edit this record" button `kind="primary"` when `missingCount > 0`, `kind="ghost"` otherwise

**Relevant Context:**
- `web/src/components/RecordsTable.tsx` lines 125-150: row data mapping
- `web/src/components/RecordsTable.tsx` lines 282-317: AI Decisions column
- `web/src/components/RecordsTable.tsx` lines 338-400: expanded row detail — currently shows datacenter/cluster/power state/etc.
- `web/src/components/RecordsTable.tsx` lines 394-410: "Edit this record" button render

**Status:** `[ ] pending`

---

## Implementation Notes

### Order: 1 → 2 → 3
Sub-Task 1 (bug fix) should go first so the error messages are correct before Sub-Task 2 (UI changes referencing them). Sub-Task 3 is independent.

### No DB migration needed
All changes are either in-memory (UI logic) or in existing JSONB fields. The `processing_status` update when saving a manually-edited record is handled by the existing PATCH endpoint — after a successful PATCH the record's `processing_status` remains `error` unless we also update it. **Important:** The PATCH endpoint should set `processing_status = "complete"` when a manual save is applied to a failed record so it moves off the failed panel. This needs a one-line change in `api/routers/uploads.py`.

### "Edit manually" saves a failed record to complete
When a user manually fills in fields and hits Save on a failed record, the PATCH endpoint currently only updates `normalized_data`. We need it to also set `processing_status = "complete"` and `error_message = None` when the record's current status is `error`. This allows the record to "graduate" out of the failed state without re-running the AI.
