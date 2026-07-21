"""Settings router — GET/POST /api/settings and POST /api/settings/test.

The active LLM provider and its (encrypted) credentials are persisted in the
`llm_settings` table (id=1 always).  API keys are encrypted with AES-256 Fernet
before storage and never returned in plaintext — only a masked hint is exposed.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import get_db
from db.models import LLMSettings
from schemas.settings import (
    LLMSettingsResponse, LLMSettingsSave, LLMTestResult, _mask,
    BenchmarkRequest, BenchmarkResult, BenchmarkCaseResult, ModelResult,
)
from services.crypto import decrypt, encrypt
from services.model_catalog import ModelRecommendation, get_recommendation, rank_local_models, get_pull_suggestion, resolve_gguf, discover_models, DiscoveredModel

logger = logging.getLogger(__name__)

router = APIRouter(tags=["settings"])

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TEST_PROMPT = (
    'Return ONLY this JSON, no other text: {"answer": "ok", "provider": "test"}'
)
_WATSONX_IAM_URL = "https://iam.cloud.ibm.com/identity/token"

# Allowlist of approved LLM provider endpoint domains.
# Stored credentials will never be sent to a URL whose host is not in this set.
# "localhost" and "127.0.0.1" are permitted for local Ollama / Docker Model Runner.
_APPROVED_ENDPOINT_HOSTS: frozenset[str] = frozenset({
    "localhost",
    "127.0.0.1",
    "host.docker.internal",          # Ollama on host from inside container
    "api.openai.com",                # OpenAI
    "api.anthropic.com",             # Anthropic
    "iam.cloud.ibm.com",             # IBM IAM token exchange
    "us-south.ml.cloud.ibm.com",     # WatsonX — US South
    "eu-de.ml.cloud.ibm.com",        # WatsonX — Frankfurt
    "eu-gb.ml.cloud.ibm.com",        # WatsonX — London
    "jp-tok.ml.cloud.ibm.com",       # WatsonX — Tokyo
    "au-syd.ml.cloud.ibm.com",       # WatsonX — Sydney
})


def _assert_approved_endpoint(url: str, provider: str) -> None:
    """Raise ValueError if the URL host is not in the approved endpoint allowlist.

    This prevents stored cloud credentials from being forwarded to arbitrary URLs
    that may be supplied in the test-endpoint request body.
    """
    from urllib.parse import urlparse
    parsed = urlparse(url)
    host = parsed.hostname or ""
    if host not in _APPROVED_ENDPOINT_HOSTS:
        raise ValueError(
            f"Endpoint '{url}' is not in the approved {provider} provider list. "
            f"Approved domains: {sorted(_APPROVED_ENDPOINT_HOSTS)}"
        )


async def _get_or_create_row(db: AsyncSession) -> LLMSettings:
    """Fetch the singleton settings row, creating it with Ollama defaults if absent."""
    row = await db.get(LLMSettings, 1)
    if row is None:
        row = LLMSettings(id=1, provider="ollama")
        db.add(row)
        await db.commit()
        await db.refresh(row)
    return row


def _row_to_response(row: LLMSettings) -> LLMSettingsResponse:
    return LLMSettingsResponse(
        provider=row.provider,  # type: ignore[arg-type]
        ollama_base_url=row.ollama_base_url,
        ollama_model=row.ollama_model,
        watsonx_api_key_hint=_mask(row.watsonx_api_key_enc),
        watsonx_project_id=row.watsonx_project_id,
        watsonx_url=row.watsonx_url,
        watsonx_model=row.watsonx_model,
        openai_api_key_hint=_mask(row.openai_api_key_enc),
        openai_base_url=row.openai_base_url,
        openai_model=row.openai_model,
        anthropic_api_key_hint=_mask(row.anthropic_api_key_enc),
        anthropic_model=row.anthropic_model,
        dmr_base_url=getattr(row, "dmr_base_url", None),
        dmr_model=getattr(row, "dmr_model", None),
        previous_model=row.previous_model,
        updated_at=row.updated_at,
    )


# ---------------------------------------------------------------------------
# GET /api/settings
# ---------------------------------------------------------------------------

@router.get("/settings", response_model=LLMSettingsResponse)
async def get_settings(db: AsyncSession = Depends(get_db)) -> LLMSettingsResponse:
    """Return current LLM provider settings (keys masked)."""
    row = await _get_or_create_row(db)
    return _row_to_response(row)


# ---------------------------------------------------------------------------
# POST /api/settings
# ---------------------------------------------------------------------------

@router.post("/settings", response_model=LLMSettingsResponse)
async def save_settings(
    payload: LLMSettingsSave,
    db: AsyncSession = Depends(get_db),
) -> LLMSettingsResponse:
    """Persist LLM provider settings.  Encrypts API keys before storage."""
    row = await _get_or_create_row(db)

    row.provider = payload.provider

    # Ollama
    if payload.ollama_base_url is not None:
        row.ollama_base_url = payload.ollama_base_url or None
    if payload.ollama_model is not None:
        row.ollama_model = payload.ollama_model or None

    # watsonx.ai
    if payload.watsonx_api_key is not None:
        row.watsonx_api_key_enc = encrypt(payload.watsonx_api_key) if payload.watsonx_api_key else None
    if payload.watsonx_project_id is not None:
        row.watsonx_project_id = payload.watsonx_project_id or None
    if payload.watsonx_url is not None:
        row.watsonx_url = payload.watsonx_url or None
    if payload.watsonx_model is not None:
        row.watsonx_model = payload.watsonx_model or None

    # OpenAI-compatible
    if payload.openai_api_key is not None:
        row.openai_api_key_enc = encrypt(payload.openai_api_key) if payload.openai_api_key else None
    if payload.openai_base_url is not None:
        row.openai_base_url = payload.openai_base_url or None
    if payload.openai_model is not None:
        row.openai_model = payload.openai_model or None

    # Anthropic
    if payload.anthropic_api_key is not None:
        row.anthropic_api_key_enc = encrypt(payload.anthropic_api_key) if payload.anthropic_api_key else None
    if payload.anthropic_model is not None:
        row.anthropic_model = payload.anthropic_model or None

    # Docker Model Runner
    if payload.dmr_base_url is not None:
        row.dmr_base_url = payload.dmr_base_url or None
    if payload.dmr_model is not None:
        row.dmr_model = payload.dmr_model or None

    await db.commit()
    await db.refresh(row)
    logger.info("LLM settings updated — provider=%s", row.provider)
    return _row_to_response(row)


# ---------------------------------------------------------------------------
# POST /api/settings/test
# ---------------------------------------------------------------------------

@router.post("/settings/test", response_model=LLMTestResult)
async def test_settings(
    payload: LLMSettingsSave,
    db: AsyncSession = Depends(get_db),
) -> LLMTestResult:
    """Test connectivity to the selected LLM provider without saving.

    If the payload contains a key, use it directly.  Otherwise fall back to
    the currently-saved encrypted key from the DB.
    """
    provider = payload.provider
    t0 = time.monotonic()

    try:
        if provider == "ollama":
            result = await _test_ollama(payload, db)
        elif provider == "watsonx":
            result = await _test_watsonx(payload, db)
        elif provider == "openai":
            result = await _test_openai(payload, db)
        elif provider == "anthropic":
            result = await _test_anthropic(payload, db)
        else:
            return LLMTestResult(ok=False, provider=provider, error=f"Unknown provider: {provider}")
    except Exception as exc:  # noqa: BLE001
        return LLMTestResult(
            ok=False,
            provider=provider,
            latency_ms=int((time.monotonic() - t0) * 1000),
            error=str(exc),
        )

    latency_ms = int((time.monotonic() - t0) * 1000)
    return LLMTestResult(ok=True, provider=provider, latency_ms=latency_ms, preview=result[:120])


# ---------------------------------------------------------------------------
# Provider test helpers (all synchronous httpx inside run_in_executor would
# complicate things; since these are one-shot short requests, sync httpx in
# an async route is acceptable for a test endpoint)
# ---------------------------------------------------------------------------

async def _test_ollama(payload: LLMSettingsSave, db: AsyncSession) -> str:
    row = await _get_or_create_row(db)
    from core.config import settings as cfg
    base_url = payload.ollama_base_url or row.ollama_base_url or cfg.ollama_base_url
    model = payload.ollama_model or row.ollama_model or cfg.ollama_model
    _assert_approved_endpoint(base_url, "ollama")
    resp = httpx.post(
        f"{base_url}/api/generate",
        json={"model": model, "prompt": _TEST_PROMPT, "stream": False,
              "format": "json", "options": {"temperature": 0, "num_predict": 60}},
        timeout=30.0,
    )
    resp.raise_for_status()
    return resp.json().get("response", "")[:120]


async def _get_watsonx_token(api_key: str) -> str:
    """Exchange an IBM Cloud API key for a short-lived Bearer token."""
    resp = httpx.post(
        _WATSONX_IAM_URL,
        data={"grant_type": "urn:ibm:params:oauth:grant-type:apikey", "apikey": api_key},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=20.0,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


async def _test_watsonx(payload: LLMSettingsSave, db: AsyncSession) -> str:
    row = await _get_or_create_row(db)
    # Resolve API key: fresh from payload OR decrypt stored value
    api_key = payload.watsonx_api_key
    if not api_key and row.watsonx_api_key_enc:
        api_key = decrypt(row.watsonx_api_key_enc)
    if not api_key:
        raise ValueError("No watsonx API key provided. Enter your IBM Cloud API key above.")
    project_id = payload.watsonx_project_id or row.watsonx_project_id
    if not project_id:
        raise ValueError("watsonx Project ID is required.")
    watsonx_url = payload.watsonx_url or row.watsonx_url or "https://us-south.ml.cloud.ibm.com"
    model = payload.watsonx_model or row.watsonx_model or "ibm/granite-3-8b-instruct"
    _assert_approved_endpoint(watsonx_url, "watsonx")

    token = await _get_watsonx_token(api_key)
    resp = httpx.post(
        f"{watsonx_url}/ml/v1/text/generation?version=2024-01-01",
        json={
            "model_id": model,
            "input": _TEST_PROMPT,
            "project_id": project_id,
            "parameters": {"max_new_tokens": 60, "temperature": 0},
        },
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=30.0,
    )
    resp.raise_for_status()
    return resp.json()["results"][0]["generated_text"]


async def _test_openai(payload: LLMSettingsSave, db: AsyncSession) -> str:
    row = await _get_or_create_row(db)
    api_key = payload.openai_api_key
    if not api_key and row.openai_api_key_enc:
        api_key = decrypt(row.openai_api_key_enc)
    if not api_key:
        raise ValueError("No OpenAI API key provided.")
    base_url = payload.openai_base_url or row.openai_base_url or "https://api.openai.com"
    model = payload.openai_model or row.openai_model or "gpt-4o-mini"
    _assert_approved_endpoint(base_url, "openai")

    resp = httpx.post(
        f"{base_url}/v1/chat/completions",
        json={
            "model": model,
            "messages": [{"role": "user", "content": _TEST_PROMPT}],
            "response_format": {"type": "json_object"},
            "max_tokens": 60,
        },
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        timeout=30.0,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


async def _test_anthropic(payload: LLMSettingsSave, db: AsyncSession) -> str:
    row = await _get_or_create_row(db)
    api_key = payload.anthropic_api_key
    if not api_key and row.anthropic_api_key_enc:
        api_key = decrypt(row.anthropic_api_key_enc)
    if not api_key:
        raise ValueError("No Anthropic API key provided.")
    model = payload.anthropic_model or row.anthropic_model or "claude-3-haiku-20240307"

    resp = httpx.post(
        "https://api.anthropic.com/v1/messages",
        json={
            "model": model,
            "max_tokens": 60,
            "messages": [{"role": "user", "content": _TEST_PROMPT}],
        },
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        },
        timeout=30.0,
    )
    resp.raise_for_status()
    return resp.json()["content"][0]["text"]


# ---------------------------------------------------------------------------
# Model recommendation endpoints
# ---------------------------------------------------------------------------

class _RecommendationResponse(LLMSettingsResponse):
    """Extended settings response that includes recommendation state."""
    pass  # LLMSettingsResponse already has previous_model


from pydantic import BaseModel as _BaseModel

class _RecommendationCheck(_BaseModel):
    recommendation: dict | None
    snoozed: bool


def _recommendation_to_dict(rec: ModelRecommendation | None) -> dict | None:
    if rec is None:
        return None
    return {
        "provider": rec.provider,
        "current_model": rec.current_model,
        "recommended_model": rec.recommended_model,
        "recommended_label": rec.recommended_label,
        "reason": rec.reason,
    }


def _is_snoozed(row: LLMSettings) -> bool:
    snooze = row.recommendation_snoozed_until
    if snooze is None:
        return False
    # Handle both tz-aware and tz-naive datetimes
    now = datetime.now(timezone.utc)
    if snooze.tzinfo is None:
        snooze = snooze.replace(tzinfo=timezone.utc)
    return snooze > now


def _active_model(row: LLMSettings) -> str | None:
    """Return the currently configured model ID for the active provider."""
    from core.config import settings as cfg
    p = row.provider
    if p == "ollama":
        return row.ollama_model or cfg.ollama_model
    if p == "watsonx":
        return row.watsonx_model
    if p == "openai":
        return row.openai_model
    if p == "anthropic":
        return row.anthropic_model
    return None


@router.get("/settings/model-recommendation", response_model=_RecommendationCheck)
async def get_model_recommendation(db: AsyncSession = Depends(get_db)) -> _RecommendationCheck:
    """Return the current model recommendation (if any) and snooze state."""
    row = await _get_or_create_row(db)
    snoozed = _is_snoozed(row)
    if snoozed:
        return _RecommendationCheck(recommendation=None, snoozed=True)
    rec = get_recommendation(row.provider, _active_model(row))
    return _RecommendationCheck(recommendation=_recommendation_to_dict(rec), snoozed=False)


@router.post("/settings/model-recommendation/apply", response_model=LLMSettingsResponse)
async def apply_model_recommendation(db: AsyncSession = Depends(get_db)) -> LLMSettingsResponse:
    """One-click upgrade: save current model as previous_model, apply recommended model."""
    row = await _get_or_create_row(db)
    current = _active_model(row)
    rec = get_recommendation(row.provider, current)
    if rec is None:
        raise HTTPException(status_code=404, detail="No recommendation available for the current provider and model.")

    # Save previous model for rollback
    row.previous_model = current
    # Apply recommended model to the active provider field
    p = row.provider
    if p == "ollama":
        row.ollama_model = rec.recommended_model
    elif p == "watsonx":
        row.watsonx_model = rec.recommended_model
    elif p == "openai":
        row.openai_model = rec.recommended_model
    elif p == "anthropic":
        row.anthropic_model = rec.recommended_model
    # Clear snooze so the user sees fresh recommendations on next check
    row.recommendation_snoozed_until = None

    await db.commit()
    await db.refresh(row)
    logger.info("Model recommendation applied — provider=%s new_model=%s previous=%s",
                p, rec.recommended_model, current)
    return _row_to_response(row)


@router.post("/settings/model-recommendation/rollback", response_model=LLMSettingsResponse)
async def rollback_model(db: AsyncSession = Depends(get_db)) -> LLMSettingsResponse:
    """Revert to the previous model (undo a one-click recommendation apply)."""
    row = await _get_or_create_row(db)
    if not row.previous_model:
        raise HTTPException(status_code=404, detail="No previous model to roll back to.")

    prev = row.previous_model
    p = row.provider
    if p == "ollama":
        row.ollama_model = prev
    elif p == "watsonx":
        row.watsonx_model = prev
    elif p == "openai":
        row.openai_model = prev
    elif p == "anthropic":
        row.anthropic_model = prev

    row.previous_model = None  # clear rollback state after use
    row.recommendation_snoozed_until = None

    await db.commit()
    await db.refresh(row)
    logger.info("Model rolled back — provider=%s restored_model=%s", p, prev)
    return _row_to_response(row)


@router.post("/settings/model-recommendation/snooze", response_model=LLMSettingsResponse)
async def snooze_recommendation(db: AsyncSession = Depends(get_db)) -> LLMSettingsResponse:
    """Snooze the recommendation banner for 7 days."""
    row = await _get_or_create_row(db)
    # Store as naive UTC — DB column is TIMESTAMP WITHOUT TIME ZONE
    row.recommendation_snoozed_until = datetime.utcnow() + timedelta(days=7)
    await db.commit()
    await db.refresh(row)
    logger.info("Model recommendation snoozed for 7 days — provider=%s", row.provider)
    return _row_to_response(row)


# ---------------------------------------------------------------------------
# GET /api/settings/local-advisor  (Sub-Task A)
# ---------------------------------------------------------------------------

import asyncio as _asyncio
import platform as _platform

_advisor_cache: dict[str, object] = {}   # simple module-level TTL cache
_ADVISOR_CACHE_TTL = 86_400              # 24 hours in seconds


def _read_ram_gb() -> float:
    """Read total machine RAM in GB.

    Tries /proc/meminfo first (Linux/Docker), then falls back to platform.
    Returns 8.0 as a safe default if neither works.
    """
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    kb = int(line.split()[1])
                    return round(kb / (1024 * 1024), 1)
    except OSError:
        pass
    try:
        import psutil  # type: ignore[import]
        return round(psutil.virtual_memory().total / (1024 ** 3), 1)
    except Exception:  # noqa: BLE001
        pass
    return 8.0


def _read_cpu_info() -> dict[str, str]:
    """Read CPU model and architecture from /proc/cpuinfo or platform."""
    arch = _platform.machine()
    cpu_model = "Unknown"
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if line.lower().startswith("model name"):
                    cpu_model = line.split(":", 1)[1].strip()
                    break
    except OSError:
        cpu_model = _platform.processor() or "Unknown"
    return {"cpu_model": cpu_model, "cpu_arch": arch}


async def _fetch_ollama_tags(base_url: str) -> list[dict]:
    """Fetch installed model list from Ollama /api/tags. Returns [] on any error."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{base_url}/api/tags")
            resp.raise_for_status()
            return resp.json().get("models", [])
    except Exception:  # noqa: BLE001
        return []


@router.get("/settings/local-advisor")
async def get_local_advisor(
    refresh: bool = False,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return hardware info, installed Ollama models, and a ranked recommendation.

    Cached for 24 hours. Pass ?refresh=true to bypass the cache.

    Response shape:
      {
        cpu_model: str, cpu_arch: str, ram_gb: float,
        ollama_reachable: bool,
        installed_models: [{name, size_gb, fits_in_ram, task_fit, recommended}],
        pull_suggestion: {model, label} | null,
        current_model: str | null,
      }
    """
    import time as _time

    row = await _get_or_create_row(db)
    from core.config import settings as cfg
    base_url = row.ollama_base_url or cfg.ollama_base_url
    current_model = row.ollama_model or cfg.ollama_model

    cache_key = base_url
    now = _time.time()
    if not refresh and cache_key in _advisor_cache:
        cached = _advisor_cache[cache_key]  # type: ignore[assignment]
        if now - cached["_ts"] < _ADVISOR_CACHE_TTL:  # type: ignore[index]
            result = dict(cached)
            result.pop("_ts", None)
            result["current_model"] = current_model
            return result

    cpu_info = _read_cpu_info()
    ram_gb = _read_ram_gb()
    installed_raw = await _fetch_ollama_tags(base_url)
    ollama_reachable = len(installed_raw) >= 0  # reachable even if no models installed

    # Re-check: if we got an empty list it could be unreachable OR just no models
    # We do a separate lightweight HEAD/GET to confirm reachability
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            await client.get(f"{base_url}/api/tags")
        ollama_reachable = True
    except Exception:  # noqa: BLE001
        ollama_reachable = False

    ranked = rank_local_models(installed_raw, ram_gb)
    pull = get_pull_suggestion([m.name for m in ranked], ram_gb)

    result = {
        **cpu_info,
        "ram_gb": ram_gb,
        "ollama_reachable": ollama_reachable,
        "installed_models": [
            {
                "name": r.name,
                "size_gb": r.size_gb,
                "fits_in_ram": r.fits_in_ram,
                "task_fit": r.task_fit,
                "recommended": r.recommended,
            }
            for r in ranked
        ],
        "pull_suggestion": pull,
        "current_model": current_model,
    }

    _advisor_cache[cache_key] = {**result, "_ts": now}
    return result


# ---------------------------------------------------------------------------
# POST /api/settings/benchmark-models
# ---------------------------------------------------------------------------

import asyncio as _benchmark_asyncio

# Module-level lock: prevents two benchmark runs from saturating the LLM
# backend simultaneously.  Benchmark runs sequentially by design.
_benchmark_lock = _benchmark_asyncio.Lock()


@router.post("/settings/benchmark-models", response_model=BenchmarkResult)
async def benchmark_models(
    req: BenchmarkRequest,
    db: AsyncSession = Depends(get_db),
) -> BenchmarkResult:
    """Run the fixed 8-case corpus through two models and return a scored comparison.

    Scoring is 50% accuracy + 50% speed (ceiling 30 s per record).
    Both models run fully before the response is returned — expect 30–120 s total
    depending on hardware and model sizes.

    model_a_backend / model_b_backend: "ollama" (default) or "docker_model_runner".
    Setting both to different backends for the same model enables pure runtime
    speed comparisons (e.g. Ollama phi4-mini vs Docker Model Runner phi4-mini).
    """
    if _benchmark_lock.locked():
        from fastapi import HTTPException as _HTTPException
        raise _HTTPException(
            status_code=409,
            detail="A benchmark is already running. Wait for it to complete before starting another.",
        )

    from core.config import settings as cfg
    from services.model_benchmarker import (
        run_benchmark, make_recommendation, CaseResult as _CaseResult,
    )

    row = await _get_or_create_row(db)
    ollama_url = row.ollama_base_url or cfg.ollama_base_url
    # DMR URL will use the saved value once Sub-Task 3.1 adds the column;
    # fall back to the well-known default in the meantime.
    dmr_url: str = getattr(row, "dmr_base_url", None) or "http://host.docker.internal:9545"

    async with _benchmark_lock:
        # Run both models in the thread pool so we don't block the event loop
        loop = _benchmark_asyncio.get_running_loop()

        result_a = await loop.run_in_executor(
            None,
            run_benchmark,
            req.model_a, req.model_a_backend, ollama_url, dmr_url,
        )
        result_b = await loop.run_in_executor(
            None,
            run_benchmark,
            req.model_b, req.model_b_backend, ollama_url, dmr_url,
        )

    winner_key, recommendation = make_recommendation(result_a, result_b)

    def _to_model_result(r) -> ModelResult:
        return ModelResult(
            name=r.name,
            backend=r.backend,
            composite_score=r.composite_score,
            accuracy_pct=r.accuracy_pct,
            speed_score=r.speed_score,
            avg_latency_ms=r.avg_latency_ms,
            reachable=r.reachable,
            cases=[
                BenchmarkCaseResult(
                    case_id=c.case_id,
                    description=c.description,
                    valid_json=c.valid_json,
                    field_results=c.field_results,
                    passed=c.passed,
                    total=c.total,
                    latency_ms=c.latency_ms,
                    error=c.error,
                )
                for c in r.cases
            ],
        )

    return BenchmarkResult(
        model_a=_to_model_result(result_a),
        model_b=_to_model_result(result_b),
        winner=winner_key,
        recommendation=recommendation,
    )


# ---------------------------------------------------------------------------
# GET /api/settings/resolve-gguf
# ---------------------------------------------------------------------------

@router.get("/settings/resolve-gguf")
async def resolve_gguf_endpoint(model: str) -> dict:
    """Query HuggingFace Hub for the best GGUF quantization for a given model name.

    Response shape:
      {
        found: bool,
        hf_repo: str | null,       # e.g. "microsoft/Phi-4-mini-instruct-GGUF"
        gguf_file: str | null,     # e.g. "Phi-4-mini-instruct-Q4_K_M.gguf"
        pull_command: str | null,  # e.g. "docker model pull hf.co/microsoft/..."
        size_gb: float | null,
      }

    Results are cached in-process for 1 hour.
    """
    if not model or not model.strip():
        from fastapi import HTTPException as _HTTPException
        raise _HTTPException(status_code=422, detail="model query parameter is required")

    from core.config import settings as cfg
    return resolve_gguf(model.strip(), hf_token=cfg.hf_token)


# ---------------------------------------------------------------------------
# GET /api/settings/discover-models
# ---------------------------------------------------------------------------

@router.get("/settings/discover-models")
async def get_discover_models(
    refresh: bool = False,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Discover models from the Ollama library and HuggingFace Hub that are not
    yet installed on the local Ollama instance.

    Results are cached for 6 hours. Pass ?refresh=true to bypass the cache.

    Response shape:
      {
        discovered: [{
          name, source, size_gb, fits_in_ram, task_fit,
          description, pull_count, pull_command
        }],
        sources_checked: ["ollama", "huggingface"],
        sources_reachable: {"ollama": bool, "huggingface": bool},
        ram_gb: float,
      }
    """
    from core.config import settings as cfg

    row = await _get_or_create_row(db)
    base_url = row.ollama_base_url or cfg.ollama_base_url

    ram_gb = _read_ram_gb()

    # Fetch installed model names for deduplication
    installed_raw = await _fetch_ollama_tags(base_url)
    installed_names = [m.get("name", "") for m in installed_raw if m.get("name")]

    # Force-clear the cache entry when refresh=True so discover_models() recomputes
    if refresh:
        from services.model_catalog import _discover_cache as _dc
        cache_key = f"discover:{round(ram_gb)}"
        _dc.pop(cache_key, None)

    results, sources_reachable = discover_models(
        installed_names=installed_names,
        ram_gb=ram_gb,
        hf_token=cfg.hf_token,
    )

    installed_model_name = row.ollama_model or cfg.ollama_model
    installed_task_fit = None
    if installed_model_name:
        from services.model_catalog import _score_model_name as _score
        installed_task_fit = _score(installed_model_name)

    return {
        "discovered": [
            {
                "name": r.name,
                "source": r.source,
                "size_gb": r.size_gb,
                "fits_in_ram": r.fits_in_ram,
                "task_fit": r.task_fit,
                "description": r.description,
                "pull_count": r.pull_count,
                "pull_command": r.pull_command,
            }
            for r in results
        ],
        "sources_checked": ["ollama", "huggingface"],
        "sources_reachable": sources_reachable,
        "ram_gb": ram_gb,
        "current_model": installed_model_name,
        "current_task_fit": installed_task_fit,
    }


# ---------------------------------------------------------------------------
# POST /api/settings/pull-model  (Ollama pull with SSE progress stream)
# ---------------------------------------------------------------------------

from fastapi.responses import StreamingResponse as _StreamingResponse
import json as _json


@router.post("/settings/pull-model")
async def pull_model(
    body: dict,
    db: AsyncSession = Depends(get_db),
) -> _StreamingResponse:
    """Stream an Ollama model pull as Server-Sent Events.

    Request body: { "model": "phi4" }

    SSE event stream shape (one JSON object per line, prefixed "data: "):
      data: {"status": "pulling manifest"}
      data: {"status": "downloading", "digest": "sha256:...", "total": 4294967296, "completed": 1073741824}
      data: {"status": "success"}
      data: {"status": "error", "error": "model not found"}

    The stream ends after a {"status": "success"} or {"status": "error"} event.
    """
    from core.config import settings as cfg

    model_name = (body.get("model") or "").strip()
    if not model_name:
        raise HTTPException(status_code=422, detail="model field is required")

    row = await _get_or_create_row(db)
    base_url = row.ollama_base_url or cfg.ollama_base_url

    async def _event_stream():
        try:
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream(
                    "POST",
                    f"{base_url}/api/pull",
                    json={"name": model_name, "stream": True},
                ) as resp:
                    if resp.status_code != 200:
                        payload = _json.dumps({"status": "error", "error": f"Ollama returned HTTP {resp.status_code}"})
                        yield f"data: {payload}\n\n"
                        return
                    async for line in resp.aiter_lines():
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            obj = _json.loads(line)
                        except ValueError:
                            continue
                        yield f"data: {_json.dumps(obj)}\n\n"
                        if obj.get("status") in ("success", "error"):
                            return
        except Exception as exc:  # noqa: BLE001
            payload = _json.dumps({"status": "error", "error": str(exc)})
            yield f"data: {payload}\n\n"

    return _StreamingResponse(
        _event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
