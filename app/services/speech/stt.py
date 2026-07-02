"""
Speech-to-Text (STT) transcription service.
Manages failover: Deepgram Nova-2 -> OpenAI Whisper.
"""

import os
import time
import requests
from app.core.config import settings


def transcribe_audio(audio_bytes: bytes, content_type: str) -> str:
    """
    Transcribe raw audio bytes into text.
    Handles failover from Deepgram REST API to OpenAI Whisper API.
    """
    transcript_text = ""
    transcribe_success = False
    errors = []

    # 1. Primary: Deepgram Nova-2
    if settings.deepgram_api_key:
        try:
            print("Attempting transcription with Deepgram...")
            # Clean content-type (e.g., audio/webm;codecs=opus -> audio/webm)
            clean_content_type = content_type or "audio/webm"
            if ";" in clean_content_type:
                clean_content_type = clean_content_type.split(";")[0].strip()

            # Deepgram REST API
            url = "https://api.deepgram.com/v1/listen?smart_format=true&model=nova-2"
            headers = {
                "Authorization": f"Token {settings.deepgram_api_key}",
                "Content-Type": clean_content_type,
            }
            response = requests.post(url, headers=headers, data=audio_bytes)
            if response.ok:
                res_data = response.json()
                transcript_text = res_data["results"]["channels"][0]["alternatives"][
                    0
                ]["transcript"]
                transcribe_success = True
                print(f"Deepgram transcription succeeded! Result: '{transcript_text}'")
            else:
                errors.append(
                    f"Deepgram status {response.status_code}: {response.text}"
                )
        except Exception as e:
            errors.append(f"Deepgram failed: {str(e)}")

    # 2. Fallback: OpenAI Whisper
    temp_filename = ""
    if not transcribe_success and settings.openai_api_key:
        try:
            print(
                "Deepgram failed. Attempting OpenAI Whisper transcription fallback..."
            )
            temp_filename = f"temp_transcribe_{int(time.time() * 1000)}.webm"
            with open(temp_filename, "wb") as temp_file:
                temp_file.write(audio_bytes)

            from openai import OpenAI as RealOpenAI
            openai_client = RealOpenAI(api_key=settings.openai_api_key)
            with open(temp_filename, "rb") as audio_file:
                result = openai_client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                )
                transcript_text = result.text

            os.remove(temp_filename)
            transcribe_success = True
            print(
                f"OpenAI Whisper transcription succeeded! Result: '{transcript_text}'"
            )
        except Exception as e:
            errors.append(f"OpenAI Whisper failed: {str(e)}")
            if temp_filename and os.path.exists(temp_filename):
                os.remove(temp_filename)

    if not transcribe_success:
        raise Exception(
            f"All Transcription APIs failed. Errors: {'; '.join(errors)}"
        )

    return transcript_text
