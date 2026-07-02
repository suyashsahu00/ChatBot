import pytest
import aiosqlite
from unittest.mock import patch
from app.core.config import settings
from app.services.data import attachments


@patch("app.api.routes.uploads.extract_content")
def test_upload_success(mock_extract, client):
    mock_extract.return_value = "Mocked extracted text content"

    # Call endpoint with multipart file upload
    file_payload = {"file": ("test.txt", b"Hello World", "text/plain")}
    response = client.post("/api/upload", files=file_payload)
    
    assert response.status_code == 200
    data = response.json()
    assert "filename" in data
    assert "extracted_text" in data
    assert data["filename"] == "test.txt"
    assert data["extracted_text"] == "Mocked extracted text content"
    mock_extract.assert_called_once_with(b"Hello World", "test.txt", "text/plain")


@patch("app.api.routes.uploads.extract_content")
def test_upload_unsupported_file(mock_extract, client):
    mock_extract.side_effect = ValueError("Unsupported file type: .xyz")

    file_payload = {"file": ("test.xyz", b"binary", "application/octet-stream")}
    response = client.post("/api/upload", files=file_payload)
    
    assert response.status_code == 400
    assert response.json()["detail"] == "Unsupported file type: .xyz"


def test_upload_empty_file(client):
    file_payload = {"file": ("test.txt", b"", "text/plain")}
    response = client.post("/api/upload", files=file_payload)
    
    assert response.status_code == 400
    assert response.json()["detail"] == "Uploaded file is empty."


# ===========================================================================
# Upload Database Integration Tests
# ===========================================================================

@pytest.mark.asyncio
async def test_upload_integration_success(client):
    # Upload a valid plain text file (does not mock extract_content)
    file_payload = {"file": ("hello.txt", b"Integration content test", "text/plain")}
    response = client.post("/api/upload", files=file_payload)
    
    assert response.status_code == 200
    assert response.json()["extracted_text"] == "Integration content test"

    # Verify rows in database
    async with aiosqlite.connect(settings.database_file) as db:
        db.row_factory = aiosqlite.Row
        
        # Verify attachment record
        async with db.execute("SELECT * FROM attachments") as cursor:
            att_rows = await cursor.fetchall()
            assert len(att_rows) == 1
            att = dict(att_rows[0])
            assert att["original_filename"] == "hello.txt"
            assert att["content_type"] == "text/plain"
            assert att["size_bytes"] == len(b"Integration content test")
            assert "uploads/" in att["storage_path"]
            
        # Verify extraction result record
        async with db.execute("SELECT * FROM attachment_extractions") as cursor:
            ext_rows = await cursor.fetchall()
            assert len(ext_rows) == 1
            ext = dict(ext_rows[0])
            assert ext["attachment_id"] == att["id"]
            assert ext["extraction_source"] == "text_parser"
            assert ext["status"] == "succeeded"
            assert ext["extracted_text"] == "Integration content test"
            assert ext["error_message"] is None


@pytest.mark.asyncio
async def test_upload_integration_failed(client):
    # Upload an unsupported file type to trigger extraction failure
    file_payload = {"file": ("bad.xyz", b"some binary data", "application/octet-stream")}
    response = client.post("/api/upload", files=file_payload)
    
    assert response.status_code == 400
    assert "Unsupported file type" in response.json()["detail"]

    # Verify rows in database (the attachment and failed extraction logs must still exist)
    async with aiosqlite.connect(settings.database_file) as db:
        db.row_factory = aiosqlite.Row
        
        # Verify attachment record
        async with db.execute("SELECT * FROM attachments") as cursor:
            att_rows = await cursor.fetchall()
            assert len(att_rows) == 1
            att = dict(att_rows[0])
            assert att["original_filename"] == "bad.xyz"
            
        # Verify extraction result record (must indicate failed status)
        async with db.execute("SELECT * FROM attachment_extractions") as cursor:
            ext_rows = await cursor.fetchall()
            assert len(ext_rows) == 1
            ext = dict(ext_rows[0])
            assert ext["attachment_id"] == att["id"]
            assert ext["extraction_source"] == "type_validator"
            assert ext["status"] == "failed"
            assert "Unsupported file type: .xyz" in ext["error_message"]
            assert ext["extracted_text"] is None


@pytest.mark.asyncio
async def test_upload_rejects_mismatched_content_type(client):
    # Upload .pdf file but with text/plain content type (should trigger MIME consistency failure)
    file_payload = {"file": ("document.pdf", b"some pdf contents", "text/plain")}
    response = client.post("/api/upload", files=file_payload)

    assert response.status_code == 400
    assert "Unsupported file type" in response.json()["detail"]

    # Verify rows in database
    async with aiosqlite.connect(settings.database_file) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM attachment_extractions") as cursor:
            ext_rows = await cursor.fetchall()
            assert len(ext_rows) == 1
            ext = dict(ext_rows[0])
            assert ext["extraction_source"] == "type_validator"
            assert ext["status"] == "failed"
            assert "Mismatched content type: text/plain for .pdf" in ext["error_message"]


@pytest.mark.asyncio
async def test_upload_rejects_file_too_large_and_logs_failure(client):
    # Mock settings.max_upload_bytes limit to 10 bytes
    original_limit = settings.max_upload_bytes
    settings.max_upload_bytes = 10

    try:
        # Upload 15 bytes file (exceeds 10 bytes limit)
        file_payload = {"file": ("hello.txt", b"Oversized file contents!", "text/plain")}
        response = client.post("/api/upload", files=file_payload)

        assert response.status_code == 400
        assert "File too large" in response.json()["detail"]

        # Verify database log contains the failure
        async with aiosqlite.connect(settings.database_file) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM attachment_extractions") as cursor:
                ext_rows = await cursor.fetchall()
                assert len(ext_rows) == 1
                ext = dict(ext_rows[0])
                assert ext["extraction_source"] == "size_validator"
                assert ext["status"] == "failed"
                assert ext["error_message"] == "File too large"
    finally:
        # Restore limit
        settings.max_upload_bytes = original_limit


@pytest.mark.asyncio
@patch("app.services.extraction.image_parser.parse_image")
async def test_upload_jpeg_signature_validation(mock_parse_image, client):
    mock_parse_image.return_value = "Mocked JPEG extraction"

    # 1. Valid JPEG signature: FF D8 FF
    file_payload = {"file": ("image.jpg", b"\xff\xd8\xff\xe0\x00\x10JFIF", "image/jpeg")}
    response = client.post("/api/upload", files=file_payload)
    
    assert response.status_code == 200
    assert response.json()["extracted_text"] == "Mocked JPEG extraction"

    # 2. Invalid JPEG signature
    file_payload_bad = {"file": ("image.jpg", b"\xff\xd8\x00\xe0JFIF", "image/jpeg")}
    response_bad = client.post("/api/upload", files=file_payload_bad)
    
    assert response_bad.status_code == 400
    assert "Invalid file signature" in response_bad.json()["detail"]

    # Verify invalid signature logging in database
    async with aiosqlite.connect(settings.database_file) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM attachment_extractions WHERE status = 'failed'") as cursor:
            rows = await cursor.fetchall()
            assert len(rows) == 1
            ext = dict(rows[0])
            assert ext["extraction_source"] == "signature_validator"
            assert ext["error_code"] == "invalid_signature"
            assert ext["error_message"] == "Invalid JPEG signature."


@pytest.mark.asyncio
async def test_upload_zero_byte_logs_empty_upload(client):
    file_payload = {"file": ("empty.txt", b"", "text/plain")}
    response = client.post("/api/upload", files=file_payload)

    assert response.status_code == 400
    assert "Uploaded file is empty" in response.json()["detail"]

    # Verify zero-byte database logging
    async with aiosqlite.connect(settings.database_file) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM attachment_extractions") as cursor:
            rows = await cursor.fetchall()
            assert len(rows) == 1
            ext = dict(rows[0])
            assert ext["extraction_source"] == "zero_byte_check"
            assert ext["error_code"] == "empty_upload"
            assert ext["error_message"] == "Uploaded file is empty."


@pytest.mark.asyncio
async def test_upload_empty_extraction_logs_correctly(client):
    # Upload file with only spaces/control noise -> yields empty normalized text
    file_payload = {"file": ("blank.txt", b"\x00\x01   \x02\r\n", "text/plain")}
    response = client.post("/api/upload", files=file_payload)

    assert response.status_code == 400
    assert "No extractable text found" in response.json()["detail"]

    # Verify empty extraction logging in database
    async with aiosqlite.connect(settings.database_file) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM attachment_extractions") as cursor:
            rows = await cursor.fetchall()
            assert len(rows) == 1
            ext = dict(rows[0])
            assert ext["extraction_source"] == "text_parser"
            assert ext["error_code"] == "empty_extraction"
            assert ext["error_message"] == "No extractable text found"


@pytest.mark.asyncio
async def test_upload_normalization_works(client):
    # Text with CRLF, control codes, excessive spacing, outer padding
    raw_bytes = b" \x00\x07Hello\r\n\r\n\r\n\r\nWorld \r\n"
    file_payload = {"file": ("normal.txt", raw_bytes, "text/plain")}
    
    response = client.post("/api/upload", files=file_payload)
    assert response.status_code == 200
    
    expected_text = "Hello\n\nWorld"
    assert response.json()["extracted_text"] == expected_text

    # Verify normalization metadata in database
    async with aiosqlite.connect(settings.database_file) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM attachment_extractions") as cursor:
            rows = await cursor.fetchall()
            assert len(rows) == 1
            ext = dict(rows[0])
            assert ext["extracted_text"] == expected_text
            assert ext["normalization_applied"] == 1
            assert ext["extracted_char_count"] == len(expected_text)
            assert ext["extraction_confidence"] == 0.95
