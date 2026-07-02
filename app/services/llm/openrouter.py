"""
OpenRouter LLM provider implementation.
"""

from openai import OpenAI
from app.core.config import settings
from app.services.llm.base import LLMGenerationError

_client = None


def get_client() -> OpenAI:
    """Lazy initializer for the OpenRouter client."""
    global _client
    if _client is None and settings.openrouter_api_key:
        _client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=settings.openrouter_api_key,
        )
    return _client


def generate(messages: list[dict]) -> str:
    """Generate completion using OpenRouter."""
    client = get_client()
    if not client:
        raise LLMGenerationError("OpenRouter client not initialized (missing API key).")
    
    try:
        print("Attempting text generation with OpenRouter...")
        completion = client.chat.completions.create(
            model=settings.openrouter_model,
            messages=messages,
            extra_headers={
                "HTTP-Referer": "https://github.com/murf-ai/chatbot-web",
                "X-Title": "Python Web Chatbot",
            },
        )
        content = completion.choices[0].message.content
        if content is None:
            raise LLMGenerationError("OpenRouter returned empty content.")
        print("OpenRouter generation succeeded!")
        return content
    except Exception as e:
        raise LLMGenerationError(f"OpenRouter Fail: {str(e)}")
