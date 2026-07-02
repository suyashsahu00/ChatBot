import pytest
from unittest.mock import patch
from app.core.config import settings


@patch("app.api.routes.audio.transcribe_audio")
def test_transcribe_success(mock_transcribe, client):
    mock_transcribe.return_value = "hello world transcript"
    settings.openai_api_key = "test-key"

    file_payload = {"file": ("recording.webm", b"mocked-audio-bytes-longer-than-100-bytes-1234567890-1234567890-1234567890-1234567890-1234567890-1234567890-1234567890", "audio/webm")}
    response = client.post("/api/transcribe", files=file_payload)
    
    assert response.status_code == 200
    data = response.json()
    assert "transcript" in data
    assert data["transcript"] == "hello world transcript"


@patch("app.api.routes.audio.transcribe_audio")
def test_transcribe_failure(mock_transcribe, client):
    mock_transcribe.side_effect = Exception("All Transcription APIs failed.")
    settings.openai_api_key = "test-key"

    file_payload = {"file": ("recording.webm", b"mocked-audio-bytes-longer-than-100-bytes-1234567890-1234567890-1234567890-1234567890-1234567890-1234567890-1234567890", "audio/webm")}
    response = client.post("/api/transcribe", files=file_payload)
    
    assert response.status_code == 502
    assert "All Transcription APIs failed." in response.json()["detail"]


def test_transcribe_empty_file(client):
    settings.openai_api_key = "test-key"
    file_payload = {"file": ("recording.webm", b"", "audio/webm")}
    response = client.post("/api/transcribe", files=file_payload)
    
    assert response.status_code == 400
    assert "No speech detected" in response.json()["detail"]


def test_transcribe_missing_keys(client):
    # Temporarily clear keys
    old_dg = settings.deepgram_api_key
    old_oa = settings.openai_api_key
    settings.deepgram_api_key = None
    settings.openai_api_key = None

    try:
        file_payload = {"file": ("recording.webm", b"mocked-audio-bytes", "audio/webm")}
        response = client.post("/api/transcribe", files=file_payload)
        assert response.status_code == 400
        assert "Missing Deepgram or OpenAI API keys" in response.json()["detail"]
    finally:
        settings.deepgram_api_key = old_dg
        settings.openai_api_key = old_oa
