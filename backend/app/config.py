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
    openai_base_url: str = "http://vllm:8000/v1"
    openai_api_key: str = "EMPTY"
    vlm_model: str = "qwen"          # = served-model-name в vLLM
    llm_model: str = "qwen"          # для агента (может быть текстовой моделью)
    request_timeout: float = 120.0

    # --- Seed demo-данных при старте ---
    seed_demo: bool = True

    # --- Qdrant (поиск товара по каталогу: текст и фото в общем CLIP-пространстве) ---
    qdrant_url: str = "http://qdrant:6333"
    qdrant_collection: str = "products"
    # CLIP ViT-B/32 через fastembed (ONNX/CPU): текст и изображение в одном 512-мерном
    # пространстве, поэтому фото-запрос матчится с проиндексированными названиями товаров.
    embed_text_model: str = "Qdrant/clip-ViT-B-32-text"
    embed_image_model: str = "Qdrant/clip-ViT-B-32-vision"
    embed_dim: int = 512
    # Best-effort индексация каталога в Qdrant при старте (после seed).
    index_catalog_on_start: bool = True


settings = Settings()
