# Model Discovery Plan — "Discover Models" Feature

## Overview

Add a **proactive model discovery** capability to the Local AI Advisor card on the
Settings page. When a user opens Settings, the app queries two live internet registries
— the **Ollama model library** and optionally **HuggingFace Hub** — filters results to
models suited for structured JSON extraction, applies the existing task-fit scoring,
and presents a ranked "Available to Install" list showing models the user does **not**
already have.

This is the capability the `resolve_gguf` endpoint (Sub-Task 3.2) does not provide:
that endpoint is reactive (user types a name they already know). This feature is
proactive — Genesis tells the user what's worth considering before they know to ask.

### Scope boundaries

- Discovery is read-only: the app **suggests** but does not pull or install.
- Ollama is the primary source (curated, structured, task-tagged). HuggingFace is
  secondary and filtered to GGUF only.
- Only models that **fit in the user's available RAM** and are **not already installed**
  are shown.
- Results are scored with the existing `_OLLAMA_TASK_FIT` table; new models not in the
  table receive a neutral score (5) unless their name matches a specialised suffix.
- Discovery is cached for **6 hours** (shorter than the 24 h advisor cache — model
  catalogs change more often than hardware).
- The feature is gated behind the Ollama provider section (same as the existing
  Local AI Advisor card).

---

## Sub-Task 1: Backend — `discover_models()` service function
**Status:** `[x] done`

**Intent:**
Add a `discover_models(installed_names, ram_gb, hf_token)` function to
`api/services/model_catalog.py`. It queries the Ollama search API for the full catalog,
filters to candidates not already installed, scores each with the existing task-fit
logic, and returns a ranked list ready for the endpoint.

**Ollama search API:**
`GET https://ollama.com/api/search?q=&limit=50&sort=newest`

Returns a JSON array where each entry has:
```json
{
  "name": "phi4-mini",
  "description": "...",
  "pulls": 1200000,
  "tags": [{"name": "latest", "size": 2147483648}, ...],
  "updated_at": "2025-01-10T..."
}
```
The `tags` array contains variant entries — each tag has a `size` in bytes. We use
the smallest tag size as the RAM estimate (or look up in `_OLLAMA_RAM_GB`).

**HuggingFace secondary source:**
`GET https://huggingface.co/api/models?task=text-generation&filter=gguf&sort=downloads&limit=20`

Used as a secondary source to surface GGUF-first models not yet in the Ollama library.
De-duplicated against the Ollama results.

**Expected Outcomes:**
- `discover_models(installed_names, ram_gb)` returns a list of `DiscoveredModel`
  dataclass instances, sorted: fits_in_ram first, then task_fit descending.
- Only models **not** in `installed_names` are returned.
- Each result has: `name`, `source` ("ollama" or "huggingface"), `size_gb`,
  `fits_in_ram`, `task_fit`, `description`, `pull_count`, `pull_command`.
- Results for models matching `_SPECIALISED_SUFFIXES` are excluded entirely
  (score ≤ 4 and not worth suggesting).
- Results cached in-process for 6 hours using the same `_time.time()` TTL pattern
  already used in `_gguf_cache`.
- Network errors (Ollama.com or HF unreachable) return an empty list — discovery
  is best-effort and must never break the page.

**Todo List:**
1. Add `DiscoveredModel` dataclass after the existing `RankedModel` dataclass in
   `api/services/model_catalog.py`.
   Fields: `name: str`, `source: str`, `size_gb: float`, `fits_in_ram: bool`,
   `task_fit: int`, `description: str`, `pull_count: int`, `pull_command: str`.
2. Add `_discover_cache: dict` and `_DISCOVER_CACHE_TTL = 21_600` (6 hours) constants.
3. Implement `_fetch_ollama_search(limit: int = 50) -> list[dict]` — async-friendly
   sync call to `https://ollama.com/api/search?q=&limit={limit}&sort=newest`.
   Returns `[]` on any network error (timeout 8 s).
4. Implement `_fetch_hf_text_gen(ram_gb: float, limit: int = 20) -> list[dict]` —
   queries `https://huggingface.co/api/models?task=text-generation&filter=gguf&sort=downloads&limit={limit}`.
   Returns `[]` on any error.
5. Implement `discover_models(installed_names: list[str], ram_gb: float, hf_token: str | None = None) -> list[DiscoveredModel]`:
   - Check cache; return if fresh.
   - Call `_fetch_ollama_search()` and `_fetch_hf_text_gen()`.
   - For each Ollama result: derive `name`, estimate `size_gb` from smallest tag size
     (or `_OLLAMA_RAM_GB` lookup), compute `task_fit`, filter out installed and
     specialised models, build `pull_command = f"ollama pull {name}"`.
   - For each HF result: derive `name` from repo id, skip if already in Ollama results,
     build `pull_command = f"docker model pull hf.co/{repo_id}"`.
   - Sort: `(fits_in_ram DESC, task_fit DESC, size_gb ASC)`.
   - Limit to top 12 results.
   - Store in cache and return.

**Relevant Context:**
- `api/services/model_catalog.py` — `_OLLAMA_TASK_FIT`, `_OLLAMA_RAM_GB`,
  `_SPECIALISED_SUFFIXES`, `_base_name()`, `rank_local_models()` (all used as-is)
- `api/services/model_catalog.py` — `_gguf_cache` TTL pattern (lines ~397-400) to copy
- `resolve_gguf()` — same HF API structure, reuse field-extraction patterns

---

## Sub-Task 2: Backend — `GET /api/settings/discover-models` endpoint
**Status:** `[x] done`

**Intent:**
Expose `discover_models()` as an HTTP endpoint that the Settings page can call.
Accepts optional `?refresh=true` to bypass cache. Reads `ram_gb` from the same
`_read_ram_gb()` helper the local advisor uses so the RAM filter is consistent.

**Expected Outcomes:**
- `GET /api/settings/discover-models` returns `200` with a `DiscoveryResponse`.
- `?refresh=true` bypasses the 6-hour cache.
- Response includes `discovered` list and a `source_reachable` dict so the UI can
  show a "Could not reach Ollama.com" warning if the registry was offline.
- Adds `discover_models` to the import from `model_catalog` in `settings.py`.

**Response shape:**
```json
{
  "discovered": [
    {
      "name": "phi4",
      "source": "ollama",
      "size_gb": 8.2,
      "fits_in_ram": true,
      "task_fit": 10,
      "description": "Microsoft's Phi-4 ...",
      "pull_count": 1500000,
      "pull_command": "ollama pull phi4"
    }
  ],
  "sources_checked": ["ollama", "huggingface"],
  "sources_reachable": {"ollama": true, "huggingface": true},
  "ram_gb": 16.0
}
```

**Todo List:**
1. Import `discover_models` and `DiscoveredModel` from `services.model_catalog` in
   `api/routers/settings.py`.
2. Add `GET /api/settings/discover-models` endpoint at the end of the router.
3. Read `ram_gb` using `_read_ram_gb()` (already in the module).
4. Read `installed_names` by calling `_fetch_ollama_tags(base_url)` and extracting
   names — same pattern as `get_local_advisor`. This ensures "already installed"
   filtering is consistent with what the advisor shows.
5. Read `hf_token` from `cfg.hf_token` (already in `config.py`).
6. Return the structured response dict. Network errors caught in `discover_models()`
   — endpoint always returns 200 (empty list if both registries unreachable).

**Relevant Context:**
- `api/routers/settings.py` — `_read_ram_gb()`, `_fetch_ollama_tags()`,
  `_get_or_create_row()`, `get_local_advisor` endpoint (pattern to follow)

---

## Sub-Task 3: Frontend — TypeScript interfaces and API binding
**Status:** `[x] done`

**Intent:**
Add the TypeScript types for `DiscoveredModel` and `DiscoveryResponse`, and add the
`discoverModels()` binding to the `api.settings` namespace in `client.ts`.

**Expected Outcomes:**
- `DiscoveredModel` and `DiscoveryResponse` interfaces exported from `client.ts`.
- `api.settings.discoverModels(refresh?)` binding calls the endpoint.

**Todo List:**
1. Add interfaces to `web/src/api/client.ts` after the `LocalAdvisorResponse` interface:
   ```typescript
   export interface DiscoveredModel {
     name: string;
     source: string;         // "ollama" | "huggingface"
     size_gb: number;
     fits_in_ram: boolean;
     task_fit: number;
     description: string;
     pull_count: number;
     pull_command: string;
   }
   export interface DiscoveryResponse {
     discovered: DiscoveredModel[];
     sources_checked: string[];
     sources_reachable: Record<string, boolean>;
     ram_gb: number;
   }
   ```
2. Add `discoverModels` binding to `api.settings`:
   ```typescript
   discoverModels: (refresh = false): Promise<DiscoveryResponse> =>
     fetch(`${BASE}/settings/discover-models${refresh ? '?refresh=true' : ''}`).then(r => r.json()),
   ```

**Relevant Context:**
- `web/src/api/client.ts` — `LocalAdvisorResponse` interface (lines 146-154),
  `getLocalAdvisor` binding (line 415) — follow same pattern

---

## Sub-Task 4: Frontend — "Discover Models" UI section
**Status:** `[x] done`

**Intent:**
Add a **"Discover Models"** section inside the existing Local AI Advisor card in
`SettingsPage.tsx`, positioned below the pull suggestion and above the Compare Models
toggle. Discovery is **button-triggered only** — a "🔭 Check for New Models" button
is shown when the advisor is loaded; clicking it opens the section and fires the first
fetch. Subsequent refreshes use a "↻ Refresh catalog" button inside the open section.
No internet call happens unless the user explicitly clicks.

**Expected Outcomes:**
- A **"🔭 Check for New Models"** `<Button kind="ghost" size="sm">` appears at the
  bottom of the installed-models list when `advisor` is loaded and `discoveryOpen`
  is false.
- Clicking it sets `discoveryOpen = true` and calls `loadDiscovery(false)`.
- While loading: shows `<InlineLoading description="Checking model registries…" />`.
- If both registries were unreachable: shows an `<InlineNotification kind="warning">`
  ("Could not reach model registries — check your internet connection").
- If list is empty after successful fetch: shows "All recommended models are already
  installed or not suited for this task."
- Each model row shows:
  - Model name (bold, `<code>`)
  - Source badge: `<Tag type="blue">Ollama</Tag>` or `<Tag type="purple">HuggingFace</Tag>`
  - Size in GB
  - Task-fit score as a coloured pill (green ≥ 8, yellow 6–7, grey 5)
  - Description (truncated to 80 chars)
  - Pull command in a `<code>` block with `userSelect: 'all'` (click to select all)
  - `<Tag type="green">↑ fits in RAM</Tag>` or `<Tag type="red">⚠ may not fit</Tag>`
- A "↻ Refresh catalog" ghost button at the section header calls
  `loadDiscovery(true)` (cache bypass).
- A "▲ Hide" button collapses the section back (`discoveryOpen = false`).
- Models shown in task-fit descending order; "fits in RAM" models first.

**State variables to add:**
- `discoveryOpen: boolean`          — section visible/hidden
- `discoveryResult: DiscoveryResponse | null`
- `discoveryLoading: boolean`
- `discoveryError: string`

**Todo List:**
1. Add four state variables to `SettingsPage.tsx` after the `ggufResult` state.
2. Add `loadDiscovery(refresh: boolean)` function that calls
   `api.settings.discoverModels(refresh)`, sets `discoveryResult`/`discoveryLoading`/
   `discoveryError` state accordingly.
3. Add the **"🔭 Check for New Models"** button JSX inside the Local AI Advisor card,
   below the installed-models list block, visible only when `advisor` is loaded and
   `!discoveryOpen`. On click: `setDiscoveryOpen(true); loadDiscovery(false)`.
4. Add the "Discover Models" open section JSX (shown only when `discoveryOpen`),
   placed between the pull suggestion block and the "Compare Models" toggle, inside
   the `{advisor && !advisorLoading}` guard.
5. Import `DiscoveryResponse` from `../api/client`.

**Relevant Context:**
- `web/src/pages/SettingsPage.tsx` — pull suggestion block (lines ~524-534),
  Compare Models toggle (lines ~466-477) — insert between these two
- `web/src/pages/SettingsPage.tsx` — `loadAdvisor()` function (lines ~132-152)
  — extend by chaining `loadDiscovery(false)` call
- Existing `InlineLoading`, `InlineNotification`, `Tag` imports already present
- `thStyle`/`tdStyle` constants already defined for table rendering

---

## Implementation Order

```
1 → 2 → 3 → 4
```

Each sub-task has a hard dependency on the previous one. Sub-Task 1 must exist
before Sub-Task 2 can call it. Sub-Task 3 must exist before Sub-Task 4 can compile.

---

## Key Design Decisions

| Decision | Rationale |
|---|---|
| Ollama.com as primary source | Only source with structured task tags and pull counts for Ollama models; most users run Ollama |
| HuggingFace as secondary | Surfaces GGUF-native models not in Ollama library; same HF API already proven by `resolve_gguf` |
| 6-hour cache | Model catalogs change weekly at most; 24 h would miss new releases; 6 h balances freshness vs. rate limits |
| Network errors → empty list | Discovery is informational — a registry outage must never break the Settings page |
| Specialised models excluded (score ≤ 4) | coder/embed/vision models are actively harmful suggestions for this task; better to show nothing than to mislead |
| Max 12 results | Prevents UI overload; top-12 by task fit + RAM fit is sufficient for decision-making |
| Button-triggered discovery | Internet call only happens when user explicitly requests — no surprise outbound requests on every Settings page open; consistent with principle of least surprise |
| Pull command per row | User can copy and run immediately without navigating away |
