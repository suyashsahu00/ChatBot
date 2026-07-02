"""
Data access helper functions for Attachments and Extraction results.
Integrates SQLite with PRAGMA foreign keys enabled on every connection.
"""

import aiosqlite


async def create_attachment(
    db_file: str,
    id: str,
    session_id: str | None,
    original_filename: str,
    content_type: str,
    size_bytes: int,
    storage_path: str,
) -> None:
    """Insert a new attachment record into the database."""
    async with aiosqlite.connect(db_file) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        await db.execute(
            """
            INSERT INTO attachments (
                id, session_id, original_filename, content_type, size_bytes, storage_path
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                id,
                session_id,
                original_filename,
                content_type,
                size_bytes,
                storage_path,
            ),
        )
        await db.commit()


async def create_extraction_result(
    db_file: str,
    id: str,
    attachment_id: str,
    extraction_source: str,
    status: str,
    error_message: str | None,
    extracted_text: str | None,
) -> None:
    """Insert a new attachment extraction result record into the database."""
    async with aiosqlite.connect(db_file) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        await db.execute(
            """
            INSERT INTO attachment_extractions (
                id, attachment_id, extraction_source, status, error_message, extracted_text
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                id,
                attachment_id,
                extraction_source,
                status,
                error_message,
                extracted_text,
            ),
        )
        await db.commit()


async def get_attachment_by_id(db_file: str, id: str) -> dict | None:
    """Retrieve an attachment record by its primary key ID."""
    async with aiosqlite.connect(db_file) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM attachments WHERE id = ?", (id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def get_extraction_by_attachment_id(db_file: str, attachment_id: str) -> dict | None:
    """Retrieve the extraction record referencing the specified attachment ID."""
    async with aiosqlite.connect(db_file) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM attachment_extractions WHERE attachment_id = ?",
            (attachment_id,),
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def delete_attachment(db_file: str, id: str) -> None:
    """Delete an attachment by its ID, validating cascade deletion of referencing extractions."""
    async with aiosqlite.connect(db_file) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        await db.execute("DELETE FROM attachments WHERE id = ?", (id,))
        await db.commit()
