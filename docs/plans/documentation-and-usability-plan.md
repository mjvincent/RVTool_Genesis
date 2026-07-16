# Documentation & Usability Improvement Plan

## Top-Level Overview

**Goal:** Bring all documentation fully current with the implemented feature set,
create a practitioner User Guide and an Operations Guide, and fix 7 locations where
generic "Please try again" errors give users no actionable information.

**Scope of documentation gaps identified:**
- 12 implemented features are completely absent from README.md
- 3 features are partially or incorrectly described
- No USER_GUIDE.md or OPERATIONS_GUIDE.md exist
- Changelog uses branch names as section headers instead of semantic versions

**Enhancements deferred to a future plan (not in scope here):**
- See "Enhancement Ideas" appendix at the bottom of this file for future reference

**Non-goals:**
- No new features
- No UI redesign
- No test changes

---

## Sub-Tasks

### Sub-Task 1 — Create `docs/USER_GUIDE.md`

**Intent:** Give IBM practitioners a single reference that covers the complete
engagement workflow from first launch to final export download, including every
feature that is currently undocumented.

**Expected Outcomes:**
- A comprehensive Markdown guide covering all 8 export types
- Step-by-step instructions for the full 5-step workflow
- Coverage of all Review-page features (edit, exclude, bulk OS replace, nxf fix)
- Coverage of the IBM Price Estimator populate workflow
- Coverage of the Settings page (LLM providers, model recommendations)
- Coverage of folder organization and project management
- A "Tips for large engagements" section
- A "Troubleshooting quick reference" table

**Sections to write:**
1. Introduction — what the tool produces and why
2. Prerequisites — Docker/OrbStack, Ollama
3. Step 1: Create a project — folder organization, region selection, naming conventions
4. Step 2: Upload a spreadsheet — supported formats, what the parser does
5. Step 3: AI Normalization — reading progress, reset stuck, what Python fallback means
6. Step 4: Review Records — table features, edit inline, exclude, assumptions panel,
   failed records panel, Bulk OS Replace, Fix Nano Profiles warning banner
7. Step 5: Export — every export type (8 types) with filename pattern, purpose,
   which downstream tool consumes it, and when to use each
8. IBM Price Estimator workflow — upload template, populate + download, truncation warning
9. Settings — 4 LLM providers, test connection, model recommendation banner
10. Project management — folders, backup/restore, delete
11. Tips for large engagements (>500 servers)
12. Troubleshooting quick reference

**Relevant Context:**
- All pages in `web/src/pages/`
- All components in `web/src/components/` (BulkOSModal, BulkNxfModal, EditRecordModal)
- Export page pricing template section: `web/src/pages/ExportPage.tsx` lines 565-634
- Settings page model recommendations: `web/src/pages/SettingsPage.tsx` lines 66-140
- Folder features: `web/src/pages/ProjectsPage.tsx` (full file)

**Status:** `[ ] pending`

---

### Sub-Task 2 — Create `docs/OPERATIONS_GUIDE.md`

**Intent:** Give the person who installs, configures, and maintains the tool a clear
reference for setup, environment variables, Docker operations, database, security,
and troubleshooting.

**Expected Outcomes:**
- Complete install instructions (clone → setup.sh)
- All environment variables documented with valid values and security notes
- Docker compose service breakdown, port mapping, volume durability
- Makefile commands explained
- Database schema overview
- LLM provider setup for all 4 providers including IBM watsonx IAM flow
- Security checklist (SECRET_KEY, API key encryption, exposed ports)
- Upgrading / pulling latest changes
- API reference pointer (Swagger at /api/docs)

**Sections to write:**
1. System requirements — macOS, Docker/OrbStack, disk space
2. Installation — git clone, chmod, ./setup.sh (what the script does step by step)
3. Environment variables — every variable, default, valid range, security note
4. Docker services — web, api, db ports, health checks, restart policy
5. Makefile reference — all 8 commands described
6. LLM provider configuration — per-provider step-by-step (Ollama, watsonx, OpenAI, Anthropic)
7. Security hardening — SECRET_KEY rotation, API key encryption, network exposure
8. Upgrading — git pull, rebuild steps, migration commands
9. Database operations — volume durability, manual psql access, alembic migration commands
10. API documentation — Swagger UI location, key endpoints summary

**Relevant Context:**
- `README.md` existing content (extract admin sections)
- `docker-compose.yml` service definitions
- `Makefile` (all targets)
- `api/alembic/versions/` (migration history)
- `api/core/config.py` (env var defaults)

**Status:** `[ ] pending`

---

### Sub-Task 3 — Update `README.md`

**Intent:** The README is the first thing anyone reads. It currently has 12 missing
features, 4 inaccuracies, and a changelog using branch names instead of versions.
Bring it fully current.

**Specific changes required:**

**Inaccuracies to fix:**
1. Line 168: "exactly 4 sheets consumed by IBM Cool tool" — tool generates BOTH 4-sheet
   (IBM Cool input) AND 22-sheet (VCF Migration Lite); clarify which is which
2. Lines 294-299: PowerVS exports — code has THREE types (4-sheet Cool Tool, 22-sheet
   VCF, 3-sheet PowerVS Calculator), README only mentions 22-sheet + Assumptions
3. Line 37: "download a Cloud Solution Export" — two Cloud Solution Exports exist
   (VPC Calculator for x86, PowerVS Calculator for AIX/IBM i)
4. Architecture section line 132: export router is split across `exports.py` and
   `pricing_template.py` — show both

**Missing sections to add:**
1. After "What it does": new **All Exports** table — all 8 output types with
   filename pattern, which IBM tool consumes it, and when to use it
2. After "Server Exclusion": new **Bulk Operations** section — Bulk OS Replace and
   Fix Nano Profiles (nxf-1x* → nxf-2x1/2x2)
3. After "Bulk Operations": new **IBM Price Estimator** section — upload template
   once, populate + download, truncation warning >300 servers
4. In LLM Providers section: add **Model Recommendations** subsection — auto-upgrade
   banner, apply/rollback/snooze buttons
5. In Projects section: add **Folder Organization** subsection — two-level hierarchy,
   create/rename/delete folders, move projects

**Changelog restructure:**
- Convert branch-name headers to semantic versions:
  - `v1.0.0` — original stable release (keep existing content)
  - `v1.1.0` — PowerVS exports (Cloud Solution, Cool Tool, 22-sheet, Assumptions)
              + IBM Price Estimator template filler
              + Folder organization
              + Backup/Restore
              + LLM multi-provider + model recommendations
  - `v1.2.0` — Data Domains 174-row fix + nxf-2x1/2x2 addition
              + Flex-Nano profile warning + bulk replace
              + Edit record modal (inline vinfo editing)
              + Bulk OS Replace

**Add links at top:**
- `📖 [User Guide](docs/USER_GUIDE.md)` and `⚙️ [Operations Guide](docs/OPERATIONS_GUIDE.md)`

**Relevant Context:**
- `README.md` (full file — must be read before editing)
- `VERSION` file (current version)
- Sub-Agent analysis above for the complete list of inaccuracies

**Status:** `[ ] pending`

---

### Sub-Task 4 — Fix 7 error message locations for actionable feedback

**Intent:** Seven frontend components emit generic "Please try again" messages
that give users no actionable information when an API error occurs. Apply the
existing `FailedRecordsPanel.tsx` error-translation pattern to all 7 locations.

**Pattern to apply (one line change per location):**
```typescript
// Before:
setError('Upload failed. Please try again.');

// After:
setError(`Upload failed: ${(err as any)?.detail || (err as any)?.message || 'Please try again.'}`);
```

**Locations to fix (file → current generic string → improved string):**

| # | File | Current | Improved prefix |
|---|------|---------|----------------|
| 1 | `web/src/pages/UploadPage.tsx` | "Upload failed. Please try again." | "Upload failed: {detail}" |
| 2 | `web/src/pages/NewProjectPage.tsx` | "Failed to create project. Please try again." | "Failed to create project: {detail}" |
| 3 | `web/src/components/BulkOSModal.tsx` | "Failed to apply OS replacement. Please try again." | "Failed to apply OS replacement: {detail}" |
| 4 | `web/src/components/BulkNxfModal.tsx` | "Failed to apply profile replacement. Please try again." | "Failed to apply profile replacement: {detail}" |
| 5 | `web/src/components/EditRecordModal.tsx` | "Failed to save changes. Please try again." | "Failed to save changes: {detail}" |
| 6 | `web/src/pages/ProjectsPage.tsx` | "Restore failed. Please try again." | "Restore failed: {detail}" |
| 7 | `web/src/pages/NormalizePage.tsx` | "Could not start normalization. Please try again." + "Reset failed — try again." | "Could not start normalization: {detail}" + "Reset failed: {detail}" |

**Reference implementation:**
- `web/src/components/FailedRecordsPanel.tsx` lines 40-81 — gold standard for error translation

**Status:** `[ ] pending`

---

### Sub-Task 5 — Commit and push

**Intent:** Ship all documentation and usability improvements to both remotes.

**Todo List:**
1. `git add docs/USER_GUIDE.md docs/OPERATIONS_GUIDE.md README.md`
2. `git add web/src/pages/UploadPage.tsx web/src/pages/NewProjectPage.tsx`
3. `git add web/src/components/BulkOSModal.tsx web/src/components/BulkNxfModal.tsx`
4. `git add web/src/components/EditRecordModal.tsx web/src/pages/ProjectsPage.tsx`
5. `git add web/src/pages/NormalizePage.tsx`
6. `git commit -m "docs: user guide, operations guide, README refresh, error message consistency (v1.2)"`
7. `git push origin main && git push ibm main`

**Status:** `[ ] pending`

---

## Enhancement Ideas (Future Work — Not In Scope for This Plan)

These are usability improvements that would make the tool meaningfully better
for IBM practitioners. Recorded here for future planning — none are being
implemented as part of this documentation task.

### High Value / Low Effort

1. **Export summary panel**
   A post-export summary showing: total servers written, total excluded, servers
   per machine type (S1022/E1050/E1080 for PowerVS; profile distribution for VPC),
   any truncation warnings. Currently the user has no feedback after clicking
   "Populate & Download" beyond a file appearing. Even a simple toast with
   "12 servers written to S1022, 4 to E1050" would reduce confusion.

2. **Duplicate project**
   One-click "Duplicate project" option in the ⋮ overflow menu. Useful when
   running the same inventory through multiple scenarios (e.g. "DAL10 sizing"
   vs "WDC04 sizing"). Saves re-uploading and re-normalizing the same file.

3. **Processing status bar on Projects page**
   Show a small inline progress indicator (e.g. "47 / 120 normalized") on each
   project card on the Projects page. Currently you have to click into a project
   to see if normalization is still running.

4. **Bulk exclude by filter**
   In the Review table: "Exclude all matching" option — select all test/dev servers
   by OS filter or name pattern and bulk-exclude in one action. Currently exclusion
   is one-by-one. High value for large inventories (500+ servers) with many
   out-of-scope records.

### Medium Value / Medium Effort

5. **Column mapping confirmation step (Upload page)**
   After parsing, show the user a preview of which source columns mapped to which
   normalized fields before normalization starts. Currently the parser silently
   makes all decisions. A "confirm mapping" step (even just a read-only preview)
   would build trust and catch mis-mappings before spending LLM credits on 500+
   records.

6. **Re-run normalization on a single record**
   A "Re-normalize" button on each row in the Review table. Useful when you edit
   a field in the raw data and want the AI to re-process just that record. Currently
   you can only reset stuck records, not re-trigger a single healthy one.

7. **Project-level notes / description field**
   Free-text notes field on the project card. IBM practitioners often need to record
   customer context ("Medtronic — Power10 only, exclude UAT servers") that currently
   lives in external notes. Surface the existing `description` field more prominently
   and make it editable from the Projects page.

8. **Export history panel**
   Show the last 3-5 exports per project with filename and timestamp. Currently
   there's no record of what was downloaded when, which makes it hard to know if
   the downloaded file is current.

### Lower Value / Higher Effort

9. **Server search / filter in Review table**
   Full-text search across LPAR names + OS + type with instant filter. Large
   inventories (300+ servers) are hard to navigate with pagination alone.
   Carbon DataTable has built-in filter toolbar support.

10. **CSV export of normalized records**
    One-click download of all normalized records as a flat CSV. Useful for
    sharing with customers or importing into other tools without opening Excel.

11. **PowerVS workload summary dashboard**
    Before export: show a breakdown of the PowerVS records by machine type
    (how many S1022 vs E1050 vs E1080), total core entitlement, total memory,
    and storage by tier. Helps practitioners spot sizing anomalies before
    generating the Price Estimator output.
