"""
Embeddings generation wrapper supporting OpenAI and Google Gemini API providers.
Implemented with raw async HTTPX requests for lightweight dependencies.
"""

import httpx
from app.core.config import settings

TIMEOUT_SECONDS = 10.0


def get_model_name() -> str:
    """Return the name of the active embedding model."""
    if settings.embedding_provider == "openai":
        return settings.openai_embedding_model
    return settings.google_embedding_model


async def get_embedding(text: str) -> list[float]:
    """
    Generate an embedding vector for the given text.
    Uses the configured provider (openai or google) and API keys.
    """
    if settings.embedding_provider == "openai":
        if not settings.openai_api_key:
            raise ValueError("OpenAI API key is missing for embeddings generation.")
            
        headers = {
            "Authorization": f"Bearer {settings.openai_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": settings.openai_embedding_model,
            "input": text,
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.openai.com/v1/embeddings",
                headers=headers,
                json=payload,
                timeout=TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            data = response.json()
            return data["data"][0]["embedding"]
            
    elif settings.embedding_provider == "google":
        if not settings.google_api_key:
            raise ValueError("Google API key is missing for embeddings generation.")
            
        payload = {
            "content": {
                "parts": [{"text": text}]
            }
        }
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{settings.google_embedding_model}:embedContent?key={settings.google_api_key}"
        )
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                json=payload,
                timeout=TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            data = response.json()
            return data["embedding"]["values"]
            
    else:
        raise ValueError(f"Unsupported embedding provider: {settings.embedding_provider}")
