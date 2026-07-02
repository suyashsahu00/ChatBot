"""
Chat endpoint with LLM failover and TTS synthesis.
Orchestrated via services.
"""

import aiosqlite
from fastapi import APIRouter, HTTPException

from app.core.config import settings
from app.schemas.chat import ChatPayload
from app.services.llm.service import generate_response
from app.services.llm.base import LLMGenerationError
from app.services.speech.tts import generate_tts

router = APIRouter()


@router.post("/chat")
async def chat_endpoint(payload: ChatPayload):
    # Ensure there's a session in the DB
    async with aiosqlite.connect(settings.database_file) as db:
        async with db.execute(
            "SELECT id FROM sessions WHERE id = ?", (payload.session_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                # Deduce title from first user message
                user_msg = next(
                    (msg.content for msg in payload.messages if msg.role == "user"),
                    "New Chat",
                )
                title = user_msg[:35] + ("..." if len(user_msg) > 35 else "")
                await db.execute(
                    "INSERT INTO sessions (id, title) VALUES (?, ?)",
                    (payload.session_id, title),
                )
                await db.commit()

    # Format messages for standard chat completion
    formatted_messages = [
        {"role": msg.role, "content": msg.content} for msg in payload.messages
    ]

    # --- TEXT GENERATION ORCHESTRATION ---
    try:
        bot_text = generate_response(formatted_messages)
    except LLMGenerationError as e:
        raise HTTPException(status_code=502, detail=str(e))

    # --- SPEECH SYNTHESIS ORCHESTRATION ---
    audio_url_path, error_msg = generate_tts(bot_text)

    # --- DATABASE STORAGE ---
    async with aiosqlite.connect(settings.database_file) as db:
        # Save User prompt
        last_user_msg = payload.messages[-1]
        await db.execute(
            "INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)",
            (payload.session_id, last_user_msg.role, last_user_msg.content),
        )
        # Save Bot reply
        await db.execute(
            "INSERT INTO messages (session_id, role, content, audio_url) VALUES (?, ?, ?, ?)",
            (payload.session_id, "assistant", bot_text, audio_url_path),
        )
        await db.commit()

    return {
        "text": bot_text,
        "audio_url": audio_url_path,
        "error": error_msg,
    }
