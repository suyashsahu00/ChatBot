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
            assert ext["extraction_source"] == "unsupported"
            assert ext["status"] == "failed"
            assert "Unsupported file type: .xyz" in ext["error_message"]
            assert ext["extracted_text"] is None

