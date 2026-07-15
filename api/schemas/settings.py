"""Pydantic v2 schemas for LLM provider settings.

API keys are NEVER returned in plaintext.  The response includes only a
masked hint (last 4 chars) so the UI can show whether a key is saved.
"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


ProviderLiteral = Literal["ollama", "watsonx", "openai", "anthropic"]


def _mask(value: str | None) -> str | None:
    """Return '••••••••<last4>' for a non-empty secret, else None."""
    if not value:
        return None
    visible = value[-4:] if len(value) >= 4 else value
    return f"••••••••{visible}"


class LLMSettingsSave(BaseModel):
    """Payload accepted by POST /api/settings."""
    provider: ProviderLiteral = "ollama"

    # Ollama
    ollama_base_url: str | None = None
    ollama_model: str | None = None

    # watsonx.ai  — raw plaintext key from the UI (will be encrypted before storage)
    watsonx_api_key: str | None = None
    watsonx_project_id: str | None = None
    watsonx_url: str | None = None
    watsonx_model: str | None = None

    # OpenAI-compatible
    openai_api_key: str | None = None
    openai_base_url: str | None = None
    openai_model: str | None = None

    # Anthropic
    anthropic_api_key: str | None = None
    anthropic_model: str | None = None


class LLMSettingsResponse(BaseModel):
    """Payload returned by GET /api/settings — keys are masked."""
    provider: ProviderLiteral

    # Ollama
    ollama_base_url: str | None
    ollama_model: str | None

    # watsonx.ai
    watsonx_api_key_hint: str | None       # masked, e.g. "••••••••abcd"
    watsonx_project_id: str | None
    watsonx_url: str | None
    watsonx_model: str | None

    # OpenAI-compatible
    openai_api_key_hint: str | None
    openai_base_url: str | None
    openai_model: str | None

    # Anthropic
    anthropic_api_key_hint: str | None
    anthropic_model: str | None

    # Model recommendation rollback
    previous_model: str | None = None

    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LLMTestResult(BaseModel):
    ok: bool
    provider: str
    latency_ms: int | None = None
    preview: str | None = None      # first 120 chars of model response
    error: str | None = None
