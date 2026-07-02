import pytest
import aiosqlite
from app.core.config import settings


@pytest.mark.asyncio
async def test_sessions_crud(client):
    # 1. Verify GET /api/sessions initially returns empty list
    response = client.get("/api/sessions")
    assert response.status_code == 200
    assert response.json() == []

    # 2. Insert dummy session and messages directly to test database
    async with aiosqlite.connect(settings.database_file) as db:
        await db.execute(
            "INSERT INTO sessions (id, title) VALUES (?, ?)",
            ("session-test-1", "Test Session Title")
        )
        await db.execute(
            "INSERT INTO messages (session_id, role, content, audio_url) VALUES (?, ?, ?, ?)",
            ("session-test-1", "user", "Hello there", None)
        )
        await db.execute(
            "INSERT INTO messages (session_id, role, content, audio_url) VALUES (?, ?, ?, ?)",
            ("session-test-1", "assistant", "General Kenobi", "/static/audio/reply_test.mp3")
        )
        await db.commit()

    # 3. Verify GET /api/sessions returns the inserted session
    response = client.get("/api/sessions")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == "session-test-1"
    assert data[0]["title"] == "Test Session Title"

    # 4. Verify GET /api/sessions/{session_id} returns both messages
    response = client.get("/api/sessions/session-test-1")
    assert response.status_code == 200
    msgs = response.json()
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"
    assert msgs[0]["content"] == "Hello there"
    assert msgs[1]["role"] == "assistant"
    assert msgs[1]["content"] == "General Kenobi"
    assert msgs[1]["audio_url"] == "/static/audio/reply_test.mp3"

    # 5. Delete session via DELETE /api/sessions/{session_id}
    response = client.delete("/api/sessions/session-test-1")
    assert response.status_code == 200
    assert response.json() == {"status": "success"}

    # 6. Verify session is deleted in sessions list
    response = client.get("/api/sessions")
    assert len(response.json()) == 0

    # 7. Verify messages are also deleted due to CASCADE delete
    async with aiosqlite.connect(settings.database_file) as db:
        async with db.execute(
            "SELECT count(*) FROM messages WHERE session_id = ?",
            ("session-test-1",)
        ) as cursor:
            count = (await cursor.fetchone())[0]
            assert count == 0
