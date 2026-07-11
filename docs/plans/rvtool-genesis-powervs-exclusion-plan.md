# RVTool Genesis — PowerVS Designation & Server Exclusion Plan

## Overview

Two distinct enhancements to the review and export pipeline:

### 1. PowerVS Auto-Detection & Separate Exports
When a server's OS is **AIX** or **IBM i** (any variant/version), the AI normalizer
automatically sets `server_type = "powervs"`. This designation:
- Appears as a distinct "PowerVS" tag in the Review table (Type column)
- Is editable in the Review panel (user can promote/demote to powervs manually)
- Causes the server to be routed into a **separate set of exports**: a dedicated
  PowerVS RVTools `.xlsx` (22-sheet Cool format) and a dedicated PowerVS
  Assumptions Report — in addition to (not instead of) the standard x86 exports

### 2. Server Exclusion with Reason
A checkbox in the Review table lets users exclude individual servers from **all**
generated reports. An optional free-text reason is stored with the exclusion.
- Excluded rows are visually distinct (greyed out / strikethrough server name)
- Excluded servers appear in a separate "Excluded Servers" tab in the
  Assumptions Report `.xlsx` (for audit purposes) but not in any RVTools output
- Exclusion state persists in the database (survives page refresh)

---

## Data Model

### `server_type` values (extended)
| Value | Meaning |
|---|---|
| `vm` | Standard x86 virtual machine (existing) |
| `bare_metal` | Standard x86 bare metal (existing) |
| `powervs` | IBM Power Virtual Server — AIX or IBM i workload (new) |

### New `ServerRecord` fields (DB migration required)
| Field | Type | Default | Purpose |
|---|---|---|---|
| `is_excluded` | Boolean | False | Excludes from all RVTools exports |
| `exclusion_reason` | Text \| None | None | Free-text reason for exclusion |

---

## Export routing logic

```
ServerRecord
    │
    ├── is_excluded = True  →  Excluded Servers tab in Assumptions Report only
    │
    ├── server_type = "powervs"  →  PowerVS RVTools export + PowerVS Assumptions
    │
    └── server_type = "vm" | "bare_metal"  →  Standard RVTools exports
```

The Export page gains **two new cards** for the PowerVS outputs:
- PowerVS Cloud Solutioning Tool Export (22-sheet, IBM Cool)
- PowerVS Assumptions Report

These cards are **only shown** when the project contains at least one PowerVS record.

When both x86 and PowerVS records coexist, an informational banner at the top of the
Export page explains the automatic separation:
> "This project contains both x86 (VPC) and PowerVS workloads. They have been
>  automatically separated into two independent exports below. Upload each file to
>  IBM Cool separately to obtain separate pricing proposals."

The standard Cool export button is always x86-only (silently excludes PowerVS).
The PowerVS export button is always PowerVS-only (silently excludes x86).
The pure 4-sheet RVTools export follows the same split.

---

## Sub-Task 1 — DB: new fields + migration

**Status:** [ ] pending

**Intent:**
Add `is_excluded` and `exclusion_reason` fields to `server_records` and generate
a new Alembic migration.

**Expected Outcomes:**
- `server_records` table has two new nullable/defaulted columns
- Alembic migration runs cleanly on `docker compose up`
- `ServerRecordResponse` Pydantic schema includes both new fields

**Todo List:**
1. Add to `ServerRecord` model in `api/db/models.py`:
   - `is_excluded: Mapped[bool]` — `default=False`, `server_default="false"`, `nullable=False`
   - `exclusion_reason: Mapped[str | None]` — `Text`, `nullable=True`
2. Add both fields to `ServerRecordResponse` in `api/schemas/upload.py`
3. Write Alembic migration `add_exclusion_fields_to_server_records`
   - `op.add_column('server_records', sa.Column('is_excluded', sa.Boolean, nullable=False, server_default='false'))`
   - `op.add_column('server_records', sa.Column('exclusion_reason', sa.Text, nullable=True))`

**Relevant Files:**
- `api/db/models.py` — `ServerRecord` model
- `api/schemas/upload.py` — `ServerRecordResponse`
- `api/alembic/versions/` — migration pattern (see `a1b2c3d4e5f6_add_llm_settings.py`)

---

## Sub-Task 2 — Backend: PowerVS detection in AI normalizer

**Status:** [ ] pending

**Intent:**
Teach the normalizer to auto-detect AIX and IBM i operating systems and set
`server_type = "powervs"`.  This applies in both the LLM path and the Python
fallback synthesizer.

**Expected Outcomes:**
- Any record whose OS string contains "AIX", "IBM i", "IBMi", "i/OS", or "OS/400"
  gets `server_type = "powervs"` after normalization
- The LLM is instructed to return `"powervs"` for these OS types
- The Python fallback `_synthesize_from_raw()` also detects and sets the type
- An assumption is added: `{"field_name": "server_type", "assumed_value": "powervs",
  "reasoning": "OS is AIX/IBM i — automatically designated as PowerVS workload",
  "confidence": "high"}`

**Todo List:**
1. Add `_POWERVS_OS_PATTERNS` list to `ai_normalizer.py`:
   `["aix", "ibm i", "ibmi", "i/os", "os/400", "ibm os/400"]`
2. Add `_is_powervs_os(os_str: str) -> bool` helper
3. Update `_SYSTEM_PROMPT` — change `server_type` description to:
   `"vm|bare_metal|powervs"` with note: `"Use powervs for AIX or IBM i operating systems"`
4. Add a **post-processor step** in `normalize_record()` after JSON parsing:
   if `vinfo.os_config` matches any PowerVS pattern, override `server_type = "powervs"`
   and append a high-confidence assumption (idempotent — only adds once)
5. Apply same override in `_synthesize_from_raw()` after `server_type` is set:
   `if _is_powervs_os(os_raw): server_type = "powervs"` + append assumption

**Relevant Files:**
- `api/services/ai_normalizer.py` — `_SYSTEM_PROMPT`, `normalize_record()`,
  `_synthesize_from_raw()`

---

## Sub-Task 3 — Backend: exclusion PATCH endpoint

**Status:** [ ] pending

**Intent:**
Add a dedicated endpoint to toggle exclusion on a server record and optionally
set the reason.  This is separate from the existing `PATCH /records/{id}` vinfo
editor so the UI can call it cleanly without touching normalized_data.

**Endpoint:**
`PATCH /api/projects/{project_id}/records/{record_id}/exclude`
Body: `{"is_excluded": bool, "exclusion_reason": str | null}`
Returns: updated `ServerRecordResponse`

**Expected Outcomes:**
- Toggling exclusion on/off persists to the DB immediately
- Exclusion reason is stored when provided, cleared when `null`
- The existing `PATCH /records/{id}` (vinfo editor) is unchanged

**Todo List:**
1. Add `ExcludeRecordBody` Pydantic model to `api/routers/uploads.py`:
   `{"is_excluded": bool, "exclusion_reason": str | None = None}`
2. Add `PATCH /projects/{project_id}/records/{record_id}/exclude` endpoint
   - Loads record, updates `is_excluded` + `exclusion_reason`, commits, returns response
3. Add `api.uploads.excludeRecord(projectId, recordId, isExcluded, reason?)` to
   `web/src/api/client.ts`

**Relevant Files:**
- `api/routers/uploads.py` — existing `patch_record` pattern
- `api/schemas/upload.py` — `ServerRecordResponse`
- `web/src/api/client.ts`

---

## Sub-Task 4 — Backend: PowerVS-aware export generators

**Status:** [ ] pending

**Intent:**
Update the RVTools generator and Assumptions generator to:
1. Filter out excluded records from all RVTools output
2. Accept a `powervs_only` flag to generate a PowerVS-only workbook
3. Include excluded servers in a dedicated "Excluded Servers" sheet in
   the Assumptions Report

Add new export endpoints:
- `POST /api/projects/{project_id}/export/rvtools-powervs` — 22-sheet PowerVS export
- `POST /api/projects/{project_id}/export/assumptions-powervs` — PowerVS assumptions

**Expected Outcomes:**
- Standard exports silently skip PowerVS records AND excluded records
- PowerVS exports only contain PowerVS records (excluded ones still skipped)
- Assumptions Report gains an "Excluded Servers" tab listing excluded VMs + reasons
- New endpoints follow identical pattern to existing export endpoints

**Todo List:**
1. Update `generate_rvtools_xlsx(records, ...)` signature:
   - Add optional `powervs_only: bool = False` parameter
   - Filter: `records = [r for r in records if not r.get("is_excluded")]`
   - If `powervs_only`: further filter to `server_type == "powervs"`
   - Else: filter OUT `server_type == "powervs"` (standard export)
2. Update `generate_assumptions_xlsx(...)`:
   - Add "Excluded Servers" sheet with columns: Server Name, OS, Reason, Excluded By
   - This sheet lists excluded records regardless of server_type
3. Add `POST /projects/{project_id}/export/rvtools-powervs` in `api/routers/exports.py`
   - Identical to `rvtools` endpoint but passes `powervs_only=True`
   - Returns 204/empty body with note if no PowerVS records exist
4. Add `POST /projects/{project_id}/export/assumptions-powervs`
   - Assumptions report filtered to PowerVS records only + excluded servers sheet
5. Add new API calls to `web/src/api/client.ts`:
   - `generateRVToolsPowerVS`, `downloadRVToolsPowerVS`
   - `generateAssumptionsPowerVS`, `downloadAssumptionsPowerVS`
6. Add `GET /api/projects/{project_id}/powervs-count` endpoint returning
   `{"powervs_count": int}` — used by the Export page to show/hide PowerVS cards

**Relevant Files:**
- `api/services/rvtools_generator.py` — `generate_rvtools_xlsx()`
- `api/services/assumptions_generator.py` — assumptions report
- `api/routers/exports.py` — existing export endpoint pattern
- `web/src/api/client.ts`

**Note on generator signatures:**
The generators currently receive `records` as a list of normalized_data dicts.
They need access to `is_excluded` and `server_type` which are on the
`ServerRecord` ORM row.  Pass the full record context (a list of
`{"normalized_data": ..., "is_excluded": bool, "server_type": str}` dicts)
rather than just the normalized_data.

---

## Sub-Task 5 — Frontend: Review table (PowerVS tag + exclusion)

**Status:** [ ] pending

**Intent:**
Update `RecordsTable` to:
1. Show a **purple "PowerVS" tag** in the Type column for `server_type = "powervs"`
2. Add an **"Exclude" checkbox column** to every row
3. Show an optional **reason text input** inline when the checkbox is checked
   (appears in the expanded row, not as a separate modal)
4. Visually dim/strikethrough excluded rows

The Edit Record Modal should also allow changing `server_type` to/from `powervs`.

**UI Design:**
- Type column: `vm` → blue "Virtual", `bare_metal` → teal "Bare Metal",
  `powervs` → purple "PowerVS" (new)
- New "Exclude" column: Carbon `Checkbox` — checked = excluded
- When checkbox is checked: a `TextInput` for reason appears in the expanded row
  (below the detail fields)
- Excluded rows: `opacity: 0.55` + `text-decoration: line-through` on server name
- A summary count shows above the table:
  "N PowerVS · M Excluded" when either count > 0

**Expected Outcomes:**
- PowerVS servers visually distinct from VM/bare metal in the Type column
- Checking "Exclude" immediately calls `PATCH .../exclude` and updates local state
- Reason field appears after checkbox is checked; saves on blur/Enter
- Excluded count shown in the table summary
- Changes survive page refresh (stored in DB)

**Todo List:**
1. Add `is_excluded` and `exclusion_reason` to `ServerRecord` interface in `client.ts`
2. Update `RecordsTable.tsx`:
   a. Add `'exclude_col'` to `headers` array
   b. In `rows` mapping: add `is_excluded`, `exclusion_reason` fields
   c. In Type cell renderer: add `powervs` case → purple Tag
   d. Add Exclude column cell renderer with `Checkbox`
   e. `handleExclude(recordId, isExcluded, reason?)` — calls `api.uploads.excludeRecord`
      then updates local state (optimistic update)
   f. In expanded row for non-failed records: add exclusion reason `TextInput`
      visible only when row is excluded
   g. Apply `opacity: 0.55` and strikethrough to excluded rows
3. Add PowerVS + Excluded summary bar above the DataTable
4. Update `EditRecordModal.tsx` — add `server_type` dropdown with vm/bare_metal/powervs options

**Relevant Files:**
- `web/src/components/RecordsTable.tsx`
- `web/src/components/EditRecordModal.tsx`
- `web/src/api/client.ts`

---

## Sub-Task 6 — Frontend: Export page (PowerVS cards)

**Status:** [ ] pending

**Intent:**
Add two new export cards to the Export page for PowerVS workloads.
The cards are **conditionally rendered** — they only appear when the project
has at least one PowerVS server record.

**UI Design:**
- Below the existing 3 cards, a new section header: "PowerVS Workloads"
  with a note: "N servers designated as IBM Power Virtual Server (AIX / IBM i)"
- Card 4: **PowerVS Cloud Solutioning Tool Export** (same 22-sheet format,
  PowerVS records only) — green/teal accent
- Card 5: **PowerVS Assumptions Report** — same structure as standard assumptions

If `powervs_count === 0`, the section is hidden entirely.

**Expected Outcomes:**
- PowerVS section only renders when project has PowerVS records
- Downloads produce correctly filtered exports
- Excluded records do not appear in either PowerVS export

**Todo List:**
1. In `ExportPage.tsx`:
   - Fetch `GET /api/projects/{id}/powervs-count` on mount
   - Add state: `powervsCount`, `pvsLoading`, `pvsDone`, `pvsAsmLoading`, `pvsAsmDone`
   - Add `handlePowerVSExport()` — calls `generateRVToolsPowerVS` + download
   - Add `handlePowerVSAssumptions()` — calls `generateAssumptionsPowerVS` + download
   - Conditionally render the "PowerVS Workloads" section when `powervsCount > 0`

**Relevant Files:**
- `web/src/pages/ExportPage.tsx`
- `web/src/api/client.ts`

---

## Sub-Task 7 — Documentation and branch hygiene

**Status:** [ ] pending

**Intent:**
Update README, Changelog. No new dependencies required.

**Todo List:**
1. Add README section "PowerVS Auto-Detection":
   - OS trigger list (AIX, IBM i, OS/400, etc.)
   - How to override type in Review
   - Note about separate exports
2. Add README section "Server Exclusion":
   - How exclusion works, what appears in Assumptions report
3. Update Changelog

---

## Ordering

```
Sub-Task 1 (DB migration)
      │
      ├──> Sub-Task 2 (AI normalizer — independent of DB fields)
      │
      └──> Sub-Task 3 (exclusion endpoint — needs DB fields)
               │
               └──> Sub-Task 4 (export generators — needs DB fields + exclusion endpoint)
                         │
                         ├──> Sub-Task 5 (Review UI — needs exclusion endpoint + powervs type)
                         │
                         └──> Sub-Task 6 (Export UI — needs new export endpoints)
                                   │
                                   └──> Sub-Task 7 (docs)
```

Sub-Tasks 2 and 3 can proceed in parallel after Sub-Task 1 completes.
Sub-Tasks 5 and 6 can proceed in parallel after Sub-Task 4 completes.

---

## New Files
| File | Purpose |
|---|---|
| `api/alembic/versions/<rev>_add_exclusion_fields.py` | DB migration |

## Changed Files
| File | Change |
|---|---|
| `api/db/models.py` | `is_excluded`, `exclusion_reason` on `ServerRecord` |
| `api/schemas/upload.py` | Expose new fields in `ServerRecordResponse` |
| `api/services/ai_normalizer.py` | PowerVS detection, updated prompt, fallback |
| `api/routers/uploads.py` | New `PATCH .../exclude` endpoint |
| `api/routers/exports.py` | Two new PowerVS export endpoints + powervs-count |
| `api/services/rvtools_generator.py` | Exclusion filter + powervs_only param |
| `api/services/assumptions_generator.py` | Excluded Servers tab |
| `web/src/api/client.ts` | New types + API calls |
| `web/src/components/RecordsTable.tsx` | PowerVS tag, exclude checkbox, reason input |
| `web/src/components/EditRecordModal.tsx` | server_type dropdown |
| `web/src/pages/ExportPage.tsx` | PowerVS export section |
| `README.md` | New sections + changelog |
