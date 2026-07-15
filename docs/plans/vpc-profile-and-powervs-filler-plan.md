# VPC Profile Catalog Fix + PowerVS Price Estimator Filler

## Overview

Two distinct but related fixes:

1. **VPC Profile Catalog Corrections** — The `_select_vpc_profile()` logic has remaining gaps:
   - `bxf-24x96` is a real IBM Flex profile that was wrongly excluded
   - `nxf` (Flex-Nano) is a 4th Flex family completely absent from the code
   - Servers with >64 vCPUs must be matched to real fixed profiles (Compute, Memory, Very High
     Memory, Ultra High Memory) — **they are NEVER sent to the Exceptions sheet**
   - If a server cannot be matched to ANY known profile in any family, it goes on the main sheet
     with an assumption note — still never the Exceptions sheet

2. **PowerVS Price Estimator Filler** — A feature allowing the user to upload an IBM PowerVS
   Price Estimator `.xlsx` template and have the tool auto-populate it with LPAR data from a
   processed PowerVS export. The original was built on a branch that was deleted without ever
   being committed. It must be rebuilt from scratch.

## Confirmed Design Decisions (from user, 2025-07-15)

| # | Decision |
|---|---|
| 1 | **No server ever goes unresolved.** Every VSI must get a profile. Flex families first, then fixed families, then closest-available assumption. Exceptions sheet is for parse/import failures only — NOT for profile mismatches. |
| 2 | **Assumptions, not errors.** When the tool picks a profile that isn't a direct spec match (e.g. rounds up vCPU or RAM to the next available profile), that is noted as an **assumption** on the output, not flagged as an exception. |
| 3 | **Missing CPU/RAM = review flag.** If a server record has no vCPU or no RAM data at all (import gap, not a sizing gap), those servers must be surfaced during the review stage — brought to the **top of the review list** for human intervention or manual exclusion. |
| 4 | **Price Estimator prompt on every tool use.** The "Upload & Fill Price Estimator" button lives at the **bottom of the page** (Exports area) for PowerVS jobs. The tool **prompts the user to upload the latest estimator template each time** — it does not cache or reuse a previously uploaded template. |

## Ground Truth

### IBM Flex VSI Profile Catalog (from IBM Cloud docs, verified 2025-07-15)

**Flex-Nano (nxf) — fixed combos, no sliding ratio:**

| Profile | vCPU | RAM (GiB) |
|---|---|---|
| nxf-1x1 | 1 | 1 |
| nxf-1x2 | 1 | 2 |
| nxf-1x4 | 1 | 4 |
| nxf-2x1 | 2 | 1 |
| nxf-2x2 | 2 | 2 |

**Flex-Compute (cxf) — 2 GB/vCPU, vCPU sizes: 2, 4, 8, 16, 24, 32, 48, 64**

**Flex-Balanced (bxf) — 4 GB/vCPU, vCPU sizes: 2, 4, 8, 16, 24, 32, 48, 64** ← 24 IS valid

**Flex-Memory (mxf) — 8 GB/vCPU, vCPU sizes: 2, 4, 8, 16, 24, 32, 48, 64**

All Flex profiles stop at 64 vCPUs. For >64 vCPU servers, IBM fixed profiles cover up to 176 vCPUs:

| Family | Profile | vCPU | RAM (GB) | Notes |
|---|---|---|---|---|
| Compute | cx2-96x192 | 96 | 192 | |
| Memory | mx2-96x768 | 96 | 768 | |
| Very High Memory | ux2d-8x224 | 8 | 224 | 1:28 ratio |
| Very High Memory | ux2d-16x448 | 16 | 448 | |
| Very High Memory | ux2d-36x1008 | 36 | 1008 | |
| Very High Memory | ux2d-52x1456 | 52 | 1456 | |
| Very High Memory | ux2d-72x2016 | 72 | 2016 | |
| Very High Memory | ux2d-100x2800 | 100 | 2800 | |
| Very High Memory | ux2d-112x3072 | 112 | 3072 | |
| Ultra High Memory | vx2d-4x56 | 4 | 56 | 1:14 ratio |
| Ultra High Memory | vx2d-8x112 | 8 | 112 | |
| Ultra High Memory | vx2d-16x224 | 16 | 224 | |
| Ultra High Memory | vx2d-28x392 | 28 | 392 | |
| Ultra High Memory | vx2d-44x616 | 44 | 616 | |
| Ultra High Memory | vx2d-56x784 | 56 | 784 | |
| Ultra High Memory | vx2d-88x1232 | 88 | 1232 | |
| Ultra High Memory | vx2d-144x2016 | 144 | 2016 | |
| Ultra High Memory | vx2d-176x2464 | 176 | 2464 | Maximum |

### Profile Selection Algorithm (updated)

```
STEP 1 — Nano check (cpus ≤ 2, ram ≤ 4):
  Find best-fit nxf profile (smallest RAM ≥ requested at given vCPU count).
  If nxf-1x4 can cover a 1-vCPU / 4 GB server, prefer it over cxf-2x4.

STEP 2 — Flex families in priority order (cxf → bxf → mxf):
  For each family, find smallest valid CPU size ≥ requested.
  Check if snap_cpu × ratio ≥ ram_gb.
  First family that satisfies both → return profile, flag = "".

STEP 3 — Fixed profiles >64 vCPU (sorted by vCPU asc, then RAM asc):
  Catalog: cx2-96x192, mx2-96x768, all ux2d, all vx2d (up to vx2d-176x2464).
  Find first entry where profile_vcpu ≥ requested AND profile_ram ≥ requested.
  Return profile, flag = "fixed_profile" (assumption note on output, stays on main sheet).

STEP 4 — No match found in any family:
  Return closest available profile (largest vCPU/RAM in catalog), flag = "assumption".
  Server appears on MAIN sheet with assumption note. NEVER on Exceptions sheet.
  Exceptions sheet is reserved for import/parse failures only.
```

### PowerVS Price Estimator Column Mapping (from filled output analysis)

Sheet: `Multiple LPAR Price Estimate`, data starts at row 19.

| Col # | Letter | Header | Value source |
|---|---|---|---|
| 2 | B | LPAR name | `server_name` |
| 3 | C | LPAR Qty | Always `1` |
| 4 | D | Data Center | Target datacenter (e.g. `DAL10`) |
| 5 | E | System | Machine type (`S1022`, `E1050`, `E1080`, `S922`, `E980`) |
| 6 | F | Processor Type | `S` (Shared) or `D` (Dedicated) |
| 7 | G | Desired Cores | vCPU count (fractional e.g. `4.5` for POWER9) |
| 8 | H | Memory (GB) | RAM in GB |
| 14 | N | OS | `AIX`, `Linux`, `IBM i` |
| 16 | P | Storage Tier 1 (GB) | Total disk in GB |

---

## Sub-Task 1 — Fix bxf-24x96 and add Flex-Nano (nxf) family

**Status:** `[ ] pending`

**Intent:**
`bxf-24x96` is a real IBM catalog profile that our code never produces because 24 was
incorrectly excluded from `_BXF_CPU_SIZES` (only 12 and 20 are absent from bxf — 24 IS valid).
Additionally, `nxf` (Flex-Nano) is a 4th Flex family shown in the Cloud Solution Tool dropdown
that is completely absent from the code. Nano profiles serve tiny workloads (≤2 vCPU, ≤4 GB RAM)
that fall below the cxf-2x4 minimum.

**Expected Outcomes:**
- `bxf-24x96` is produced for a 24-vCPU / ≤96 GB server
- `nxf` profiles are produced for servers with ≤2 vCPU and ≤4 GB RAM before the Flex families are tried
- A 1-vCPU / 4 GB server gets `nxf-1x4` (not `cxf-2x4`)
- A 2-vCPU / 2 GB server gets `nxf-2x2`
- All existing tests continue to pass; new tests cover nxf and bxf-24x96 cases

**Todo List:**
1. In `_BXF_CPU_SIZES`, restore `24` (valid per IBM docs — only 12 and 20 are absent)
2. Add `_NXF_PROFILES` as an ordered list of `(vcpu, ram_gb, profile_name)` tuples for the 5 nano profiles, sorted smallest-first so best-fit lookup is a simple `next()` scan:
   - `(1,1,'nxf-1x1'), (1,2,'nxf-1x2'), (1,4,'nxf-1x4'), (2,1,'nxf-2x1'), (2,2,'nxf-2x2')`
3. In `_select_vpc_profile()`, before the Flex family loop, add nano check: if `cpus <= 2 AND ram_gb <= 4`, scan `_NXF_PROFILES` for first entry where `p_vcpu >= cpus AND p_ram >= ram_gb`; if found return `("Flex-Nano", profile_name, "")`
4. Add `"Flex-Nano"` to any category label sets used in the Cloud Solution sheet generator
5. Update tests in `tests/test_vpc_profile.py`: add `TestFlexNano` class covering the 5 nxf profiles and boundary cases; add `test_bxf_24x96` to `TestFlexBalanced`

**Relevant Context:**
- [`api/services/vpc_calculator_generator.py:54`](api/services/vpc_calculator_generator.py:54) — `_BXF_CPU_SIZES`
- [`api/services/vpc_calculator_generator.py:63`](api/services/vpc_calculator_generator.py:63) — `_FLEX_FAMILIES`
- [`api/services/vpc_calculator_generator.py:70`](api/services/vpc_calculator_generator.py:70) — `_select_vpc_profile()`
- [`tests/test_vpc_profile.py`](tests/test_vpc_profile.py) — test suite

---

## Sub-Task 2 — Fixed-profile fallback for >64 vCPU; eliminate Exceptions for profile mismatches

**Status:** `[ ] pending`

**Intent:**
Currently any server with >64 vCPUs returns `no_matching_profile` and goes to the Exceptions sheet.
Per the confirmed design decision, **no server is ever left without a profile**. IBM offers fixed
(non-Flex) VSI profiles up to 176 vCPUs. The algorithm must try those before falling back to a
closest-available assumption. The Exceptions sheet must be restricted to import/parse failures only.

When no exact match exists at all (genuinely beyond 176 vCPU or extreme RAM), the tool picks the
closest available profile and writes it as an assumption note on the main sheet.

**Expected Outcomes:**
- 96-vCPU / 192 GB → `cx2-96x192`, flag `"fixed_profile"`, on main sheet with assumption note
- 96-vCPU / 500 GB → `mx2-96x768`, flag `"fixed_profile"`, on main sheet with assumption note
- 100-vCPU server → best-fit `ux2d` profile, on main sheet
- 144-vCPU server → `vx2d-144x2016`, on main sheet
- 200-vCPU server → `vx2d-176x2464` (closest available, rounds down), assumption note on main sheet — **not** Exceptions
- Exceptions sheet still exists for servers that failed to parse (missing name, import error etc.)
- Tests verify the full cascade from nano → flex → fixed → assumption

**Todo List:**
1. Add `_FIXED_PROFILES` as an ordered list of `(vcpu, ram_gb, category, profile_name)` tuples covering all fixed profiles shown in the Ground Truth table above, sorted by vCPU ascending then RAM ascending
2. In `_select_vpc_profile()` after all Flex families fail, scan `_FIXED_PROFILES` for first entry where `p_vcpu >= cpus AND p_ram >= ram_gb`; return `(category, profile_name, "fixed_profile")`
3. If no fixed profile covers the spec (genuinely beyond catalog), pick the largest available profile (`vx2d-176x2464`) and return it with flag `"assumption"` — the server stays on the main sheet
4. In `generate_vpc_calculator_xlsx`, change the routing logic:
   - `flag == ""` → normal main sheet row
   - `flag == "fixed_profile"` → main sheet row, yellow highlight, "Fixed profile (non-Flex) — verify ordering path" in Issues column
   - `flag == "assumption"` → main sheet row, orange highlight, "Closest available profile — spec exceeds catalog max" in Issues column
   - Only import/parse errors (missing name, failed AI normalization) → Exceptions sheet
5. Add tests covering the fixed-profile cascade and the assumption fallback

**Relevant Context:**
- [`api/services/vpc_calculator_generator.py:94`](api/services/vpc_calculator_generator.py:94) — fallback area to update
- [`api/services/vpc_calculator_generator.py`](api/services/vpc_calculator_generator.py) — `generate_vpc_calculator_xlsx` function, Exceptions sheet logic
- Fixed profiles from Ground Truth table above

---

## Sub-Task 3 — Review stage: surface servers missing CPU or RAM data

**Status:** `[ ] pending`

**Intent:**
When a server record arrives with no vCPU count or no RAM value (an import gap, not a sizing
gap), it cannot be profile-matched at all. Per the design decision, these servers must be
**surfaced at the top of the review list** for human intervention or manual exclusion —
not silently dropped or assigned a default profile.

This is distinct from Sub-Tasks 1 & 2 (which handle servers that have CPU/RAM but need
profile selection). This sub-task is about servers where the data simply wasn't in the import.

**Expected Outcomes:**
- In the review UI, servers with `null`/`0`/missing `cpu_count` or `memory_mb` appear at the
  **top of the server list**, visually distinguished (e.g. red/orange badge: "Missing CPU" or
  "Missing RAM")
- These servers can be manually edited in the review stage to add CPU/RAM values
- These servers can be excluded from the export with a single click
- No change to the existing logic for servers that have CPU/RAM data

**Todo List:**
1. Check how the review-stage server list is sorted and rendered in the frontend (`web/src/pages/`)
2. Add a sort priority: servers with missing `cpu_count` or `memory_mb` (null, 0, or absent) sort to top of the list
3. Add a visual indicator badge on those rows: e.g. `"⚠ Missing CPU"` or `"⚠ Missing RAM"` in red/orange
4. Ensure the existing manual-edit capability (already present from the failed-record-ux feature) works for these rows
5. No backend changes needed if the data is already stored as null — just frontend sort/display

**Relevant Context:**
- [`web/src/pages/`](web/src/pages/) — review stage pages
- [`docs/plans/rvtool-genesis-review-enhancements-plan.md`](docs/plans/rvtool-genesis-review-enhancements-plan.md) — prior review enhancement work
- [`docs/plans/rvtool-genesis-failed-record-ux-plan.md`](docs/plans/rvtool-genesis-failed-record-ux-plan.md) — manual edit capability already exists

---

## Sub-Task 4 — Rebuild PowerVS Price Estimator filler service

**Status:** `[ ] pending`

**Intent:**
Recreate `api/services/pricing_template_filler.py` — the service that takes a user-uploaded
IBM PowerVS Price Estimator `.xlsx` template and writes LPAR data from a processed PowerVS export
into the correct cells of the `Multiple LPAR Price Estimate` sheet.

The original was lost (never committed). Rebuilt from the filled output reference file and the
confirmed column mapping in the Ground Truth section above.

**Expected Outcomes:**
- `fill_powervs_price_estimator(template_bytes, servers, datacenter) -> bytes` writes one row per server starting at row 19
- Each row fills the columns per the Ground Truth mapping: B=name, C=1, D=datacenter, E=machine_type, F=processor_type, G=cores, H=memory_gb, N=os, col16=storage_gb
- The filled workbook preserves all formulas, formatting, and structure of the original template
- No template file is cached — each call receives the template bytes fresh from the user upload

**Todo List:**
1. Create `api/services/pricing_template_filler.py` with `fill_powervs_price_estimator(template_bytes: bytes, servers: list[dict], datacenter: str) -> bytes`
2. Open template with `openpyxl(keep_vba=False, data_only=False)` to preserve formulas; do NOT use `data_only=True`
3. Target sheet: `Multiple LPAR Price Estimate`; data starts at row 19; clear example rows (rows 19–22 in blank template) before writing
4. For each server write: col B=`server_name`, C=`1`, D=`datacenter`, E=`machine_type`, F=processor_type (`S`=Shared default), G=`cores`, H=`memory_gb`, N=os_normalized, col 16=`storage_gb`
5. OS normalization: `AIX`→`AIX`, `RHEL`/`CentOS`/`SLES`/`Rocky`/`Ubuntu`/`Debian`/`Linux`→`Linux`, `IBMi`/`IBM i`→`IBM i`, `VIOS`→`AIX`; default `AIX`
6. Machine type: pass through as-is from PowerVS DB (`S1022`, `E1050`, `E1080`, `S922`, `E980`)
7. Return `io.BytesIO` result as bytes

**Relevant Context:**
- [`api/services/powervs_calculator_generator.py`](api/services/powervs_calculator_generator.py) — data field names and `_select_pvs_machine_type()`
- Ground Truth column map above
- Reference filled output: `~/Downloads/Test/PowerVS_PriceEstimator_MedTronic_Power10_20260714_155050.xlsx`

---

## Sub-Task 5 — Rebuild PowerVS Filler API router and frontend prompt

**Status:** `[ ] pending`

**Intent:**
Recreate `api/routers/pricing_template.py` and wire the frontend so that:
- At the bottom of the page for any completed PowerVS export job, there is an
  "Upload & Fill Price Estimator" section
- **Each time** the user initiates a fill, they are prompted to upload the latest estimator
  template file (no caching of previous uploads)
- After upload + fill, the filled `.xlsx` is immediately downloaded

**Expected Outcomes:**
- `POST /api/pricing-template/fill` accepts `template: UploadFile` + `job_id: int`, returns filled `.xlsx` download
- Router registered in `api/main.py`
- UI: at the bottom of the Exports/Downloads page for PowerVS jobs, a clearly labelled section:
  "IBM PowerVS Price Estimator — Upload the latest template to auto-fill with this job's LPAR data"
  with a file picker button and a "Fill & Download" action
- The file picker opens fresh every time (no state persisted between uses)
- Filename: `PowerVS_PriceEstimator_{ProjectName}_{YYYYMMDD_HHmmss}.xlsx`

**Todo List:**
1. Create `api/routers/pricing_template.py`:
   - `POST /fill`: accept `template: UploadFile`, `job_id: int = Form(...)`
   - Query DB for PowerVS servers belonging to `job_id`
   - Call `fill_powervs_price_estimator()` from Sub-Task 4
   - Return `StreamingResponse` with correct content-type and `Content-Disposition: attachment` header
2. Register in `api/main.py` with prefix `/api/pricing-template`
3. Add `pricingTemplate.fill(jobId: number, templateFile: File): Promise<Blob>` to `web/src/api/client.ts`
4. In the frontend Exports/Downloads page component, add at the **bottom** of the PowerVS export section:
   - A labelled section header: "IBM PowerVS Price Estimator"
   - A description: "Upload the latest estimator template to auto-fill with this job's LPAR data"
   - A file-input (`<input type="file" accept=".xlsx">`) — state is reset after each use
   - A "Fill & Download" button that calls the API and triggers `URL.createObjectURL` download
   - Loading state while the API call is in flight

**Relevant Context:**
- [`api/main.py`](api/main.py) — router registration
- [`api/routers/exports.py`](api/routers/exports.py) — existing download pattern to reuse
- [`web/src/api/client.ts`](web/src/api/client.ts) — API client
- [`web/src/pages/`](web/src/pages/) — identify correct page for bottom placement

---

## Sub-Task 6 — Tests for pricing filler

**Status:** `[ ] pending`

**Intent:**
Add unit tests for the filler service to catch regressions — verify correct column placement,
OS mapping, machine type passthrough, and that template structure is preserved.

**Expected Outcomes:**
- `tests/test_pricing_template_filler.py` passes in the Docker container
- Covers: column mapping, OS normalization, row ordering, qty always 1, machine type passthrough

**Todo List:**
1. Create `tests/test_pricing_template_filler.py`
2. Build a minimal in-memory template workbook (with header rows in place per the column mapping) to test against — no need for the real template file
3. Test cases: AIX server → col N = `AIX`; RHEL server → col N = `Linux`; IBM i server → col N = `IBM i`; VIOS server → col N = `AIX`; verify col C (qty) = 1 always; verify machine type S1022/E1050/E1080 pass through unchanged; verify 3-server batch produces 3 rows starting at row 19
4. Run `docker compose exec api python3 -m pytest /tests/test_pricing_template_filler.py -v`

**Relevant Context:**
- [`tests/test_vpc_profile.py`](tests/test_vpc_profile.py) — test style and Docker path to follow
