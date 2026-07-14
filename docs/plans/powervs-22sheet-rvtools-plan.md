# Plan: Add 22-Sheet RVTools Export for PowerVS Servers

## Status: [ ] pending

---

## Top-Level Overview

The goal is to add a **22-sheet full RVTools export** for PowerVS servers, mirroring exactly what already exists for x86 servers ("RVTools Export" button). This export would be consumed by tools that require the full 22-sheet RVTools 4.x format — just scoped to AIX/IBM i/Power workloads instead of x86.

**Current state:**
- x86 servers: Two export options — "RVTools Export" (22-sheet, via `POST /export/rvtools`) and a legacy "RVTools Pure" (4-sheet, via `POST /export/rvtools-pure`)
- PowerVS servers: Only a 4-sheet "PowerVS Cool Tool Export" (via `POST /export/rvtools-powervs`) — intended specifically for IBM Cool input

**Gap:** There is no 22-sheet RVTools export for PowerVS records. Power workloads may also need to go through tools like VCF Migration Lite or other validators that require all 22 RVTools tabs. The `generate_rvtools_xlsx()` function already has a `powervs_only=True` filter flag that does the right thing — it is simply never called with that flag from an endpoint.

**Approach:**
1. Add a new API endpoint `POST /projects/{id}/export/rvtools-powervs-full` that calls `generate_rvtools_xlsx(enriched, project.name, powervs_only=True)`
2. Add a corresponding API client method in the frontend
3. Add a new "RVTools Export (22-sheet)" card in the PowerVS section of ExportPage.tsx

**Non-goals:**
- Do not change the existing 4-sheet `POST /export/rvtools-powervs` endpoint — IBM Cool still needs the 4-sheet format
- Do not change the generator functions — `generate_rvtools_xlsx(..., powervs_only=True)` already works correctly
- No DB migration needed — uses existing `RVToolsExport` model and `_fetch_enriched_records` helper
- No new UI state patterns needed — mirror the existing x86 RVTools card pattern exactly

---

## Sub-Tasks

---

### Sub-Task 1: Add API endpoint for PowerVS 22-sheet RVTools export

**Intent:** Expose a new FastAPI endpoint that generates the 22-sheet RVTools workbook filtered to PowerVS records only. The generator already supports this via the `powervs_only=True` flag — this task simply wires it up.

**Expected Outcomes:**
- `POST /api/projects/{project_id}/export/rvtools-powervs-full` returns `RVToolsExportResponse`
- Response filename: `RVTools_PowerVS_Full_<ProjectName>_<YYYYMMDD_HHMMSS>.xlsx`
- Returns HTTP 422 if no PowerVS records exist (consistent with existing PowerVS endpoints)
- `record_count` in response reflects non-excluded PowerVS records only
- Endpoint appears in `/api/docs` (FastAPI auto-docs)

**Todo List:**
1. Open `api/routers/exports.py`
2. Add a new `@router.post("/projects/{project_id}/export/rvtools-powervs-full", ...)` endpoint after the existing `generate_rvtools_powervs_export` function (around line 240)
3. The endpoint follows the exact same structure as `generate_rvtools_export()` (line 150) but:
   - Filters `powervs_records = [r for r in enriched if r["server_type"] == "powervs" and not r["is_excluded"]]`
   - Raises 422 if `not powervs_records`
   - Calls `rvtools_generator.generate_rvtools_xlsx(enriched, project.name, powervs_only=True)`
   - Uses filename prefix `RVTools_PowerVS_Full_`
4. No import changes needed — `rvtools_generator` is already imported in `exports.py`

**Relevant Context:**
- `api/routers/exports.py` line 145–191: x86 22-sheet endpoint to mirror
- `api/routers/exports.py` line 194–239: existing 4-sheet PowerVS endpoint (for context/guard pattern)
- `api/services/rvtools_generator.py` line 226: `generate_rvtools_xlsx()` with `powervs_only` flag already implemented
- `api/db/models.py`: `RVToolsExport` model, `RVToolsExportResponse` — no changes needed

**Status: [ ] pending**

---

### Sub-Task 2: Add frontend API client method

**Intent:** Expose the new endpoint to the React frontend via the existing typed API client.

**Expected Outcomes:**
- `api.exports.generateRVToolsPowerVSFull(projectId)` calls `POST /projects/{projectId}/export/rvtools-powervs-full`
- `api.exports.downloadRVToolsPowerVSFull(projectId, exportId)` calls the correct download path (same download route pattern as existing exports — `GET /projects/{projectId}/exports/rvtools/{exportId}/download`)
- TypeScript compiles cleanly (`npx tsc --noEmit`)

**Todo List:**
1. Open `web/src/api/client.ts`
2. Locate the `exports` object (find the `generateRVToolsPowerVS` and `downloadRVToolsPowerVS` methods)
3. Add two new methods immediately after `generateRVToolsPowerVS` / `downloadRVToolsPowerVS`:
   - `generateRVToolsPowerVSFull(projectId)` → POST to `/projects/${projectId}/export/rvtools-powervs-full`
   - `downloadRVToolsPowerVSFull(projectId, exportId)` → GET download using same download path as x86 rvtools exports
4. Follow the exact same shape as the existing `generateRVToolsPowerVS` / `downloadRVToolsPowerVS` pair

**Relevant Context:**
- `web/src/api/client.ts`: locate `generateRVToolsPowerVS` and `downloadRVToolsPowerVS` to see the exact pattern
- The download route for all `RVToolsExport` records (x86 and PowerVS) is the same: `GET /projects/{projectId}/exports/rvtools/{exportId}/download`

**Status: [ ] pending**

---

### Sub-Task 3: Add UI card in ExportPage PowerVS section

**Intent:** Add a new "RVTools Export (22-sheet)" card inside the PowerVS section of the Export page, matching the visual pattern of the x86 "RVTools Export" card. This gives users the option to generate the full 22-sheet workbook for PowerVS servers when their downstream tooling requires it.

**Expected Outcomes:**
- A new export card appears in the PowerVS section (purple accent)
- Card title: "PowerVS RVTools Export"
- Subtitle/label: "(Full 22-sheet / VCF Migration Lite format)"
- Tooltip: "Full 22-sheet RVTools workbook for PowerVS (AIX/IBM i) records. Required by tools that validate all 22 RVTools tabs on import."
- Body text: "Full 22-sheet RVTools format for PowerVS records. Contains {powervsCount} PowerVS records."
- Button: "Download PowerVS RVTools export" (secondary style, purple border to match section)
- Download/loading/done state behaviour mirrors the existing x86 "RVTools Export" card exactly
- PowerVS section layout expands from a 2-column grid to accommodate the third card (match the 3-card pattern used in the x86 section)
- TypeScript compiles cleanly

**Todo List:**
1. Open `web/src/pages/ExportPage.tsx`
2. Add state variables for the new card: `pvsFull{Loading,Done,ExportId}` — mirror the pattern of `pvsCool{Loading,Done,ExportId}`
3. Add a handler function `handlePVSFullExport` — mirror `handlePVSCoolExport` but calling `api.exports.generateRVToolsPowerVSFull` and `api.exports.downloadRVToolsPowerVSFull`
4. In the PowerVS section card grid (around line 376), update `gridTemplateColumns` from `'1fr 1fr'` to `'1fr 1fr 1fr'` (or `repeat(3, 1fr)`) to accommodate the new card
5. Insert the new card between the "PowerVS Cool Tool Export" card and the "PowerVS AI Assumptions Report" card
6. Apply `borderTop: '3px solid #6929c4'` to match the purple section accent
7. Use `DocumentDownload` icon with `color: '#6929c4'`

**Relevant Context:**
- `web/src/pages/ExportPage.tsx` line 283–355: x86 section with RVTools Export card to mirror
- `web/src/pages/ExportPage.tsx` line 357–416: existing PowerVS section (2-card grid)
- `web/src/pages/ExportPage.tsx` line 123–177: existing state and handler patterns
- `web/src/api/client.ts`: `generateRVToolsPowerVS` / `downloadRVToolsPowerVS` pattern

**Status: [ ] pending**

---

### Sub-Task 4: Validate and commit

**Intent:** Verify nothing is broken, build passes, and commit the change on a feature branch.

**Expected Outcomes:**
- `npx tsc --noEmit` in `web/` passes with no errors
- Docker API container builds cleanly
- New endpoint appears in FastAPI docs at `/api/docs`
- Feature branch committed and pushed to both `origin` and `ibm`

**Todo List:**
1. Run `cd web && npx tsc --noEmit` — fix any type errors
2. Run `docker compose build api` — confirm no Python syntax errors
3. Optionally smoke-test: `docker compose up -d && curl -X POST http://localhost:8001/api/projects/{id}/export/rvtools-powervs-full`
4. `git add -A && git commit -m "feat: add 22-sheet RVTools export for PowerVS servers"`
5. `git push origin HEAD && git push ibm HEAD`

**Relevant Context:**
- Branch naming convention: `feat/powervs-22sheet-rvtools`
- Always build API container and TypeScript-check frontend before committing
- Both remotes: `origin` (github.com) and `ibm` (github.ibm.com)

**Status: [ ] pending**

---

## Open Questions / Decisions Needed

None — design is straightforward. The generator already supports `powervs_only=True`. This is purely wiring: one new endpoint, one API client method pair, one UI card.
