# RVTool Genesis — User Guide

> **Who this is for:** IBM practitioners who use RVTool Genesis to size customer
> server inventories for IBM Cloud migration proposals.
>
> **Related guides:** [Operations Guide](OPERATIONS_GUIDE.md) · [README](../README.md)

---

## Table of Contents

1. [What the tool produces](#1-what-the-tool-produces)
2. [Prerequisites](#2-prerequisites)
3. [Step 1 — Create a project](#3-step-1--create-a-project)
4. [Step 2 — Upload a spreadsheet](#4-step-2--upload-a-spreadsheet)
5. [Step 3 — AI Normalization](#5-step-3--ai-normalization)
6. [Step 4 — Review Records](#6-step-4--review-records)
7. [Step 5 — Export](#7-step-5--export)
8. [IBM Price Estimator workflow](#8-ibm-price-estimator-workflow)
9. [Settings — LLM provider & model recommendations](#9-settings--llm-provider--model-recommendations)
10. [Project management — folders, backup, restore](#10-project-management--folders-backup-restore)
11. [Tips for large engagements](#11-tips-for-large-engagements)
12. [Troubleshooting quick reference](#12-troubleshooting-quick-reference)

---

## 1. What the tool produces

RVTool Genesis takes a customer's server inventory spreadsheet — in any format,
any column layout — and produces the IBM sizing files you need for a migration
proposal, without any manual data entry.

### All 8 output files

| Output | Format | Feeds into | When to use |
|---|---|---|---|
| **Cloud Solution Export** | 3-sheet .xlsx | IBM Cloud Cost Estimator (VPC) | x86/VPC workloads — primary deliverable |
| **RVTools Export (x86)** | 22-sheet .xlsx | VCF Migration Lite, IBM Cool | When the downstream tool requires all 22 RVTools tabs |
| **AI Assumptions Report (x86)** | .xlsx | Customer review, audit | Documents every AI inference |
| **PowerVS Cloud Solution Export** | 3-sheet .xlsx | IBM PowerVS Cost Estimator | AIX/IBM i workloads — direct upload |
| **PowerVS Cool Tool Export** | 4-sheet .xlsx | IBM Cool (PowerVS input) | IBM Cool pricing for AIX/IBM i |
| **PowerVS RVTools Export** | 22-sheet .xlsx | VCF Migration Lite (PowerVS) | When tooling requires all 22 tabs |
| **PowerVS AI Assumptions Report** | .xlsx | Customer review, audit | AI decisions for PowerVS records only |
| **IBM Price Estimator (populated)** | .xlsx | IBM Price Estimator (Excel) | Detailed per-LPAR PowerVS pricing |

> **x86 and PowerVS records are automatically separated.** If a project contains
> both types, all exports are generated independently. Upload x86 exports and
> PowerVS exports to IBM Cool **separately** to get correct independent pricing.

---

## 2. Prerequisites

| Requirement | Notes |
|---|---|
| **OrbStack** (recommended) or Docker Desktop | [orbstack.dev](https://orbstack.dev) |
| **Ollama** *(only if using the default Ollama provider)* | [ollama.com](https://ollama.com) — must be running on your Mac |
| `phi4-mini` model | `ollama pull phi4-mini` |

The app runs at **http://localhost:3001** after `./setup.sh`.

---

## 3. Step 1 — Create a project

### Creating a project

1. Open the **Projects** page (http://localhost:3001)
2. Click **New project**
3. Enter a project name (e.g. `MedTronic_PowerVS_DAL10`) and optional description
4. Choose the **IBM Cloud target region** and **availability zone** — used in the
   Cloud Solution Export
5. Choose the **PowerVS region** and **datacenter** — used in all PowerVS exports
   (e.g. `us-south` / `dal10`). These can be changed later on the Export page.
6. Click **Create project**

> Both regions can be edited inline on the Export page at any time — you do not
> need to recreate a project to change the target datacenter.

### Folder organization

Projects can be organized into a two-level folder hierarchy:
**Root → Customer folder → Engagement folder**

This is useful for keeping multiple engagements per customer tidy.

**Creating a folder:**
1. On the Projects page, click **New folder**
2. Enter the folder name (e.g. `Medtronic`)
3. Click **Create** — the folder appears in the project list

**Creating a sub-folder (engagement level):**
1. Open a customer folder by clicking it
2. Click **New folder** — the new folder is created inside the current folder

**Moving a project into a folder:**
1. Open the **⋮** overflow menu on any project row
2. Click **Move to folder**
3. Choose the destination folder and click **Move**

**Renaming or deleting a folder:**
- Open the **⋮** overflow menu on a folder row
- Select **Rename folder** or **Delete folder**
- Deleting a folder moves its projects to root; it does not delete them

---

## 4. Step 2 — Upload a spreadsheet

### Supported formats

| Format | Notes |
|---|---|
| `.xlsx` / `.xls` | Any Excel workbook — no template required |
| `.csv` | Comma-separated values |
| Up to 50 MB | Larger files can be split into multiple uploads |

### What the parser does automatically

- **Any column layout** — column names are mapped by the AI; there is no required format
- **Merged cells** — forward-fills values across visually merged cells
- **Phantom rows** — ignores the thousands of empty rows Excel appends beyond real data
- **Title/banner rows** — if row 1 has fewer than 2 headers, falls back to row 2
- **Mixed types** — converts all values to clean JSON-safe types

### Uploading

1. Open a project and click **Upload**
2. Drag a file onto the drop zone or click **Browse files**
3. The parser runs and a **mapping confirmation preview** appears

### Mapping confirmation — verify column detection

After the file is parsed, a preview panel shows the **detected column names**
and **5 sample rows** from the source file before normalization begins. This
lets you verify that VM name, CPU, RAM, OS, disk, and cluster columns were
correctly detected.

| Action | Effect |
|---|---|
| **Looks good — proceed to normalize** | Continues to the Normalize page |
| **Re-upload different file** | Clears state so you can choose a different file |

> You can upload a replacement file at any time. The previous records and
> assumptions for the project are cleared and replaced with the new upload.

---

## 5. Step 3 — AI Normalization

### Starting normalization

1. On the **Normalize** page, click **Start normalization**
2. A progress bar shows: **complete / total** records processed
3. A per-record heartbeat timer shows how long the current record is taking
4. The name of the server currently being normalized is shown below the progress bar: *"Currently processing: vm-name"*

> **For Ollama (local):** phi4-mini typically takes 3–8 seconds per record.
> A 100-server inventory completes in roughly 5–15 minutes.

### What the AI infers

For each server the AI maps freeform customer columns to IBM VPC fields:

| Field | What the AI decides |
|---|---|
| CPU count | Reads any variation of "CPUs", "vCPUs", "cores" |
| RAM | Reads MB or GB; detects and corrects GB→MB unit mismatches |
| OS family | Maps 30+ OS name patterns to IBM VPC stock images |
| Disk size | Reads any disk/storage column. **x86 VSIs:** applies 100 GB min / 250 GB max boot disk rule; overflow becomes a separate Data Volume. **PowerVS (AIX / IBM i):** customer disk size passes through unchanged — no floor or ceiling. |
| Server type | If OS is AIX or IBM i → `powervs`; otherwise → `x86` |

Every inference is recorded as an **assumption** with field name, assumed value,
original value, reasoning, and confidence level (High / Medium / Low).

### Python fallback synthesizer

If the AI fails (timeout, invalid JSON, model overloaded), the Python fallback
synthesizer takes over. It reads the raw spreadsheet data directly using 64
field-name synonyms and applies IBM defaults. Records processed this way complete
as `complete` (not `error`) with **Low** confidence assumptions.

### Stuck records

If a record takes more than **90 seconds**, a **"Reset stuck & resume"** button
appears automatically. Click it to reset orphaned `processing` records and
resume from where normalization stopped.

---

## 6. Step 4 — Review Records

The Review page shows all normalized records in a sortable table. This is where
you inspect AI decisions, fix any problems, and prepare the data for export.

### Filter presets — focus on problems first

Four preset filter buttons sit above the records table. The page defaults to
**Needs attention** so problems surface immediately without manual filtering.

| Preset | What it shows | Default? |
|---|---|---|
| **Needs attention** | Error records first, then low-confidence AI results, then records missing key fields (CPU/RAM/OS) | ✅ Yes |
| **Errors** | Only `processing_status = error` records | — |
| **Excluded** | Only excluded records | — |
| **All** | Every record (all statuses, all types) | — |

Each button shows a count badge (e.g. "Needs attention (4)"). If zero records
need attention on load, the page silently shows **All** records with a green
"✓ All records look good" notification.

### Reading the table

| Column | Meaning |
|---|---|
| **Server Name** | Normalized VM name |
| **vCPUs / RAM** | CPU and memory after normalization |
| **OS** | Mapped IBM OS family |
| **Type** | Blue = x86 Virtual, Teal = Bare Metal, Purple = PowerVS |
| **Profile** | VPC Flex profile assigned (x86 only) |
| **Exclude** | Checkbox to remove from all exports |
| **Actions** | Expand row, view assumptions, edit record |

### Viewing AI assumptions

Click any row to expand it and see every assumption the AI made for that server.
Each assumption shows:
- **Field** — which value was inferred
- **Assumed** — what was written to the output
- **Original** — what the customer spreadsheet said
- **Reasoning** — why this value was chosen
- **Confidence** — High (direct map) / Medium (inferred) / Low (IBM default)

### Editing a record inline

Click the **Edit** (pencil) icon on any row to open the Edit Record modal.

**Editable fields:**
- Server Name, vCPUs, RAM (MB), Disk Provisioned (MB), Disk In Use (MB)
- OS, Datacenter, Cluster, Power State, NIC count, Disk count

Fields with a **red border** are critical (affect pricing directly).
Fields with a **yellow border** are advisory (affect report detail but not cost).

After saving, the record is immediately updated and any subsequent export
reflects your changes.

### Excluding a server

Check the **Exclude** checkbox on any row to remove that server from all exports.
- The row dims to 55% opacity with a strikethrough server name
- An optional **reason** field appears — enter text for the audit trail
- Excluded servers appear in the **"Excluded Servers"** sheet of the AI Assumptions Report

**Common exclusion reasons:**
- Server already migrated
- Decommissioned / out of scope
- Test/dev server excluded from sizing
- Customer explicitly requested exclusion

### Fixing failed records

If any records failed normalization (AI timeout + fallback also failed), a
**Failed Records** panel appears at the top of the Review page.

For each failed record:
1. Click **Edit & fix** — the Edit Record modal opens with fields pre-filled from
   the raw spreadsheet data using best-effort column matching
2. Fill in the required fields (red-bordered fields are mandatory for a valid export)
3. Click **Save** — the record is promoted to `complete` and joins the main table

### Bulk OS Replace

Use **Bulk OS Replace** (button above the records table) to replace the OS family
on all records matching a specific value in a single operation. This is useful for:
- Generating a lower-cost pricing estimate (e.g. replacing paid Windows or RHEL
  licences with a BYO/free Linux variant)
- Correcting a systematic mis-mapping where the AI assigned the wrong OS family
  to a large group of servers

**How to use it:**
1. Click **Bulk OS Replace**
2. In the modal, select the **OS to replace** (dropdown shows only OS values
   present in your project)
3. Select the **replacement OS**
4. The modal shows how many records will be affected. Expand **"Show N affected servers"**
   to see the first 10 server names before confirming.
5. Click **Replace OS on N records**

The change is permanent and logged as an assumption in the AI Assumptions Report,
so the substitution is clearly documented for the customer.

### Fix Nano Profiles (Flex-Nano warning)

If any x86 servers were assigned `nxf-1x1`, `nxf-1x2`, or `nxf-1x4` profiles, a
**yellow warning banner** appears on the Review page:

> ⚠ N server(s) have nxf-1x* profiles not recognized by the IBM Cloud Solutioning Tool.

**Why this matters:** The IBM Cloud Solutioning Tool only recognizes `nxf-2x1` and
`nxf-2x2` in its Data Domains sheet. Servers with `nxf-1x*` profiles will silently
fail to populate when you import the Cloud Solution Export.

**To fix:**
1. Click **Fix Nano Profiles** in the warning banner
2. Choose the target profile: `nxf-2x1` (2 vCPU / 1 GB RAM) or `nxf-2x2` (2 vCPU / 2 GB RAM)
3. Expand **"Show N affected servers"** to preview which servers will be upgraded before confirming
4. Click **Replace on N servers**

The upgrade sets `num_cpus = 2` and adjusts RAM to match the target profile.
The change is logged as an assumption.

### Bulk Exclude by filter

Use **Bulk Exclude** (button above the records table) to exclude all active records
matching a server name substring or OS family in one action.

**How to use it:**
1. Click **Bulk Exclude**
2. Choose filter type: **Server name contains…** or **OS equals…**
3. Enter the filter value (e.g. `dev`, `test-`, or select an OS from the dropdown)
4. The modal shows a live count of matching records. Expand **"Show N affected servers"**
   to preview the first 10 server names before confirming.
5. Optionally enter an **exclusion reason** (e.g. *"Test servers — out of scope"*)
6. Click **Exclude N records**

Excluded servers appear in the **Excluded Servers** audit sheet of the AI Assumptions
Report. Exclusion is reversible — uncheck the Exclude checkbox on any row at any time.

---

## 7. Step 5 — Export

The Export page generates all output files. The page is divided into two sections:
**x86 / VPC Workloads** and **PowerVS Workloads** — each section only appears if
the project contains that type of record.

### Migration Readiness Summary

At the top of the Export page, a colour-coded **Migration Readiness Summary**
banner shows the complete project health before any export is attempted.

| Stat tile | Shows |
|---|---|
| **Total servers** | All records (any status) |
| **x86 ready** | Complete, non-excluded x86/VPC records — export-ready |
| **PowerVS ready** | Complete, non-excluded PowerVS records — export-ready |
| **Pending** | Records not yet normalized |
| **Errors** | Records that failed normalization |
| **Excluded** | Records manually excluded from exports |

The banner header line gives a single clear decision:

| Colour | Message | Meaning |
|---|---|---|
| 🟢 Green | ✓ Ready to export | At least one x86 record complete, zero errors |
| 🔴 Red | ✗ N records need attention | Error records exist — review before exporting |
| 🟡 Amber | ⏳ Processing not yet started | No normalization run yet |
| 🟡 Amber | ⚠ No complete x86 records | Processing done but no results ready |

### Setting the target datacenter

Before exporting, confirm the target regions shown in the two banner rows below
the Readiness Summary:

- **IBM Cloud Target** — the VPC region and availability zone used in the Cloud
  Solution Export (e.g. `us-south` / `us-south-1`)
- **PowerVS target** — the PowerVS region and datacenter used in all PowerVS
  exports (e.g. `us-south` / `dal10`)

Click **Change region** / the pencil icon to edit either target inline.

---

### x86 / VPC exports

#### Cloud Solution Export ⭐ Primary

**File:** `CloudSolution_<ProjectName>_<date>.xlsx`
**Feeds:** IBM Cloud Cost Estimator (upload directly)
**Format:** 3-sheet workbook — Project Settings, Exceptions, Data Domains

This is the primary deliverable for x86 workloads. Upload it directly to the
IBM Cloud Cost Estimator to obtain VPC instance pricing. It is equivalent to
the output of the `rvtools2vpc.vmware-solutions.cloud.ibm.com` web tool.

Each server is mapped to a **Flex-Compute**, **Flex-Balanced**, or **Flex-Memory**
IBM VPC profile based on its CPU-to-RAM ratio. Servers with no matching profile
appear in the Exceptions sheet.

#### RVTools Export (22-sheet)

**File:** `RVTools_<ProjectName>_<date>.xlsx`
**Feeds:** VCF Migration Lite, IBM Cool, any tool requiring the full RVTools format
**Format:** Full 22-sheet RVTools 4.x workbook

Use this when a downstream tool validates that all 22 RVTools tabs are present.

#### AI Assumptions Report

**File:** `Assumptions_<ProjectName>_<date>.xlsx`
**Feeds:** Customer review, engagement documentation

Documents every AI decision with field, assumed value, original value, reasoning,
and confidence. Includes an "Excluded Servers" audit sheet.

---

### PowerVS exports

#### PowerVS Cloud Solution Export ⭐ Primary

**File:** `CloudSolution_PowerVS_<ProjectName>_<date>.xlsx`
**Feeds:** IBM PowerVS Cost Estimator (upload directly)
**Format:** 3-sheet workbook — Project Settings, Exceptions, Data Domains

Primary deliverable for AIX and IBM i workloads. Each server is mapped to an
S1022 (Power10 scale-out), E1050, or E1080 machine with entitled processor count,
OS family, and Tier 1 / Tier 3 storage.

#### PowerVS Cool Tool Export

**File:** `COOL_PowerVS_<ProjectName>_<date>.xlsx`
**Feeds:** IBM Cool (PowerVS input)
**Format:** 4-sheet RVTools workbook (IBM Cool input format)

Upload to IBM Cool **separately** from the x86 Cool Tool export to get dedicated
PowerVS pricing.

#### PowerVS RVTools Export (22-sheet)

**File:** `RVTools_PowerVS_<ProjectName>_<date>.xlsx`
**Feeds:** VCF Migration Lite (PowerVS), tools requiring all 22 tabs
**Format:** Full 22-sheet RVTools workbook, PowerVS records only

#### PowerVS AI Assumptions Report

**File:** `Assumptions_PowerVS_<ProjectName>_<date>.xlsx`
**Feeds:** Customer review, engagement documentation

AI decisions for PowerVS records only.

---

## 8. IBM Price Estimator workflow

The IBM Price Estimator is a separate Excel workbook (provided by IBM) that
calculates per-LPAR PowerVS pricing when you open it in Excel. RVTool Genesis
can populate its yellow input cells automatically from your project's PowerVS
records.

### Setup (one time per project)

1. Obtain the IBM Power Virtual Server Price Estimator `.xlsx` from IBM
   (any version — the tool detects the layout automatically)
2. On the Export page, scroll to the **IBM Price Estimator** section
   (inside the PowerVS section)
3. Click **Upload IBM Price Estimator**
4. Select the `.xlsx` file — the tool validates that it contains the
   `Multiple LPAR Price Estimate` sheet and stores it for the project

> The template is stored per-project. You only need to upload it once;
> subsequent downloads always use the stored template.

### Populate and download

1. Click **Populate & Download**
2. The tool fills in the yellow input cells for every PowerVS server:
   - **Column B** — LPAR name
   - **Column C** — LPAR Qty (always 1)
   - **Column D** — Data Center (e.g. DAL10)
   - **Column E** — System (S1022 / E1050 / E1080 based on CPU and RAM)
   - **Column F** — Processor Type (S = Shared Uncapped)
   - **Column G** — Desired Cores (CPU × 0.5 entitlement, rounded to 0.25)
   - **Column H** — Memory (GB)
   - **Column N** — OS (AIX / IBM_i / IBM_i_MOL / Red Hat GP / etc.)
   - **Column P** — Storage Tier 1 GB (AIX / IBM i workloads)
   - **Column Q** — Storage Tier 3 GB (Linux on Power workloads)
3. Open the downloaded file in **Excel** — all pricing formulas recalculate
   automatically when the file opens

### Machine selection rules

| Criteria | Machine assigned |
|---|---|
| ≤ 51 cores AND ≤ 1,904 GB RAM | S1022 (Power10 scale-out) |
| ≤ 120 cores (any RAM) | E1050 (Power10 enterprise) |
| > 120 cores | E1080 (Power10 enterprise, largest) |

### Truncation warning (> 300 servers)

The template has approximately 300 pre-built rows. If your project has more than
300 active PowerVS servers, only the first 300 are written and a warning is shown.
Use the batch export endpoint for large inventories (see [Tips for large engagements](#11-tips-for-large-engagements)).

### Replacing the template

Click **Replace template** to upload a newer version of the IBM Price Estimator.
The stored template is replaced immediately; the next Populate & Download uses
the new version.

---

## 9. Settings — LLM provider & model recommendations

Access Settings from the navigation bar (top right gear icon or `/settings`).

### Choosing an LLM provider

| Provider | Best for | API key needed |
|---|---|---|
| **Ollama (local)** | Offline work, no cloud spend, maximum privacy | No |
| **IBM watsonx.ai** ⭐ | IBM engagement work — Granite models | Yes |
| **OpenAI-compatible** | GPT-4o / Azure OpenAI / local vLLM / LM Studio | Yes |
| **Anthropic** | Claude models | Yes |

Select the radio button for your desired provider, fill in credentials, and click
**Test connection** to validate before saving. The test sends a short prompt and
reports latency and a sample response.

Changes take effect immediately on the next normalization run. No container
restart needed.

### Watsonx.ai setup

1. Log in to [cloud.ibm.com](https://cloud.ibm.com)
2. **Manage → Access (IAM) → API keys** → Create an API key
3. Open your watsonx.ai project → **Manage → General** → copy the Project ID
4. Enter both in Settings and click **Test connection**
5. Recommended model: `ibm/granite-3-8b-instruct`

An IBM IAM Bearer token is obtained once and cached for 50 minutes. IAM is called
once per processing run, not once per server.

### Model recommendation banner

When a newer or more capable model becomes available for your current provider,
a **recommendation banner** appears at the top of the Settings page.

**Options:**
- **Apply** — upgrades to the recommended model immediately; the previous model
  is saved so you can roll back
- **Roll back** — reverts to the model you were using before the last apply
- **Snooze for 7 days** — dismisses the banner until next week

---

## 10. Project management — folders, backup, restore

### Deleting a project

1. On the Projects page, open the **⋮** overflow menu on any project row
2. Click **Delete project**
3. Confirm in the dialog — this is permanent and removes all records, assumptions,
   and stored exports for that project

### Backing up a project

1. Open the **⋮** overflow menu on any project row
2. Click **Backup project**
3. Optionally check **Include original spreadsheet file** (increases file size)
4. Click **Download backup** → saves `rvtg-<project-name>-<date>.json`

The backup contains all normalized records, assumptions, server types, exclusion
flags and reasons, and project metadata. Generated `.xlsx` exports are not included
(they are regenerated in seconds from the saved data).

### Backing up all projects

Click the **Backup all** button in the Projects page header.
Downloads `rvtoolgenesis-backup-<date>.zip` — one JSON bundle per project.

### Restoring from backup

1. Click **Restore from backup** (ghost button in the Projects page header)
2. Select a `.json` (single project) or `.zip` (multi-project) backup file
3. Restored projects appear immediately with a `(restored YYYY-MM-DD)` suffix
4. Navigate straight to **Review → Export** — no re-normalization needed

> The PostgreSQL data volume (`postgres_data`) survives container restarts and
> `docker compose down`. Backup/restore is for off-machine portability and
> archiving — not crash recovery.

---

## 11. Tips for large engagements

### Inventories over 500 servers

- **Use watsonx.ai or OpenAI** instead of Ollama for large runs. Cloud providers
  are significantly faster and don't require a powerful local Mac.
- **Upload in segments** if the customer spreadsheet has mixed populations
  (e.g. separate x86 and AIX/IBM i servers into separate projects).
- **Watch the heartbeat timer** on the Normalize page. If it exceeds 90 seconds
  for multiple records, click "Reset stuck & resume" — this is normal with Ollama
  under memory pressure.

### Inventories with many excluded servers

- Use **Bulk OS Replace** before exclusion to generate a scenario estimate
  (e.g. all Windows → Linux for a cost comparison) without permanently altering
  the primary project.
- Exclusion is reversible — uncheck the Exclude checkbox at any time.

### PowerVS inventories over 300 servers

The IBM Price Estimator template has ~300 pre-built rows. For larger inventories:
- Contact the tool maintainer for the batch export workflow
- Or split the inventory across two projects (e.g. by business unit)

### Naming conventions

Use a consistent naming convention for projects to keep the folder hierarchy useful:
```
Customer_Workload_Datacenter_Date
e.g.  Medtronic_PowerVS_DAL10_2026Q3
      Medtronic_x86_VPC_USSouth_2026Q3
```

---

## 12. Troubleshooting quick reference

| Symptom | Cause | Fix |
|---|---|---|
| **Upload shows 0 records** | Parser couldn't find data rows | Check the upload count badge; if 0, the file may use a non-standard layout. Try exporting the customer spreadsheet as CSV and re-uploading. |
| **Normalization never completes** | Ollama not running or model not pulled | Run `ollama pull phi4-mini` in a terminal and restart the app (`./setup.sh`). |
| **"Reset stuck & resume" button appears** | Record in Ollama taking >90 s | Click the button — it resets the stuck record and resumes. Normal under memory pressure. |
| **Cloud Solution Export has empty rows** | Records with `nxf-1x*` profiles | Use **Fix Nano Profiles** on the Review page before exporting. |
| **IBM Price Estimator opens with #UNCALCULATED** | Expected behavior | These are formula cells. Open in Excel — they recalculate automatically. Do not open in Numbers or LibreOffice. |
| **IBM Price Estimator shows $0 pricing** | OS value doesn't match Assumptions sheet | Verify the OS column in the Multiple LPAR Price Estimate sheet uses exact values: `AIX`, `IBM_i`, `IBM_i_MOL`, `Red Hat GP`, `Red Hat SAP`, `SUSE GP`, `SUSE SAP`, `BYO Lnx / NA`. |
| **Export page shows 0 PowerVS servers** | Records not tagged as PowerVS | In Review, check that AIX/IBM i servers show the purple "PowerVS" tag. If not, use Edit Record to set the correct OS, then re-export. |
| **PowerVS disk size was changed to 100 GB** | Old normalization run before v1.3.0 | Re-normalize affected records (Edit Record → save, or reset to pending). v1.3.0+ passes customer disk sizes through unchanged for PowerVS. |
| **Backup restore creates a duplicate project** | Expected behavior | Restore always creates a new project with `(restored YYYY-MM-DD)` suffix. Delete the original if it's no longer needed. |
| **Test connection fails for watsonx.ai** | Wrong API key or Project ID | Confirm the API key has `ML Platform` scope. Confirm the Project ID is from the watsonx.ai project (not the IBM Cloud project). |
| **Container won't start** | Port conflict | Check `docker ps` — another service may be using port 3001 or 8001. Edit `docker-compose.yml` to use different host ports. |
