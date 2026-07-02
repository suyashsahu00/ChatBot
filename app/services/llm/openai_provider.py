"""
OpenAI LLM provider implementation.
"""

from openai import OpenAI as RealOpenAI
from app.core.config import settings
from app.services.llm.base import LLMGenerationError

_client = None


def get_client() -> RealOpenAI:
    """Lazy initializer for the OpenAI client."""
    global _client
    if _client is None and settings.openai_api_key:
        _client = RealOpenAI(api_key=settings.openai_api_key)
    return _client


def generate(messages: list[dict]) -> str:
    """Generate completion using OpenAI fallback."""
    client = get_client()
    if not client:
        raise LLMGenerationError("OpenAI client not initialized (missing API key).")
        
    try:
        print("OpenRouter failed. Attempting OpenAI fallback...")
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
        )
        content = completion.choices[0].message.content
        if content is None:
            raise LLMGenerationError("OpenAI returned empty content.")
        print("OpenAI fallback generation succeeded!")
        return content
    except Exception as e:
        raise LLMGenerationError(f"OpenAI Fail: {str(e)}")
