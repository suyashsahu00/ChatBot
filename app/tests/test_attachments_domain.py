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
