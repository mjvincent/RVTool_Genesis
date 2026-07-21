# IBM Presentation Readiness — Remediation Plan

## Overview

**Goal:** Harden RVTool Genesis for a home-network prototype and eventual IBM-server deployment without breaking existing functionality.

**Scope:** All findings from the IBM Presentation Readiness Assessment that were validated against actual source code. One finding (export validator vs. 22-sheet mismatch) was confirmed to be intentional design and is excluded. The large-file limit was already implemented and is excluded.

**Constraints:**
- All work is done on a dedicated branch (`ibm-readiness`). `main` is never touched until the work is reviewed and merged.
- No IBM IAM or external identity provider — authentication must be self-contained.
- Functionality must not change: same workflows, same exports, same UI.
- Home-network prototype context: the most critical risks are credential leakage and accidental data exposure, not nation-state attacks.
- Auth token (Sub-Task 2.4) is **optional and off-by-default** — if `API_TOKEN` is not set, the API runs open exactly as today. No change for home-network use.
- Production web serving uses `vite preview` (serves compiled `dist/` assets, no dev tooling) rather than Nginx for now. Nginx can be added later as a clean upgrade.

**Approach:** Phased delivery, all on the `ibm-readiness` branch. Phase 1 addresses all security and build blockers. Phase 2 addresses reliability and API quality. Phase 3 addresses polish and CI. All phases can be implemented in sequence — each sub-task is independently reviewable and low-risk.

---

## Branch Strategy

All implementation work happens on a dedicated branch. `main` remains untouched and fully functional throughout.

**Todo:**
1. Create branch: `git checkout -b ibm-readiness`
2. Implement sub-tasks in order, committing after each one.
3. Each commit should reference the sub-task number (e.g., `feat: 1.1 remove postgres host port`).
4. After all phases are validated end-to-end, open a PR from `ibm-readiness` → `main`.
5. Do not merge until the full validation checklist at the bottom of this plan passes.

---

## Phase 1 — Security and Build Blockers

### Sub-Task 1.1 — Remove PostgreSQL host-port exposure

**Intent:** The database port `5433:5432` is published to the host in `docker-compose.yml`. This means any process or user on the same network can connect directly to PostgreSQL, bypassing the API entirely. Removing this port mapping confines the database to the internal Docker bridge network.

**Expected Outcomes:**
- `docker-compose.yml` no longer publishes port 5433 to the host.
- The `api` container can still reach the database via the internal `db:5432` hostname.
- No application code changes are required — the API connection string already uses `db:5432`.

**Todo List:**
1. In `docker-compose.yml`, remove the `ports` block from the `db` service (lines 14–15).
2. Verify the `api` service `DATABASE_URL` in `.env.example` still points to `db:5432` (internal hostname), not `localhost:5433`.
3. Add a comment in `docker-compose.yml` explaining the port is intentionally absent from production.

**Relevant Context:**
- `docker-compose.yml` lines 14–15: `"5433:5432"` port mapping on the `db` service.
- `api/core/config.py` line 11: `DATABASE_URL` defaults to `postgresql://rvtool:rvtool_password@db:5432/rvtooldb` — correct, uses internal hostname.

**Status:** [ ] pending

---

### Sub-Task 1.2 — Enforce a strong SECRET_KEY at startup

**Intent:** `api/core/config.py` and `api/main.py` both contain the literal default value `"rvtool-genesis-change-me-in-production"`. The API logs a warning but starts normally. Any deployment that forgets to set `SECRET_KEY` silently uses a publicly known encryption key, meaning all stored cloud LLM API keys can be decrypted by anyone who knows the default. The fix is to make startup fail hard when the default is detected.

**Expected Outcomes:**
- The API refuses to start (raises a `RuntimeError` with a clear message) if `SECRET_KEY` equals the default value.
- `.env.example` is updated to make the requirement explicit.
- No functional change for any deployment that already sets a real `SECRET_KEY`.

**Todo List:**
1. In `api/main.py`, inside the `lifespan` function, change the warning block (lines 56–62) to raise a `RuntimeError` instead of logging a warning.
2. Update `.env.example` to document that `SECRET_KEY` must be set to a strong random value (e.g., output of `openssl rand -hex 32`).
3. Optionally add a minimum-length check (e.g., ≥ 32 characters) in the same guard.

**Relevant Context:**
- `api/main.py` lines 56–62: current warning block.
- `api/core/config.py` line 16: default value in Pydantic settings.
- `.env.example` line 19: current placeholder.

**Status:** [ ] pending

---

### Sub-Task 1.3 — Restrict the LLM settings test endpoint

**Intent:** `POST /api/settings/test` is unauthenticated and accepts LLM provider credentials (API keys, endpoint URLs) in plaintext. In the current form, any user on the network can test arbitrary endpoints with the stored cloud-provider keys. The risk on a home network is low but the fix is simple: require that the test endpoint only tests the currently-configured provider from the database, and does not accept inline credentials from the request body when a key is already stored.

**Expected Outcomes:**
- The test endpoint still works from the Settings page UI.
- A request without a stored key that also provides no inline key returns a clear error rather than testing with an empty credential.
- The endpoint does not forward stored decrypted keys to arbitrary URLs provided in the request body.

**Todo List:**
1. In `api/routers/settings.py`, update the `_test_watsonx`, `_test_openai`, and `_test_anthropic` helper functions to validate that the `endpoint_url` (if provided in the payload) matches an allowlist of known provider domains (e.g., `api.openai.com`, `us-south.ml.cloud.ibm.com`, `api.anthropic.com`, `localhost`).
2. If the payload endpoint does not match the allowlist, return `LLMTestResult(ok=False, error="Endpoint not in approved provider list")` without making any outbound call.
3. Document the allowlist in a constant at the top of the settings router.

**Relevant Context:**
- `api/routers/settings.py` lines 144–177: the test endpoint.
- `api/routers/settings.py` lines 186+: provider test helper functions where `payload.endpoint_url` is used.

**Status:** [ ] pending

---

### Sub-Task 1.4 — Fix spreadsheet formula injection in exports

**Intent:** All Python export generators write user-supplied values (VM names, assumed values, field values) directly into Excel cells as raw values. A VM named `=1+1` or `=HYPERLINK("http://evil.com","click")` will be stored as an active Excel formula in the generated workbook. Any IBM stakeholder opening the file in Excel will execute it. The fix is a one-line helper that prefixes any string starting with a formula character (`=`, `+`, `-`, `@`) with a single quote, which Excel treats as a literal string.

**Expected Outcomes:**
- A cell value of `=1+1` is written as `'=1+1` (rendered as the literal text `=1+1` in Excel).
- All three generator files are protected: `rvtools_generator.py`, `assumptions_generator.py`, and `vpc_calculator_generator.py`.
- Normal values (VM names, numbers, OS strings) are completely unaffected.
- A regression test confirms that a formula-character value round-trips as literal text.

**Todo List:**
1. Add a shared helper function `_sanitize_cell(value)` to a common location (e.g., a new `api/services/export_utils.py` or directly in each generator) that checks if a string value starts with `=`, `+`, `-`, or `@` and prepends `'` if so. Non-string values pass through unchanged.
2. Wrap every `ws.append([...])` call in `rvtools_generator.py` — wrap string-typed fields (vm_name, os_cfg, disk_label, etc.) through `_sanitize_cell()`.
3. Apply the same wrapper in `assumptions_generator.py` to `vm_name`, `field_name`, `assumed_value`, `original_value`, and `reasoning` fields.
4. Apply the same wrapper in `vpc_calculator_generator.py` to any user-sourced string cells.
5. Add a pytest test in `tests/` that creates a record with `vm_name = "=1+1"`, generates an export, opens the `.xlsx` with openpyxl, and asserts the cell value is the literal string `'=1+1` (or that openpyxl reads it back as plain text, not a formula).

**Relevant Context:**
- `api/services/rvtools_generator.py` lines 312–443: all `sheets[...].append([...])` calls.
- `api/services/assumptions_generator.py` lines 134–142: `ws_a.append([...])` call.
- `openpyxl` is already a project dependency (`api/requirements.txt`).

**Status:** [ ] pending

---

### Sub-Task 1.5 — Fix the web container production build

**Intent:** `web/Dockerfile` runs `npm run dev` (`vite --host`) which starts the Vite development server. This is the hot-module-replacement server designed for local development — it exposes source maps, development error overlays, and unminified code. For any shared or IBM-facing deployment, the container must serve a production build. The fix uses `vite preview`, which is Vite's built-in production-preview static file server — it serves the compiled `dist/` folder with no dev tooling, no source maps, and no HMR. Nginx would be more production-grade but requires additional configuration (`nginx.conf`, proxy rules for `/api`); that can be added as a later upgrade. For this plan, `vite preview` achieves the security goal with minimal risk.

**Expected Outcomes:**
- `web/Dockerfile` builds production assets with `npm run build` (`tsc && vite build`) into `dist/`.
- The final image serves those assets with `vite preview --host --port 3000`.
- The development override (`docker-compose.override.yml`) still bind-mounts source and overrides the command to `npm run dev` — the local developer workflow is completely unchanged.
- The production container has no source files and no dev tooling.
- The `vite preview` proxy configuration must be added to `vite.config.ts` so `/api` is still forwarded to the API container (Vite's dev `server.proxy` does not apply to preview — a `preview.proxy` block is needed).

**Todo List:**
1. In `web/vite.config.ts`, add a `preview` block mirroring the `server` proxy config: `preview: { host: '0.0.0.0', port: 3000, proxy: { '/api': { target: 'http://api:8000', changeOrigin: true } } }`.
2. In `web/Dockerfile`, add a `build` stage after `deps`: copy source, run `npm run build`, producing `dist/`.
3. Update the final stage `CMD` from `["npm", "run", "dev"]` to `["npm", "run", "preview"]` and ensure `"preview": "vite preview --host --port 3000"` exists in `web/package.json` scripts.
4. Confirm `docker-compose.override.yml` still overrides the web command to `npm run dev` — this is the local dev path and must remain unchanged.

**Relevant Context:**
- `web/Dockerfile` lines 1–18: current multi-stage dev build.
- `docker-compose.override.yml` lines 10–12: dev source mount and command override (must remain intact).
- `web/package.json` line 7: `"dev": "vite --host"`, line 8: `"build": "tsc && vite build"`.

**Status:** [ ] pending

---

### Sub-Task 1.6 — Fix TypeScript type errors and add a typecheck gate

**Intent:** `BulkNxfModal.tsx` line 75 references `previewNames` directly in JSX (used in the template at lines 75, 80, 84, 86, 87) but the destructuring in the function signature on line 18 omits `previewNames` from the destructured props. This causes `previewNames is not defined` TypeScript errors. There are also widespread `any` casts in `client.ts` and `RecordsTable.tsx` that undermine strict-mode benefits. The fix for the modal is surgical. The broader `any` cleanup should be targeted to the highest-risk locations.

**Expected Outcomes:**
- `npm run build` (which runs `tsc && vite build`) completes with zero TypeScript errors.
- `BulkNxfModal.tsx` destructures `previewNames` in its function signature.
- The most critical `any` uses in `client.ts` (API response types) are replaced with defined interfaces where one already exists or is trivially definable.
- No functional change to any component.

**Todo List:**
1. In `web/src/components/BulkNxfModal.tsx` line 18, add `previewNames` to the destructured props: `{ projectId, unsupportedCount, previewNames, onClose, onApplied }`.
2. In `web/src/api/client.ts`, replace the `Promise<any>` return type on `uploads.upload` (line 300) with a typed interface matching the actual API response shape.
3. Run `npm run typecheck` (or `tsc --noEmit`) and fix any remaining errors surfaced — prioritize errors in `BulkNxfModal.tsx` and normalization error handling paths as called out in the assessment.
4. The goal is zero errors from `tsc --noEmit`. Suppress with `// @ts-expect-error` only where the type genuinely cannot be known (e.g., raw LLM JSON responses) and add a comment explaining why.

**Relevant Context:**
- `web/src/components/BulkNxfModal.tsx` line 18: function signature missing `previewNames`.
- `web/src/api/client.ts` line 300: `Promise<any>` on upload.
- `web/tsconfig.json`: strict mode, noUnusedLocals, noUnusedParameters all enabled.

**Status:** [ ] pending

---

## Phase 2 — Reliability and API Quality

### Sub-Task 2.1 — Add a centralized API fetch wrapper with HTTP error handling

**Intent:** In `web/src/api/client.ts`, 37 of 41 API call sites call `.then(r => r.json())` directly without checking `r.ok`. When the server returns a 4xx or 5xx, the JSON body may contain an error detail but the calling code treats it identically to a success response. This means UI components silently display `undefined` data or crash with a cryptic JSON parse error. The fix is a single shared `apiFetch` wrapper at the top of `client.ts` that checks `r.ok` before parsing.

**Expected Outcomes:**
- A `apiFetch` helper function exists in `client.ts` that throws a typed `ApiError` (containing `status` and `detail`) for any non-2xx response.
- All existing `fetch(...).then(r => r.json())` call sites are replaced with `apiFetch(...)`.
- Components that already have try/catch blocks continue to work — they will now catch `ApiError` instead of receiving malformed data.
- No new behavior for successful responses.

**Todo List:**
1. Add `class ApiError extends Error { status: number; detail: string }` and an `async function apiFetch<T>(input: RequestInfo, init?: RequestInit): Promise<T>` helper near the top of `web/src/api/client.ts`. The helper fetches, checks `r.ok`, and throws `ApiError` if not; otherwise returns `r.json()`.
2. Replace every `.then(r => r.json())` call site in the `api` export object with `apiFetch(...)`.
3. For call sites that already have `if (!r.ok)` checks (the 4 correct ones), migrate them to also use `apiFetch` with a try/catch.
4. Verify that pages currently catching errors (`catch (e: any)`) still display a useful error message with the new `ApiError` type.

**Relevant Context:**
- `web/src/api/client.ts` lines 243–481: all endpoint definitions.
- `web/src/api/client.ts` lines 294–296: example of the correct existing pattern.

**Status:** [ ] pending

---

### Sub-Task 2.2 — Add startup-time secret key validation and document generation

**Intent:** Companion to Sub-Task 1.2. Now that startup fails on the default key, operators need clear instructions for generating a valid secret. This sub-task adds a `Makefile` target and README section for generating a `SECRET_KEY`, and ensures `.env.example` is complete and correct for a clean first-run experience.

**Expected Outcomes:**
- `Makefile` has a `generate-secret` target that prints an `openssl rand -hex 32` value and instructions.
- `README.md` includes a setup section explaining the requirement.
- `.env.example` has a clear `# REQUIRED: generate with: openssl rand -hex 32` comment.

**Todo List:**
1. In `Makefile`, add a `generate-secret` target: `@echo "SECRET_KEY=$$(openssl rand -hex 32)"`.
2. Update `.env.example` to add an explicit generation comment above the `SECRET_KEY` line.
3. Update `README.md` first-run instructions to reference the new target.

**Relevant Context:**
- `Makefile`: check for existing targets.
- `.env.example` line 19: current placeholder.
- `README.md`: existing setup section.

**Status:** [ ] pending

---

### Sub-Task 2.3 — Add stuck-record detection on processing startup

**Intent:** If the API container crashes mid-processing, records are left in `processing_status = "processing"` forever. The manual reset endpoint exists but requires the operator to know to call it. A simple guard in the lifespan startup event can automatically reset any orphaned `processing` records to `pending`, so the next `start_processing` call recovers them transparently.

**Expected Outcomes:**
- On API startup, any `ServerRecord` rows with `processing_status = "processing"` are reset to `pending`.
- A startup log message reports how many records were recovered.
- No change to the existing manual reset endpoint — it remains available.
- No functional change during normal operation (no records are stuck at startup in the happy path).

**Todo List:**
1. In `api/main.py` lifespan function, after the secret key check, add an async DB call to reset stuck records: `UPDATE server_records SET processing_status='pending' WHERE processing_status='processing'`.
2. Log the count of reset records at `INFO` level.
3. Import the necessary DB session and model into `main.py` (or call a small helper in a service module to keep main.py clean).

**Relevant Context:**
- `api/main.py` lines 52–70: lifespan function.
- `api/db/models.py`: `ServerRecord` model with `processing_status` column.
- `api/routers/processing.py` lines 316–350: existing manual reset endpoint for reference.

**Status:** [ ] pending

---

### Sub-Task 2.4 — Add optional API authentication (shared token, off-by-default)

**Intent:** Currently every API endpoint is open to any caller on the network. For home-network use this is acceptable — adding a required token would break the current workflow with no benefit. The right approach is to wire the infrastructure now so that a token *can* be activated for a corporate or IBM-facing demo, without any impact on deployments that don't set one. If `API_TOKEN` is absent from `.env`, the API behaves exactly as it does today — completely open. If `API_TOKEN` is set, every request must supply it as a bearer token.

**Expected Outcomes:**
- A `Depends(require_token)` dependency exists on all routers.
- If `API_TOKEN` env var is empty or unset: dependency is a no-op, no behaviour change whatsoever.
- If `API_TOKEN` is set: a missing or wrong `Authorization: Bearer` header returns `HTTP 401`.
- The frontend automatically includes the token header when `VITE_API_TOKEN` is set in the build environment.
- The health check endpoint is excluded from token enforcement.
- Current home-network deployment: set nothing, works identically to today.

**Todo List:**
1. Add `api_token: str = ""` field to `api/core/config.py` `Settings` class.
2. Create `api/core/auth.py` with a `require_token` FastAPI dependency: if `settings.api_token` is empty, return immediately (no-op). If set, read the `Authorization: Bearer` header and compare using `hmac.compare_digest`; raise `HTTP 401` on mismatch.
3. Add `Depends(require_token)` to each router in `api/routers/` (folders, projects, uploads, processing, exports, settings, backups, pricing_template). The health router is excluded.
4. In `web/src/api/client.ts`, update the `apiFetch` helper (from Sub-Task 2.1) to include `Authorization: Bearer ${token}` header only when `import.meta.env.VITE_API_TOKEN` is non-empty.
5. Add `# API_TOKEN=` (commented out) to `.env.example` with a comment: "Leave blank for home-network use. Set to a strong random value for shared/IBM-facing deployments."
6. `docker-compose.yml` already passes `.env` to the API container via `env_file` — no change needed there.

**Relevant Context:**
- `api/main.py` lines 90–98: router includes — each needs the dependency added.
- `api/core/config.py` lines 6–20: settings class.
- `web/src/api/client.ts` line 1: `BASE` constant and fetch pattern.
- `docker-compose.yml` line 28: `env_file: - .env` already passes env to API — no change needed.

**Status:** [ ] pending

---

## Phase 3 — IBM Demo Polish

### Sub-Task 3.1 — Update CORS for non-localhost deployments ✅

**Intent:** `api/main.py` hardcodes `allow_origins=["http://localhost:3001"]`. If the demo is run from a machine at a non-localhost address (e.g., `192.168.1.x:3001`), browser CORS preflight requests will be rejected and the UI will fail entirely. Making origins configurable via an env var costs two lines and eliminates this demo-day risk.

**Expected Outcomes:**
- `ALLOWED_ORIGINS` env var accepts a comma-separated list of origins.
- Default remains `http://localhost:3001` for development.
- `api/main.py` reads the env var and passes the list to `CORSMiddleware`.

**Todo List:**
1. Add `allowed_origins: list[str] = ["http://localhost:3001"]` to `api/core/config.py` using Pydantic's comma-split parsing: `Field(default=["http://localhost:3001"])`.
2. Update `api/main.py` CORS middleware to use `allow_origins=settings.allowed_origins`.
3. Add `ALLOWED_ORIGINS=http://localhost:3001` to `.env.example` with a comment explaining comma-separated format for multi-origin use.

**Relevant Context:**
- `api/main.py` lines 82–88: current hardcoded CORS config.
- `api/core/config.py`: Pydantic settings with env var parsing.

**Status:** [x] complete

---

### Sub-Task 3.2 — Upgrade npm packages and run dependency audit ✅

**Intent:** `npm audit` identifies 2 Vite/esbuild vulnerabilities. The web container also runs the Vite dev server in production (addressed in Sub-Task 1.5), which means these vulnerabilities are live in the running container. Upgrading Vite to the latest 5.x patch and running `npm audit` to confirm resolution is a low-risk, high-confidence step.

**Expected Outcomes:**
- `vite` is upgraded to the latest 5.x patch release.
- `npm audit` reports zero high/critical vulnerabilities.
- `package-lock.json` is committed with the updated versions.

**Todo List:**
1. Run `npm update vite` in the `web/` directory.
2. Run `npm audit --audit-level=high` and resolve any remaining high/critical findings.
3. Commit updated `package.json` and `package-lock.json`.

**Relevant Context:**
- `web/package.json` line 25: `"vite": "^5.4.8"`.

**Status:** [x] complete

---

### Sub-Task 3.3 — Add CI gates for typecheck, tests, and lint ✅

**Intent:** The assessment notes that TypeScript errors and Ruff lint findings are currently not enforced. A minimal CI gate (GitHub Actions or a Makefile target) that runs `tsc --noEmit`, `ruff check`, and `pytest` on every push prevents regressions and demonstrates engineering discipline to IBM reviewers.

**Expected Outcomes:**
- A GitHub Actions workflow file (`.github/workflows/ci.yml`) runs on push/PR to `main`.
- The workflow checks out, installs Python deps, runs `ruff check api/`, runs `pytest`, installs Node deps, and runs `tsc --noEmit`.
- A `make lint` / `make test` / `make typecheck` target in the `Makefile` wraps each step for local use.

**Todo List:**
1. Create `.github/workflows/ci.yml` with jobs: `lint-python` (ruff check), `test-python` (pytest), `typecheck-frontend` (tsc --noEmit).
2. Add corresponding `Makefile` targets: `lint`, `test`, `typecheck`.
3. Fix any Ruff findings that block the lint gate (the assessment mentions 20 findings, mostly hygiene — prioritize `E` and `F` codes, allow `N` and `ANN` if they're stylistic).

**Relevant Context:**
- `pytest.ini`: existing pytest configuration.
- `web/tsconfig.json`: existing TS config.
- `api/requirements.txt`: `ruff` should be added if not already present (check).

**Status:** [x] complete

---

## Validation Checklist

Before considering any phase complete, verify:

- [x] `docker-compose up` starts cleanly (with a real SECRET_KEY in `.env`).
- [x] `docker-compose up` fails fast with a clear error message when SECRET_KEY is default.
- [x] DB is not reachable from outside the container network (`psql -h localhost -p 5433` fails).
- [x] `npm run build` (inside `web/`) completes with zero TypeScript errors.
- [x] `pytest` passes with no failures.
- [x] A generated Excel export with `vm_name = "=1+1"` opens in Excel as literal text, not a formula.
- [x] The Settings test endpoint returns an error for an unknown/untrusted endpoint URL.
- [x] The UI works end-to-end: create project → upload → normalize → review → export.
- [x] CORS works from the intended demo origin.
