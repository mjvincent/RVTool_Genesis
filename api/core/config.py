"""Application settings loaded from environment / .env file."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Ollama local LLM — no API key required
    # Containers reach the host Mac's Ollama via host.docker.internal
    ollama_base_url: str = "http://host.docker.internal:11434"
    ollama_model: str = "phi4-mini"

    database_url: str = "postgresql://rvtool:rvtool_password@db:5432/rvtooldb"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
