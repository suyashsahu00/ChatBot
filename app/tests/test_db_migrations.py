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
            
            # Assert user_version is updated to latest
            version = await get_user_version(db)
            assert version == LATEST_SCHEMA_VERSION
            
            # Verify core tables exist
            async with db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('sessions', 'messages', 'attachments', 'attachment_extractions')"
            ) as cursor:
                tables = {row[0] for row in await cursor.fetchall()}
                assert len(tables) == 4
                
            # Verify new quality columns exist in attachment_extractions
            async with db.execute("PRAGMA table_info(attachment_extractions)") as cursor:
                columns = {row[1] for row in await cursor.fetchall()}
                assert "error_code" in columns
                assert "extracted_char_count" in columns
                assert "extraction_confidence" in columns
                assert "normalization_applied" in columns
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
            
            # Verify columns do not exist initially
            async with db.execute("PRAGMA table_info(attachment_extractions)") as cursor:
                cols = {row[1] for row in await cursor.fetchall()}
                assert "error_code" not in cols
                assert "extracted_char_count" not in cols

        # 2. Run migrations
        async with aiosqlite.connect(db_file) as db:
            await run_migrations(db)
            
            # Assert user_version is upgraded to 2
            assert await get_user_version(db) == 2
            
            # Verify columns have been successfully added
            async with db.execute("PRAGMA table_info(attachment_extractions)") as cursor:
                cols_after = {row[1] for row in await cursor.fetchall()}
                assert "error_code" in cols_after
                assert "extracted_char_count" in cols_after

        # 3. Re-run migrations and check for idempotency
        async with aiosqlite.connect(db_file) as db:
            # Running again should succeed without throwing operational errors
            await run_migrations(db)
            assert await get_user_version(db) == LATEST_SCHEMA_VERSION
    finally:
        if os.path.exists(db_file):
            os.remove(db_file)


@pytest.mark.asyncio
async def test_newer_version_raises_runtime_error():
    db_file = "test_mig_new.db"
    if os.path.exists(db_file):
        os.remove(db_file)

    try:
        # Setup DB with future schema version
        async with aiosqlite.connect(db_file) as db:
            await db.execute("PRAGMA user_version = 3")
            await db.commit()
            
        async with aiosqlite.connect(db_file) as db:
            with pytest.raises(RuntimeError) as exc_info:
                await run_migrations(db)
            assert "newer than the application version" in str(exc_info.value)
    finally:
        if os.path.exists(db_file):
            os.remove(db_file)
