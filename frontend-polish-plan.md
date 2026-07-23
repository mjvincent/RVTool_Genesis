# Frontend Polish Plan

## Overview

Four targeted fixes to make RVTool Genesis reliable for daily coworker use.
All changes are frontend-only except where noted. No new API endpoints are needed —
the backend already supports cancel and all required responses.

Items are ordered by coworker pain: settings hang first (most visible), then
normalize page (job queue catch-up), then the two smaller polish items.

---

## Sub-tasks

---

### Sub-task 1 — Fix Settings page infinite spinner when Ollama is unreachable

**Status:** `[x] done`

**Intent**

The Settings page calls `api.settings.getRecommendation()` and (when provider is
`ollama`) `loadAdvisor()` on mount with no timeout. If Ollama is not running —
which is normal for coworkers using watsonx.ai or who haven't started Ollama yet —
these calls hang and the page never resolves its loading state.

The fix is two-part:
1. Wrap both mount calls in `Promise.race` against a short timeout (4 seconds).
   If either times out, mark as loaded and show the settings form with an inline
   notice ("Local advisor unavailable — Ollama may not be running").
2. The `loadAdvisor()` function already has its own loading/error state
   (`advisorError`). Ensure it surfaces a clear message rather than silently
   failing when Ollama is unreachable.

**Expected outcomes**

- Settings page renders within ~4 seconds regardless of whether Ollama is running.
- When the advisor is unavailable, the Ollama section shows an inline warning
  rather than an indefinite spinner.
- When using watsonx.ai, OpenAI, or Anthropic as provider, the page loads
  instantly (no Ollama calls made at all — already the case, just verified).
- No change to any settings save/test functionality.

**Todo list**

1. In `web/src/pages/SettingsPage.tsx`, wrap the `Promise.all` in the mount
   `useEffect` (lines 131–144) with a 4-second `Promise.race` timeout. On
   timeout, call `setLoaded(true)` and set an `advisorError` state message.
2. Ensure `loadAdvisor()` (lines 146–160) sets a clear `advisorError` message
   on catch — it already has this structure, confirm the error text is
   user-friendly ("Could not reach Ollama — make sure it is running locally").
3. Run `npx tsc --noEmit` to confirm zero TypeScript errors.

**Relevant context**

- `web/src/pages/SettingsPage.tsx` — `useEffect` mount block lines 131–144;
  `loadAdvisor()` function lines 146–160.
- Timeout pattern: `Promise.race([somePromise, new Promise((_, reject) => setTimeout(() => reject(new Error('timeout')), 4000))])`
- The `advisorLoading` and `advisorError` state variables already exist and are
  rendered in the Ollama section — just need to ensure they are set on timeout.

---

### Sub-task 2 — Wire up Cancel button and handle `already_running` on NormalizePage

**Status:** `[x] done`

**Intent**

The backend job queue (added in v2.3.0) supports cancellation via
`POST /projects/{id}/processing/cancel`, but the frontend has no Cancel button.
A coworker who starts normalization on the wrong project, or who needs to stop a
long-running job, has no way to do so from the UI.

Additionally, when `POST /process` returns `status: "already_running"`, the
`handleProcess()` function ignores the response and starts polling anyway — the
UI correctly shows progress, but the user gets no feedback that a job was already
running rather than freshly started.

Two changes:

1. **Add `cancelProcessing()` to `api/client.ts`** — a wrapper for
   `POST /projects/{id}/processing/cancel`.

2. **Add a Cancel button to NormalizePage** — visible only while `isInProgress`.
   Clicking it calls `cancelProcessing()`, stops polling, and shows a confirmation
   notification: "Cancellation requested — the current record will finish, then
   normalization will stop."

3. **Handle `already_running` response in `handleProcess()`** — if the response
   `status === "already_running"`, show an info notification ("Normalization is
   already running for this project") and start polling without showing the
   "started" feedback.

**Expected outcomes**

- A "Cancel normalization" button (tertiary, with Stop icon) appears below the
  progress bar while a job is in progress.
- Clicking Cancel shows a notification and stops the polling loop; the progress
  bar remains visible showing last known state.
- The backend job's `cancel_requested` flag is set; the worker stops after the
  current record.
- If normalization is already running when the user clicks "Start", the UI shows
  an info notice rather than silently proceeding.
- TypeScript compiles with zero errors.

**Todo list**

1. In `web/src/api/client.ts`, add `cancel` to the `processing` object:
   `cancel: (projectId: string): Promise<{ cancelled: boolean; message: string }> => apiFetch(..., { method: 'POST' })`
2. In `web/src/pages/NormalizePage.tsx`:
   a. Import `Stop` from `@carbon/icons-react`.
   b. Add a `handleCancel()` async function that calls `api.processing.cancel()`,
      clears the poll and heartbeat intervals, sets `processing` to false, and
      sets a `cancelMsg` state string to display in a notification.
   c. Add a Cancel button in the `isInProgress` JSX section, below the heartbeat
      row, styled as `kind="danger--ghost"` with the `Stop` icon.
   d. In `handleProcess()`, inspect the response: if `resp.status === 'already_running'`,
      show an info notification and start polling (do not show "started" feedback).
3. Run `npx tsc --noEmit` to confirm zero TypeScript errors.

**Relevant context**

- `web/src/api/client.ts` — `processing` object lines 404–417; pattern to follow
  for `resetStuck` on line 416.
- `web/src/pages/NormalizePage.tsx` — `handleProcess()` lines 132–145; `isInProgress`
  JSX section lines 260–314; `handleResetStuck` as style reference for the new handler.
- Backend endpoint: `POST /api/projects/{id}/processing/cancel` returns
  `{ cancelled: bool, message: str }`.
- Carbon `Stop` icon is available from `@carbon/icons-react`.

---

### Sub-task 3 — Add empty/error state to MappingPreview

**Status:** `[x] done`

**Intent**

`MappingPreview` renders a table of sample rows but has no guard when
`sampleRows` is empty. If the parser returns an empty `sample_rows` array (e.g.
file parsed successfully but all rows were blank after cleaning), the table body
renders with zero rows. To a coworker this looks like the upload failed, when in
fact it succeeded with an unusually clean file or a parsing edge case.

Two additions:
1. When `sampleRows.length === 0` but `rowCount > 0`, show an inline notice:
   "Preview unavailable — {rowCount} rows were detected but no sample data could
   be shown. Proceed to normalize to inspect records."
2. When both `sampleRows.length === 0` and `rowCount === 0`, show a warning:
   "No records were detected. Check that the file contains data rows and try
   re-uploading."

**Expected outcomes**

- An empty `sampleRows` array with a positive `rowCount` renders a clear info
  notice rather than a blank table.
- Zero `rowCount` renders a warning notice with guidance to re-upload.
- Normal case (rows present) is unchanged.
- TypeScript compiles with zero errors.

**Todo list**

1. In `web/src/components/MappingPreview.tsx`, add a conditional before the
   table render:
   - If `rowCount === 0`: render a Carbon `InlineNotification` kind="warning"
     with "No records detected" message and only the Re-upload button.
   - Else if `sampleRows.length === 0`: render a Carbon `InlineNotification`
     kind="info" with "Preview unavailable" message, plus both action buttons
     so the user can still proceed or re-upload.
2. Add `InlineNotification` to the imports from `@carbon/react`.
3. Run `npx tsc --noEmit` to confirm zero TypeScript errors.

**Relevant context**

- `web/src/components/MappingPreview.tsx` — full file is 114 lines; table render
  starts at line 44; the `displayCols` / `sampleRows.map()` section is what
  needs the guard.
- `web/src/pages/UploadPage.tsx` renders `MappingPreview` and passes `sampleRows`
  from the upload API response — no changes needed there.

---

### Sub-task 4 — Surface per-project status fetch failures on ProjectsPage

**Status:** `[x] done`

**Intent**

`ProjectsPage` fetches processing status for all projects using
`Promise.allSettled`. When a fetch fails (e.g. the processing endpoint is slow
or returns an error), the project silently shows no progress indicator. To a
coworker who has previously normalized records, this looks like normalization
never ran.

The fix is minimal: when a `Promise.allSettled` result has `status: 'rejected'`,
still add an entry to the status map — but with a sentinel value that the
project card can render as a "status unavailable" indicator (a small grey dash)
rather than showing nothing.

**Expected outcomes**

- Projects whose status fetch failed show a subtle "—" or grey indicator rather
  than a blank progress area.
- Projects with no records (total === 0) continue to show nothing (existing
  behaviour — only entries with `total > 0` are added to the map).
- No change to the error banner logic for full page load failures.
- TypeScript compiles with zero errors.

**Todo list**

1. In `web/src/pages/ProjectsPage.tsx`, in the `Promise.allSettled` loop
   (lines 87–98), change the rejected branch: instead of skipping, add a map
   entry with a `status: 'unavailable'` flag.
2. Find where the project card renders the progress indicator (grep for
   `statusMap`). Add a branch: if `statusMap[p.id]?.status === 'unavailable'`,
   render a small grey "—" span with `title="Status unavailable"` in place of
   the progress bar.
3. Update the TypeScript type for the `statusMap` state to include the
   `status?: 'unavailable'` field.
4. Run `npx tsc --noEmit` to confirm zero TypeScript errors.

**Relevant context**

- `web/src/pages/ProjectsPage.tsx` — `Promise.allSettled` loop lines 87–98;
  `statusMap` state used in the project card render (search for `statusMap[`).
- The `statusMap` state type is defined inline as
  `Record<string, { complete: number; total: number; is_complete: boolean }>` —
  needs `status?: 'unavailable'` added.

---

## Version and changelog

After all sub-tasks pass `npx tsc --noEmit`:

- Bump `VERSION` to `2.3.1` (patch — no new features, all fixes/polish)
- Add a `## [2.3.1]` entry to `CHANGELOG.md`
- Add entry to `README.md` changelog section
- Commit: `fix: v2.3.1 — settings timeout, cancel button, mapping empty state, status failures`
- Push to both remotes (no new tag needed for a patch; or tag `v2.3.1` for consistency)
