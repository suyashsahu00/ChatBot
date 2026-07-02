"""
Session management endpoints.
Migrated from legacy_app.py L112-138.
"""

import aiosqlite
from fastapi import APIRouter

from app.core.config import settings

router = APIRouter()


@router.get("/sessions")
async def get_sessions():
    """Retrieve list of all chat sessions for the sidebar."""
    async with aiosqlite.connect(settings.database_file) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM sessions ORDER BY created_at DESC"
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


@router.get("/sessions/{session_id}")
async def get_session_messages(session_id: str):
    """Retrieve all messages in a specific session to restore history."""
    async with aiosqlite.connect(settings.database_file) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM messages WHERE session_id = ? ORDER BY id ASC",
            (session_id,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """Delete a session and all its messages."""
    async with aiosqlite.connect(settings.database_file) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        await db.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        await db.commit()
        return {"status": "success"}
