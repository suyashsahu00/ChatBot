import pytest
from unittest.mock import patch, MagicMock
from app.core.config import settings
from app.services.llm.base import LLMGenerationError
from app.services.llm.service import generate_response
from app.services.speech.tts import generate_tts
from app.services.speech.stt import transcribe_audio


# ===========================================================================
# LLM Failover Tests
# ===========================================================================

@patch("app.services.llm.openrouter.generate")
@patch("app.services.llm.openai_provider.generate")
@patch("app.services.llm.gemini_provider.generate")
def test_llm_failover_openrouter_to_openai(mock_gemini, mock_openai, mock_openrouter):
    settings.openrouter_api_key = "key1"
    settings.openai_api_key = "key2"
    settings.google_api_key = "key3"

    # OpenRouter fails, OpenAI succeeds
    mock_openrouter.side_effect = LLMGenerationError("OpenRouter failed")
    mock_openai.return_value = "OpenAI response"

    response = generate_response([{"role": "user", "content": "hello"}])
    assert response == "OpenAI response"
    mock_openrouter.assert_called_once()
    mock_openai.assert_called_once()
    mock_gemini.assert_not_called()


@patch("app.services.llm.openrouter.generate")
@patch("app.services.llm.openai_provider.generate")
@patch("app.services.llm.gemini_provider.generate")
def test_llm_failover_openai_to_gemini(mock_gemini, mock_openai, mock_openrouter):
    settings.openrouter_api_key = "key1"
    settings.openai_api_key = "key2"
    settings.google_api_key = "key3"

    # OpenRouter and OpenAI fail, Gemini succeeds
    mock_openrouter.side_effect = LLMGenerationError("OpenRouter failed")
    mock_openai.side_effect = LLMGenerationError("OpenAI failed")
    mock_gemini.return_value = "Gemini response"

    response = generate_response([{"role": "user", "content": "hello"}])
    assert response == "Gemini response"
    mock_openrouter.assert_called_once()
    mock_openai.assert_called_once()
    mock_gemini.assert_called_once()


# ===========================================================================
# TTS Failover Tests
# ===========================================================================

@patch("app.services.speech.tts.get_murf_client")
@patch("openai.resources.audio.speech.Speech.create")
def test_tts_failover_murf_to_openai(mock_openai_tts, mock_get_murf):
    settings.murf_api_key = "murf-key"
    settings.openai_api_key = "openai-key"

    # Murf fails by returning empty or throwing
    mock_murf = MagicMock()
    mock_get_murf.return_value = mock_murf
    mock_murf.text_to_speech.generate.side_effect = Exception("Murf synthesis error")

    # Mock OpenAI TTS response
    mock_openai_response = MagicMock()
    mock_openai_tts.return_value = mock_openai_response

    # Generate TTS
    with patch("builtins.open", MagicMock()):
        url, error = generate_tts("Testing TTS fallback")

    # Assert fallback succeeded
    assert url is not None
    assert "reply_" in url
    assert error is None
    mock_openai_tts.assert_called_once()


# ===========================================================================
# STT Failover Tests
# ===========================================================================

@patch("requests.post")
@patch("openai.resources.audio.transcriptions.Transcriptions.create")
def test_stt_failover_deepgram_to_whisper(mock_whisper, mock_post):
    settings.deepgram_api_key = "dg-key"
    settings.openai_api_key = "openai-key"

    # Mock Deepgram REST endpoint returning failure status
    mock_dg_response = MagicMock()
    mock_dg_response.ok = False
    mock_dg_response.status_code = 500
    mock_dg_response.text = "Internal Server Error"
    mock_post.return_value = mock_dg_response

    # Mock Whisper SDK success response
    mock_whisper_result = MagicMock()
    mock_whisper_result.text = "Whisper transcription result"
    mock_whisper.return_value = mock_whisper_result

    # Call STT service
    with patch("builtins.open", MagicMock()):
        with patch("os.remove", MagicMock()):
            transcript = transcribe_audio(b"audio-data-mock-bytes", "audio/webm")

    assert transcript == "Whisper transcription result"
    mock_whisper.assert_called_once()
