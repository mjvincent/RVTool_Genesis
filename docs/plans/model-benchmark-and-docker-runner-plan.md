# Model Benchmark, Catalog Fix & Docker Model Runner Plan

## Overview

Three coordinated tracks addressing model recommendation quality and adding an empirical
model comparison capability backed by Docker Model Runner for candidate model delivery.

## Key Design Decisions

| Decision | Rationale |
|---|---|
| Accuracy and latency equally weighted in benchmark score | Speed is as important as correctness for practitioner workflows — a slow model blocks the normalization pipeline even if accurate |
| Benchmark can compare same model on Ollama vs Docker Model Runner | Enables pure runtime speed comparison; useful for validating whether DMR's Metal acceleration is faster than Ollama on Apple Silicon |
| Extra sheets in validator moved to warnings, not errors | Real RVTools exports always contain 20+ sheets; only missing required sheets are a genuine structural problem |

**Tracks:**

1. **Fix the model catalog** — Correct static task-fit scoring so `qwen2.5-coder` variants
   are not misidentified as good JSON-extraction models, and add an unknown-model fallback
   that penalises specialised (coder, vision, embed) models.

2. **Model benchmark feature** — A `POST /api/settings/benchmark-models` endpoint that runs
   5–8 synthetic server records through two Ollama models and returns an accuracy + latency
   scorecard. The Settings page Local AI Advisor card gets a "Compare Models" inline
   expandable section.

3. **Docker Model Runner integration** — Docker Model Runner (Docker Desktop ≥ 4.25) added as
   a 6th LLM provider, used primarily as a pull-and-run mechanism for candidate models not
   yet installed locally. At benchmark time the app queries the HuggingFace Hub API to
   resolve the best GGUF quantization for a requested model, then pulls and runs it via
   Docker Model Runner so the benchmark can compare it against the resident Ollama model.

---

## Track 1 — Fix Model Catalog

### Sub-Task 1.1: Correct task-fit scores for known models
**Status:** `[x] done`

**Intent:**
`qwen2.5-coder:1.5b` is a 1.5 B-parameter code-generation model. It should score low (3–4)
for structured JSON extraction. The current catalog has no entry for it, so it inherits a
mid-range score via name-prefix matching against `qwen2.5` (score 9). Fix this by adding
explicit entries for all known `qwen2.5-coder` variants and other known mismatches.

**Expected Outcomes:**
- `qwen2.5-coder:*` models score ≤ 4 in the task-fit table.
- `phi4-mini` remains recommended when installed alongside `qwen2.5-coder`.
- The existing `get_pull_suggestion()` logic continues to work correctly.

**Todo List:**
1. Open `api/services/model_catalog.py`.
2. Add explicit entries in `_OLLAMA_TASK_FIT` for:
   - `"qwen2.5-coder"` → 3 (all sizes; matched by prefix)
   - `"qwen2.5-coder:1.5b"` → 3
   - `"qwen2.5-coder:7b"` → 3
   - `"qwen2.5-coder:14b"` → 3
   - `"codellama"` → 3 (code-tuned)
   - `"deepseek-coder"` → 3
   - `"starcoder"` → 3
   - `"nomic-embed"` → 1 (embedding model)
   - `"mxbai-embed"` → 1
   - `"all-minilm"` → 1
3. In `rank_local_models()`, add a fallback rule: if a model name contains any of
   `["-coder", "-code", "-embed", "-vision", "-vl", "starcoder"]`, cap its task_fit at 4
   regardless of the lookup table.
4. Add a short comment block above `_OLLAMA_TASK_FIT` explaining the scoring rationale.

**Relevant Context:**
- `api/services/model_catalog.py` — `_OLLAMA_TASK_FIT` dict (lines 185–199),
  `rank_local_models()` (lines 244–299), `get_pull_suggestion()` (lines 302–319)

---

### Sub-Task 1.2: Validate fix with unit tests
**Status:** `[x] done`

**Intent:**
Ensure the catalog fix is correct and does not regress existing recommendations.

**Expected Outcomes:**
- New test `tests/test_model_catalog.py` with at least 5 assertions.
- All existing tests still pass.

**Todo List:**
1. Create `tests/test_model_catalog.py`.
2. Add tests:
   - `qwen2.5-coder:1.5b` ranks below `phi4-mini` when both installed.
   - Embedding models (`nomic-embed-text`) are ranked last.
   - `phi4-mini` is `recommended=True` when installed alongside `qwen2.5-coder:1.5b`.
   - `get_pull_suggestion()` returns `None` when `phi4-mini` is installed (task_fit ≥ 8).
   - Unknown model without special suffix gets a neutral default score (5).

**Relevant Context:**
- `api/services/model_catalog.py`
- Existing test pattern: `tests/test_normalizer_disk_clamping.py`

---

## Track 2 — Model Benchmark Feature

### Sub-Task 2.1: Define benchmark corpus
**Status:** `[x] done`

**Intent:**
Define a fixed set of synthetic raw server rows that test the exact edge cases Genesis
cares about. These are used as benchmark inputs, and the expected normalized output is
pre-computed so scoring is deterministic without human judgment.

**Expected Outcomes:**
- A constant `BENCHMARK_CASES` in a new `api/services/model_benchmarker.py` module.
- Each case has `raw_row: dict`, `expected: dict` (a subset of key fields to check).
- 8 cases covering all critical scenarios.

**Benchmark Cases:**

| # | Raw Input Description | Critical Fields to Score |
|---|---|---|
| 1 | Windows Server 2022, RAM expressed as "64" (no unit) | `memory_mb == 65536`, `os_config` contains "Windows Server 2022" |
| 2 | AIX server, OS = "AIX 7.2", disk 10 GB | `server_type == "powervs"`, `os_config` contains "AIX" |
| 3 | IBM i server, OS = "IBM i 7.4" | `server_type == "powervs"`, `os_config` contains "IBM i" |
| 4 | RHEL 9, disk expressed as "500" (no unit) | `server_type == "vm"`, `os_config` contains "Red Hat Enterprise Linux 9" |
| 5 | Windows Server 2019, RAM = "128 GB" (explicit) | `memory_mb == 131072`, correct disk clamping |
| 6 | Minimal record (name + OS only, all else missing) | Valid JSON produced, defaults applied, `vm_name` non-empty |
| 7 | SAP on Red Hat Linux | `server_type == "powervs"`, `os_config` contains "SAP" |
| 8 | Ubuntu 22.04, 16 vCPU, 32 GB RAM | `server_type == "vm"`, `memory_mb == 32768`, `cpus == 16` |

**Todo List:**
1. Create `api/services/model_benchmarker.py`.
2. Define `BENCHMARK_CASES` as a list of `BenchmarkCase` dataclasses with fields:
   `id`, `description`, `raw_row`, `expected_fields`.
3. Define `expected_fields` as a flat dict of dotted-path → expected-value, e.g.:
   `{"vinfo.memory_mb": 65536, "server_type": "powervs"}`.
4. Do not include fields that require LLM creativity (datacenter, cluster name, etc.) —
   only score deterministic fields.

**Relevant Context:**
- Prompt structure: `api/services/ai_normalizer.py` (system prompt lines 187–223)
- Sanitization oracle: `_sanitize_numeric_fields()` (lines 507–797)
- OS normalization: `_normalize_os_name()` (lines 351–458)
- PowerVS detection: `_is_powervs_os()` (lines 131–150)
- Existing synthetic record: `tests/test_pipeline.py` (lines 167–252)

---

### Sub-Task 2.2: Benchmark runner backend
**Status:** `[x] done`

**Intent:**
A new `POST /api/settings/benchmark-models` endpoint that accepts two Ollama model names,
runs both through the benchmark corpus, scores each response, and returns a structured
scorecard. The endpoint also accepts an optional Docker Model Runner model name so the
benchmark can test a model served by Docker Model Runner instead of Ollama.

**Expected Outcomes:**
- Endpoint at `POST /api/settings/benchmark-models` returns `200` with a `BenchmarkResult`.
- Both models run sequentially (not concurrently) to avoid GPU/CPU resource contention.
- Each case reports: `valid_json`, `correct_server_type`, `correct_memory_mb`,
  `correct_os_config`, `latency_ms`.
- The `BenchmarkResult` aggregates a **composite score (0–100)** where accuracy and speed
  are equally weighted (50/50): `composite = (accuracy_pct * 0.5) + (speed_score * 0.5)`.
  Speed score = `clamp(1 - (avg_latency_ms / LATENCY_CEILING_MS), 0, 1) * 100` where
  `LATENCY_CEILING_MS = 30_000` (30 seconds — beyond this a model scores 0 on speed).
- If a model is unreachable, its result shows `reachable: false` and composite score 0.
- Both models can use either Ollama or Docker Model Runner as their backend, enabling
  same-model-different-runtime comparisons (e.g., phi4-mini on Ollama vs phi4-mini on DMR).

**Request Schema:**
```
{
  "model_a": str,              # e.g., "phi4-mini"
  "model_a_backend": "ollama" | "docker_model_runner",  # default "ollama"
  "model_b": str,              # e.g., "qwen2.5:7b" or same model as A on different backend
  "model_b_backend": "ollama" | "docker_model_runner"   # default "ollama"
}
```

**Response Schema:**
```
{
  "model_a": {
    "name": str,
    "backend": str,
    "composite_score": float,   # 0–100, equally weighted accuracy + speed
    "accuracy_pct": float,      # 0–100, correctness only
    "speed_score": float,       # 0–100, latency only (ceiling 30 s)
    "avg_latency_ms": float,
    "reachable": bool,
    "cases": [...]
  },
  "model_b": { ...same shape... },
  "winner": "model_a" | "model_b" | "tie",
  "recommendation": str    # e.g. "phi4-mini wins — 12% faster with equal accuracy"
}
```

**Todo List:**
1. Add scoring helper `score_response(normalized: dict, expected_fields: dict) -> dict`
   to `model_benchmarker.py`. Uses existing `_sanitize_numeric_fields` as the oracle.
2. Add `run_benchmark(model_name, backend, ollama_base_url, dmr_base_url) -> ModelBenchmarkResult`
   to `model_benchmarker.py`. Iterates `BENCHMARK_CASES`, calls the correct LLM backend per
   case, measures wall-clock latency, scores each response. Composite score formula:
   `composite = (accuracy_pct * 0.5) + (clamp(1 - avg_latency_ms / 30_000, 0, 1) * 100 * 0.5)`.
3. Add `POST /api/settings/benchmark-models` to `api/routers/settings.py`.
4. Add request/response schemas `BenchmarkRequest` and `BenchmarkResult` to
   `api/schemas/settings.py`.
5. The endpoint uses the currently saved `ollama_base_url` from `LLMSettings` for the Ollama
   backend, and `docker_model_runner_base_url` (new setting field, see Sub-Task 3.1) for
   Docker Model Runner.
6. No caching — benchmark always runs fresh. Guard with a short lock (module-level asyncio
   `Event`) to prevent concurrent benchmark runs.

**Relevant Context:**
- `api/routers/settings.py` — existing endpoint patterns, `get_db` dependency
- `api/services/ai_normalizer.py` — `_call_ollama()` for the LLM call pattern
- `api/schemas/settings.py` — schema conventions

---

### Sub-Task 2.3: Benchmark UI — "Compare Models" inline section
**Status:** `[x] done`

**Intent:**
Add a "Compare Models" toggle button inside the Local AI Advisor card on the Settings page.
When expanded, the section shows two model selectors (pre-filled with the installed models),
a "Run Benchmark" button, and — after running — a side-by-side scorecard table.

**Expected Outcomes:**
- A "Compare Models" `<Button kind="ghost">` appears at the bottom of the Local AI Advisor
  card (only when `advisor` data is loaded and ≥ 2 models are installed).
- Clicking it expands an inline section (no modal, no navigation) using a `useState` toggle.
- Model A defaults to the currently active model. Model B defaults to the next-best
  installed model or empty.
- A `<Select>` dropdown for each model, populated from `advisor.installed_models`.
- A "Run Benchmark" button that calls `api.settings.benchmarkModels(...)`.
- During run: shows `<InlineLoading description="Benchmarking…" />`.
- After run: shows a 3-column Carbon `<DataTable>` with rows per benchmark case:
  `Case`, `Model A`, `Model B` (✓/✗ per field, latency ms).
- Footer row: **composite score** (bold), accuracy %, speed score, avg latency ms for each model.
- A `<Tag type="green">` winner badge or `<Tag type="gray">Tie</Tag>`.
- An explicit scoring note: "Score = 50% accuracy + 50% speed (ceiling 30 s)".
- The `recommendation` string from the response shown as an `<InlineNotification kind="info">`.
- Model B backend selector (`<Select>`) allowing choice of `ollama` or `docker_model_runner`
  — enabling same-model-different-runtime comparisons.

**Todo List:**
1. Add `benchmarkModels(req)` to `web/src/api/client.ts` with correct TypeScript interfaces
   for `BenchmarkRequest` and `BenchmarkResult` (include `composite_score`, `accuracy_pct`,
   `speed_score`, `backend` fields on each model result).
2. Add state variables to `SettingsPage.tsx`:
   `benchmarkOpen`, `benchmarkRunning`, `benchmarkResult`, `benchmarkModelA`,
   `benchmarkModelABackend`, `benchmarkModelB`, `benchmarkModelBBackend`.
3. Add the "Compare Models" button and expandable inline section to the Local AI Advisor
   card section of `SettingsPage.tsx`.
4. Render the scorecard table using Carbon `DataTable` (import is already available
   or add to existing imports).
5. Display the `recommendation` string as an `<InlineNotification kind="info">` below
   the table.

**Relevant Context:**
- `web/src/pages/SettingsPage.tsx` — Local AI Advisor card (lines 355–427)
- `web/src/api/client.ts` — existing API binding patterns
- Carbon DataTable: same pattern as `RecordsTable.tsx`

---

## Track 3 — Docker Model Runner Integration

### Sub-Task 3.1: Add Docker Model Runner as a provider option
**Status:** `[x] done`

**Intent:**
Add `"docker_model_runner"` as a 6th LLM provider. Persist its base URL and active model
in `LLMSettings`. The provider routes inference through Docker Model Runner's
OpenAI-compatible `/v1/chat/completions` endpoint. In the Settings UI, it appears as a
new radio option with a URL field and model field, similar to the OpenAI-compatible card.

**Expected Outcomes:**
- `ProviderLiteral` in `api/schemas/settings.py` includes `"docker_model_runner"`.
- `LLMSettings` ORM model has `dmr_base_url` and `dmr_model` columns.
- `ai_normalizer.py` routes to `_call_docker_model_runner()` when provider is
  `docker_model_runner`.
- Settings UI shows a new "Docker Model Runner" radio card.
- A new Alembic migration adds the two columns.
- Benchmark endpoint accepts `model_a_backend` and `model_b_backend` independently, so
  the same model can be compared across runtimes (e.g., Ollama phi4-mini vs DMR phi4-mini).

**Todo List:**
1. Add `"docker_model_runner"` to `ProviderLiteral` in `api/schemas/settings.py`.
2. Add `dmr_base_url: str = "http://host.docker.internal:9545"` and
   `dmr_model: str = ""` to `LLMSettingsSave` and `LLMSettingsResponse`.
3. Add `dmr_base_url` and `dmr_model` columns (VARCHAR, nullable) to `LLMSettings` in
   `api/db/models.py`.
4. Generate Alembic migration: `alembic revision --autogenerate -m "add docker model runner settings"`.
5. Implement `_call_docker_model_runner(prompt, settings)` in `api/services/ai_normalizer.py`.
   It calls `POST {dmr_base_url}/v1/chat/completions` with the OpenAI messages format.
   Response parsing mirrors `_call_openai()` since the API is compatible.
6. Add the dispatch case for `"docker_model_runner"` in the provider router inside
   `normalize_record()`.
7. Add the Docker Model Runner radio card to `SettingsPage.tsx` (provider selection section),
   with `dmrBaseUrl` and `dmrModel` fields.
8. Add `DMR_BASE_URL` and `DMR_MODEL` to `.env.example` with defaults.

**Relevant Context:**
- `api/schemas/settings.py` — `ProviderLiteral` (line 12), `LLMSettingsSave` (lines 23–44)
- `api/db/models.py` — `LLMSettings` model
- `api/services/ai_normalizer.py` — `_call_openai()` (reuse this pattern exactly)
- `api/routers/settings.py` — provider save/load logic
- `web/src/pages/SettingsPage.tsx` — provider radio cards section

---

### Sub-Task 3.2: HuggingFace Hub GGUF resolver
**Status:** `[x] done`

**Intent:**
When a user wants to benchmark a model that is not yet installed locally (in either Ollama
or Docker Model Runner), the app needs to resolve which GGUF file on HuggingFace Hub to
pull. Add a `GET /api/settings/resolve-gguf?model=<name>` endpoint that queries the
HuggingFace Hub API, finds the best Q4_K_M or Q5_K_M quantization for the named model,
and returns the Docker Model Runner pull command.

**Expected Outcomes:**
- `GET /api/settings/resolve-gguf?model=phi4-mini` returns:
  ```
  {
    "hf_repo": "microsoft/Phi-4-mini-instruct-GGUF",
    "gguf_file": "Phi-4-mini-instruct-Q4_K_M.gguf",
    "pull_command": "docker model pull hf.co/microsoft/Phi-4-mini-instruct-GGUF",
    "size_gb": 2.5,
    "found": true
  }
  ```
- If the model is not found on HF Hub, returns `{ "found": false }`.
- HF Hub API is queried via `https://huggingface.co/api/models?search=<name>&filter=gguf`
  (public, no auth required for public models). Optional `HF_TOKEN` env var for rate limit
  headroom.
- Results cached in-process for 1 hour (same TTL-dict pattern as the advisor cache).

**Todo List:**
1. Add `_resolve_gguf(model_name: str) -> dict` function to
   `api/services/model_catalog.py`.
2. Add `GET /api/settings/resolve-gguf` endpoint to `api/routers/settings.py`.
3. Add `HF_TOKEN` optional env var to `api/core/config.py` (None default).
4. Add `HF_TOKEN=` (empty default) to `.env.example`.
5. Add `resolveGguf(modelName)` binding to `web/src/api/client.ts`.
6. In the benchmark "Compare Models" section: when model B is selected and its backend
   is `docker_model_runner`, show a "Find on HuggingFace" inline link that calls
   `resolveGguf` and displays the pull command in a `<CodeSnippet>`.

**Relevant Context:**
- HuggingFace Hub API: `GET https://huggingface.co/api/models?search={name}&filter=gguf`
  returns array of `{ id, modelId, tags, siblings: [{ rfilename }] }`.
  Filter `siblings` for filenames matching `Q4_K_M` or `Q5_K_M`.
- `api/routers/settings.py` — `_advisor_cache` TTL pattern (lines 427–435)
- `api/core/config.py` — existing env var patterns

---

### Sub-Task 3.3: Fix the 3 failing tests in test_pipeline.py
**Status:** `[x] done`

**Intent:**
Fix the root-cause failure in `test_generator_and_validator` (assertion expects 4 sheets
but generator produces 22), which cascades to `test_export_before_processing_fails` and
`test_delete_project` via fixture state pollution.

**Expected Outcomes:**
- `test_generator_and_validator` passes.
- `test_export_before_processing_fails` passes.
- `test_delete_project` passes.
- Total passing tests: 109/109.

**Root Cause Analysis:**
`test_generator_and_validator` (line 261) asserts `set(result["sheets"]) == {"vInfo", "vNetwork", "vPartition", "vHost"}`. The generator writes all 22 RVTools sheets. The validator treats extra sheets as hard errors. The test assertion predates the full-sheet generator implementation.

**Fix Strategy (Option A — semantically correct fix):**
Update `api/services/validator.py` line 66 to move "unexpected extra sheets" from `errors`
to `warnings`. Real RVTools exports always contain 20+ sheets; the IBM import tool only
reads the 4 required sheets and ignores the rest. Only *missing* required sheets are a
genuine structural problem. This is the right semantic fix — the validator logic was too
strict, not the generator or the test.

**Todo List:**
1. In `api/services/validator.py` line 66, change `errors.append(...)` to
   `warnings.append(...)` for the extra-sheets case.
2. Update the validator comment at line 58 from "Exactly the 4 required sheets —
   no more, no less" to "Required sheets must be present; extra sheets are permitted".
3. In `tests/test_pipeline.py` line 261, change the strict equality assertion to:
   `assert {"vInfo", "vNetwork", "vPartition", "vHost"}.issubset(set(result["sheets"]))`.
4. The `result["errors"] == []` assertion on line 262 now passes naturally (no errors fired).
5. Update the `result["warnings"] == []` assertion on line 264 to:
   `assert not any("no data rows" in w for w in result["warnings"])` — confirms the 4
   required sheets all have data, without requiring zero warnings total.
6. Run `pytest tests/test_pipeline.py -v` and confirm 109/109 tests pass.

**Relevant Context:**
- `tests/test_pipeline.py` lines 255–264 (assertions block)
- `api/services/validator.py` line 66 (extra sheets → errors)
- `api/services/rvtools_generator.py` lines 162–185 (`ALL_SHEETS`)

---

## Implementation Order

Sub-tasks should be implemented in this sequence to minimise conflicts:

```
1.1 → 1.2 → 3.3 → 2.1 → 2.2 → 2.3 → 3.1 → 3.2
```

Rationale:
- 1.1 and 1.2 are isolated catalog fixes — no dependencies.
- 3.3 (test fixes) is isolated — should be done early to restore green CI.
- 2.1 must precede 2.2 (benchmark corpus before the runner).
- 2.2 must precede 2.3 (backend before UI).
- 3.1 must precede 3.2 (Docker Model Runner provider before GGUF resolver uses it).
- 3.2 can be done independently of 2.3 but its UI integration requires 2.3.
