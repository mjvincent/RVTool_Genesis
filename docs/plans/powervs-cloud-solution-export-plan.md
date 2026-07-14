# Plan: PowerVS Cloud Solution Export (3-sheet IBM PowerVS Calculator workbook)

## Status: [ ] pending

---

## Top-Level Overview

**Goal:** Create a new "PowerVS Cloud Solution Export" that mirrors the structure of the existing x86 Cloud Solution Export (3 sheets: Project Settings, Exceptions, Data Domains), but uses IBM Power Virtual Server (PowerVS) service columns instead of IBM VPC columns.

The x86 Cloud Solution Export targets the IBM Cloud VPC Cost Estimator and uses VPC-specific constructs (Flex profiles, boot volumes, x86 architecture). The PowerVS equivalent targets the IBM PowerVS Cost Estimator and uses Power-specific constructs (PowerVS machine types, PowerVS OS families, storage tiers, network types).

**Approach:** Build a new generator file `api/services/powervs_calculator_generator.py` following the exact same structural pattern as `vpc_calculator_generator.py`, with PowerVS-appropriate columns. Wire it to a new endpoint and a new UI card.

**Non-goals:**
- Do not modify the existing 4-sheet PowerVS Cool Tool Export (RVTools format)
- Do not modify the x86 Cloud Solution Export
- Do not add a new DB migration (reuse `vpc_region`/`vpc_datacenter` unless a separate PowerVS region field is desired — see Open Questions)

---

## IBM PowerVS Column Design

IBM PowerVS pricing is fundamentally different from VPC:

| Concept | x86 VPC | IBM PowerVS |
|---|---|---|
| Architecture | x86 | Power (ppc64le) |
| Machine type | Flex-Compute/Balanced/Memory profile (cxf, bxf, mxf) | `s922`, `e980`, `s1022` (POWER9/POWER10) |
| CPU type | Shared vCPU | Shared Uncapped / Capped / Dedicated core |
| CPU unit | vCPU | Core (entitlement) |
| RAM | GB linked to profile | Any value in GB |
| OS family | IBM image ID (e.g. `ibm-redhat-9-2-...`) | PowerVS OS family string: `AIX`, `IBM i`, `Linux BYOL`, etc. |
| Storage | Boot volume (100–250 GB SSD) + Data Volume | Tier 1 (NVMe, 10 IOPS/GB) or Tier 3 (HDD, 3 IOPS/GB) |
| Network | VPC subnet | Public or Private network, bandwidth-based |
| Boot disk | Always min 100 GB | No hard min/max — pass customer value directly |

### Project Settings Sheet — PowerVS columns (PVS_HEADERS)

The IBM PowerVS Calculator workbook (used by IBM Cloud Solutioning tool) uses these columns:

```
Issues
Server name
Machine type
Number of instances
CPU type
Entitled processors
Memory (GB)
OS family
Storage type
Storage size (GB)
Requirement Type
Geography
Region
Data Center
Network type
Expected bandwidth (Gbps)
```

### Exceptions sheet
Same layout as Project Settings (PVS_HEADERS). Contains only records where machine type could not be mapped (e.g. extreme outlier CPU/RAM values). This mirrors the `no_matching_profile` concept from VPC.

### Data Domains sheet
Static reference table of valid PowerVS values (machine types, OS families, storage tiers, CPU types, regions, etc.). Mirrors the x86 Data Domains sheet concept.

### Machine type selection (PowerVS equivalent of _select_vpc_profile)

IBM PowerVS standard server types:
- `s922` — POWER9, up to 15 cores, up to 960 GB RAM — general workloads (AIX/IBM i/Linux)
- `s1022` — POWER10, up to 24 cores, up to 1920 GB RAM — general workloads
- `e980` — POWER9, up to 143.5 cores, up to 15307 GB RAM — very large workloads

Selection logic:
- cpus ≤ 15 and mem_gb ≤ 960 → `s922`
- cpus ≤ 24 and mem_gb ≤ 1920 → `s1022`
- cpus ≤ 143 → `e980`
- else → `e980` (flag as `no_matching_profile` if it exceeds e980 limits)

CPU type:
- Default: `Shared Uncapped` (best value, recommended)
- Entitled processors = max(0.5, round(cpus × 0.25, 1)) — PowerVS core entitlement default

Storage type:
- AIX / IBM i → `Tier 1` (NVMe, higher IOPS, standard for mission-critical Power workloads)
- Linux on Power → `Tier 3` (HDD, cost-effective for dev/test)
- Default fallback → `Tier 1`

---

## Sub-Tasks

---

### Sub-Task 1: Build `api/services/powervs_calculator_generator.py`

**Intent:** Create the PowerVS equivalent of `vpc_calculator_generator.py`. This is the core work. The file should follow the exact same structural pattern: constants at the top, helper functions, then the main generator function.

**Expected Outcomes:**
- `generate_powervs_calculator_xlsx(records, project_name, pvs_region, pvs_datacenter) -> bytes`
- Sheet 1: `Project Settings` — rows: Zone, Subnet (or equivalent), per-server Compute row, optional Storage row if disk > 0
- Sheet 2: `Exceptions` — same headers, only records that exceed known machine type limits
- Sheet 3: `Data Domains` — static reference table of valid PowerVS values
- File compiles with no Python errors
- Generator only processes `server_type == "powervs"` records (non-excluded)

**Todo List:**
1. Create `api/services/powervs_calculator_generator.py`
2. Define constants:
   - `_PVS_MACHINE_RULES` — list of (max_cpus, max_mem_gb, machine_type) tuples for s922/s1022/e980
   - `_PVS_CPU_TYPES` — `["Shared Uncapped", "Capped", "Dedicated"]`
   - `_PVS_STORAGE_TIERS` — `{"aix": "Tier 1", "ibm i": "Tier 1", "linux": "Tier 3"}`
   - `IBM_POWERVS_REGIONS` — dict of region → geography (mirror structure of IBM_VPC_REGIONS)
   - `IBM_POWERVS_DATACENTERS` — dict of region → list of datacenters
3. Define helper functions:
   - `_select_pvs_machine_type(cpus, mem_gb)` → `(machine_type, issues_flag)`
   - `_map_pvs_storage_tier(os_family)` → `"Tier 1"` or `"Tier 3"`
   - `get_pvs_geography(region)` → geography string
   - `_write_header(ws, headers)` — copy from vpc_calculator_generator
   - `_auto_size(ws, headers)` — copy from vpc_calculator_generator
4. Define `PVS_HEADERS` list (16 columns, see design above)
5. Define `_PVS = {h: i for i, h in enumerate(PVS_HEADERS, 1)}` index map
6. Define `_pvs_row(n)` and `_set(row, header, val)` helpers
7. Define `_DATA_DOMAINS_HEADERS` and `_DATA_DOMAINS_ROWS` static reference table for PowerVS
8. Implement `generate_powervs_calculator_xlsx()`:
   - Filter: `server_type == "powervs"` and `not is_excluded` and `normalized_data is not None`
   - Sheet 1 (Project Settings): Zone row + per-server Compute row + optional Storage row
   - Sheet 2 (Exceptions): same structure, only `no_matching_profile` records
   - Sheet 3 (Data Domains): static rows
   - Apply same styling (bold headers, gray fill, borders, auto-size, freeze row 1)

**Relevant Context:**
- `api/services/vpc_calculator_generator.py` — structural template to mirror
- `vinfo` fields available: `vm_name`, `cpus`/`num_cpus`, `memory_mb`, `provisioned_mb`, `total_disk_mb`, `powervs_os_family`
- `powervs_os_family` values: `AIX`, `IBM i`, `IBM i MOL`, `Linux BYOL`, `SAP Red Hat`, `SAP SUSE`, `Red Hat GP`, `SUSE GP`
- No boot-disk clamping for PowerVS — pass raw disk size directly

**Status: [ ] pending**

---

### Sub-Task 2: Add PowerVS region/datacenter fields to Project model

**Intent:** The PowerVS Calculator needs a target PowerVS region and datacenter (e.g. `us-south` / `dal10`). PowerVS regions/datacenters differ from VPC regions/datacenters — PowerVS uses datacenter names like `dal10`, `lon06`, `tok04` rather than `us-south-1`. Add `pvs_region` and `pvs_datacenter` columns to the `projects` table.

**Expected Outcomes:**
- New Alembic migration: two nullable string columns `pvs_region` and `pvs_datacenter` on `projects` with sensible defaults (`dal10` datacenter, `us-south` region)
- `Project` model in `api/db/models.py` has the two new fields
- `ProjectCreate` / `ProjectUpdate` schemas in `api/db/schemas.py` include the new fields
- `GET /projects/{id}` and `POST /projects` and `PATCH /projects/{id}` all handle the new fields
- Frontend `Project` TypeScript type includes `pvs_region` and `pvs_datacenter`

**Todo List:**
1. Add `pvs_region: Mapped[str | None]` and `pvs_datacenter: Mapped[str | None]` to `Project` model in `api/db/models.py`
2. Add fields to `ProjectCreate`, `ProjectUpdate`, `ProjectResponse` schemas in `api/db/schemas.py`
3. Generate Alembic migration: `docker compose run --rm api alembic revision --autogenerate -m "add_pvs_region_datacenter"`
4. Verify migration adds both columns with `server_default='dal10'` etc.
5. Add `IBM_POWERVS_REGIONS` and `IBM_POWERVS_DATACENTERS` to `web/src/api/client.ts` (same pattern as `IBM_VPC_REGIONS` and `IBM_VPC_DATACENTERS`)
6. Update `ProjectCreate` form (wherever it is) to include PowerVS region/datacenter pickers — only shown when the project has PowerVS records, or always shown as a secondary section

**Relevant Context:**
- `api/db/models.py`: `Project` model, current fields `vpc_region`, `vpc_datacenter`
- `api/db/schemas.py`: existing schema patterns
- `web/src/api/client.ts`: `IBM_VPC_REGIONS`, `IBM_VPC_DATACENTERS` export constants
- Alembic migration chain: current head is `d1e2f3a4b5c6`

**PowerVS regions and datacenters:**
```
us-south: dal10, dal12
eu-de:    eu-de-1 (FRA04), eu-de-2 (FRA05)
eu-gb:    lon04, lon06
jp-tok:   tok04, tok02
jp-osa:   osa21
au-syd:   syd04, syd05
ca-tor:   tor01
br-sao:   sao01, sao04
us-east:  wdc06, wdc07
in-che:   che01
```

**Status: [ ] pending**

---

### Sub-Task 3: Add API endpoint and UI card

**Intent:** Wire the new generator to an endpoint and add a "PowerVS Cloud Solution Export" card to the PowerVS section of the Export page, parallel to the x86 "Cloud Solution Export" card.

**Expected Outcomes:**
- New endpoint: `POST /projects/{id}/export/powervs-calculator`
- Returns `RVToolsExportResponse`, stored as `RVToolsExport` record
- Filename: `CloudSolution_PowerVS_<ProjectName>_<date>.xlsx`
- New API client method: `api.exports.generatePowerVSCalculator(projectId)`
- New UI card in PowerVS section: "PowerVS Cloud Solution Export" (purple primary button)
  - Card order: PowerVS Cloud Solution Export | PowerVS Cool Tool | PowerVS RVTools (22-sheet) | AI Assumptions
  - Grid: `repeat(2, 1fr)` — two rows of two cards
- Tooltip explains this is the PowerVS equivalent of the IBM Cloud VPC Cost Estimator workbook

**Todo List:**
1. Add `generate_powervs_calculator_export()` endpoint in `api/routers/exports.py`
   - Filters: `server_type == "powervs"` and `not is_excluded`
   - Sources `pvs_region` and `pvs_datacenter` from `project` model (with defaults)
   - Calls `powervs_calculator_generator.generate_powervs_calculator_xlsx(enriched, project.name, pvs_region, pvs_datacenter)`
   - Stores result as `RVToolsExport`, returns `RVToolsExportResponse`
2. Import new generator module in `exports.py`
3. Add `generatePowerVSCalculator()` + `downloadPowerVSCalculator()` to `web/src/api/client.ts`
4. Add state + handler in `ExportPage.tsx`: `pvsSolLoading`, `pvsSolDone`, `handlePVSSolutionExport`
5. Add new card to the PowerVS section — make it the first card (primary blue-purple style)
6. Update grid to `repeat(2, 1fr)` with 4 cards total (2×2 layout)
7. TypeScript check: `npx tsc --noEmit`

**Relevant Context:**
- `api/routers/exports.py`: existing endpoint patterns, `_fetch_enriched_records` helper
- `web/src/pages/ExportPage.tsx` line 357+: PowerVS section, currently 3 cards in a 3-col grid
- `web/src/api/client.ts` line 226+: existing PowerVS export methods
- `api/db/models.py`: `RVToolsExport` model reused (no new model needed)

**Status: [ ] pending**

---

### Sub-Task 4: Add PowerVS region/datacenter UI to project settings

**Intent:** Allow users to set the PowerVS target region and datacenter on a project (parallel to how VPC region/zone is configurable on the Export page). This ensures the PowerVS Cloud Solution Export stamps the correct target datacenter.

**Expected Outcomes:**
- Export page PowerVS section header shows the current `pvs_datacenter` (e.g. "dal10")
- An "Edit" button opens an inline region/datacenter picker (same UX as existing VPC region edit)
- Saving updates `project.pvs_region` and `project.pvs_datacenter` via `PATCH /projects/{id}`
- Dropdowns use `IBM_POWERVS_REGIONS` and `IBM_POWERVS_DATACENTERS` from `client.ts`

**Todo List:**
1. Add editing state variables: `editingPvsRegion`, `editPvsRegion`, `editPvsDatacenter`, `pvsRegionSaving`
2. Add `handleSavePvsRegion()` function — calls `api.projects.update(projectId, { pvs_region: editPvsRegion, pvs_datacenter: editPvsDatacenter })`
3. Add the inline editor in the PowerVS section header (below the "PowerVS Workloads" title)
   - Displays current `project?.pvs_datacenter ?? 'dal10'`
   - Edit icon opens two `<Select>` dropdowns (region → datacenter cascade)
4. Pre-populate `editPvsRegion` / `editPvsDatacenter` from `project` in the `useEffect`

**Relevant Context:**
- `web/src/pages/ExportPage.tsx` lines 77–117: existing VPC region edit pattern to mirror exactly
- `IBM_POWERVS_REGIONS` and `IBM_POWERVS_DATACENTERS` added in Sub-Task 2

**Status: [ ] pending**

---

### Sub-Task 5: Validate and commit

**Intent:** End-to-end validation and clean commit on a feature branch.

**Expected Outcomes:**
- `npx tsc --noEmit` passes clean
- `docker compose build api` passes clean
- Alembic migration applies cleanly: `docker compose run --rm api alembic upgrade head`
- Feature branch committed and pushed to both `origin` and `ibm`

**Todo List:**
1. Run `cd web && npx tsc --noEmit`
2. Run `docker compose build api`
3. Run `docker compose run --rm api alembic upgrade head`
4. Smoke test: `docker compose up -d && curl -X POST http://localhost:8001/api/projects/{id}/export/powervs-calculator`
5. `git add -A && git commit -m "feat: add PowerVS Cloud Solution Export (3-sheet PowerVS calculator workbook)"`
6. `git push origin HEAD && git push ibm HEAD`
7. Merge to main, delete branch, push both remotes

**Relevant Context:**
- Branch: `feat/powervs-cloud-solution-export`
- Alembic current head: `d1e2f3a4b5c6`

**Status: [ ] pending**

---

## Open Questions / Decisions Needed

1. **PowerVS region field**: Does the project need a *separate* PowerVS region/datacenter (like `dal10`) distinct from the VPC region (`us-south`), or is it acceptable to reuse `vpc_region`/`vpc_datacenter`? PowerVS datacenters are named differently (e.g. `dal10`, `lon06`, `tok04`) vs VPC (`us-south-1`, `eu-gb-2`). **Recommendation: add separate `pvs_region` + `pvs_datacenter` columns.**

2. **Entitled processors formula**: For PowerVS, customers buy core entitlements (fractions of a POWER core). The default assumption of `cpus × 0.25` (25% entitlement) is conservative. Should this be configurable or documented purely as an assumption?

3. **Storage size source**: Should storage use `total_disk_mb` (full original disk) or `provisioned_mb` (boot-clamped)? For PowerVS there is no 100/250 GB boot constraint — all disk is simply storage. **Recommendation: use `total_disk_mb`, pass raw GB to the export.**
