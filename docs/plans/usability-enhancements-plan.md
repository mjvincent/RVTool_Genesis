# Usability Enhancements Plan

## Top-Level Overview

**Goal:** Implement the four highest-value usability improvements identified in the
documentation plan. All four have clear, constrained scopes and reuse existing
patterns heavily.

**Deliverables:**
1. Export summary — show machine-type breakdown after IBM Price Estimator populate
2. Duplicate project — one-click copy in the ⋮ overflow menu
3. Processing status badge — "47/120 normalized" on each project card
4. Bulk exclude by filter — exclude all records matching OS or name pattern in one action

**Non-goals:**
- No changes to normalization logic
- No changes to export file content
- No new pages

---

## Sub-Tasks

### Sub-Task 1 — Export summary after IBM Price Estimator populate

**Intent:** After "Populate & Download", show a summary inline so the user knows
how many servers were written and to which machine types. Currently the only feedback
is a file appearing in the downloads folder.

**Expected Outcomes:**
- After a successful populate, an info panel appears below the Populate & Download
  button showing counts by machine type (S1022 / E1050 / E1080) and any skipped count
- The panel replaces the existing truncation warning (which is folded into the summary)
- Counts come from custom response headers; no API contract changes

**Files to change:**
- `api/routers/pricing_template.py` — add `X-Summary-*` headers to the StreamingResponse
- `api/services/pricing_template_filler.py` — `_extract_server_fields` already returns
  `machine`; count per machine in `fill_pricing_template()`
- `web/src/pages/ExportPage.tsx` — parse headers in `handlePopulate()`, render summary panel

**Relevant Context:**
- `pricing_template.py` lines 207-238: endpoint currently returns `written` and `skipped`
  counts via logger but not to the client
- `ExportPage.tsx` lines 231-247: `handlePopulate()` already checks for a `truncated=` hint
  in `Content-Disposition`; that pattern is replaced by explicit headers
- State variables `populateDone` and `truncatedCount` already exist (lines 111-112)

**Status:** `[ ] pending`

---

### Sub-Task 2 — Duplicate project

**Intent:** Add "Duplicate project" to the ⋮ overflow menu on each project row.
Creates a shallow copy (metadata + region settings only — no uploads or records)
with a user-editable name pre-filled as `<original> (copy)`.

**Expected Outcomes:**
- "Duplicate project" appears in the ⋮ overflow menu alongside "Move to folder",
  "Backup project", and "Delete project"
- Clicking it opens a compact modal with an editable name field (pre-filled)
- On confirm, the new project appears in the list immediately
- No records are copied — only name, description, folder, vpc_region, vpc_datacenter,
  pvs_region, pvs_datacenter

**Files to change:**
- `api/routers/projects.py` — add `POST /projects/{project_id}/duplicate` endpoint
- `web/src/api/client.ts` — add `duplicate(id, name)` to `api.projects`
- `web/src/pages/ProjectsPage.tsx` — add state, overflow menu item, inline modal

**Relevant Context:**
- `ProjectsPage.tsx` lines 57-61: existing modal state pattern (deleteTarget, moveTarget, backupTarget)
- `ProjectsPage.tsx` lines 413-417: existing overflow menu items to mirror
- `api/routers/projects.py`: existing `create_project()` endpoint is the template
- `api/db/models.py` lines 46-88: Project fields to copy
- No new component file needed — modal fits inline in ProjectsPage (same pattern as rename folder)

**Status:** `[ ] pending`

---

### Sub-Task 3 — Processing status badge on Projects page

**Intent:** Show a small status badge on each project card so the user can see
normalization progress without clicking into the project.

**Expected Outcomes:**
- Each project row shows one of three states:
  - No badge — project has no uploads yet (total = 0)
  - `"47 / 120 normalized"` amber badge — normalization in progress
  - `"✓ Complete"` green badge — all records processed
- Badges are fetched in parallel with the project list load (no extra page-load cost)
- Badge disappears when a project has no records yet

**Files to change:**
- `web/src/pages/ProjectsPage.tsx` — fetch status for all projects in parallel after
  the project list loads; render badge on each row
- `web/src/api/client.ts` — no new method needed; `api.processing.getStatus(id)` already exists

**Relevant Context:**
- `api/routers/processing.py`: `GET /projects/{id}/processing/status` returns
  `{ complete, total, is_complete, processing, error, pending }` — everything needed
- `ProjectsPage.tsx` line 70-84: existing `load()` function fetches projects + folders;
  status fetches are added here with `Promise.all(projects.map(...))`
- `ProjectsPage.tsx` lines 405-408: project row render — add the badge here
- Carbon `Tag` component already imported (used elsewhere)

**Status:** `[ ] pending`

---

### Sub-Task 4 — Bulk exclude by filter

**Intent:** Add a "Bulk exclude" action to the Review page that lets users select
all records matching a name prefix or OS family and exclude them all in one click.
Essential for large inventories with many test/dev servers to filter out.

**Expected Outcomes:**
- A "Bulk exclude" button appears alongside "Bulk OS Replace" on the Review page
- A modal lets the user choose filter type (Server name contains / OS equals),
  enter the filter value, enter an optional reason, and see a live count of
  records that will be affected
- Affected records are excluded atomically server-side
- All excluded records appear in the Review table with the standard 55%-opacity
  strikethrough styling and in the Excluded Servers audit sheet

**Files to change:**
- `api/routers/uploads.py` — add `POST /projects/{project_id}/bulk-exclude` endpoint
  (follows the `bulk_os_replace` pattern at lines 396-466)
- `web/src/api/client.ts` — add `bulkExclude(projectId, filterType, filterValue, reason)`
- `web/src/components/BulkExcludeModal.tsx` — new component (mirrors BulkOSModal structure)
- `web/src/pages/ReviewPage.tsx` — add state, import modal, add button

**Relevant Context:**
- `api/routers/uploads.py` lines 396-466: `bulk_os_replace` — copy this pattern for the
  new endpoint (same query/loop/commit structure)
- `api/routers/uploads.py` lines 218-257: existing single-record exclude endpoint —
  the bulk version replicates this logic in a loop
- `web/src/components/BulkOSModal.tsx`: full template for the new modal
- `web/src/pages/ReviewPage.tsx` lines 27-32: existing bulk state pattern to extend

**Status:** `[ ] pending`

---

### Sub-Task 5 — Commit and push

**Todo List:**
1. `git add` all changed files
2. `git commit -m "feat: export summary, duplicate project, status badges, bulk exclude"`
3. `git push origin main && git push ibm main`

**Status:** `[ ] pending`
