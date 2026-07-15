# Plan: VPC Profile Fix + LLM Model Recommendations

## Overview

Two independent improvements to the RVTool Genesis API and settings UI:

1. **VPC Profile Selection — Full 10-Family Support** — The IBM Cloud Solutioning tool exposes
   10 compute families (confirmed from screenshot): Flex-Balanced, Flex-Compute, Flex-Memory,
   Flex-Nano, Balanced, Compute, Memory, GPU, High memory, Storage optimized. The current tool
   only maps to 3 Flex families and has two bugs in that logic. This sub-task replaces the
   profile selection algorithm with a complete, accurate implementation covering all 10 families,
   with Flex families prioritised when the spec sits in an ambiguous zone.

2. **LLM Model Recommendation System** — At startup and once per week while the app is running,
   check a curated internal model catalog for each provider. If a newer or more capable model
   exists for the active provider/model combination, surface a notification in the Settings UI
   with a one-click "Use recommended" button. The previous model is stored so the user can
   roll back with a single click if the new model proves problematic.

---

## Full VPC Profile Catalog Audit

Cross-reference of all 10 families from the IBM Cloud Solutioning tool dropdown against the
profile data already present in `_DATA_DOMAINS_ROWS` and the IBM Cloud VPC catalog (mid-2025).

### Flex families (flexible CPU + RAM — ANY valid combination)

The Flex families use the naming pattern `{prefix}-{cpu}x{ram}`. CPU must be a standard
size from `[2, 4, 8, 12, 16, 20, 24, 32, 48, 64, 96, 128]`. RAM must equal `cpu × ratio × N`
where N ≥ 1 is an integer.

| Family | Prefix | Ratio | CPU sizes in Data Domains ref |
|--------|--------|-------|-------------------------------|
| Flex-Compute | `cxf` | 2 GB/vCPU | 2,4,8,16,24,32,48,64,96 |
| Flex-Balanced | `bxf` | 4 GB/vCPU | 2,4,8,16,32,48,64,96 |
| Flex-Memory | `mxf` | 8 GB/vCPU | 2,4,8,16,24,32,48,64,96 |

**Flex-Nano** appears as a category in `_DATA_DOMAINS_ROWS` but maps to the 1 vCPU entries
(`bz2e-1x4`, `bz2-1x4`) which are actually the Balanced family at minimum size. Flex-Nano is
not a separately selectable Flex profile family — it is how the tool labels the
sub-2-vCPU entries. Do not add a `Flex-Nano` code path; the 1-vCPU case falls through to
Balanced naturally.

### Fixed families (standard discrete profiles)

These families have a fixed catalogue — the tool must snap to the nearest profile size ≥ the
requested spec. The complete profile sets are derived from `_DATA_DOMAINS_ROWS`:

**Balanced** (`bz2`/`bz2e` — 4 GB/vCPU fixed):
Sizes: 2×8, 4×16, 8×32, 16×64
(1×4 is the nano entry — only assign when cpus=1)

**Compute** (`cz2`/`cz2e` — 2 GB/vCPU fixed):
Sizes: 2×4, 4×8, 8×16, 16×32

**Memory** (`mz2`/`mz2e` — 8 GB/vCPU fixed):
Sizes: 2×16, 4×32, 8×64, 16×128, 32×256

**GPU** (`gx2` — special non-linear ratios):
Discrete profiles: 8×64 (1×V100), 16×128 (1×V100), 32×256 (2×V100), 80×1280 (8×V100)
Only selected when a GPU flag is present (future: `has_gpu` field on vinfo). Currently: not
auto-selected — GPU workloads land in Exceptions sheet (correct behaviour until GPU detection
is implemented in the normalizer).

**High memory** — covers three sub-families with very high RAM/vCPU ratios:
- `ox2`/`ox2d` (Very High Memory, 8 GB/vCPU extended): 2×16, 4×32, 8×64, 16×128, 32×256
- `vx2d` (SAP HANA certified, non-linear): 4×56, 8×112, 16×224, 28×392, 44×616, 56×784,
  88×1232, 144×2016, 176×2464
- `ux2d` (Ultra High Memory): 8×224, 16×448, 36×1008, 52×1456, 72×2016, 100×2800
High memory is only appropriate when RAM/vCPU ratio > 8 (i.e. beyond Flex-Memory capacity).

**Storage optimized** — maps to `ox2d` with `{Instance Storage}` feature flag. No separate
profile prefix. The tool sets `Feature VS = "{Instance Storage}"` for these entries. Selecting
this family requires detection of large local disk requirements; out of scope for the current
normalizer. Storage optimized workloads are handled by using `ox2d` profiles with the feature
flag when explicitly requested.

### Selection priority (per user requirement: Flex first)

When a server spec could be satisfied by both a Flex and a fixed profile, the Flex family is
always chosen. The priority order for profile selection is:

```
1. Flex-Compute  (cxf)  — ratio ≤ 2.0 GB/vCPU
2. Flex-Balanced (bxf)  — ratio ≤ 4.0 GB/vCPU
3. Flex-Memory   (mxf)  — ratio ≤ 8.0 GB/vCPU
4. High memory   (ox2)  — ratio > 8.0 GB/vCPU (up to ~8 GB/vCPU extended)
5. no_matching_profile  — only if CPU count > 128 (no Flex profile exists)
```

Fixed families (Balanced, Compute, Memory) are NOT used for automatic profile selection —
they remain in the Data Domains reference sheet only. The IBM Cloud Solutioning tool itself
uses Flex profiles as the recommended migration path, and the user has confirmed Flex takes
priority. GPU and Storage optimized remain out of scope for auto-selection (too specialised).

### Two bugs in current Flex selection (to be fixed in Sub-Task 1)

**Bug A — RAM rounding:** `math.ceil(ram_gb / base_ratio) * base_ratio` rounds to any multiple
of the ratio (e.g. 4) instead of the nearest `snap_cpu × ratio` multiple (e.g. 32 for 8-vCPU
bxf). Produces invalid profile names like `bxf-8x36`.

**Bug B — Category boundary gray zone:** Current boundaries (2.5, 5.5) cause a server at ratio
2.5 to be assigned `cxf` and given `cxf-8x16` — under-provisioned by 4 GB. The correct
algorithm picks the smallest ratio in [2, 4, 8] that *covers* `ram_gb / snap_cpu`, then
computes `snap_ram = snap_cpu × that_ratio`. No fuzzy boundaries needed.

---

## Sub-Task 1 — Rewrite `_select_vpc_profile()` — full 10-family support + both bug fixes

**Status:** [ ] pending

### Intent
Replace the current 3-family Flex-only algorithm with a complete implementation that:
- Fixes both RAM-rounding and category-boundary bugs in Flex selection
- Adds High memory (`ox2`) selection for ratio > 8.0 GB/vCPU
- Updates the category label list and Data Domains reference to match all 10 families
- Keeps Flex families as the first-choice for any spec they can cover
- Marks GPU and Storage optimized workloads as `no_matching_profile` (goes to Exceptions sheet)
  rather than silently assigning the wrong family — future GPU detection can be added later

### Expected Outcomes — profile selection

Flex families (existing, fixed):
- `_select_vpc_profile(8, 16)` → `("Flex-Compute", "cxf-8x16", "")` — unchanged
- `_select_vpc_profile(8, 32)` → `("Flex-Balanced", "bxf-8x32", "")` — unchanged
- `_select_vpc_profile(8, 64)` → `("Flex-Memory", "mxf-8x64", "")` — unchanged

Bug A fixes (RAM rounding):
- `_select_vpc_profile(8, 36)` → `("Flex-Balanced", "bxf-8x64", "")` — was `bxf-8x36`
- `_select_vpc_profile(8, 65)` → `("Flex-Balanced", "bxf-8x96", "")` — was `bxf-8x68`
- `_select_vpc_profile(8, 97)` → `("Flex-Memory", "mxf-8x128", "")` — was `mxf-8x104`

Bug B fixes (category boundaries):
- `_select_vpc_profile(8, 20)` → `("Flex-Balanced", "bxf-8x32", "")` — was `cxf-8x16` (under-provisioned!)
- `_select_vpc_profile(8, 44)` → `("Flex-Memory", "mxf-8x64", "")` — was `bxf-8x44` (invalid!)

High memory (new):
- `_select_vpc_profile(8, 90)` → `("High memory", "ox2-8x64", "")` — ratio 11.25, beyond mxf capacity at this CPU
  Wait — mxf-8x64 only provides 8×8=64 GB. 90 > 64 → mxf-8x128 covers it (snap_ram=128 ≥ 90). So this stays in mxf.
  High memory only activates when mxf at the maximum snap_ram still cannot cover the need,
  OR when ratio > 8.0 after mxf snap. Concretely: `mxf-128x1024` is the largest Flex-Memory
  profile (128 vCPU × 8 GB). Beyond that, use `ox2`.
- `_select_vpc_profile(130, 1100)` → `("High memory", "ox2-...", "no_matching_profile")` — CPU > 128

### Todo List

1. **Replace `_FLEX_PROFILE_RULES`, `_FLEX_RAM_RATIO`** with a single ordered constant:
   ```python
   # (gb_per_vcpu_ratio, prefix, category_label)
   _FLEX_FAMILIES = [
       (2, "cxf", "Flex-Compute"),
       (4, "bxf", "Flex-Balanced"),
       (8, "mxf", "Flex-Memory"),
   ]
   ```
   Keep `_FLEX_CPU_SIZES` unchanged.

2. **Rewrite `_select_vpc_profile()`** using the "smallest covering ratio" algorithm:
   - `snap_cpu` = next standard CPU size ≥ requested (unchanged)
   - If `snap_cpu` is None → return `no_matching_profile`
   - `required_ratio = ram_gb / snap_cpu` (actual GB/vCPU needed at this CPU size)
   - Find first `(ratio, prefix, category)` in `_FLEX_FAMILIES` where `ratio >= required_ratio`
   - If found → `snap_ram = snap_cpu × ratio`, return `(category, f"{prefix}-{snap_cpu}x{snap_ram}", "")`
   - If none found (ratio > 8) → currently return `no_matching_profile`. In the future this is
     where High memory (`ox2`) selection would go; for now flag it so it goes to Exceptions.
   - Remove the old `if ram_gb > snap_ram` override block entirely.

3. **Update module docstring and inline comments** to document:
   - The 10-family catalog from the IBM Cloud Solutioning tool
   - Which families are auto-selected vs. reference-only
   - The "Flex-first" priority rule

4. **Update `_DATA_DOMAINS_ROWS` Compute Category VS values** — confirm `"Flex-Nano"` entry
   in the category column (row index 3) accurately reflects the tool's label. No change needed
   to the profile strings themselves; the Data Domains sheet is a static reference.

5. **Add / update unit tests** in `tests/test_vpc_profile.py` (create if it doesn't exist):
   - All "Expected Outcomes" cases above
   - Boundary conditions: ratio exactly = 2.0, 4.0, 8.0
   - CPU between standard sizes: 10 → snaps to 12
   - CPU = 128 (maximum) → valid profile
   - CPU > 128 → `no_matching_profile`
   - Very large RAM at max CPU: `_select_vpc_profile(128, 1024)` → `("Flex-Memory", "mxf-128x1024", "")`
   - RAM beyond mxf max: `_select_vpc_profile(128, 1025)` → `no_matching_profile`

### Relevant Context
- File: `api/services/vpc_calculator_generator.py` lines 21-96
- Caller: `generate_vpc_calculator_xlsx()` line 487 — passes `(cpus, mem_gb)` directly
- No DB changes, no frontend changes
- The 10 families confirmed from IBM Cloud Solutioning tool screenshot

---

## Sub-Task 2 — Add LLM model recommendation DB columns + migration

**Status:** [ ] pending

### Intent
The rollback feature needs to remember what the previous model was before the user upgraded.
Add a `previous_model` column to the `llm_settings` table and an Alembic migration.
Also add a `recommendation_snoozed_until` timestamp column so the user can snooze a
recommendation for 7 days without seeing it again every page load.

### Expected Outcomes
- `llm_settings` table has two new nullable columns:
  - `previous_model: Text | null` — stores the last model name before any one-click upgrade
  - `recommendation_snoozed_until: DateTime | null` — snooze expiry timestamp
- Alembic migration runs cleanly on existing databases (both columns nullable, no default)
- `LLMSettings` ORM model in `api/db/models.py` reflects the new columns
- `LLMSettingsResponse` schema in `api/schemas/settings.py` exposes `previous_model`
- `_row_to_response()` in `api/routers/settings.py` includes `previous_model`

### Todo List
1. Add `previous_model` (`Text`, nullable) and `recommendation_snoozed_until` (`DateTime`,
   nullable) columns to `LLMSettings` in `api/db/models.py`.
2. Create an Alembic migration under `api/alembic/versions/` adding the two columns.
3. Extend `LLMSettingsResponse` in `api/schemas/settings.py` to include `previous_model: str | None`.
4. Update `_row_to_response()` in `api/routers/settings.py` to map `row.previous_model`.

### Relevant Context
- Model: `api/db/models.py` `LLMSettings` class (lines 203-242)
- Schema: `api/schemas/settings.py` `LLMSettingsResponse`
- Router: `api/routers/settings.py` `_row_to_response()`
- Alembic env: `api/alembic/`

---

## Sub-Task 3 — Build curated model catalog + recommendation service

**Status:** [ ] pending

### Intent
Maintain a curated in-code catalog per provider. A recommendation is only offered when we
have high confidence it is beneficial — the catalog must have an explicit `recommended_successor`
entry for the user's current model. If no entry exists, no notification is shown.

### Expected Outcomes
- `api/services/model_catalog.py` exists with:
  - `CATALOG` — per-provider ordered model list (newest first) with human labels
  - `SUCCESSOR_MAP` — `{provider: {current_model: better_model}}` — explicit upgrade paths only
  - `ModelRecommendation` dataclass: `provider`, `current_model`, `recommended_model`, `reason`
  - `get_recommendation(provider, current_model) -> ModelRecommendation | None`
- No false positives — if current model has no successor entry, returns `None`
- Ollama returns `None` always (user-managed local models)

### Todo List
1. Create `api/services/model_catalog.py` with the catalog and `get_recommendation()` function.
2. Populate known upgrade paths at minimum:
   - watsonx: `granite-3-8b-instruct` has no recommended successor (it IS the recommended model
     for structured extraction); `granite-3-2b-instruct` → `granite-3-8b-instruct` (more capable)
   - openai: `gpt-4o-mini` is current recommended; document that `gpt-4o` is available for
     higher quality but at higher cost — include as optional upgrade with reason note
   - anthropic: `claude-3-haiku-20240307` → `claude-3-5-haiku-20241022` (same cost tier, newer)
   - ollama: always `None`

### Relevant Context
- New file: `api/services/model_catalog.py`
- No DB access needed — pure data + logic

---

## Sub-Task 4 — Add recommendation endpoints + scheduled background check

**Status:** [ ] pending

### Intent
Expose four new API endpoints and a lightweight background scheduler using `asyncio` (no new
dependencies). The background task checks on startup and weekly; the UI polls on page load.

### Expected Outcomes
- `GET /api/settings/model-recommendation` → `{recommendation: {...} | null, snoozed: bool}`
- `POST /api/settings/model-recommendation/apply` → one-click upgrade; saves `previous_model`
- `POST /api/settings/model-recommendation/rollback` → reverts to `previous_model`
- `POST /api/settings/model-recommendation/snooze` → sets snooze for 7 days
- All return `LLMSettingsResponse` (apply/rollback/snooze) or the recommendation shape (GET)
- Background `asyncio.Task` runs in `lifespan()`: checks at startup, then every 7 days

### Todo List
1. Add the four endpoints to `api/routers/settings.py`.
2. Wire the `asyncio`-based weekly checker into `lifespan()` in `api/main.py`:
   - `asyncio.create_task(recommendation_checker_loop(app))` before `yield`
   - Cancel on shutdown after `yield`
3. The background task reads active provider+model from DB, calls `get_recommendation()`,
   logs the result at INFO level — no push to UI.
4. No new Python package dependencies.

### Relevant Context
- Router: `api/routers/settings.py`
- Startup: `api/main.py` `lifespan()` (lines 17-29)
- Service: `api/services/model_catalog.py` (Sub-Task 3)
- DB columns: Sub-Task 2

---

## Sub-Task 5 — Settings UI — recommendation banner + apply/rollback/snooze

**Status:** [ ] pending

### Intent
On Settings page load, call `GET /api/settings/model-recommendation`. If a recommendation
exists and is not snoozed, show a Carbon `InlineNotification` (kind `"info"`) above the
provider picker with the recommended model, reason, and three action buttons.

### Expected Outcomes
- Blue info banner appears above provider picker when recommendation exists and not snoozed
- "Use recommended" → calls apply endpoint, refreshes settings + recommendation state
- "Rollback" button visible only when `previous_model` is set; calls rollback endpoint
- "Dismiss for 7 days" calls snooze endpoint, hides banner immediately
- No banner when no recommendation or snoozed — page looks identical to today

### Todo List
1. Add four new API calls to `web/src/api/client.ts`:
   - `settings.getRecommendation()` — `GET /api/settings/model-recommendation`
   - `settings.applyRecommendation()` — `POST /api/settings/model-recommendation/apply`
   - `settings.rollbackModel()` — `POST /api/settings/model-recommendation/rollback`
   - `settings.snoozeRecommendation()` — `POST /api/settings/model-recommendation/snooze`
2. In `web/src/pages/SettingsPage.tsx`:
   - Fetch `getRecommendation()` on mount alongside existing `api.settings.get()`
   - Store result in component state (`recommendation`, `previousModel`)
   - Render recommendation banner conditionally above the provider picker section
   - Wire the three button handlers (apply, rollback, snooze)
   - After apply/rollback: refresh both settings and recommendation state

### Relevant Context
- Frontend page: `web/src/pages/SettingsPage.tsx`
- API client: `web/src/api/client.ts`
- Carbon components already available: `InlineNotification`, `Button`, `Tag`
- `LLMSettingsResponse` already includes `previous_model` after Sub-Task 2

---

## Implementation Order

```
Sub-Task 1  →  VPC profile fix (independent, implement + verify first)
Sub-Task 2  →  DB migration (must precede 3, 4, 5)
Sub-Task 3  →  Model catalog service (must precede 4)
Sub-Task 4  →  API endpoints + scheduler (must precede 5)
Sub-Task 5  →  UI notification (last)
```
