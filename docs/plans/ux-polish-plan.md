# UX Polish — Plan

## Overview

Five targeted UX improvements across the Review, Normalize, and bulk-operation flows.
All changes are minimal and self-contained — no new pages or major refactors.

---

## Sub-Task 1 — Clear stale banners on page navigation

### Intent
Error and success banners (`InlineNotification`) persist in React state when the user
navigates away and returns. This causes stale "OS replacement complete" banners to
reappear on ReviewPage and stale upload errors to reappear on UploadPage.

### Expected Outcomes
- Navigating away from ReviewPage and back clears all bulk-op success banners
- Navigating away from UploadPage and back clears any upload error banner
- Banners still appear normally within the same page visit

### Todo List
1. In `ReviewPage.tsx` add a `useEffect` with an unmount return that sets
   `bulkOsSuccess('')`, `bulkNxfSuccess('')`, and `bulkExcludeSuccess('')` to `''`
2. In `UploadPage.tsx` add a `useEffect` with an unmount return that sets
   `uploadError('')` to `''`
3. Verify NormalizePage already has cleanup (confirmed: lines 64-68 clear polling
   timers but not `processError` / `resetMsg` — clear those too in the same return)

### Relevant Context
- `web/src/pages/ReviewPage.tsx` lines 29, 33, 36 — state declarations
- `web/src/pages/ReviewPage.tsx` lines 193–224 — banner renders
- `web/src/pages/UploadPage.tsx` line 16 — `uploadError` state
- `web/src/pages/UploadPage.tsx` lines 80–89 — banner render
- `web/src/pages/NormalizePage.tsx` lines 21–22 — `processError`, `resetMsg` state
- `web/src/pages/NormalizePage.tsx` lines 64–68 — existing cleanup (add error clears here)

### Status
[ ] pending

---

## Sub-Task 2 — Empty state on Review page before normalization runs

### Intent
When a user navigates to the Review step before running Normalize, the page renders
an empty `RecordsTable` with no explanation. It looks broken.

### Expected Outcomes
- When `status.total === 0` (no records have been normalized yet), ReviewPage renders
  an informational message: "No records to review yet — run the Normalize step first."
  instead of an empty table
- When `status.total > 0` the table renders as normal
- The status check reuses the existing `api.processing.getStatus()` call already
  made by ReviewPage for the failed-records panel

### Todo List
1. In `ReviewPage.tsx` check if the existing `useEffect` already fetches processing
   status; if not, add a `getStatus()` call on mount to get `status.total`
2. Wrap the `RecordsTable` render (lines 246–257) in a conditional:
   - if `status === null` → show `InlineLoading`
   - if `status.total === 0` → show `InlineNotification kind="info"` with message
   - otherwise → render `RecordsTable` as normal

### Relevant Context
- `web/src/pages/ReviewPage.tsx` lines 246–257 — current RecordsTable render
- `web/src/pages/ReviewPage.tsx` lines 60–68 — existing useEffect (check for status fetch)
- `web/src/api/client.ts` lines 262–263 — `api.processing.getStatus()`
- `api/routers/processing.py` lines 34–40 — `ProcessingStatusResponse` shape
  (`total`, `pending`, `processing`, `complete`, `error`, `is_complete`)

### Status
[ ] pending

---

## Sub-Task 3 — Bulk operation modals: show preview list of affected server names

### Intent
All three bulk modals (`BulkExcludeModal`, `BulkOSModal`, `BulkNxfModal`) only show
a count of affected records ("Will exclude **47 records**"). The user has no way to
see *which* servers will be affected before confirming — they only find out after.

Add a scrollable preview list of the first 10 affected server names inside each modal,
below the existing count pill. If more than 10 are affected, show "…and N more."

### Expected Outcomes
- When `affectedCount > 0`, the modal shows a compact list of up to 10 server names
  that will be affected, styled consistently with the existing count pill
- The list updates live as the user types the filter (same debounce as the count)
- The confirm button text and disabled logic are unchanged
- `BulkNxfModal` is simpler (fixed list of nxf-1x* servers) — it should also show
  the first 10 server names from the unsupported list it already fetches

### Todo List
1. **Backend**: Add an optional `preview: bool = False` query param to the affected-count
   endpoints (or add a separate `/preview` endpoint) that returns both `count` and
   `names: list[str]` (first 10 VM names matching the filter). The simplest approach
   is to return both from the existing count endpoint when `preview=true`.
   - `GET /projects/{id}/uploads/{uid}/bulk-os-replace-count?from_os=X&preview=true`
   - `GET /projects/{id}/bulk-exclude-count?filter_type=X&filter_value=Y&preview=true`
2. **`BulkExcludeModal.tsx`**: update the `affectedCount` fetch to also request preview
   names; render a `<ul>` list of names below the count pill
3. **`BulkOSModal.tsx`**: same pattern as BulkExcludeModal
4. **`BulkNxfModal.tsx`**: the nxf modal already fetches the full unsupported list
   (`api.uploads.checkNxfProfiles`) — slice the first 10 names from that list and
   render below the existing count line; no backend change needed here

### Relevant Context
- `web/src/components/BulkExcludeModal.tsx` lines 135–147 — current count-only preview
- `web/src/components/BulkOSModal.tsx` lines 114–119 — current count-only preview
- `web/src/components/BulkNxfModal.tsx` lines 74–77 — current count-only preview
- `api/routers/uploads.py` — locate the existing count endpoints for bulk-os and bulk-exclude
- `api/routers/uploads.py` — `checkNxfProfiles` endpoint (read this before implementing)
- Pattern to follow: return `{"count": N, "names": [...]}` and update TypeScript interface

### Status
[ ] pending

---

## Sub-Task 4 — Normalize polling exponential backoff

### Intent
The polling loop in `NormalizePage.tsx` calls `api.processing.getStatus()` every 2
seconds. If the API is slow or briefly unavailable, the `catch` block silently
swallows all errors and retries at the same 2-second rate indefinitely. This hammers
the backend during transient failures.

### Expected Outcomes
- After 3 consecutive failed poll attempts, the interval doubles (up to a cap of 30s)
- On the next successful response, the interval resets to 2s
- No visible change to the UI during normal operation
- If polling is backing off, a subtle status message could optionally say
  "Connection slow — retrying…" (optional, low priority)

### Todo List
1. In `NormalizePage.tsx` add a `failureCountRef = useRef(0)` alongside the existing
   `pollRef` and `heartbeatRef`
2. Inside the `catch` block of `startPolling()` (line 109), increment `failureCountRef.current`
3. After 3 failures, stop the current interval and restart with a doubled interval:
   `Math.min(currentInterval * 2, 30000)`
4. On a successful response (inside `try`), reset `failureCountRef.current = 0` and
   if interval was increased, restart polling at 2s
5. Store current interval in a `intervalRef = useRef(2000)` so it persists across
   closure captures

### Relevant Context
- `web/src/pages/NormalizePage.tsx` lines 89–109 — `startPolling()` function
- `web/src/pages/NormalizePage.tsx` line 108 — hardcoded `2000` interval
- `web/src/pages/NormalizePage.tsx` lines 64–68 — existing cleanup (update to clear
  backoff state too)
- No backend changes needed

### Status
[ ] pending

---

## Sub-Task 5 — Show current record name during normalization

### Intent
NormalizePage currently shows "Processing record 5 of 100" but not the name of the
server being processed. When normalization stalls or slows on a specific record, the
user can't tell which one it is.

This requires a small backend addition: expose the VM name of the currently-processing
record in the status response.

### Expected Outcomes
- Status response gains an optional `current_record_name: str | None` field
- NormalizePage renders "Processing: **vm-name-001**…" below the progress bar when
  a record is in-flight
- When `processing === 0` (all queued but none in-flight), the label shows nothing
  or falls back to "Processing record N of M…" as today
- No DB schema change needed — query the VM name from the ServerRecord that currently
  has `processing_status = "processing"`

### Todo List
1. **Backend**: In `api/routers/processing.py`, update `ProcessingStatusResponse` to
   add `current_record_name: str | None = None`
2. In the status endpoint handler, after computing counts, run a single extra query:
   find any `ServerRecord` where `processing_status = "processing"` for the project,
   get its `vinfo.vm_name` from `normalized_data` (or fall back to `server_record.id`)
3. **`web/src/api/client.ts`**: add `current_record_name?: string` to the
   `ProcessingStatus` interface (lines 59–66)
4. **`NormalizePage.tsx`**: below the existing "Processing record N of M" text
   (line 270), conditionally render `status.current_record_name` as a dimmed
   subtitle: `"Currently processing: vm-name-001"`

### Relevant Context
- `api/routers/processing.py` lines 34–40 — `ProcessingStatusResponse` schema
- `api/routers/processing.py` lines 203–234 — status endpoint handler
- `api/db/models.py` line 128 — `processing_status` field on `ServerRecord`
- `web/src/api/client.ts` lines 59–66 — `ProcessingStatus` interface
- `web/src/pages/NormalizePage.tsx` line 270 — "Processing record N of M" label
- The VM name lives in `record.normalized_data["vinfo"]["vm_name"]` — if
  `normalized_data` is None (record not yet normalized), fall back to `str(record.id)`

### Status
[ ] pending
