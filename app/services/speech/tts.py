"""
Text-to-Speech (TTS) service.
Manages failover: Murf AI -> OpenAI TTS.
"""

import os
import re
import time
import glob
import requests
from app.core.config import settings

_murf_client = None


def get_murf_client():
    """Lazy initializer for Murf AI client."""
    global _murf_client
    if _murf_client is None and settings.murf_api_key:
        from murf import Murf
        _murf_client = Murf(api_key=settings.murf_api_key)
    return _murf_client


def clean_text_for_tts(text: str) -> str:
    """Prepare text for TTS by removing markdown formatting, code blocks, and dividers."""
    if not text:
        return ""
    # 1. Remove code blocks
    cleaned = re.sub(r'```[\s\S]*?```', '', text)
    # 2. Remove headers
    cleaned = re.sub(r'^#+\s+', '', cleaned, flags=re.MULTILINE)
    # 3. Remove dividers
    cleaned = re.sub(r'^---$', '', cleaned, flags=re.MULTILINE)
    # 4. Remove bold/italics
    cleaned = re.sub(r'\*\*([^*]+)\*\*|__([^_]+)__', r'\1\2', cleaned)
    cleaned = re.sub(r'\*([^*]+)\*|_([^_]+)_', r'\1\2', cleaned)
    # 5. Remove blockquotes
    cleaned = re.sub(r'^>\s+', '', cleaned, flags=re.MULTILINE)
    # 6. Simplify multiple spacing/newlines
    cleaned = re.sub(r'\n+', ' ', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned)
    return cleaned.strip()


def cleanup_old_audio(directory="static/audio", max_age_seconds=600):
    """Periodically remove audio files older than 10 minutes to save disk space."""
    if not os.path.exists(directory):
        return
    now = time.time()
    for file_path in glob.glob(os.path.join(directory, "reply_*.mp3")):
        try:
            if os.path.getmtime(file_path) < now - max_age_seconds:
                os.remove(file_path)
        except Exception as e:
            print(f"Error cleaning up file {file_path}: {e}")


def generate_tts(bot_text: str) -> tuple[str | None, str | None]:
    """
    Generate speech audio file path for text.
    Handles failover from Murf AI to OpenAI TTS.
    Returns (audio_url_path, error_message_if_failed).
    """
    audio_filename = f"reply_{int(time.time() * 1000)}.mp3"
    audio_path = os.path.join("static/audio", audio_filename)
    audio_url_path = f"/static/audio/{audio_filename}"
    audio_success = False
    tts_errors = []

    # Clean text for speech synthesis
    tts_text = clean_text_for_tts(bot_text)
    if not tts_text:
        tts_text = "Here is the code block you requested."

    # 1. Primary: Murf AI (Only if clean text is <= 3000 chars)
    murf = get_murf_client()
    if not audio_success and murf and len(tts_text) <= 3000:
        try:
            print("Attempting speech synthesis with Murf AI...")
            response = murf.text_to_speech.generate(
                text=tts_text,
                voice_id=settings.murf_voice_id,
                format="MP3",
                sample_rate=44100,
            )

            audio_url = getattr(response, "audioFile", None) or getattr(
                response, "audio_file", None
            )
            if not audio_url and isinstance(response, dict):
                audio_url = response.get("audioFile") or response.get("audio_file")

            if not audio_url:
                raise ValueError("No audioFile URL found in Murf response.")

            # Download the synthesized file
            audio_data = requests.get(audio_url)
            audio_data.raise_for_status()
            with open(audio_path, "wb") as f:
                f.write(audio_data.content)

            audio_success = True
            print("Murf AI Speech synthesis succeeded!")
        except Exception as e:
            err_msg = f"Murf AI TTS Fail: {str(e)}"
            print(err_msg)
            tts_errors.append(err_msg)
    else:
        if murf and len(tts_text) > 3000:
            tts_errors.append(
                "Bypassed Murf: Clean text exceeds 3000-character limit."
            )

    # 2. Fallback: OpenAI TTS
    if not audio_success and settings.openai_api_key:
        try:
            print("Murf failed. Attempting OpenAI TTS fallback...")
            from openai import OpenAI as RealOpenAI
            openai_client = RealOpenAI(api_key=settings.openai_api_key)

            response = openai_client.audio.speech.create(
                model="tts-1",
                voice="alloy",
                input=tts_text,
            )

            # Save audio bytes
            response.stream_to_file(audio_path)
            audio_success = True
            print("OpenAI TTS fallback speech synthesis succeeded!")
        except Exception as e:
            err_msg = f"OpenAI TTS Fail: {str(e)}"
            print(err_msg)
            tts_errors.append(err_msg)

    # Set URL to None if both fail
    if not audio_success:
        print(f"All TTS synthesis APIs failed. Errors: {'; '.join(tts_errors)}")
        audio_url_path = None
        error_msg = f"Speech synthesis failed: {'; '.join(tts_errors)}"
    else:
        error_msg = None

    # Clean old files
    cleanup_old_audio()

    return audio_url_path, error_msg
