import pytest
from unittest.mock import patch


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
