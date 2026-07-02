"""
Centralized configuration using Pydantic Settings.
Loads all environment variables from .env file.
Replaces the scattered os.getenv() calls in legacy_app.py L37-50.
"""

from pydantic import field_validator
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    # OpenRouter
    openrouter_api_key: Optional[str] = None
    openrouter_model: str = "openrouter/free"

    # Murf AI
    murf_api_key: Optional[str] = None
    murf_voice_id: str = "en-US-natalie"

    # OpenAI
    openai_api_key: Optional[str] = None

    # Google Gemini
    google_api_key: Optional[str] = None

    # Deepgram
    deepgram_api_key: Optional[str] = None

    # Database
    database_file: str = "chatbot.db"

    # Server
    port: int = 8000

    # Uploads Hardening & Retention
    max_upload_bytes: int = 5 * 1024 * 1024  # Default: 5MB
    attachment_retention_days: int = 30  # Default: 30 days

    # Embeddings Configuration
    embedding_provider: str = "openai"  # openai or google
    openai_embedding_model: str = "text-embedding-3-small"
    google_embedding_model: str = "models/embedding-001"

    # RAG Observability & Answering Configuration
    enable_grounding: bool = True
    rag_top_k: int = 3
    rag_score_threshold: float = 0.35
    enable_debug_routes: bool = False

    @field_validator(
        "openrouter_api_key",
        "murf_api_key",
        "openai_api_key",
        "google_api_key",
        "deepgram_api_key",
        mode="before",
    )
    @classmethod
    def strip_and_nullify(cls, v):
        """Strip whitespace and convert empty strings to None.
        Replicates the original: os.getenv(..., "").strip() or None
        """
        if isinstance(v, str):
            v = v.strip()
            return v if v else None
        return v

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


# Singleton instance — import this everywhere
settings = Settings()
