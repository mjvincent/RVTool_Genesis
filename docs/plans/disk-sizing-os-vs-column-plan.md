# Plan: IBM VPC Boot Disk Clamping, Data Volume Overflow & OS Family Mapping

## Overview

Three related correctness gaps in the export pipeline need fixing:

1. **Boot disk sizing (Cloud Solution Export)** — IBM Cloud VPC VSIs have a boot volume minimum of **100 GB** and maximum of **250 GB**. The current generator hardcodes `10 GB`, which is wrong. Any disk below 100 GB must be raised to 100 GB. Any disk above 250 GB caps the boot at 250 GB and the overflow goes to the **Data Volume Size**.

2. **`Operating System VS` column unpopulated (Cloud Solution Export)** — The `"Operating System VS"` column in the Project Settings sheet is currently never written. It must be populated with the IBM VPC OS family name (e.g. `"Windows Server"`, `"Red Hat Enterprise Linux"`).

3. **PowerVS OS family mapping** — The IBM Cool PowerVS pricing tool reads an OS string from the RVTools vInfo sheet and maps it to one of these 8 families visible in the IBM Cool UI:
   - **AIX**
   - **IBM i**
   - **IBM i MOL** (Marketplace OS License)
   - **Linux BYOL** (Bring Your Own License)
   - **SAP SUSE** (SUSE for SAP on PowerVS)
   - **SAP Red Hat** (RHEL for SAP on PowerVS)
   - **Red Hat GP** (Red Hat General Purpose on PowerVS)
   - **SUSE GP** (SUSE General Purpose on PowerVS)

   Currently the PowerVS 4-sheet export writes raw OS strings from `vinfo.os_config` (e.g. `"IBM AIX 7.x"`) directly. For IBM Cool to correctly price PowerVS workloads, the `os_config` value written to the vInfo sheet should map to one of these 8 IBM Cool OS families. Additionally, the AI normalizer's PowerVS OS detection must be extended to recognise Linux-on-PowerVS variants (Linux BYOL, SAP SUSE, SAP Red Hat, Red Hat GP, SUSE GP) so they are correctly routed to the PowerVS export instead of the x86 export.

These changes touch **3 Python files** and **1 TypeScript file**. No schema migrations are required.

---

## PowerVS OS Family Mapping Reference

| Customer OS string (examples) | IBM Cool OS Family | Notes |
|-------------------------------|-------------------|-------|
| AIX 7.2, AIX 7.3, IBM AIX | **AIX** | Most AIX workloads |
| AIX 6.1, IBM AIX 6 | **AIX** | Legacy AIX |
| IBM i, OS/400, i/OS, IBM i 7.x | **IBM i** | IBM i traditional license |
| IBM i MOL | **IBM i MOL** | IBM i with marketplace license |
| Linux (generic on Power) | **Linux BYOL** | Any BYOL Linux on PowerVS |
| SUSE SAP, SLES SAP, SAP SUSE Power | **SAP SUSE** | SUSE for SAP certified |
| RHEL SAP, Red Hat SAP, SAP Red Hat Power | **SAP Red Hat** | RHEL for SAP certified |
| Red Hat Power, RHEL Power | **Red Hat GP** | RHEL general purpose on Power |
| SUSE Power, SLES Power | **SUSE GP** | SUSE general purpose on Power |

---

## Sub-Tasks

---

### Sub-Task 1 — Fix Boot Volume Size and Data Volume overflow in `vpc_calculator_generator.py`

**Intent**

Replace the hardcoded `Boot Volume Size (GB) = 10` with correct IBM VPC boot disk clamping:
- `provisioned_gb < 100` → boot = 100 GB, data volume = 0 (no data volume row)
- `100 ≤ provisioned_gb ≤ 250` → boot = provisioned_gb, data volume = 0
- `provisioned_gb > 250` → boot = 250 GB, data volume = (provisioned_gb − 250)

**Expected Outcomes**

- Every Compute row in the Project Settings sheet has `Boot Volume Size (GB)` between 100 and 250 inclusive.
- A Data Volume row is only written when provisioned disk exceeds 250 GB.
- When a data volume row is written, `Data Volume Size (GB)` = `provisioned_gb − 250`.
- The `Issues` column correctly signals `"boot_clamped_100"` or `"boot_clamped_250"` only when clamping occurs; no blanket `"boot_increased"` on every row.

**Todo List**

1. In `vpc_calculator_generator.py`, locate the block at line 462 (`prov_mb = int(...)`).
2. After computing `prov_gb`, add:
   ```python
   boot_gb = max(100, min(250, prov_gb))
   data_gb = max(0, prov_gb - 250)
   ```
3. Replace `_set(cmp_row, "Boot Volume Size (GB)", 10)` with `_set(cmp_row, "Boot Volume Size (GB)", boot_gb)`.
4. Update `issues_parts`:
   - Remove the always-present `"boot_increased"` entry (line 471).
   - Append `"boot_clamped_100"` only when `prov_gb < 100`.
   - Append `"boot_clamped_250"` only when `prov_gb > 250`.
5. Make the Data Volume row conditional: only write it when `data_gb > 0`. Change `_set(dv_row, "Data Volume Size (GB)", prov_gb)` to `_set(dv_row, "Data Volume Size (GB)", data_gb)`.
6. Wrap the entire data volume row block (`dv_row = _ps_row(...)` through `ps_ws.append(dv_row)`) in `if data_gb > 0:`.

**Relevant Context**

- File: `api/services/vpc_calculator_generator.py`
- Lines 462–509: compute + data volume row building
- Line 471: `issues_parts = ["boot_increased"]` — replace
- Line 482: `_set(cmp_row, "Boot Volume Size (GB)", 10)` — replace
- Line 504: `_set(dv_row, "Data Volume Size (GB)", prov_gb)` — replace with `data_gb`, add conditional

**Status**: [ ] pending

---

### Sub-Task 2 — Populate the `"Operating System VS"` column in `vpc_calculator_generator.py`

**Intent**

`"Operating System VS"` (the OS family name) and `"Operating System Version VS"` (the IBM image ID) are two separate columns required by the IBM Cloud Cost Estimator. Currently only `Operating System Version VS` is written. The fix is a single two-line change: capture the `os_family` return value from `_map_os_to_image()` and write it to `"Operating System VS"`.

**Expected Outcomes**

- Every Compute row has `Operating System VS` populated (e.g. `"Red Hat Enterprise Linux"`, `"Windows Server"`, `"Ubuntu Linux"`).
- No change to `_map_os_to_image()` signature or `_OS_IMAGE_MAP` structure needed for this sub-task.

**Todo List**

1. Find `_, os_image = _map_os_to_image(os_config)` (line 467).
2. Change the destructuring to: `os_family, os_image = _map_os_to_image(os_config)`.
3. After `_set(cmp_row, "Operating System Version VS", os_image)` (line 490), add:
   `_set(cmp_row, "Operating System VS", os_family)`.

**Relevant Context**

- File: `api/services/vpc_calculator_generator.py`
- Line 467: `_, os_image = _map_os_to_image(os_config)` — change `_` to `os_family`
- Line 490: existing `Operating System Version VS` set call — add a new line immediately after

**Status**: [ ] pending

---

### Sub-Task 3 — Add PowerVS OS family mapping to `ai_normalizer.py` and `rvtools_generator.py`

**Intent**

IBM Cool reads the `"OS according to the configuration file"` column from the vInfo sheet to determine pricing tier. It expects one of 8 specific family strings (AIX, IBM i, IBM i MOL, Linux BYOL, SAP SUSE, SAP Red Hat, Red Hat GP, SUSE GP). Currently the PowerVS export writes raw normalised OS strings like `"IBM AIX 7.x"` which IBM Cool may or may not map correctly.

This sub-task has two parts:

**Part A — Extend PowerVS OS detection in `ai_normalizer.py`**

Currently `_POWERVS_OS_PATTERNS` only catches `aix` and `ibm i` variants. Linux-on-PowerVS variants (SAP SUSE Power, SAP Red Hat Power, Red Hat GP, SUSE GP, Linux BYOL) will be classified as x86 by the current logic and land in the wrong export. Add patterns to detect them as PowerVS.

**Part B — Add `powervs_os_family` to the normalised data and write it in the PowerVS export**

Add a new function `_map_powervs_os_family(os_config: str) -> str` in `ai_normalizer.py` that maps a normalised OS string to one of the 8 IBM Cool PowerVS OS family strings. Call it during normalization for PowerVS records and store the result in `vinfo["powervs_os_family"]`. In `generate_rvtools_pure_xlsx()` (the 4-sheet PowerVS export), write `powervs_os_family` to the `"OS according to the configuration file"` column instead of `os_config` when it is present.

**Expected Outcomes**

- Customer records with OS `"RHEL for SAP"` or `"SAP Red Hat Power"` are classified as PowerVS (`server_type = "powervs"`) and appear in the PowerVS export, not the x86 export.
- The PowerVS 4-sheet export's vInfo sheet `"OS according to the configuration file"` column contains one of the 8 IBM Cool family strings (e.g. `"AIX"`, `"IBM i"`, `"SAP Red Hat"`, `"Linux BYOL"`).
- An Assumption row is recorded for each record where the PowerVS OS family was inferred from the raw OS string.
- Records with `"IBM AIX 7.x"` map to `"AIX"`, `"IBM i"` maps to `"IBM i"`, generic Linux-on-Power maps to `"Linux BYOL"`, etc.

**Mapping table (to implement):**

| `os_config` contains | IBM Cool family string |
|---|---|
| `aix` | `"AIX"` |
| `ibm i`, `ibmi`, `i/os`, `os/400` (without MOL) | `"IBM i"` |
| `ibm i mol`, `i mol` | `"IBM i MOL"` |
| `sap suse`, `sles sap`, `suse.*sap` | `"SAP SUSE"` |
| `sap red hat`, `rhel.*sap`, `red hat.*sap` | `"SAP Red Hat"` |
| `red hat.*power`, `rhel.*power`, `red hat gp` | `"Red Hat GP"` |
| `suse.*power`, `sles.*power`, `suse gp` | `"SUSE GP"` |
| any other linux on power, generic linux | `"Linux BYOL"` |

**Todo List**

1. In `api/services/ai_normalizer.py`, extend `_POWERVS_OS_PATTERNS` to also match:
   - `"sap suse"`, `"sap red hat"`, `"rhel.*power"`, `"suse.*power"`, `"linux byol"`, `"red hat gp"`, `"suse gp"`, `"sap hana"`
2. Add a new function `_map_powervs_os_family(os_config: str) -> str` after `_is_powervs_os()`. It receives a normalised OS string and returns the IBM Cool family string using the mapping table above. Fallback = `"Linux BYOL"` for any unrecognised PowerVS record.
3. In the PowerVS post-processor block of `normalize_record()` (lines 1030–1034), call `_map_powervs_os_family()` and store the result: `result["vinfo"]["powervs_os_family"] = _map_powervs_os_family(os_cfg_str)`. Also add an Assumption entry documenting the family inference.
4. In `api/services/rvtools_generator.py` in `generate_rvtools_pure_xlsx()`, for the vInfo row write, use `vinfo.get("powervs_os_family") or _get(vinfo, "os_config")` as the value for `"OS according to the configuration file"` (column 13 of the VINFO_HEADERS).
5. Similarly update `generate_rvtools_xlsx()` (the 22-sheet generator) — the PowerVS records in the full export also use `os_cfg` for column 13; apply the same `powervs_os_family` override when present.

**Relevant Context**

- File: `api/services/ai_normalizer.py`
  - Line 91: `_POWERVS_OS_PATTERNS` — extend
  - Line 94: `_is_powervs_os()` — add new `_map_powervs_os_family()` after it
  - Lines 1030–1034: PowerVS post-processor — add `powervs_os_family` to vinfo + assumption
- File: `api/services/rvtools_generator.py`
  - Line 529 (pure xlsx): `_get(vinfo, "os_config")` → use `powervs_os_family` override
  - Line 300 (22-sheet): `os_cfg = _get(vinfo, "os_config")` → use `powervs_os_family` override when present
- The `powervs_os_family` field is stored in `vinfo` inside `normalized_data` — no schema migration needed (JSONB column absorbs new keys)

**Status**: [ ] pending

---

### Sub-Task 4 — Extend `_OS_NORMALIZATION` in `ai_normalizer.py` and update `IBM_OS_OPTIONS` in frontend

**Intent**

`_OS_NORMALIZATION` currently has no patterns for Rocky Linux, Fedora CoreOS, AlmaLinux, and the PowerVS Linux-on-Power OS variants. These exist in `IBM_OS_OPTIONS` (frontend dropdown) but will fall through normalization unchanged, which means they may not be recognised by downstream tools.

Also add the three x86 IBM VPC OS families that appear in the IBM Cloud Cost Estimator but are absent from both `_OS_NORMALIZATION` and `_OS_IMAGE_MAP`:
- `"Red Hat Enterprise Linux for SAP (64-bit)"` 
- `"SUSE Linux Enterprise Server for SAP (64-bit)"`
- `"Microsoft Windows Server with SQL Server (64-bit)"`

**Expected Outcomes**

- `"Rocky Linux 9"` from a customer spreadsheet normalizes to `"Rocky Linux (64-bit)"`.
- `"Fedora CoreOS 38"` normalizes to `"Fedora CoreOS (64-bit)"`.
- `"AlmaLinux 9"` normalizes to `"AlmaLinux (64-bit)"`.
- `"RHEL for SAP"` (x86) normalizes to `"Red Hat Enterprise Linux for SAP (64-bit)"`.
- `"SLES SAP"` (x86) normalizes to `"SUSE Linux Enterprise Server for SAP (64-bit)"`.
- `"Windows 2022 SQL"` normalizes to `"Microsoft Windows Server with SQL Server (64-bit)"`.
- `IBM_OS_OPTIONS` in the frontend includes the three new SAP/SQL x86 OS strings.
- `_OS_IMAGE_MAP` in `vpc_calculator_generator.py` has entries for the three SAP/SQL families with IBM image IDs (placeholder IDs following the established naming convention — clearly marked for catalog verification).

**Todo List**

1. In `api/services/ai_normalizer.py`, add to `_OS_NORMALIZATION` (before the AIX section):
   ```python
   # Rocky Linux
   (r"rocky.*linux.*9",   "Rocky Linux (64-bit)"),
   (r"rocky.*linux.*8",   "Rocky Linux (64-bit)"),
   (r"rocky.*linux",      "Rocky Linux (64-bit)"),
   # AlmaLinux
   (r"alma.*linux.*9",    "AlmaLinux (64-bit)"),
   (r"alma.*linux",       "AlmaLinux (64-bit)"),
   (r"almalinux",         "AlmaLinux (64-bit)"),
   # Fedora CoreOS
   (r"fedora.*coreos",    "Fedora CoreOS (64-bit)"),
   (r"coreos",            "Fedora CoreOS (64-bit)"),
   ```
2. Add SAP/SQL x86 patterns **before** the generic RHEL / SUSE / Windows entries (first-match-wins):
   ```python
   # RHEL for SAP (x86 VPC)
   (r"red\s*hat.*sap",    "Red Hat Enterprise Linux for SAP (64-bit)"),
   (r"rhel.*sap",         "Red Hat Enterprise Linux for SAP (64-bit)"),
   # SUSE for SAP (x86 VPC)
   (r"suse.*sap",         "SUSE Linux Enterprise Server for SAP (64-bit)"),
   (r"sles.*sap",         "SUSE Linux Enterprise Server for SAP (64-bit)"),
   # Windows with SQL Server
   (r"windows.*sql",      "Microsoft Windows Server with SQL Server (64-bit)"),
   (r"sql.*server.*win",  "Microsoft Windows Server with SQL Server (64-bit)"),
   ```
3. In `api/services/vpc_calculator_generator.py`, add to `_OS_IMAGE_MAP` before the generic RHEL / SUSE / Windows entries:
   ```python
   # RHEL for SAP — placeholder image ID, verify against IBM Cloud catalog
   ("red hat enterprise linux for sap",  "Red Hat Enterprise Linux for SAP", "ibm-redhat-9-2-sap-hana-amd64-3"),   # PLACEHOLDER
   ("rhel for sap",                      "Red Hat Enterprise Linux for SAP", "ibm-redhat-9-2-sap-hana-amd64-3"),   # PLACEHOLDER
   # SUSE for SAP — placeholder image ID
   ("suse linux enterprise server for sap", "SUSE Linux Enterprise Server for SAP", "ibm-sles-15-5-sap-hana-amd64-1"),  # PLACEHOLDER
   ("sles for sap",                      "SUSE Linux Enterprise Server for SAP", "ibm-sles-15-5-sap-hana-amd64-1"),  # PLACEHOLDER
   # Windows with SQL Server — placeholder image ID
   ("windows server with sql server",    "Windows Server with SQL Server", "ibm-windows-server-2022-sql-2022-amd64-1"),  # PLACEHOLDER
   ("microsoft windows server with sql", "Windows Server with SQL Server", "ibm-windows-server-2022-sql-2022-amd64-1"),  # PLACEHOLDER
   ```
   > **Note**: Image IDs marked `# PLACEHOLDER` follow IBM naming conventions but must be verified against the live IBM Cloud catalog before production use. They will appear in the `Operating System Version VS` column.
4. In `web/src/constants/osOptions.ts`, add to `IBM_OS_OPTIONS`:
   - After the existing RHEL entries: `'Red Hat Enterprise Linux for SAP (64-bit)'`
   - After the existing SUSE entries: `'SUSE Linux Enterprise Server for SAP (64-bit)'`
   - After the existing Windows entries: `'Microsoft Windows Server with SQL Server (64-bit)'`

**Relevant Context**

- File: `api/services/ai_normalizer.py` lines 283–334 (`_OS_NORMALIZATION`)
- File: `api/services/vpc_calculator_generator.py` lines 103–155 (`_OS_IMAGE_MAP`)
- File: `web/src/constants/osOptions.ts` lines 6–47 (`IBM_OS_OPTIONS`)
- SAP/SQL patterns must appear BEFORE generic RHEL/SUSE/Windows fallbacks (first-match-wins in both `_normalize_os_name()` and `_map_os_to_image()`)

**Status**: [ ] pending

---

### Sub-Task 5 — Record boot disk clamping as AI Assumptions at normalize time in `ai_normalizer.py`

**Intent**

The boot disk clamping in Sub-Task 1 happens at **export generation time**, so it is invisible to the Assumptions Report and the Review page. Users examining the Review page have no indication that a 50 GB disk was silently raised to 100 GB. Apply the same clamping at **normalization time** in `_sanitize_numeric_fields()` so the adjustment is documented as an Assumption record in the database and visible in the AssumptionsPanel on the Review page.

**Expected Outcomes**

- A record with `provisioned_mb = 51200` (50 GB) gets `provisioned_mb` raised to `102400` (100 GB) during normalization with an Assumption: `confidence="medium"`, `field_name="vinfo/provisioned_mb"`, reasoning citing the IBM VPC 100 GB minimum boot disk rule.
- A record with `provisioned_mb = 512000` (500 GB) gets `provisioned_mb` capped to `256000` (250 GB) with an Assumption noting the 250 GB cap and that `244 GB` of overflow will become the Data Volume in the Cloud Solution export.
- `in_use_mb` (which is AI-estimated at 60% of provisioned) is recalculated after clamping to stay consistent with the new `provisioned_mb`.

**Todo List**

1. In `api/services/ai_normalizer.py`, add two constants above `_sanitize_numeric_fields()`:
   ```python
   _IBM_VPC_BOOT_MIN_MB = 100 * 1024   # 100 GB — IBM Cloud VPC minimum boot volume
   _IBM_VPC_BOOT_MAX_MB = 250 * 1024   # 250 GB — IBM Cloud VPC maximum boot volume
   ```
2. After the existing `vinfo["provisioned_mb"] = _clamp_mb(...)` call (line 461), add:
   - If `vinfo["provisioned_mb"] < _IBM_VPC_BOOT_MIN_MB`: set to `_IBM_VPC_BOOT_MIN_MB` and append assumption (`reasoning` = "IBM Cloud VPC boot volume minimum is 100 GB. Customer-provided disk size of X GB was raised to 100 GB. Confirm with customer.")
   - Elif `vinfo["provisioned_mb"] > _IBM_VPC_BOOT_MAX_MB`: record original value, set to `_IBM_VPC_BOOT_MAX_MB`, append assumption (`reasoning` = "IBM Cloud VPC boot volume maximum is 250 GB. Customer disk of X GB exceeds this; boot disk set to 250 GB. The excess Y GB will be added as a Data Volume in the Cloud Solution Export.")
3. After both clamp checks, recalculate `in_use_mb` only if it was the AI default (60% of original provisioned): `if vinfo["in_use_mb"] == round(original_prov * 0.6): vinfo["in_use_mb"] = round(vinfo["provisioned_mb"] * 0.6)`.
4. The `original_prov` value should be captured immediately before the clamp: `original_prov = vinfo.get("provisioned_mb", 0)`.

**Relevant Context**

- File: `api/services/ai_normalizer.py`
- Lines 461–462: `provisioned_mb` and `in_use_mb` existing clamp calls
- Lines 492–494: `in_use_mb <= provisioned_mb` guard (still needed as final safety)
- `new_assumptions` list accumulates throughout `_sanitize_numeric_fields()` and is merged back into the result

**Status**: [ ] pending

---

## Implementation Order

1. **Sub-Task 5** first — normalization-time clamping; no other sub-tasks depend on it but it should land first so re-processed records get correct Assumption records
2. **Sub-Task 1** second — generator-time clamping; reads `provisioned_mb` which is now pre-clamped by ST-5
3. **Sub-Task 2** third — trivial two-line change to OS VS column; zero dependencies
4. **Sub-Task 3** fourth — PowerVS OS family mapping; builds on the PowerVS detection infrastructure already in place
5. **Sub-Task 4** last — x86 SAP/SQL normalizer patterns + frontend dropdown; depends on decisions from ST-3 about PowerVS pattern ordering

All five sub-tasks belong in a single branch: **`feat/vpc-boot-disk-sizing-os-families`**

## Branch & Validation Checklist

- [ ] Branch from main: `git checkout -b feat/vpc-boot-disk-sizing-os-families`
- [ ] After sub-task changes: `docker compose restart api` (background tasks hold old module refs)
- [ ] Test with records having disk < 100 GB, 100–250 GB, and > 250 GB
- [ ] Verify `Boot Volume Size (GB)` is between 100–250 in Cloud Solution Export
- [ ] Verify `Data Volume Size (GB)` = overflow amount when > 250 GB, absent otherwise
- [ ] Verify `Operating System VS` column is populated in Cloud Solution Export
- [ ] Verify PowerVS records with SAP OS strings route to PowerVS export (not x86)
- [ ] Verify `"OS according to the configuration file"` column in PowerVS 4-sheet export contains IBM Cool family strings (e.g. `"AIX"`, `"IBM i"`, `"SAP Red Hat"`)
- [ ] Verify Assumptions Report contains boot disk clamping assumptions
- [ ] TypeScript check: `cd web && npx tsc --noEmit`
- [ ] Push to both `origin` and `ibm` remotes after merge to main
