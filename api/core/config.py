"""Application settings loaded from environment / .env file."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Ollama local LLM — no API key required
    # Containers reach the host Mac's Ollama via host.docker.internal
    ollama_base_url: str = "http://host.docker.internal:11434"
    ollama_model: str = "phi4-mini"

    database_url: str = "postgresql://rvtool:rvtool_password@db:5432/rvtooldb"

    # Encryption key for API keys stored in the DB.
    # Override with a long random string in .env before using cloud LLM providers.
    # The default is intentionally weak — it works out of the box for Ollama-only use.
    secret_key: str = "rvtool-genesis-change-me-in-production"

    # Optional HuggingFace API token — used by the GGUF resolver for higher rate limits.
    # Public models work without it; set HF_TOKEN in .env for private models or heavy use.
    hf_token: str | None = None

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
