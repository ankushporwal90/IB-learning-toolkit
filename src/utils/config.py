"""Configuration loading for the AI SEC Filing Analyzer."""

from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Environment variables used by the application."""

    groq_api_key: str = ""
    groq_model: str = "llama-3.1-8b-instant"
    app_env: str = "development"
    log_level: str = "INFO"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


def get_settings() -> Settings:
    """Load local `.env` values and return typed settings."""

    load_dotenv(PROJECT_ROOT / ".env")
    return Settings()
