# Polish and Reliability Plan

## Overview

This plan addresses the five outstanding items identified in the IBM Presentation Readiness
Assessment. All items were confirmed against the current source before scoping.

Items are ordered by risk and effort: fast wins first (lint, accessibility), then backend
safety (upload limits), then the two structural changes (atomic → durable job queue).

One item — the export validator / 22-sheet mismatch — was found to be already correct and
requires no action.

---

## Sub-tasks

---

### Sub-task 1 — Widen Ruff lint gate to full `api/` directory

**Status:** `[x] done`

**Intent**

The current `lint-python` CI job scopes `ruff check` to 9 specific files. All other
`api/` Python files — including `api/routers/processing.py`, `api/routers/uploads.py`,
`api/services/spreadsheet_parser.py`, `api/services/validator.py`, and all router/schema
modules — are outside enforcement. Widening the gate closes the blind spot and brings the
codebase to a consistent lint baseline.

**Expected outcomes**

- `ruff check api/` (excluding `api/alembic/`) passes with zero errors in CI.
- Any pre-existing issues in the previously unchecked files are fixed.
- The `lint-python` CI job comment is updated to reflect full-directory coverage.

**Todo list**

1. Run `ruff check api/` locally to surface all current violations outside the 9 scoped files.
2. Fix each violation. The existing `pyproject.toml` configuration (`E`, `F`, `W` rules,
   `E501` ignored, `api/alembic/` excluded) is correct — do not change it.
3. In `.github/workflows/ci.yml`, replace the explicit 9-file list in the `lint-python` job
   with `ruff check api/` and remove the scoping comment.
4. Verify CI passes locally with `ruff check api/`.

**Relevant context**

- `.github/workflows/ci.yml` — `lint-python` job, lines 43–66
- `pyproject.toml` — ruff configuration (already excludes `api/alembic/`)
- The 9 currently scoped files already pass; only the previously unchecked files need fixes.

---

### Sub-task 2 — Add accessible label to the Exclude checkbox

**Status:** `[x] done`

**Intent**

The Exclude `Checkbox` in the records table uses `labelText=""` with `hideLabel`, leaving
screen readers with no description of the control. The fix is a single prop addition. All
other keyboard-navigation concerns (project rows, folder rows, overflow menus) are already
correctly implemented.

**Expected outcomes**

- Each Exclude checkbox announces a meaningful label to assistive technology, e.g.
  `"Exclude <server name> from exports"` (or a static fallback if the server name column
  is not reliably available, e.g. `"Exclude from exports"`).
- No visual change — the checkbox still renders without visible label text (`hideLabel`
  remains).
- TypeScript compile passes with zero errors.

**Todo list**

1. In `web/src/components/RecordsTable.tsx`, locate the `<Checkbox>` block for
   `exclude_col` (around line 362).
2. Determine the appropriate server name field available in the `row` object at that scope
   (likely `row.cells` or the normalized name field).
3. Add an `aria-label` prop to the `<Checkbox>` with a descriptive string that includes
   the server identifier.
4. Run `npx tsc --noEmit` to confirm zero type errors.

**Relevant context**

- `web/src/components/RecordsTable.tsx` — `exclude_col` cell renderer, lines 356–374
- Carbon `Checkbox` accepts an `aria-label` prop alongside `hideLabel`; both can coexist.

---

### Sub-task 3 — Add upload decompression-ratio and row-count guards

**Status:** `[x] done`

**Intent**

The current upload pipeline checks that raw file bytes are ≤ 50 MB, but XLSX files are
ZIP-compressed: a file well under 50 MB can expand to gigabytes in memory when pandas
opens it. There is also no ceiling on the number of rows parsed. Both allow a single
upload to exhaust API container memory.

The fix is two lightweight guards added to `api/services/spreadsheet_parser.py`:

1. **Before parsing** — open the XLSX as a ZIP and sum the uncompressed member sizes.
   Reject if the total exceeds a configurable threshold (default 500 MB) or if any single
   member has a decompression ratio above a configurable ceiling (default 100×).
2. **After the first DataFrame read** — reject if the row count exceeds a configurable
   maximum (default 100 000 rows).

CSV files do not have a ZIP container, so only the row-count guard applies to them.

**Expected outcomes**

- Uploading a zip-bomb XLSX raises a `ValueError` with a clear message before pandas
  touches the file contents.
- Uploading a file with more than `MAX_ROWS` rows raises a `ValueError` before records
  are created.
- The 50 MB byte limit already in place is preserved unchanged.
- A unit test covers both the decompression-ratio rejection and the row-count rejection.

**Todo list**

1. Add constants to `api/services/spreadsheet_parser.py`:
   - `MAX_UNCOMPRESSED_BYTES` (500 MB default)
   - `MAX_DECOMPRESSION_RATIO` (100 default)
   - `MAX_ROWS` (100 000 default)
2. Add a `_check_xlsx_zip_safety(file_bytes)` helper that opens the bytes as a `zipfile.ZipFile`
   and iterates `infolist()` to check total uncompressed size and per-member ratio.
   Raise `ValueError` with a clear message on violation.
3. Call `_check_xlsx_zip_safety` inside `parse_spreadsheet` immediately after the file-size
   check, before `_read_dataframe`, for `.xlsx` and `.xlsm` files only.
4. After the DataFrame is built, add `if len(df) > MAX_ROWS: raise ValueError(...)`.
5. Add unit tests in `api/tests/` covering: zip-bomb rejection, ratio rejection, row-count
   rejection, and a clean small file passing all guards.

**Relevant context**

- `api/services/spreadsheet_parser.py` — `parse_spreadsheet()` function; `MAX_FILE_SIZE`
  and `_read_dataframe` patterns to follow for style consistency.
- `api/routers/uploads.py` — the 50 MB check at line 57 is a pre-read guard and is not
  changed by this sub-task.
- Python stdlib `zipfile.ZipFile` — `infolist()` returns `ZipInfo` objects with
  `.file_size` (uncompressed) and `.compress_size` (compressed).

---

### Sub-task 4 — Replace BackgroundTasks with a PostgreSQL-backed job queue

**Status:** `[x] done`

**Intent**

Processing is currently dispatched via FastAPI `BackgroundTasks`. This means:

- Two simultaneous POST `/process` requests both read `"pending"` records and schedule
  duplicate tasks for the same record IDs.
- If the API container crashes mid-run, records remain stuck in `"processing"` status
  and require manual reset.
- There is no retry, no durable state, and no worker heartbeat.

The replacement uses a lightweight `processing_jobs` table in the existing PostgreSQL
database as a job queue. No new infrastructure is required — the queue runs in-process
against the same DB connection the API already holds. The design:

- A single `processing_jobs` row is created (or a duplicate is rejected) atomically per
  project, preventing double-scheduling.
- A background worker loop claims the next unclaimed job using `SELECT … FOR UPDATE SKIP LOCKED`.
- On crash/restart, any job that was `in_progress` beyond a timeout is automatically
  re-queued on next startup.
- Cancellation: setting a job to `cancelled` causes the worker loop to stop after the
  current record completes.
- The existing `/process`, `/processing-status`, `/cancel-processing`, and
  `/reset-stuck-records` endpoint contracts are preserved so the frontend needs no changes.

**Expected outcomes**

- A second POST `/process` while processing is running returns a `409 Conflict` (or
  `"already_running"` status) without creating a duplicate job.
- Restarting the API container while processing is in-flight causes the job to resume
  from the next unprocessed record automatically (or after a configurable re-queue timeout).
- The `processing-status` endpoint continues to return accurate progress counts.
- The manual `reset-stuck-records` endpoint still works as an emergency override.
- A new Alembic migration creates the `processing_jobs` table.
- Existing unit tests pass; a new integration test covers the duplicate-submission guard.

**Todo list**

1. **DB model and migration** — Add a `ProcessingJob` ORM model to `api/db/models.py`
   with columns: `id`, `project_id` (FK), `status` (`pending`/`in_progress`/`done`/
   `cancelled`/`failed`), `total_records`, `processed_records`, `started_at`,
   `updated_at`, `worker_pid`. Write an Alembic migration following the existing naming
   and chain convention.

2. **Worker module** — Create `api/services/job_worker.py`. This module owns the
   `_claim_next_job()` function (uses `SELECT … FOR UPDATE SKIP LOCKED`) and the
   `run_worker_loop()` async function that polls for claimed jobs and processes records
   one at a time. It imports `_process_single_record` from `api/routers/processing.py`
   — the function stays where it is, keeping all its existing DB/normalizer/audit
   imports in one place. `job_worker.py` only owns queue mechanics, not record logic.

3. **Lifespan integration** — In `api/main.py`, start `run_worker_loop()` as a long-lived
   asyncio task in the FastAPI `lifespan` context. On startup, re-queue any
   `in_progress` jobs older than the re-queue timeout (default 5 minutes).

4. **Update `start_processing` endpoint** — Replace the `BackgroundTasks` dispatch in
   `api/routers/processing.py` with an `INSERT INTO processing_jobs … ON CONFLICT DO NOTHING`
   pattern. Return `"already_running"` if the insert was a no-op (job already exists for
   the project in a non-terminal state).

5. **Update `processing-status` endpoint** — Source progress from the `processing_jobs`
   row rather than re-counting `server_records` statuses on every poll (keeps the
   response contract identical).

6. **Update `cancel-processing` endpoint** — Set the job row `status = 'cancelled'`; the
   worker loop checks this flag after each record and exits cleanly.

7. **Keep `reset-stuck-records`** — This endpoint now also resets any stuck
   `processing_jobs` row for the project.

8. **Tests** — Add a test that posts `/process` twice concurrently and asserts only one
   job is created. Add a test that simulates a restart by marking a job `in_progress`
   with an old `updated_at` and confirms the startup re-queue logic picks it up.

**Relevant context**

- `api/routers/processing.py` — current `start_processing`, `processing-status`,
  `cancel-processing`, `reset-stuck-records` endpoints; `_process_single_record` and
  `process_all_records` functions (to be moved/refactored).
- `api/db/models.py` — ORM model patterns to follow (`AuditLog`, `ServerRecord`).
- `api/main.py` — lifespan context; existing startup patterns.
- `api/alembic/versions/g1h2i3j4k5l6_add_audit_log_table.py` — most recent migration;
  new migration must set this as `down_revision`.
- PostgreSQL `SELECT … FOR UPDATE SKIP LOCKED` — the correct primitive for a
  single-DB job queue; no external broker needed.

---

## Version and changelog

After all sub-tasks are complete:

- Bump `VERSION` to `2.3.0`
- Add a `## [2.3.0]` entry to `CHANGELOG.md` covering all four changes
- Add a changelog entry to `README.md`
- Commit and push to both remotes with tag `v2.3.0`
