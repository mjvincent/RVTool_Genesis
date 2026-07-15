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
from schemas.settings import LLMSettingsResponse, LLMSettingsSave, LLMTestResult, _mask
from services.crypto import decrypt, encrypt
from services.model_catalog import ModelRecommendation, get_recommendation

logger = logging.getLogger(__name__)

router = APIRouter(tags=["settings"])

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TEST_PROMPT = (
    'Return ONLY this JSON, no other text: {"answer": "ok", "provider": "test"}'
)
_WATSONX_IAM_URL = "https://iam.cloud.ibm.com/identity/token"


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
