"""
Google Gemini LLM provider implementation.
"""

from app.core.config import settings
from app.services.llm.base import LLMGenerationError


def generate(messages: list[dict]) -> str:
    """Generate completion using Google Gemini fallback."""
    if not settings.google_api_key:
        raise LLMGenerationError("Gemini client not initialized (missing API key).")
        
    try:
        print("OpenAI failed. Attempting Google Gemini fallback...")
        import google.generativeai as genai
        genai.configure(api_key=settings.google_api_key)
        
        # Map OpenAI message roles to Gemini format
        gemini_messages = []
        for msg in messages:
            role = "user" if msg["role"] == "user" else "model"
            if msg["role"] == "system":
                continue
            gemini_messages.append({"role": role, "parts": [msg["content"]]})
            
        model = genai.GenerativeModel(
            "gemini-2.5-flash",
            system_instruction="You are a helpful assistant who gives short, clear answers.",
        )
        response = model.generate_content(gemini_messages)
        content = response.text
        if content is None:
            raise LLMGenerationError("Google Gemini returned empty content.")
        print("Google Gemini fallback generation succeeded!")
        return content
    except Exception as e:
        raise LLMGenerationError(f"Google Gemini Fail: {str(e)}")
