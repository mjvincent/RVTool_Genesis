# RVTool Genesis — LLM Provider Configuration Plan

## Overview

Add a multi-provider LLM abstraction layer so users can choose between:

- **Ollama (local)** — current default, no API key, works offline
- **IBM watsonx.ai** — IBM-native cloud LLM, recommended for IBM engagements
- **OpenAI-compatible** — covers OpenAI, Azure OpenAI, and any OpenAI-compatible endpoint
- **Anthropic** — Claude models via the Anthropic API

The active provider and its credentials are configured via a new **Settings page** in the
UI and persisted to a `llm_settings` table in PostgreSQL. API keys are encrypted at rest
using AES-256 (via the `cryptography` package) so they are never stored or logged in
plaintext.

**Scope:** LLM provider switching only. Backup/restore is a separate feature (see
`rvtool-genesis-backup-plan.md`).

---

## Architecture

```
Settings page (UI)
      |
      v
POST /api/settings  ──────────────────────────────────>  llm_settings table (DB)
                                                          (api_key encrypted AES-256)

normalize_record()
      |
      v
_call_llm()  ──>  reads active provider from settings  ──>  dispatch
                        |               |               |              |
                    _call_ollama()  _call_watsonx()  _call_openai()  _call_anthropic()
                        |
                     (fallback: Python synthesizer — unchanged)
```

### Provider API Summary

| Provider | Endpoint | Auth | IBM Notes |
|---|---|---|---|
| Ollama | `{base_url}/api/generate` | None | Current default |
| watsonx.ai | `{iam_url}/identity/token` → `{watsonx_url}/ml/v1/text/generation` | IAM API key + project_id | Recommended for IBM |
| OpenAI-compatible | `{base_url}/v1/chat/completions` | Bearer API key | Covers OpenAI, Azure, local vLLM |
| Anthropic | `https://api.anthropic.com/v1/messages` | `x-api-key` header | Claude models |

### Prompt Differences

The existing `_SYSTEM_PROMPT` + `_build_prompt()` are Ollama-specific (using
`format: "json"` for structured output). Each provider adapter must translate the
prompt appropriately:

- **watsonx / OpenAI / Anthropic**: Use chat completions format (system + user messages).
  Append "Return ONLY valid JSON." to the system prompt. Parse JSON from the text
  response (same `_extract_json()` already used for fallback).
- **Ollama**: Unchanged — `format: "json"` enforces structured output.

---

## Sub-Task 1 — Database: `llm_settings` table and migration

**Status:** [x] done

**Intent:**
Add a `llm_settings` table to persist the active provider configuration. This survives
container restarts without requiring `.env` edits. Exactly one row is active at a time
(single-row settings pattern with `id = 1`).

**Expected Outcomes:**
- Migration creates `llm_settings` table
- `Settings` Pydantic schema exposed for GET/POST
- `api/db/models.py` has `LLMSettings` model

**Todo List:**
1. Add `LLMSettings` model to `api/db/models.py`:
   - `id` (Integer, PK, default 1)
   - `provider` (String, default `"ollama"`) — `ollama | watsonx | openai | anthropic`
   - `ollama_base_url` (String, nullable) — override for Ollama URL
   - `ollama_model` (String, nullable) — override for Ollama model name
   - `watsonx_api_key_enc` (Text, nullable) — AES-256 encrypted
   - `watsonx_project_id` (String, nullable)
   - `watsonx_url` (String, nullable, default `"https://us-south.ml.cloud.ibm.com"`)
   - `watsonx_model` (String, nullable, default `"ibm/granite-3-8b-instruct"`)
   - `openai_api_key_enc` (Text, nullable) — AES-256 encrypted
   - `openai_base_url` (String, nullable, default `"https://api.openai.com"`)
   - `openai_model` (String, nullable, default `"gpt-4o-mini"`)
   - `anthropic_api_key_enc` (Text, nullable) — AES-256 encrypted
   - `anthropic_model` (String, nullable, default `"claude-3-haiku-20240307"`)
   - `updated_at` (DateTime)
2. Generate Alembic migration: `alembic revision --autogenerate -m "add llm_settings"`
3. Add `LLMSettingsSchema` Pydantic model to `api/schemas/` (never exposes `_enc` fields
   in responses — return masked key like `"sk-...abc"` for display only)

**Relevant Files:**
- `api/db/models.py` — existing model pattern (6 models)
- `api/alembic/` — migration pattern
- `api/schemas/project.py` — Pydantic v2 schema pattern

---

## Sub-Task 2 — Backend: encryption utility + settings router

**Status:** [x] done

**Intent:**
Add a thin encryption helper (`api/services/crypto.py`) and a settings CRUD router
(`api/routers/settings.py`) so the UI can read and update the active provider config.
API keys are encrypted before storage and never returned in plaintext.

**Expected Outcomes:**
- `GET /api/settings` returns current provider + non-sensitive fields + masked key hints
- `POST /api/settings` validates and saves new provider config (encrypts keys before write)
- `POST /api/settings/test` tests connectivity to the configured provider, returns
  `{"ok": true}` or `{"ok": false, "error": "..."}`
- Encrypted keys survive container restarts (stored in DB, not memory)

**Todo List:**
1. Create `api/services/crypto.py`:
   - `_get_fernet()` — derives a Fernet key from `SECRET_KEY` env var using PBKDF2
   - `encrypt(plaintext: str) -> str` — returns base64 Fernet token
   - `decrypt(token: str) -> str` — raises on bad key
   - Add `SECRET_KEY` to `core/config.py` (random default, override in `.env`)
2. Add `SECRET_KEY` to `.env.example` with a note to override before production use
3. Create `api/routers/settings.py`:
   - `GET /api/settings` — reads row `id=1`, returns provider + public fields + masked keys
   - `POST /api/settings` — upserts row `id=1`, encrypts key fields before write
   - `POST /api/settings/test` — calls appropriate `_test_provider()` helper, returns
     `{ok, latency_ms, model_response_preview}`
4. Register `settings_router` in `api/main.py`
5. Add `cryptography` to `api/requirements.txt`

**Relevant Files:**
- `api/core/config.py` — add `SECRET_KEY` setting
- `api/main.py` — router registration
- `api/routers/exports.py` — pattern for router structure
- `api/db/models.py` — `LLMSettings` (from Sub-Task 1)

---

## Sub-Task 3 — Backend: LLM provider abstraction in `ai_normalizer.py`

**Status:** [x] done

**Intent:**
Replace the hardcoded `_call_ollama()` call in `normalize_record()` with a dispatcher
`_call_llm()` that reads the active provider from the database and routes to the correct
adapter. Ollama remains the default when no DB settings exist.

**Expected Outcomes:**
- Switching provider in Settings page takes effect on the next `POST /process` call
  (no container restart needed)
- Each adapter returns the same raw text string as `_call_ollama()` currently does
  (all downstream JSON parsing is unchanged)
- Fallback chain preserved: cloud LLM failure → Python synthesizer (not Ollama, since
  Ollama may intentionally be disabled)
- `normalize_record()` signature unchanged

**Todo List:**
1. Add `_call_watsonx(payload_text: str) -> str`:
   - Exchange IBM IAM API key for a Bearer token via
     `POST https://iam.cloud.ibm.com/identity/token`
   - POST to `{watsonx_url}/ml/v1/text/generation?version=2024-01-01`
   - Body: `{"model_id": model, "input": prompt, "project_id": ..., "parameters": {"max_new_tokens": 3000}}`
   - Returns the `results[0].generated_text` string
   - IAM token is cached in a module-level dict for 50 minutes (tokens expire at 60 min)
2. Add `_call_openai(payload_text: str) -> str`:
   - POST to `{base_url}/v1/chat/completions`
   - Body: `{"model": model, "messages": [{"role":"system","content":system_prompt}, {"role":"user","content":payload_text}], "response_format": {"type":"json_object"}}`
   - Returns `choices[0].message.content`
3. Add `_call_anthropic(payload_text: str) -> str`:
   - POST to `https://api.anthropic.com/v1/messages`
   - Headers: `x-api-key`, `anthropic-version: 2023-06-01`
   - Body: `{"model": model, "max_tokens": 3000, "system": system_prompt, "messages": [{"role":"user","content":payload_text}]}`
   - Returns `content[0].text`
4. Add `_call_llm(prompt_text: str) -> str`:
   - Reads active `LLMSettings` from DB (synchronous SQLAlchemy call since
     `normalize_record` runs in a background thread, not async context)
   - Falls back to Ollama config from `core/config.py` if no DB row exists
   - Dispatches to the correct adapter
   - On any exception: re-raises `ValueError` (caller handles fallback to Python synthesizer)
5. Update `normalize_record()`: replace `_call_ollama(payload)` with `_call_llm(prompt)`
   - For Ollama: pass the full structured payload dict (unchanged)
   - For cloud providers: pass only the prompt text string (no `model` / `format` wrapper)

**Relevant Files:**
- `api/services/ai_normalizer.py` — `_call_ollama()`, `normalize_record()`, `_SYSTEM_PROMPT`
- `api/services/crypto.py` — `decrypt()` (from Sub-Task 2)
- `api/db/models.py` — `LLMSettings`
- `api/core/config.py` — fallback Ollama settings

---

## Sub-Task 4 — Frontend: Settings page

**Status:** [x] done

**Intent:**
Add a `/settings` route and a `SettingsPage` component that lets users pick their LLM
provider, enter credentials, and test the connection — all using Carbon components and
the IBM g10 theme consistent with the rest of the app.

**UI Design:**
- New nav item "Settings" (gear icon) in the left nav / header
- `SettingsPage` layout:
  - **LLM Provider** section: Carbon `RadioButtonGroup` with 4 options
    (Ollama local, IBM watsonx.ai ★ recommended, OpenAI-compatible, Anthropic)
  - **Provider-specific fields** shown conditionally based on selection:
    - Ollama: Base URL + Model name (pre-filled from defaults)
    - watsonx.ai: API Key (`PasswordInput`), Project ID, Region URL, Model name
    - OpenAI: API Key (`PasswordInput`), Base URL (for Azure/custom), Model name
    - Anthropic: API Key (`PasswordInput`), Model name
  - **"Test Connection"** button — calls `POST /api/settings/test`, shows inline
    `InlineLoading` → success/error `InlineNotification` with latency and model preview
  - **"Save Settings"** button — calls `POST /api/settings`
  - A callout note: "IBM watsonx.ai is recommended for IBM engagement work.
    Ollama requires the Ollama app running on your local machine."

**Expected Outcomes:**
- User can switch from Ollama to watsonx.ai by entering an IBM Cloud API key + project ID
- "Test Connection" confirms credentials before saving
- Saved settings persist across browser refresh and container restarts
- Carbon `PasswordInput` used for all key fields (masked by default, reveal toggle)

**Todo List:**
1. Add API client calls in `web/src/api/client.ts`:
   - `api.settings.get()` → `GET /api/settings`
   - `api.settings.save(payload)` → `POST /api/settings`
   - `api.settings.test()` → `POST /api/settings/test`
2. Create `web/src/pages/SettingsPage.tsx`:
   - Carbon `RadioButtonGroup`, `TextInput`, `PasswordInput`, `Button`, `InlineNotification`
   - Conditional field rendering based on selected provider
   - Load current settings on mount, show saved values (keys masked as `"••••••••abcd"`)
3. Add `/settings` route to `web/src/App.tsx`
4. Add "Settings" link to the navigation (existing nav pattern in `App.tsx`)

**Relevant Files:**
- `web/src/App.tsx` — route and nav pattern
- `web/src/pages/ExportPage.tsx` — `InfoTooltip` and card layout pattern
- `web/src/pages/NormalizePage.tsx` — `InlineLoading` + `InlineNotification` pattern
- `web/src/api/client.ts` — existing API call pattern

---

## Sub-Task 5 — Documentation and branch hygiene

**Status:** [x] done

**Intent:**
Update README with LLM provider documentation, update Changelog, and manage branches.

**Todo List:**
1. Cut branch `feat/llm-providers` from `feat/resilience-and-ux` (or `main` if merged)
2. Add README section "LLM Providers":
   - Comparison table (Ollama vs watsonx.ai vs OpenAI vs Anthropic)
   - How to get an IBM Cloud API key and watsonx.ai project ID
   - How the IAM token cache works (50-min cache, auto-refreshed)
   - Security note: keys stored AES-256 encrypted in PostgreSQL
   - Note: switching providers takes effect on the next processing run, no restart needed
3. Update Changelog
4. Add `cryptography` to `requirements.txt` note in README

**Relevant Files:**
- `README.md`
- `api/requirements.txt`

---

## Dependencies and Ordering

```
Sub-Task 1 (DB schema)
      |
      v
Sub-Task 2 (crypto + settings router)
      |
      v
Sub-Task 3 (LLM dispatcher in ai_normalizer)
      |
      v
Sub-Task 4 (Settings UI)
      |
      v
Sub-Task 5 (docs + branch)
```

Sub-Tasks 3 and 4 can proceed in parallel once Sub-Task 2 is complete.

---

## New Files

| File | Purpose |
|---|---|
| `api/services/crypto.py` | AES-256 encrypt/decrypt for API keys |
| `api/routers/settings.py` | GET/POST `/api/settings` + test endpoint |
| `web/src/pages/SettingsPage.tsx` | Carbon Settings page UI |

## Changed Files

| File | Change |
|---|---|
| `api/db/models.py` | Add `LLMSettings` model |
| `api/core/config.py` | Add `SECRET_KEY` setting |
| `api/requirements.txt` | Add `cryptography` |
| `api/main.py` | Register `settings_router` |
| `api/services/ai_normalizer.py` | Replace `_call_ollama` with `_call_llm` dispatcher |
| `api/alembic/versions/` | New migration file |
| `.env.example` | Add `SECRET_KEY` |
| `web/src/App.tsx` | Add `/settings` route + nav link |
| `web/src/api/client.ts` | Add `api.settings.*` calls |
| `README.md` | New LLM Providers section |

## No New Heavy Dependencies

- `cryptography` — stdlib-style, ~4 MB, already a transitive dep of many packages
- All LLM provider calls use `httpx` (already in `requirements.txt`) — no vendor SDKs
