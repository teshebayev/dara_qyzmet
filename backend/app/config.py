"""Конфигурация через переменные окружения (.env)."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Dara Kyzmet API"
    port: int = 8000

    # --- Database ---
    database_url: str = "postgresql+psycopg://postgres:postgres@db:5432/dara"

    # --- Auth ---
    jwt_secret: str = "change-me-in-prod"
    jwt_algorithm: str = "HS256"
    access_token_ttl_min: int = 720  # 12 часов

    # --- VLM / LLM (OpenAI-совместимый, напр. vLLM с Qwen2.5-VL) ---
    # mock_vlm=true -> сервис работает без GPU/модели (детерминированная заглушка),
    # удобно поднять весь проект одной командой на ноутбуке.
    mock_vlm: bool = True
    openai_base_url: str = "http://vllm:8000/v1"
    openai_api_key: str = "EMPTY"
    vlm_model: str = "qwen"          # = served-model-name в vLLM
    llm_model: str = "qwen"          # для агента (может быть текстовой моделью)
    request_timeout: float = 120.0

    # --- Seed demo-данных при старте ---
    seed_demo: bool = True


settings = Settings()
