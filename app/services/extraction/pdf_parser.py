"""
PDF Document parser.
Extracts embedded text. Falls back to extracting page images and running OCR (via Gemini / OpenAI)
for pages that are empty/scanned.
"""

import io
import base64
import requests
import pypdf
from PIL import Image
from app.core.config import settings


def parse_pdf(file_bytes: bytes) -> str:
    """
    Extract text from PDF pages.
    Performs OCR fallback on any pages that yield empty text.
    """
    pdf_reader = pypdf.PdfReader(io.BytesIO(file_bytes))
    text_parts = []
    
    for i, page in enumerate(pdf_reader.pages):
        page_text = page.extract_text()
        if page_text and page_text.strip():
            text_parts.append(f"--- Page {i+1} ---\n{page_text}")
        else:
            print(f"No text extracted on page {i+1}. Checking for page images...")
            page_images_text = []
            try:
                images_list = list(page.images)
                if images_list:
                    for img_idx, image_file_object in enumerate(images_list):
                        print(f"Extracting image {img_idx+1} from page {i+1}...")
                        img_bytes = image_file_object.data

                        # Resolve PIL Image
                        try:
                            image = image_file_object.image
                        except Exception:
                            image = Image.open(io.BytesIO(img_bytes))

                        # OCR via Gemini
                        img_desc = None
                        if settings.google_api_key:
                            try:
                                import google.generativeai as genai

                                genai.configure(api_key=settings.google_api_key)
                                model = genai.GenerativeModel("gemini-2.5-flash")
                                response = model.generate_content(
                                    [
                                        "Perform OCR on this image. Extract and transcribe all visible text exactly as it appears. If it is an image, describe it briefly.",
                                        image,
                                    ]
                                )
                                img_desc = response.text
                            except Exception as e:
                                print(f"Gemini page image OCR failed: {e}")

                        # OCR via OpenAI fallback
                        if not img_desc and settings.openai_api_key:
                            try:
                                base64_image = base64.b64encode(img_bytes).decode("utf-8")
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
                                                    "text": "Extract and transcribe all text from this image.",
                                                },
                                                {
                                                    "type": "image_url",
                                                    "image_url": {
                                                        "url": f"data:image/jpeg;base64,{base64_image}"
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
                                    img_desc = response.json()["choices"][0]["message"]["content"]
                            except Exception as e:
                                print(f"OpenAI page image OCR failed: {e}")

                        if img_desc:
                            page_images_text.append(img_desc)

                if page_images_text:
                    text_parts.append(
                        f"--- Page {i+1} (OCR/Vision Extracted) ---\n"
                        + "\n".join(page_images_text)
                    )
                else:
                    text_parts.append(
                        f"--- Page {i+1} ---\n[Scanned/Empty Page - No text or images extracted]"
                    )
            except Exception as page_err:
                print(f"Failed to extract page {i+1} image content: {page_err}")
                text_parts.append(
                    f"--- Page {i+1} ---\n[Scanned Page - Failed to parse images: {str(page_err)}]"
                )

    extracted_text = "\n\n".join(text_parts)
    if not extracted_text.strip():
        extracted_text = "[No readable text or images found in PDF.]"
        
    return extracted_text
