import pytest
import aiosqlite
from unittest.mock import patch
from app.core.config import settings
from app.services.retrieval import chunking, embeddings, vector_store
from app.services.extraction.pipeline import extract_content


def test_deterministic_chunking():
    # Test text: 540 characters to produce a chunk and a tiny trailing chunk
    text = "A" * 520 + " " + "B" * 20
    chunks = chunking.chunk_text(text, chunk_size=500, overlap=50)
    
    # Tiny trailing chunk of "B"s (length 20 < 100) should be merged into the first chunk
    assert len(chunks) == 1
    assert "B" in chunks[0]["chunk_text"]
    assert chunks[0]["char_count"] == len(chunks[0]["chunk_text"])


@pytest.mark.asyncio
@patch("app.services.retrieval.embeddings.get_embedding")
async def test_successful_indexing(mock_get_embedding, client):
    # Mock embedding return vector
    mock_get_embedding.return_value = [0.1, 0.2, 0.3, 0.4]

    file_payload = {"file": ("document.txt", b"This is the grounding context for RAG pipelines.", "text/plain")}
    response = client.post("/api/upload", files=file_payload)
    
    assert response.status_code == 200
    
    # Verify chunks are created in database
    async with aiosqlite.connect(settings.database_file) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM attachment_chunks") as cursor:
            rows = await cursor.fetchall()
            assert len(rows) == 1
            chunk = dict(rows[0])
            assert chunk["chunk_text"] == "This is the grounding context for RAG pipelines."
            assert "0.1" in chunk["embedding_vector"]
            assert chunk["embedding_model"] == embeddings.get_model_name()


@pytest.mark.asyncio
@patch("app.services.retrieval.embeddings.get_embedding")
async def test_indexing_failure_logs_distinct_error_code(mock_get_embedding, client):
    # Mock embedding generator failure
    mock_get_embedding.side_effect = RuntimeError("Embeddings service unavailable")

    file_payload = {"file": ("failed_doc.txt", b"Grounding content text.", "text/plain")}
    response = client.post("/api/upload", files=file_payload)
    
    # Should fail due to indexing error
    assert response.status_code == 400
    assert "Indexing failed" in response.json()["detail"]

    # Verify parent extraction is updated to failed status and error_code is indexing_failure
    async with aiosqlite.connect(settings.database_file) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM attachment_extractions") as cursor:
            rows = await cursor.fetchall()
            assert len(rows) == 1
            ext = dict(rows[0])
            assert ext["status"] == "failed"
            assert ext["error_code"] == "indexing_failure"
            assert "Embeddings service unavailable" in ext["error_message"]


@pytest.mark.asyncio
async def test_duplicate_reindexing_protection():
    db_file = settings.database_file
    store = vector_store.get_vector_store(db_file)
    att_id = "test-reindex-attachment"
    ext_id = "test-reindex-extraction"

    # Insert parent attachment and extraction records first (foreign key constraints enforce this)
    async with aiosqlite.connect(db_file) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        await db.execute(
            "INSERT INTO attachments (id, original_filename, content_type, size_bytes, storage_path) VALUES (?, ?, ?, ?, ?)",
            (att_id, "test.txt", "text/plain", 100, "uploads/test.txt")
        )
        await db.execute(
            "INSERT INTO attachment_extractions (id, attachment_id, extraction_source, status, error_message, extracted_text) VALUES (?, ?, ?, ?, ?, ?)",
            (ext_id, att_id, "text_parser", "succeeded", None, "Parent extracted text")
        )
        await db.commit()

    # Store 2 initial chunks for attachment
    for i in range(2):
        await store.store_chunk(
            id=f"chunk-{i}",
            attachment_id=att_id,
            extraction_id=ext_id,
            chunk_index=i,
            chunk_text=f"Text chunk {i}",
            char_count=12,
            token_estimate=3,
            embedding_model="test-model",
            embedding_vector=[0.1, 0.2]
        )

    # Verify 2 chunks exist
    async with aiosqlite.connect(db_file) as db:
        async with db.execute("SELECT COUNT(*) FROM attachment_chunks WHERE attachment_id = ?", (att_id,)) as cursor:
            count = (await cursor.fetchone())[0]
            assert count == 2

    # Run clean re-indexing deletion helper
    await store.delete_chunks_by_attachment_id(att_id)

    # Verify count is 0
    async with aiosqlite.connect(db_file) as db:
        async with db.execute("SELECT COUNT(*) FROM attachment_chunks WHERE attachment_id = ?", (att_id,)) as cursor:
            count = (await cursor.fetchone())[0]
            assert count == 0
