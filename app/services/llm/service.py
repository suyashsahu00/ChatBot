"""
LLM Orchestrator service.
Manages the failover ordering: OpenRouter -> OpenAI -> Google Gemini.
"""

from app.core.config import settings
from app.services.llm import openrouter, openai_provider, gemini_provider
from app.services.llm.base import LLMGenerationError


def generate_response(messages: list[dict]) -> str:
    """
    Generate chat completion with automatic API failover routing.
    Preserves original sequence:
    1. OpenRouter (Grok-2 or Free model)
    2. OpenAI (gpt-4o-mini)
    3. Google Gemini (gemini-2.5-flash)
    """
    text_errors = []

    # 1. OpenRouter
    if settings.openrouter_api_key:
        try:
            return openrouter.generate(messages)
        except LLMGenerationError as e:
            text_errors.append(str(e))

    # 2. OpenAI
    if settings.openai_api_key:
        try:
            return openai_provider.generate(messages)
        except LLMGenerationError as e:
            text_errors.append(str(e))

    # 3. Google Gemini
    if settings.google_api_key:
        try:
            return gemini_provider.generate(messages)
        except LLMGenerationError as e:
            text_errors.append(str(e))

    # If all fail
    raise LLMGenerationError(
        f"All Text Generation APIs failed. Errors: {'; '.join(text_errors)}"
    )
