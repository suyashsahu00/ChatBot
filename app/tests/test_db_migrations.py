import os
import pytest
import aiosqlite
from app.services.data.db_migrations import run_migrations, get_user_version, LATEST_SCHEMA_VERSION


@pytest.mark.asyncio
async def test_user_version_initial_zero_goes_to_latest():
    db_file = "test_mig_zero.db"
    if os.path.exists(db_file):
        os.remove(db_file)
        
    try:
        # Run migrations on blank DB
        async with aiosqlite.connect(db_file) as db:
            await run_migrations(db)
            
            # Assert user_version is updated to latest (3)
            version = await get_user_version(db)
            assert version == LATEST_SCHEMA_VERSION
            assert version == 3
            
            # Verify core tables exist
            async with db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('sessions', 'messages', 'attachments', 'attachment_extractions', 'attachment_chunks')"
            ) as cursor:
                tables = {row[0] for row in await cursor.fetchall()}
                assert len(tables) == 5
                
            # Verify indexes exist on attachment_chunks
            async with db.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name IN ('idx_chunks_attachment_id', 'idx_chunks_extraction_id', 'idx_chunks_chunk_index')"
            ) as cursor:
                indexes = {row[0] for row in await cursor.fetchall()}
                assert len(indexes) == 3
    finally:
        if os.path.exists(db_file):
            os.remove(db_file)


@pytest.mark.asyncio
async def test_v1_to_v2_adds_metadata_columns_only_once():
    db_file = "test_mig_v1_v2.db"
    if os.path.exists(db_file):
        os.remove(db_file)

    try:
        # 1. Setup v1 basic schema manually
        async with aiosqlite.connect(db_file) as db:
            await db.execute("""
                CREATE TABLE attachment_extractions (
                    id TEXT PRIMARY KEY,
                    attachment_id TEXT NOT NULL,
                    extraction_source TEXT NOT NULL,
                    status TEXT NOT NULL,
                    error_message TEXT,
                    extracted_text TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await db.execute("PRAGMA user_version = 1")
            await db.commit()
            
            # Verify user_version is 1 initially
            assert await get_user_version(db) == 1

        # 2. Run migrations
        async with aiosqlite.connect(db_file) as db:
            await run_migrations(db)
            
            # Assert user_version is upgraded to LATEST (3)
            assert await get_user_version(db) == LATEST_SCHEMA_VERSION
            
            # Verify columns have been successfully added
            async with db.execute("PRAGMA table_info(attachment_extractions)") as cursor:
                cols_after = {row[1] for row in await cursor.fetchall()}
                assert "error_code" in cols_after
                assert "extracted_char_count" in cols_after

        # 3. Re-run migrations and check for idempotency
        async with aiosqlite.connect(db_file) as db:
            await run_migrations(db)
            assert await get_user_version(db) == LATEST_SCHEMA_VERSION
    finally:
        if os.path.exists(db_file):
            os.remove(db_file)


@pytest.mark.asyncio
async def test_v2_to_v3_upgrade_path():
    db_file = "test_mig_v2_v3.db"
    if os.path.exists(db_file):
        os.remove(db_file)

    try:
        # 1. Setup v2 basic schema manually
        async with aiosqlite.connect(db_file) as db:
            await db.execute("""
                CREATE TABLE attachments (
                    id TEXT PRIMARY KEY,
                    session_id TEXT,
                    original_filename TEXT NOT NULL,
                    content_type TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    storage_path TEXT NOT NULL,
                    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await db.execute("""
                CREATE TABLE attachment_extractions (
                    id TEXT PRIMARY KEY,
                    attachment_id TEXT NOT NULL,
                    extraction_source TEXT NOT NULL,
                    status TEXT NOT NULL,
                    error_message TEXT,
                    extracted_text TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    error_code TEXT,
                    extracted_char_count INTEGER DEFAULT 0,
                    extraction_confidence REAL,
                    normalization_applied INTEGER DEFAULT 0,
                    FOREIGN KEY (attachment_id) REFERENCES attachments(id) ON DELETE CASCADE
                )
            """)
            await db.execute("PRAGMA user_version = 2")
            await db.commit()
            
            # Verify user_version is 2 initially
            assert await get_user_version(db) == 2

        # 2. Run migrations
        async with aiosqlite.connect(db_file) as db:
            await run_migrations(db)
            
            # Assert user_version is upgraded to 3
            assert await get_user_version(db) == 3
            
            # Verify table attachment_chunks exists
            async with db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name = 'attachment_chunks'"
            ) as cursor:
                res = await cursor.fetchone()
                assert res is not None
    finally:
        if os.path.exists(db_file):
            os.remove(db_file)


@pytest.mark.asyncio
async def test_newer_version_raises_runtime_error():
    db_file = "test_mig_new.db"
    if os.path.exists(db_file):
        os.remove(db_file)

    try:
        # Setup DB with future schema version (LATEST_SCHEMA_VERSION + 1 = 4)
        async with aiosqlite.connect(db_file) as db:
            await db.execute(f"PRAGMA user_version = {LATEST_SCHEMA_VERSION + 1}")
            await db.commit()
            
        async with aiosqlite.connect(db_file) as db:
            with pytest.raises(RuntimeError) as exc_info:
                await run_migrations(db)
            assert "newer than the application version" in str(exc_info.value)
    finally:
        if os.path.exists(db_file):
            os.remove(db_file)
