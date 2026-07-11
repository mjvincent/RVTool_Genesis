# RVTool Genesis — Backup & Restore Plan

## Overview

Add project backup and restore capability so that data survives machine
migrations, is shareable between colleagues, and can be archived after
an engagement completes.

**Note:** The PostgreSQL data lives in a named Docker volume (`postgres_data`)
which survives container restarts and OrbStack crashes. This feature adds
portability and true off-machine backup, not crash recovery.

**Scope:** Backup/restore only. LLM provider configuration is a separate
feature and is NOT included here.

---

## Bundle format

Each project is serialised as a single JSON file:

```
project-<slug>-<date>.json
{
  "schema_version": 1,
  "exported_at": "ISO-8601",
  "project": { id, name, description, created_at, updated_at },
  "records": [
    {
      "id", "upload_id", "raw_data", "normalized_data",
      "server_type", "processing_status", "error_message",
      "created_at", "updated_at",
      "assumptions": [ { field_name, assumed_value, original_value,
                          reasoning, confidence, created_at } ]
    }
  ],
  "original_file": {            // only present when user chose to include it
    "filename": str,
    "row_count": int,
    "data_base64": str          // base64-encoded bytes of the uploaded spreadsheet
  }
}
```

**Multi-project (full system) backup:** a `.zip` file containing one
JSON per project, named `rvtoolgenesis-backup-<date>.zip`.

**Single-project backup:** a single `.json` file (optionally zipped if
the original file bytes are included and size warrants it).

**Generated .xlsx exports are NOT included** — they are re-generatable
from `normalized_data` in seconds via the Export page.

---

## Sub-Task 1 — Backend: backup endpoints

**Status:** [ ] pending

**Intent:**
Add two API endpoints to `api/routers/backups.py` (new router):

1. `GET /api/projects/{project_id}/backup?include_file=true|false`
   Returns a single-project JSON bundle as a file download.

2. `GET /api/backup/all?include_files=true|false`
   Returns a zip of all projects as a `.zip` download.

Both endpoints are read-only — no DB mutations.

**Expected outcomes:**
- `GET /api/projects/<id>/backup` streams a `.json` file
- `GET /api/backup/all` streams a `.zip` containing one `.json` per project
- `include_file=false` (default) produces lean bundles (~KB range)
- `include_file=true` includes `original_file.data_base64`
- New router registered in `api/main.py`

**Todo list:**
1. Create `api/routers/backups.py`
2. Implement `_serialize_project(project_id, db, include_file) -> dict`
   - Query project, all server_records with their assumptions, upload row
   - base64-encode `upload.raw_file` only when `include_file=True`
3. Implement single-project endpoint (streams JSON via `StreamingResponse`)
4. Implement all-projects endpoint (builds in-memory zip, streams as `.zip`)
5. Register router in `api/main.py` with prefix `/api`
6. Add `import base64, zipfile` — no new pip dependencies needed

**Relevant files:**
- `api/routers/exports.py` — pattern for StreamingResponse + file downloads
- `api/db/models.py` — all model relationships
- `api/main.py` — router registration

---

## Sub-Task 2 — Backend: restore endpoint

**Status:** [ ] pending

**Intent:**
Add a restore endpoint that accepts a single-project JSON bundle and
creates a new project from it, preserving all normalized data and
assumptions so the user goes straight to Review → Export without
re-running the AI.

`POST /api/restore`
Accepts: `multipart/form-data` with field `file` (.json or .zip)
Returns: list of restored project summaries

**Behaviour:**
- If `.json`: restore one project
- If `.zip`: restore all projects found inside
- **Always creates a NEW project** — never overwrites an existing one
  (append ` (restored YYYY-MM-DD)` to the project name to avoid confusion)
- If `original_file` is present in the bundle, recreate the `Upload` row
  with the decoded bytes; otherwise create a stub Upload row
- All server records are inserted with their `normalized_data` intact
  and `processing_status = "complete"` (no re-processing needed)
- All assumptions are restored
- `schema_version` is checked; unsupported versions return 422

**Expected outcomes:**
- POST with a valid .json restores a project and returns the new project id
- POST with a valid .zip restores N projects
- Restored project appears immediately in the Projects list
- Navigating to Review shows all normalized records

**Todo list:**
1. Add `_restore_project_from_dict(bundle: dict, db) -> Project`
   - Validate `schema_version == 1`
   - Create Project (new UUID, same name + " (restored YYYY-MM-DD)")
   - If `original_file` present: decode base64, create Upload row
   - Else: create stub Upload row (status="complete", raw_file=b"")
   - Bulk-insert ServerRecord rows preserving normalized_data
   - Bulk-insert Assumption rows
2. Add `POST /api/restore` endpoint accepting multipart file
3. Handle `.zip` by extracting and restoring each `.json` inside

**Relevant files:**
- `api/routers/uploads.py` — pattern for multipart file handling
- `api/db/models.py` — all model fields and relationships

---

## Sub-Task 3 — Frontend: backup dialog on Projects page

**Status:** [ ] pending

**Intent:**
Add a backup button/menu to each project row on the Projects page, plus
a "Backup all projects" option in the page header. Each triggers a small
modal dialog with a checkbox for "Include original spreadsheet file" and
a format note.

**UI design:**
- Each project card/row gets a `⬇ Backup` overflow menu item (alongside
  the existing Delete option)
- Clicking opens a small Carbon `Modal` with:
  - Title: "Backup [project name]"
  - Checkbox: "Include original spreadsheet file (larger download)"
  - Helper text explaining what is and isn't included
  - Buttons: "Download backup" | "Cancel"
- Page header gets a "Backup all projects" button (tertiary style)
  - Same modal pattern but for all projects

**Expected outcomes:**
- Clicking "Download backup" on a project downloads `project-<name>-<date>.json`
- "Backup all projects" downloads `rvtoolgenesis-backup-<date>.zip`
- The `include_file` checkbox state is passed as a query param to the API

**Todo list:**
1. Add `api.backup.downloadProject(projectId, includeFile)` to `client.ts`
2. Add `api.backup.downloadAll(includeFiles)` to `client.ts`
3. Create `web/src/components/BackupModal.tsx`
   - Props: `mode: "project" | "all"`, `project?: Project`, `onClose()`
   - Carbon `Modal` + `Checkbox`
   - Calls the appropriate API method on confirm, then triggers download
4. Wire into `ProjectsPage.tsx`:
   - Add "Backup" to the overflow/action menu on each project row
   - Add "Backup all projects" button to the page header area
   - Render `<BackupModal>` conditionally

**Relevant files:**
- `web/src/pages/ProjectsPage.tsx` — existing project card/delete modal pattern
- `web/src/components/EditRecordModal.tsx` — Carbon Modal pattern to follow
- `web/src/api/client.ts` — add backup API calls

---

## Sub-Task 4 — Frontend: restore UI

**Status:** [ ] pending

**Intent:**
Add a "Restore from backup" button on the Projects page that opens a
file picker accepting `.json` and `.zip` files. On success, the restored
project(s) appear immediately in the list.

**UI design:**
- "Restore from backup" button on the Projects page header (ghost style)
- Clicking opens a simple file-pick dialog (native `<input type="file">`,
  same pattern as the Upload page — no Carbon FileUploader)
- After picking, shows an InlineLoading state while the API processes
- On success: shows an InlineNotification "N project(s) restored" and
  refreshes the projects list
- On error: shows error notification with the API's detail message

**Expected outcomes:**
- User picks a `.json` file → one project appears in the list
- User picks a `.zip` file → multiple projects appear in the list
- Restored projects have name suffix " (restored YYYY-MM-DD)"

**Todo list:**
1. Add restore state variables to `ProjectsPage.tsx`
   (`restoring`, `restoreError`, `restoreSuccess`)
2. Add hidden `<input type="file" accept=".json,.zip">` ref
3. Add "Restore from backup" ghost button in the page header
4. On file selection: `POST /api/restore` with FormData
5. On success: refresh project list, show success notification
6. Add `api.backup.restore(file)` to `client.ts`

**Relevant files:**
- `web/src/pages/ProjectsPage.tsx`
- `web/src/pages/UploadPage.tsx` — native file input pattern to follow
- `web/src/api/client.ts`

---

## Sub-Task 5 — Documentation and branch hygiene

**Status:** [ ] pending

**Intent:**
Update README with backup/restore documentation, update the changelog,
merge `feat/resilience-and-ux` → `main`, and cut a new feature branch
`feat/backup-restore` for this work.

**Todo list:**
1. Create branch `feat/backup-restore` from current `feat/resilience-and-ux`
2. Add README section "Backup & Restore" covering:
   - What is and isn't in a bundle
   - How to download a project backup
   - How to restore from a backup file
   - Note on Docker volume durability
3. Update Changelog section
4. After all sub-tasks pass: PR `feat/backup-restore` → `main` on both remotes

**Note on `feat/resilience-and-ux`:**
That branch should be merged into `main` before or alongside this work.
Its commits include: timeout/retry, heartbeat UI, reset-stuck endpoint,
dual export (Cool + Pure RVTools), data quality fixes (6 vInfo bugs).
