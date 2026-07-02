"""
Image vision description and OCR parser.
Manages Gemini Vision -> OpenAI GPT-4o-mini Vision fallback.
"""

import io
import base64
import requests
from PIL import Image
from app.core.config import settings


def parse_image(file_bytes: bytes, filename: str, content_type: str) -> str:
    """
    Analyze image using Google Gemini or OpenAI vision fallback.
    Returns the generated description or text extraction.
    """
    description = None

    # Try Google Gemini Vision
    if not description and settings.google_api_key:
        try:
            print("Using Google Gemini to analyze image...")
            import google.generativeai as genai

            genai.configure(api_key=settings.google_api_key)
            model = genai.GenerativeModel("gemini-2.5-flash")
            image = Image.open(io.BytesIO(file_bytes))
            response = model.generate_content(
                [
                    "Describe this image in detail. Extract any visible text or code exactly as it appears. Provide a structured summary of the visual elements.",
                    image,
                ]
            )
            description = response.text
            print("Gemini image analysis succeeded!")
        except Exception as e:
            print(f"Gemini image analysis failed: {e}")

    # Try OpenAI GPT-4o-mini Vision fallback
    if not description and settings.openai_api_key:
        try:
            print("Using OpenAI GPT-4o-mini to analyze image...")
            base64_image = base64.b64encode(file_bytes).decode("utf-8")
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {settings.openai_api_key}",
            }
            vision_payload = {
                "model": "gpt-4o-mini",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "Describe this image in detail. Extract any visible text or code exactly as it appears. Provide a structured summary of the visual elements.",
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{content_type or 'image/jpeg'};base64,{base64_image}"
                                },
                            },
                        ],
                    }
                ],
            }
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=vision_payload,
            )
            if response.ok:
                description = response.json()["choices"][0]["message"]["content"]
                print("OpenAI image analysis succeeded!")
            else:
                print(
                    f"OpenAI image analysis status {response.status_code}: {response.text}"
                )
        except Exception as e:
            print(f"OpenAI image analysis failed: {e}")

    if description:
        return description
    else:
        try:
            img = Image.open(io.BytesIO(file_bytes))
            return (
                f"[Image Attached: {filename} ({img.width}x{img.height}px, "
                f"format: {img.format}). No active vision API keys were able "
                f"to process description.]"
            )
        except Exception:
            return f"[Image Attached: {filename}. Vision processing unavailable.]"
