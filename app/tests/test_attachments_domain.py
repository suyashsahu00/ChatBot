import pytest
import aiosqlite
from app.core.config import settings
from app.services.data import attachments


@pytest.mark.asyncio
async def test_attachment_domain_helpers():
    db_file = settings.database_file
    att_id = "test-att-uuid-1"
    ext_id = "test-ext-uuid-1"

    # 1. Create an attachment
    await attachments.create_attachment(
        db_file=db_file,
        id=att_id,
        session_id=None,
        original_filename="sample.txt",
        content_type="text/plain",
        size_bytes=100,
        storage_path="uploads/sample.txt",
    )

    # 2. Retrieve attachment and verify fields
    att_record = await attachments.get_attachment_by_id(db_file, att_id)
    assert att_record is not None
    assert att_record["id"] == att_id
    assert att_record["original_filename"] == "sample.txt"
    assert att_record["content_type"] == "text/plain"
    assert att_record["size_bytes"] == 100
    assert att_record["storage_path"] == "uploads/sample.txt"

    # 3. Create an extraction result linked to attachment
    await attachments.create_extraction_result(
        db_file=db_file,
        id=ext_id,
        attachment_id=att_id,
        extraction_source="text_parser",
        status="succeeded",
        error_message=None,
        extracted_text="Successfully parsed content text.",
    )

    # 4. Retrieve extraction and verify fields
    ext_record = await attachments.get_extraction_by_attachment_id(db_file, att_id)
    assert ext_record is not None
    assert ext_record["id"] == ext_id
    assert ext_record["attachment_id"] == att_id
    assert ext_record["extraction_source"] == "text_parser"
    assert ext_record["status"] == "succeeded"
    assert ext_record["extracted_text"] == "Successfully parsed content text."
    assert ext_record["error_message"] is None

    # 5. Delete the attachment and verify CASCADE deleted the extraction result
    await attachments.delete_attachment(db_file, att_id)
    
    # Verification checks
    att_check = await attachments.get_attachment_by_id(db_file, att_id)
    ext_check = await attachments.get_extraction_by_attachment_id(db_file, att_id)
    assert att_check is None, "Attachment row was not deleted"
    assert ext_check is None, "Cascade delete did not remove linked extraction result"


@pytest.mark.asyncio
async def test_cleanup_expired_attachments_deletes_files_and_rows():
    import os
    db_file = settings.database_file
    
    # 1. Create a dummy file in uploads/
    uploads_dir = os.path.abspath("uploads")
    os.makedirs(uploads_dir, exist_ok=True)
    temp_storage_path = os.path.join(uploads_dir, "expired-test.txt")
    with open(temp_storage_path, "w") as f:
        f.write("Expired file test content")
        
    # Relative path for database entry
    db_storage_path = os.path.join("uploads", "expired-test.txt").replace("\\", "/")

    # 2. Insert backdated attachment (35 days ago) and extraction records
    att_id = "expired-uuid-1"
    async with aiosqlite.connect(db_file) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        await db.execute(
            """
            INSERT INTO attachments (
                id, session_id, original_filename, content_type, size_bytes, storage_path, uploaded_at
            ) VALUES (?, ?, ?, ?, ?, ?, datetime('now', '-35 days'))
            """,
            (att_id, None, "expired.txt", "text/plain", 25, db_storage_path)
        )
        await db.execute(
            """
            INSERT INTO attachment_extractions (
                id, attachment_id, extraction_source, status, error_message, extracted_text
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("expired-ext-uuid", att_id, "text_parser", "succeeded", None, "Parsed text content")
        )
        await db.commit()

    # Verify rows exist before cleanup
    att_before = await attachments.get_attachment_by_id(db_file, att_id)
    ext_before = await attachments.get_extraction_by_attachment_id(db_file, att_id)
    assert att_before is not None
    assert ext_before is not None
    assert os.path.exists(temp_storage_path)

    # 3. Execute cleanup with a 30-day retention threshold
    await attachments.cleanup_expired_attachments(db_file, 30)

    # 4. Verify cleanup deleted both the physical file and the database records
    assert not os.path.exists(temp_storage_path), "Physical expired file was not deleted"
    
    att_after = await attachments.get_attachment_by_id(db_file, att_id)
    ext_after = await attachments.get_extraction_by_attachment_id(db_file, att_id)
    assert att_after is None, "Expired attachment DB record was not cleaned up"
    assert ext_after is None, "Expired extraction DB record was not cascade cleaned up"

