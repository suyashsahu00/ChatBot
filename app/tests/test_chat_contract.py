import pytest
import aiosqlite
from unittest.mock import patch
from app.core.config import settings
from app.services.llm.base import LLMGenerationError


@patch("app.api.routes.chat.generate_response")
@patch("app.api.routes.chat.generate_tts")
def test_chat_successful_response(mock_tts, mock_llm, client):
    # Mock services
    mock_llm.return_value = "Mocked bot text"
    mock_tts.return_value = ("/static/audio/reply_test.mp3", None)

    session_id = "test-session-chat-contract"
    payload = {
        "session_id": session_id,
        "messages": [
            {"role": "user", "content": "Hello bot"}
        ]
    }

    # Call endpoint
    response = client.post("/api/chat", json=payload)
    assert response.status_code == 200
    
    # Verify response schema contract
    data = response.json()
    assert "text" in data
    assert "audio_url" in data
    assert "error" in data
    assert data["text"] == "Mocked bot text"
    assert data["audio_url"] == "/static/audio/reply_test.mp3"
    assert data["error"] is None

    # Verify DB writes
    async def verify_db():
        async with aiosqlite.connect(settings.database_file) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM messages WHERE session_id = ? ORDER BY id ASC",
                (session_id,)
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
                
    import asyncio
    db_rows = asyncio.run(verify_db())
    assert len(db_rows) == 2
    assert db_rows[0]["role"] == "user"
    assert db_rows[0]["content"] == "Hello bot"
    assert db_rows[1]["role"] == "assistant"
    assert db_rows[1]["content"] == "Mocked bot text"
    assert db_rows[1]["audio_url"] == "/static/audio/reply_test.mp3"


@patch("app.api.routes.chat.generate_response")
def test_chat_llm_failure(mock_llm, client):
    # Mock LLM failover raising LLMGenerationError
    mock_llm.side_effect = LLMGenerationError("All APIs failed testing")

    payload = {
        "session_id": "test-session-chat-fail",
        "messages": [
            {"role": "user", "content": "Trigger failure"}
        ]
    }

    response = client.post("/api/chat", json=payload)
    assert response.status_code == 502
    assert response.json()["detail"] == "All APIs failed testing"


def test_chat_validation_error(client):
    # Sending missing payload values to test Pydantic validation
    payload = {
        "messages": []
    }
    response = client.post("/api/chat", json=payload)
    assert response.status_code == 422
