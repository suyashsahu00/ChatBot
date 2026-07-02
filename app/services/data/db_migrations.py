"""
Database schema migrations pipeline using SQLite PRAGMA user_version.
Ensures schema versioning progresses sequentially (v0 -> v1 -> v2).
"""

import logging
import aiosqlite

logger = logging.getLogger(__name__)
LATEST_SCHEMA_VERSION = 2


async def get_user_version(db: aiosqlite.Connection) -> int:
    """Read the current schema version from SQLite user_version header."""
    async with db.execute("PRAGMA user_version") as cursor:
        row = await cursor.fetchone()
        return row[0] if row else 0


async def set_user_version(db: aiosqlite.Connection, version: int) -> None:
    """Set the schema version in SQLite user_version header."""
    await db.execute(f"PRAGMA user_version = {version}")


async def migrate_to_v1(db: aiosqlite.Connection) -> None:
    """Migrate database to Version 1 (Base tables setup)."""
    logger.info("Running database migration to version 1 (base tables)...")
    await db.execute("BEGIN")
    
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
    await db.execute("""
        CREATE TABLE IF NOT EXISTS attachments (
            id TEXT PRIMARY KEY,
            session_id TEXT,
            original_filename TEXT NOT NULL,
            content_type TEXT NOT NULL,
            size_bytes INTEGER NOT NULL,
            storage_path TEXT NOT NULL,
            uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS attachment_extractions (
            id TEXT PRIMARY KEY,
            attachment_id TEXT NOT NULL,
            extraction_source TEXT NOT NULL,
            status TEXT NOT NULL,
            error_message TEXT,
            extracted_text TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (attachment_id) REFERENCES attachments(id) ON DELETE CASCADE
        )
    """)
    
    await set_user_version(db, 1)
    await db.execute("COMMIT")
    logger.info("Successfully migrated database to version 1.")


async def migrate_to_v2(db: aiosqlite.Connection) -> None:
    """Migrate database to Version 2 (Add extraction quality metrics columns)."""
    logger.info("Running database migration to version 2 (extraction quality metadata)...")
    await db.execute("BEGIN")

    # Add columns to attachment_extractions if they are missing
    async with db.execute("PRAGMA table_info(attachment_extractions)") as cursor:
        cols = await cursor.fetchall()
        existing = {c[1] for c in cols}

    for name, col_def in [
        ("error_code", "TEXT"),
        ("extracted_char_count", "INTEGER DEFAULT 0"),
        ("extraction_confidence", "REAL"),
        ("normalization_applied", "INTEGER DEFAULT 0"),
    ]:
        if name not in existing:
            await db.execute(f"ALTER TABLE attachment_extractions ADD COLUMN {name} {col_def}")

    await set_user_version(db, 2)
    await db.execute("COMMIT")
    logger.info("Successfully migrated database to version 2.")


async def run_migrations(db: aiosqlite.Connection) -> None:
    """Run migrations sequentially up to the latest supported version."""
    current = await get_user_version(db)
    
    if current > LATEST_SCHEMA_VERSION:
        raise RuntimeError(
            f"Database schema version ({current}) is newer than the application version ({LATEST_SCHEMA_VERSION})."
        )
        
    if current < 1:
        await migrate_to_v1(db)
        current = 1
        
    if current < 2:
        await migrate_to_v2(db)
