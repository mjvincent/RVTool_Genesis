# nxf Flex-Nano Profile Warning & Bulk Replace

## Top-Level Overview

**Goal:** When a project contains servers assigned to `nxf-1x1`, `nxf-1x2`, or `nxf-1x4`
profiles, warn the user on the Review Page that those profiles are not recognized by the
IBM Cloud Solutioning tool (only `nxf-2x1` and `nxf-2x2` appear in Data Domains).
Provide a "Fix Now" button that opens a modal allowing the user to bulk-replace all
nxf-1x* servers with either `nxf-2x1` or `nxf-2x2` in a single action — permanently
updating stored records, exactly like Bulk OS Replace.

**Profiles that are unsupported by the Cloud Solutioning tool:**
- `nxf-1x1` (1 vCPU / 1 GB)
- `nxf-1x2` (1 vCPU / 2 GB)
- `nxf-1x4` (1 vCPU / 4 GB)

**Supported replacement targets:**
- `nxf-2x1` (2 vCPU / 1 GB)
- `nxf-2x2` (2 vCPU / 2 GB)

**Profile is computed at export time** — it is NOT stored in `normalized_data.vinfo`.
The frontend derives the profile by re-running `_select_vpc_profile(num_cpus, mem_gb)`.
To determine which records are affected, the backend needs a query endpoint that
computes the profile for each x86 record and returns the count / record IDs.

**Approach:**
1. Add a backend endpoint `GET /projects/{id}/nxf-unsupported-count` that returns
   how many active x86 records would be assigned an unsupported nxf-1x* profile.
2. Add a backend endpoint `POST /projects/{id}/bulk-nxf-replace` that patches the
   `num_cpus` and `memory_mb` fields on all affected records to match a chosen target
   profile (`nxf-2x1` or `nxf-2x2`), and logs an Assumption per record.
3. Add a `BulkNxfModal` frontend component (mirrors `BulkOSModal` pattern).
4. Integrate the warning banner + "Fix Now" button into `ReviewPage`, visible only
   when the unsupported count > 0.

---

## Sub-Tasks

### Sub-Task 1 — Backend: nxf unsupported count endpoint

**Intent:** Give the frontend a cheap way to know whether any nxf-1x* servers exist
in this project without re-implementing profile selection in TypeScript.

**Expected Outcomes:**
- `GET /projects/{project_id}/nxf-unsupported-count` returns
  `{ "unsupported_count": N }` where N is the number of active, non-excluded, complete
  x86 ServerRecords whose (num_cpus, mem_gb) would resolve to `nxf-1x1`, `nxf-1x2`,
  or `nxf-1x4` via `_select_vpc_profile`.

**Todo List:**
1. In `api/routers/uploads.py`, add a `NxfUnsupportedCountResponse` Pydantic model
   with one field: `unsupported_count: int`.
2. Add a `GET /projects/{project_id}/nxf-unsupported-count` endpoint that:
   - Queries all `ServerRecord` rows where `project_id` matches, `processing_status ==
     "complete"`, `is_excluded == False`, `server_type` is not `"powervs"`.
   - For each record, reads `normalized_data.vinfo.num_cpus` and
     `normalized_data.vinfo.memory_mb`, calls `_select_vpc_profile(cpus, mem_gb)`,
     and checks if `profile_name in {"nxf-1x1", "nxf-1x2", "nxf-1x4"}`.
   - Returns the count.
3. Import `_select_vpc_profile` from `services.vpc_calculator_generator`.
4. Add `api.uploads.getNxfUnsupportedCount(projectId)` to `web/src/api/client.ts`.

**Relevant Context:**
- `api/routers/uploads.py` lines 382-466 — bulk_os_replace pattern to follow
- `api/services/vpc_calculator_generator.py` lines 115-154 — `_select_vpc_profile`
- `web/src/api/client.ts` line 229 — `bulkOsReplace` binding to mirror

**Status:** `[ ] pending`

---

### Sub-Task 2 — Backend: bulk nxf replace endpoint

**Intent:** Allow the user to reassign all nxf-1x* servers to a supported profile by
patching `num_cpus` and `memory_mb` in `normalized_data.vinfo`, logging one Assumption
per updated record.

**Expected Outcomes:**
- `POST /projects/{project_id}/bulk-nxf-replace` with body `{ "target_profile": "nxf-2x1" | "nxf-2x2" }`
  updates every active, non-excluded record that currently resolves to an unsupported
  nxf profile, setting `num_cpus` and `memory_mb` to match the target.
- Returns `{ "updated_count": N, "target_profile": "nxf-2x1" }`.
- One `Assumption` row is inserted per updated record, documenting the original
  `(num_cpus, memory_mb)` and the reason.

**Profile spec for the two valid targets:**
- `nxf-2x1` → num_cpus = 2, memory_mb = 1024  (1 GB)
- `nxf-2x2` → num_cpus = 2, memory_mb = 2048  (2 GB)

**Todo List:**
1. In `api/routers/uploads.py`, add `BulkNxfReplaceBody` (field: `target_profile: str`)
   and `BulkNxfReplaceResponse` (fields: `updated_count: int`, `target_profile: str`).
2. Validate `target_profile` is one of `{"nxf-2x1", "nxf-2x2"}` — raise HTTP 422
   otherwise.
3. Add `POST /projects/{project_id}/bulk-nxf-replace` that:
   - Queries all complete, non-excluded, non-powervs records.
   - For each record, computes `_select_vpc_profile(cpus, mem_gb)` and checks if the
     result is an unsupported nxf profile.
   - If so, patches `normalized_data.vinfo.num_cpus` and `.memory_mb` to the target
     values, and inserts an `Assumption` row documenting `field_name = "vinfo/num_cpus"`,
     `original_value`, `assumed_value`, and a clear reasoning string.
4. Add `api.uploads.bulkNxfReplace(projectId, targetProfile)` to `client.ts`.

**Relevant Context:**
- `api/routers/uploads.py` lines 400-466 — `bulk_os_replace` is the direct model
- `api/services/vpc_calculator_generator.py` lines 57-63 — `_NXF_PROFILES` for target specs
- `db/models.py` — `Assumption` model fields

**Status:** `[ ] pending`

---

### Sub-Task 3 — Frontend: BulkNxfModal component

**Intent:** A Carbon Modal component that shows a warning about unsupported nxf profiles
and lets the user pick `nxf-2x1` or `nxf-2x2` as the replacement target.

**Expected Outcomes:**
- `web/src/components/BulkNxfModal.tsx` renders a modal with:
  - Warning text explaining that `nxf-1x1`, `nxf-1x2`, and `nxf-1x4` are not
    recognized by the IBM Cloud Solutioning tool (not listed in Data Domains).
  - The affected server count (`unsupportedCount` prop).
  - A two-option select (or two radio buttons) for `nxf-2x1` vs `nxf-2x2`, with a
    brief description of each (2 vCPU / 1 GB vs 2 vCPU / 2 GB).
  - Primary button: "Replace on N server(s)" — calls `bulk-nxf-replace` and calls
    `onApplied(count, targetProfile)` on success.
  - Secondary button: "Cancel" (no change).
  - Error notification on failure.

**Todo List:**
1. Create `web/src/components/BulkNxfModal.tsx` — use `BulkOSModal.tsx` as the
   structural template (same Modal, InlineNotification, Select pattern).
2. Props interface: `{ projectId: string; unsupportedCount: number; onClose: () => void;
   onApplied: (count: number, target: string) => void }`.
3. State: `targetProfile` (default `"nxf-2x1"`), `saving`, `error`.
4. On submit: call `api.uploads.bulkNxfReplace(projectId, targetProfile)`, then
   `onApplied(result.updated_count, result.target_profile)`.

**Relevant Context:**
- `web/src/components/BulkOSModal.tsx` — direct structural model
- `web/src/api/client.ts` — `bulkNxfReplace` binding (added in Sub-Task 2)

**Status:** `[ ] pending`

---

### Sub-Task 4 — Frontend: ReviewPage warning banner + Fix Now button

**Intent:** Integrate the nxf warning into `ReviewPage` so it is visible as soon as the
user arrives at the review step, parallel to the existing "Bulk OS Replace" button.

**Expected Outcomes:**
- On load, `ReviewPage` calls `getNxfUnsupportedCount` and stores the result.
- If `unsupportedCount > 0`, a yellow `InlineNotification` (kind="warning") appears
  above the records table with the message:
  `"{N} server(s) are assigned nxf-1x1 / nxf-1x2 / nxf-1x4 profiles. The IBM Cloud
  Solutioning tool only recognises nxf-2x1 and nxf-2x2. Use 'Fix Nano Profiles' to
  bulk-upgrade them before exporting."`
  with an action button (or a separate button nearby) labelled "Fix Nano Profiles".
- Clicking "Fix Nano Profiles" opens `BulkNxfModal`.
- On `onApplied`, show a success `InlineNotification` (same pattern as `bulkOsSuccess`)
  and reload records + re-check the count (it should drop to 0).

**Todo List:**
1. In `ReviewPage.tsx`, import `BulkNxfModal`.
2. Add state: `nxfUnsupportedCount` (number, default 0), `bulkNxfOpen` (boolean),
   `bulkNxfSuccess` (string).
3. Add an async `checkNxfCount()` helper that calls `api.uploads.getNxfUnsupportedCount`
   and sets `nxfUnsupportedCount`. Call it inside `useEffect` alongside the existing
   record load.
4. Render the warning `InlineNotification` + "Fix Nano Profiles" button when
   `nxfUnsupportedCount > 0` and `isComplete`.
5. Render `BulkNxfModal` when `bulkNxfOpen` is true.
6. In `handleBulkNxfApplied`, close modal, set success message, call `loadRecords()`
   and `checkNxfCount()`, increment `tableKey`.

**Relevant Context:**
- `web/src/pages/ReviewPage.tsx` lines 26-86 — existing bulk OS state + handler pattern
- `web/src/pages/ReviewPage.tsx` lines 113-122 — "Bulk OS Replace" button placement
- `web/src/pages/ReviewPage.tsx` lines 139-148 — success notification pattern
- Carbon `InlineNotification` with `actions` prop can embed a button inline

**Status:** `[ ] pending`

---

### Sub-Task 5 — Commit and push

**Intent:** Ship the complete feature to both remotes.

**Todo List:**
1. `git add` changed files
2. `git commit -m "feat: warn + bulk-replace unsupported nxf-1x* profiles on Review page"`
3. `git push origin main && git push ibm main`

**Status:** `[ ] pending`
