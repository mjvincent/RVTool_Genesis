# Feature Plan — SECRET_KEY Onboarding + Billing Type on Cloud Solution Export

## Overview

Two independent improvements:

1. **SECRET_KEY onboarding** — The `setup.sh` script currently copies `.env.example` verbatim, which contains the known-insecure default `SECRET_KEY`. As of v1.7.0 the API hard-fails on startup when that default is present. New users hit a confusing crash on their very first run. `setup.sh` should auto-generate a strong key during first-time setup, and the README Quick Start should explain the requirement clearly. Windows users (running `setup.sh` via Git Bash or WSL) must also be covered — Python is available in the Docker environment so a cross-platform Python fallback is used when `openssl` is not found.

2. **Billing type at export time** — The Cloud Solution Export (VPC Calculator xlsx) hardcodes `"PAYG"` in the Billing Type column of every Compute row. IBM Cloud pricing differs meaningfully between PAYG, 1 Yr Reserved, and 3 Yr Reserved. A modal prompt at download time lets the user choose before each export; no persistence required. The exact strings the IBM Cloud Solutioning Tool recognises are: `PAYG`, `1 Yr Reserved`, `3 Yr Reserved`.

---

## Sub-Task 1 — Auto-generate SECRET_KEY in setup.sh

**Intent:**  
`setup.sh` currently copies `.env.example` → `.env` on first run, leaving the default insecure `SECRET_KEY`. Since v1.7.0 the API refuses to start with that default, so first-time users immediately hit a startup crash with no obvious fix. Generating a strong key automatically during setup eliminates the failure and removes a manual step.

**Expected Outcomes:**
- On first run (`setup.sh` with no existing `.env`), a cryptographically strong `SECRET_KEY` is generated and written into `.env` automatically.
- The user sees a clear console message confirming the key was generated.
- Users who already have a `.env` are unaffected (existing behaviour preserved).
- `.env.example` keeps the placeholder value so it remains a valid reference template.

**Todo List:**
1. In `setup.sh`, after copying `.env.example` → `.env`, generate a 32-byte hex secret and `sed`-replace the default `SECRET_KEY` value in the new `.env`. Use the following cross-platform generation strategy (try in order):
   - `openssl rand -hex 32` — available on macOS, Linux, Git Bash for Windows, WSL
   - `python3 -c "import secrets; print(secrets.token_hex(32))"` — fallback when openssl is absent
   - If neither is available, leave the placeholder and print a `warn` message instructing the user to run `make generate-secret` manually before starting.
2. Add a `success` console message confirming the key was auto-generated (e.g. "Generated SECRET_KEY in .env — keep this file private").
3. Ensure the `sed` replacement targets only the `SECRET_KEY=` line to avoid accidental substitution elsewhere in `.env`.

**Relevant Context:**
- `setup.sh` lines 93–99: the env copy block.
- `.env.example` line 21: `SECRET_KEY=rvtool-genesis-change-me-in-production`.
- `api/main.py` lines 59–79: the startup enforcement check — compares against `_DEFAULT_SECRET_KEY`.
- `make generate-secret` already exists as a standalone helper for users who need to rotate keys manually.

**Status:** [x] complete

---

## Sub-Task 2 — Update README Quick Start for SECRET_KEY

**Intent:**  
Even with the auto-generation fix in Sub-Task 1, the README Quick Start should briefly explain the SECRET_KEY requirement so users understand what it is, why it exists, and how to rotate it. This is especially important for IBM-facing deployments where a second person picks up the repo.

**Expected Outcomes:**
- The Quick Start section has a short note explaining that `setup.sh` auto-generates a `SECRET_KEY` on first run.
- A brief mention that to rotate the key (e.g. after sharing the repo), run `make generate-secret`, paste the output into `.env`, and restart the API.
- The Security hardening section (already updated in v1.7.0) remains the authoritative reference; the Quick Start note just points to it.

**Todo List:**
1. In `README.md` Quick Start section, add a callout block (blockquote or `> **Note:**`) after the `setup.sh` description explaining the auto-generated `SECRET_KEY`.
2. Add a one-liner pointing to the Security hardening section for rotation instructions.

**Relevant Context:**
- `README.md` lines 76–93: current Quick Start section.
- `README.md` `## 7. Security hardening` (in `docs/OPERATIONS_GUIDE.md`): the detailed reference.
- `README.md` lines 135–160: Environment Variables table — `SECRET_KEY` row already present with description.

**Status:** [x] complete

---

## Sub-Task 3 — Billing type modal on Cloud Solution Export

**Intent:**  
The VPC Calculator xlsx hardcodes `"PAYG"` in the `Billing Type` column for every Compute row. IBM Cloud reserved pricing (1 Yr, 2 Yr) is significantly cheaper and is a common choice in migration proposals. Adding a modal prompt at download time — radio buttons for PAYG / 1 Yr Reserved / 3 Yr Reserved — lets the user control this per-export without any DB changes or persistence.

**Expected Outcomes:**
- Clicking "Download Cloud Solution Export" opens a small Carbon `Modal` with three radio button options: `PAYG` (default selected), `1 Year Reserved`, `2 Year Reserved`.
- Confirming the modal triggers the existing export flow, passing the chosen billing type through to the generator.
- The generated xlsx writes the chosen value into every `Billing Type` cell in the Project Settings sheet.
- Cancelling the modal does nothing (export does not start).
- The existing export flow (API call, download, done-state) is otherwise unchanged.

**Todo List:**

**Frontend (`web/src/pages/ExportPage.tsx`):**
1. Add state: `billingModalOpen: boolean`, `billingType: string` (default `'PAYG'`).
2. Replace the direct `handleCloudSolutionExport()` call on button click with opening the modal (`setBillingModalOpen(true)`).
3. Add a Carbon `Modal` component with title "Cloud Solution Export — Billing Type", three `RadioButton` options with the exact IBM Cloud Solutioning Tool strings: `PAYG` (default), `1 Yr Reserved`, `3 Yr Reserved`. Cancel and Download (primary) actions.
4. On modal confirm: close modal, call the existing export logic passing `billingType` as a parameter.
5. Update `handleCloudSolutionExport` to accept `billingType: string` and pass it to `api.exports.generateVPCCalculator(projectId, billingType)`.

**API client (`web/src/api/client.ts`):**
6. Update `generateVPCCalculator(projectId, billingType)` to include `billing_type` in the POST request body.

**API router (`api/routers/exports.py`):**
7. Update the `generate_vpc_calculator_export` request schema/body to accept an optional `billing_type: str` field (default `"PAYG"`).
8. Pass `billing_type` through to `generate_vpc_calculator_xlsx(... billing_type=billing_type)`.

**Generator (`api/services/vpc_calculator_generator.py`):**
9. Add `billing_type: str = "PAYG"` parameter to `generate_vpc_calculator_xlsx()`.
10. Replace the hardcoded `"PAYG"` string at line 736 with the `billing_type` parameter value.

**Relevant Context:**
- `web/src/pages/ExportPage.tsx` lines 143–152: `handleCloudSolutionExport()` — button handler.
- `web/src/pages/ExportPage.tsx` line 392–393: the download button JSX.
- `web/src/api/client.ts` lines 396–429: `generateVPCCalculator()` and `downloadVPCCalculator()`.
- `api/routers/exports.py` lines 352–413: `generate_vpc_calculator_export` router handler.
- `api/services/vpc_calculator_generator.py` line 622: function signature; line 736: hardcoded `"PAYG"`.
- Carbon `Modal` and `RadioButton` are already used elsewhere in the codebase — follow the existing pattern.

**Status:** [x] complete

---

## Validation Checklist

- [x] `./setup.sh` on a machine with no `.env` starts the API cleanly without any SECRET_KEY error.
- [x] The generated `.env` contains a strong (64-char hex) `SECRET_KEY`, not the default placeholder.
- [x] Existing `.env` is untouched when re-running `setup.sh`.
- [x] README Quick Start clearly explains the auto-generated key and how to rotate it.
- [x] Clicking "Download Cloud Solution Export" opens the billing type modal.
- [x] Selecting "1 Yr Reserved" and downloading produces an xlsx where every Billing Type cell reads `1 Yr Reserved`.
- [x] Selecting "3 Yr Reserved" produces `3 Yr Reserved` in the xlsx.
- [x] PAYG (default) produces `PAYG` — unchanged from current behaviour.
- [x] Cancelling the modal does not trigger any export or loading state.
- [x] All existing tests still pass (`make test`).
