"""
FastAPI application factory.
Creates the app, registers routers, and mounts static files.
Migrated from legacy_app.py L52-82, L614-619.
"""

import os
from contextlib import asynccontextmanager

import aiosqlite
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.core.config import settings
from app.api.routes import chat, uploads, audio, sessions, health


# ---------------------------------------------------------------------------
# Lifespan: database initialization (from legacy_app.py L52-76)
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize the SQLite database and create schemas on startup."""
    async with aiosqlite.connect(settings.database_file) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                audio_url TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
            )
        """)
        await db.commit()
    yield


# ---------------------------------------------------------------------------
# Create directories for caching audio files (from legacy_app.py L78-80)
# ---------------------------------------------------------------------------

os.makedirs("static", exist_ok=True)
os.makedirs("static/audio", exist_ok=True)


# ---------------------------------------------------------------------------
# App creation and router registration
# ---------------------------------------------------------------------------

app = FastAPI(title="Grok & Murf AI Voice Assistant", lifespan=lifespan)

# Register API routers — all prefixed under /api
app.include_router(health.router,    prefix="/api", tags=["health"])
app.include_router(sessions.router,  prefix="/api", tags=["sessions"])
app.include_router(chat.router,      prefix="/api", tags=["chat"])
app.include_router(uploads.router,   prefix="/api", tags=["uploads"])
app.include_router(audio.router,     prefix="/api", tags=["audio"])

# Serve static assets (from legacy_app.py L614-615)
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def get_index():
    """Serve the frontend SPA."""
    return FileResponse("static/index.html")
