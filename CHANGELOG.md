# Changelog

All notable changes to RVTool Genesis are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) conventions.
Versions are tagged on `main`; each section maps to one or more git commits.

---

## [Unreleased]

---

## [1.3.0] — 2025-07-17

### Fixed
- **PowerVS disk clamping bypass** — IBM Cloud VPC boot-volume constraints
  (100 GB minimum / 250 GB maximum) no longer apply to PowerVS (AIX / IBM i /
  Linux-on-Power) records. The customer's raw disk size is passed through unchanged
  to the IBM Price Estimator and all PowerVS exports. x86 VPC clamping behaviour
  is unaffected. Detection uses both the LLM `server_type` field and `_is_powervs_os()`
  on `os_config` as a belt-and-suspenders guard.
  (`api/services/ai_normalizer.py` — `_sanitize_numeric_fields`)

### Added
- **14 new unit tests** for disk-clamping behaviour
  (`tests/test_normalizer_disk_clamping.py`) — 6 x86 tests confirming clamping
  still fires, 8 PowerVS tests confirming raw pass-through for AIX, IBM i,
  Linux-on-Power (SAP), and the `os_config` guard path.

---

## [1.2.2] — 2025-07-17

### Added
- **UX polish — 5 improvements** across the Review, Normalize, and bulk-operation flows:
  - Stale error/success banners now clear on page navigation (ReviewPage, UploadPage,
    NormalizePage unmount cleanup).
  - Review page shows an info banner instead of a blank table when no records have been
    normalized yet.
  - All three bulk-operation modals (Bulk OS Replace, Fix Nano Profiles, Bulk Exclude)
    now display a collapsible Carbon Accordion section listing the first 10 affected
    server names before confirmation, with an "…and N more" overflow label.
  - Normalize polling adds exponential backoff after 3 consecutive API failures
    (interval doubles up to a 30 s cap, resets to 2 s on success).
  - Normalize page shows "Currently processing: `<vm-name>`" below the progress bar
    while a record is in-flight (backend: `current_record_name` added to
    `ProcessingStatusResponse`).

---

## [1.2.1] — 2025-07-16

### Added
- **Export summary panel** — After populating the IBM Price Estimator, the Export
  page displays a machine-type breakdown card (S1022 / E1050 / E1080 counts).
  Response headers `X-Written-Count`, `X-Skipped-Count`, and `X-Machine-Counts`
  added to the pricing template endpoint.
- **Duplicate project** — One-click project copy from the ⋮ overflow menu. Copies
  name, description, folder, VPC and PowerVS region/datacenter settings, and the
  stored pricing template if one exists.
- **Processing status badge** — Project cards on the Projects page show a green
  "✓ Complete" pill or an amber "N / M normalized" pill based on parallel
  `Promise.allSettled()` status fetches.
- **Bulk Exclude by filter** — New "Bulk Exclude" button on the Review page.
  Filter by server name substring or OS family; all matching active records are
  excluded atomically with a documented assumption per record. Live preview count
  updates as you type.

---

## [1.2.0] — 2025-07-15

### Added
- **Flex-Nano profile warning + bulk replace** — Review page shows a warning
  banner when any x86 server resolves to an `nxf-1x1`, `nxf-1x2`, or `nxf-1x4`
  profile not recognized by the IBM Cloud Solutioning Tool. "Fix Nano Profiles"
  button upgrades all affected servers to `nxf-2x1` or `nxf-2x2` in one action;
  change is logged as an assumption.
- **Edit record modal** — Any normalized record can be edited inline from the
  Review table. 11 editable vinfo fields with critical (red) and advisory (yellow)
  severity indicators. Failed records can be pre-filled from raw spreadsheet data
  and promoted to `complete` on manual edit.
- **Bulk OS Replace** — Replace the OS family on all records matching a chosen
  value in one operation; changes are logged as assumptions.
- **Folder organization** — Two-level folder hierarchy (Root → Customer →
  Engagement). Create, rename, delete folders; move projects between folders.

### Fixed
- **Data Domains coverage** — `_DATA_DOMAINS_ROWS` expanded from 75 to 174 rows
  covering all non-Flex IBM VPC profile families (`bx2-*`, `cx2-*`, `mx2-*`,
  `bx3d-*`, `cx3d-*`, `mx3d-*`, `ux2d-*`, `gx2-*`, `gx3-*`, `vx2d-*`, `ox2-*`).
  Resolves blank rows in the IBM Cloud Cost Estimator after import.
- **nxf-2x1 / nxf-2x2 added to Data Domains** — Flex-Nano profiles now recognized
  by the IBM Cloud Solutioning Tool.

---

## [1.1.0] — 2025-07-14

### Added
- **PowerVS Cloud Solution Export** — 3-sheet IBM PowerVS Calculator workbook
  (Project Settings, Exceptions, Data Domains). PowerVS equivalent of the x86
  Cloud Solution Export; direct upload to IBM PowerVS Cost Estimator.
- **PowerVS Cool Tool Export** — 4-sheet RVTools workbook for IBM Cool PowerVS
  pricing. Must be uploaded to IBM Cool separately from the x86 export.
- **PowerVS RVTools Export (22-sheet)** — Full 22-sheet format for VCF
  Migration Lite.
- **PowerVS AI Assumptions Report** — Assumptions for PowerVS records only.
- **IBM Price Estimator template filler** — Upload the IBM Power Virtual Server
  Price Estimator `.xlsx` once per project. Click "Populate & Download" to fill
  the yellow input cells from PowerVS records using surgical zip-level XML surgery
  (preserves all formulas, named ranges, and VML drawings). Machine type
  auto-selected: S1022 / E1050 / E1080.
- **Backup & Restore** — Download any project as a portable `.json` bundle; full
  system `.zip` backup; restore on any instance without re-normalization.
- **Multi-provider LLM support** — Settings page: Ollama (local, default),
  IBM watsonx.ai, OpenAI-compatible, Anthropic Claude. AES-256 Fernet encryption
  for all cloud API keys at rest.
- **Model recommendations** — Auto-detect available model upgrades per provider;
  one-click apply, rollback, or 7-day snooze.
- **PowerVS region/datacenter per project** — Independent from VPC region; set
  at project creation; editable on the Export page.

---

## [1.0.0] — 2025-07-10 — First stable release

### Added
- **Cloud Solution Export** — 3-sheet IBM Cloud Cost Estimator workbook (Project
  Settings, Exceptions, Data Domains). Profiles x86 servers onto IBM VPC Flex
  instances. Eliminates the need for the `rvtools2vpc` web tool.
- **RVTools Export (22-sheet)** — Full 22-tab format required by VCF Migration
  Lite and IBM Cool.
- **AI Assumptions Report** — Every AI inference documented with field, assumed
  value, original value, reasoning, and confidence.
- **IBM VPC profile selection** — Flex-Compute (`cxf`), Flex-Balanced (`bxf`),
  Flex-Memory (`mxf`) selected automatically from CPU/RAM ratio.
- **IBM VPC boot disk sizing** — Boot disk clamped to 100 GB minimum / 250 GB
  maximum per IBM VPC rules (x86 VSIs only). Overflow written as a separate Data
  Volume row. Both cases recorded as documented assumptions.
- **`total_disk_mb` field** — Full original disk size preserved before boot cap
  so the Data Volume is never lost when the boot disk is clamped.
- **GB → MB unit mismatch detection** — Auto-corrects raw GB values in MB fields;
  cross-checked against raw column names; fix logged as assumption.
- **PowerVS OS families** — Eight IBM Cool PowerVS OS families (`AIX`, `IBM i`,
  `IBM i MOL`, `Linux BYOL`, `SAP SUSE`, `SAP Red Hat`, `Red Hat GP`, `SUSE GP`)
  mapped at normalize time and written to the RVTools exports.
- **`Operating System VS` column** — Cloud Solution Export populates the IBM VPC
  stock image name for every x86 row including SAP and SQL Server variants.
- **PowerVS auto-detection** — AIX and IBM i OS designate records as
  `server_type = "powervs"` automatically, enforced in both LLM and fallback paths.
- **Server exclusion** — Exclude checkbox in Review table; optional reason stored
  in DB; Excluded Servers audit sheet in AI Assumptions Report.
- **Per-project VPC region/zone** — 15 regions, all standard zones.
- **Ollama timeout + retry + Python fallback synthesizer** — Records never get
  permanently stuck. 120 s timeout, one retry, then Python synthesizer using 64
  column-name synonyms.
- **Reset stuck endpoint + UI button** — One-click recovery from stuck
  normalization without needing the terminal.
- **VERSION file** — Single source of truth at repo root.

---

[Unreleased]: https://github.com/mjvincent/RVTool_Genesis/compare/v1.3.0...HEAD
[1.3.0]: https://github.com/mjvincent/RVTool_Genesis/compare/v1.2.2...v1.3.0
[1.2.2]: https://github.com/mjvincent/RVTool_Genesis/compare/v1.2.1...v1.2.2
[1.2.1]: https://github.com/mjvincent/RVTool_Genesis/compare/v1.2.0...v1.2.1
[1.2.0]: https://github.com/mjvincent/RVTool_Genesis/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/mjvincent/RVTool_Genesis/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/mjvincent/RVTool_Genesis/releases/tag/v1.0.0
