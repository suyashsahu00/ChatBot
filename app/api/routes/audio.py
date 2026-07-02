"""
Audio transcription endpoint (Speech-to-Text).
Orchestrated via services.
"""

from fastapi import APIRouter, HTTPException, UploadFile, File

from app.core.config import settings
from app.services.speech.stt import transcribe_audio

router = APIRouter()


@router.post("/transcribe")
async def transcribe_endpoint(file: UploadFile = File(...)):
    # Ensure at least one key is present
    if not settings.deepgram_api_key and not settings.openai_api_key:
        raise HTTPException(
            status_code=400,
            detail="Missing Deepgram or OpenAI API keys for transcription.",
        )

    try:
        audio_bytes = await file.read()
        print(
            f"Received audio recording: {len(audio_bytes)} bytes, "
            f"content_type: {file.content_type}"
        )

        # Save audio backup for troubleshooting
        backup_path = "static/audio/last_recording.webm"
        with open(backup_path, "wb") as f_backup:
            f_backup.write(audio_bytes)
        print(f"Saved last recording to {backup_path}")

        if not audio_bytes or len(audio_bytes) < 100:
            raise HTTPException(
                status_code=400,
                detail="No speech detected (audio recording is too short or empty).",
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=400, detail=f"Failed to read audio file: {str(e)}"
        )

    try:
        transcript_text = transcribe_audio(audio_bytes, file.content_type)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))

    return {"transcript": transcript_text}
