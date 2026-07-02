import pytest
import aiosqlite
from unittest.mock import patch, MagicMock
from app.core.config import settings
from app.services.retrieval import query_retrieval, vector_store


@pytest.mark.asyncio
@patch("app.api.routes.chat.generate_response")
@patch("app.services.retrieval.embeddings.get_embedding")
async def test_grounded_answering_injects_context(mock_get_embedding, mock_generate_response, client):
    mock_get_embedding.return_value = [0.1, 0.2]
    mock_generate_response.return_value = "Answer grounded in files."

    # 1. Setup mock attachment and chunk in the test DB
    db_file = settings.database_file
    att_id = "test-grounded-att"
    ext_id = "test-grounded-ext"
    
    async with aiosqlite.connect(db_file) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        await db.execute(
            "INSERT INTO attachments (id, original_filename, content_type, size_bytes, storage_path) VALUES (?, ?, ?, ?, ?)",
            (att_id, "grounded_rules.txt", "text/plain", 100, "uploads/grounded_rules.txt")
        )
        await db.execute(
            "INSERT INTO attachment_extractions (id, attachment_id, extraction_source, status, error_message, extracted_text, extraction_confidence) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (ext_id, att_id, "text_parser", "succeeded", None, "Grounded content: Keep all things clean.", 1.0)
        )
        await db.commit()

    store = vector_store.get_vector_store(db_file)
    # The stored vector [0.1, 0.2] yields exact 1.0 cosine similarity with the query vector [0.1, 0.2]
    await store.store_chunk(
        id="grounded-chunk-1",
        attachment_id=att_id,
        extraction_id=ext_id,
        chunk_index=0,
        chunk_text="Grounded content: Keep all things clean.",
        char_count=38,
        token_estimate=9,
        embedding_model="test-model",
        embedding_vector=[0.1, 0.2]
    )

    payload = {
        "session_id": "session-grounded",
        "messages": [{"role": "user", "content": "How to keep things?"}]
    }

    # Call /chat
    response = client.post("/api/chat", json=payload)
    assert response.status_code == 200

    # Verify generate_response received the grounding prompt
    assert mock_generate_response.call_count == 1
    args, _ = mock_generate_response.call_args
    passed_messages = args[0]
    assert len(passed_messages) == 1
    assert "Retrieved attachment context:" in passed_messages[0]["content"]
    assert "grounded_rules.txt" in passed_messages[0]["content"]
    assert "Grounded content: Keep all things clean." in passed_messages[0]["content"]


@pytest.mark.asyncio
@patch("app.api.routes.chat.generate_response")
@patch("app.services.retrieval.embeddings.get_embedding")
async def test_unrelated_query_no_injection(mock_get_embedding, mock_generate_response, client):
    # Query vector is orthogonal to the stored [0.1, 0.2] chunk, returning <= 0 score
    mock_get_embedding.return_value = [-0.2, 0.1]
    mock_generate_response.return_value = "Unrelated answer."

    payload = {
        "session_id": "session-unrelated",
        "messages": [{"role": "user", "content": "Unrelated topic inquiry?"}]
    }

    # Call /chat
    response = client.post("/api/chat", json=payload)
    assert response.status_code == 200

    # Verify no grounding context is injected in prompt
    assert mock_generate_response.call_count == 1
    args, _ = mock_generate_response.call_args
    passed_messages = args[0]
    assert passed_messages[0]["content"] == "Unrelated topic inquiry?"


@pytest.mark.asyncio
@patch("app.api.routes.chat.generate_response")
@patch("app.services.retrieval.embeddings.get_embedding")
async def test_attribution_returned_correctly(mock_get_embedding, mock_generate_response, client):
    mock_get_embedding.return_value = [0.1, 0.2]
    mock_generate_response.return_value = "Mocked reply"

    db_file = settings.database_file
    att_id = "test-attr-att"
    ext_id = "test-attr-ext"

    async with aiosqlite.connect(db_file) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        await db.execute(
            "INSERT INTO attachments (id, original_filename, content_type, size_bytes, storage_path) VALUES (?, ?, ?, ?, ?)",
            (att_id, "attribution_doc.txt", "text/plain", 100, "uploads/attribution_doc.txt")
        )
        await db.execute(
            "INSERT INTO attachment_extractions (id, attachment_id, extraction_source, status, error_message, extracted_text, extraction_confidence) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (ext_id, att_id, "text_parser", "succeeded", None, "Target attr details.", 1.0)
        )
        await db.commit()

    store = vector_store.get_vector_store(db_file)
    await store.store_chunk(
        id="attr-chunk-1",
        attachment_id=att_id,
        extraction_id=ext_id,
        chunk_index=3,
        chunk_text="Target attr details.",
        char_count=20,
        token_estimate=5,
        embedding_model="test-model",
        embedding_vector=[0.1, 0.2]
    )

    payload = {
        "session_id": "session-attribution",
        "messages": [{"role": "user", "content": "Fetch details"}]
    }

    response = client.post("/api/chat", json=payload)
    assert response.status_code == 200
    
    data = response.json()
    assert "sources" in data
    assert len(data["sources"]) == 1
    source = data["sources"][0]
    assert source["attachment_id"] == att_id
    assert source["filename"] == "attribution_doc.txt"
    assert source["chunk_index"] == 3
    assert "similarity" in source
    assert "final_score" in source


@pytest.mark.asyncio
@patch("app.services.retrieval.embeddings.get_embedding")
async def test_grounding_context_respects_size_cap(mock_get_embedding):
    mock_get_embedding.return_value = [0.1, 0.2]

    # Create many chunks to exceed MAX_CONTEXT_CHARS = 3000
    candidates = []
    for i in range(15):
        candidates.append({
            "id": f"large-chunk-{i}",
            "attachment_id": f"att-{i}",
            "original_filename": f"file_{i}.txt",
            "extraction_id": f"ext-{i}",
            "chunk_index": i,
            "chunk_text": "Z" * 300,  # Each formatted block is ~350 chars
            "char_count": 300,
            "token_estimate": 75,
            "similarity": 0.90,
            "extraction_confidence": 1.0,
            "normalization_applied": 1,
            "extracted_char_count": 1000,
            "status": "succeeded"
        })

    with patch("app.services.retrieval.vector_store.SQLiteVectorStore.search_similar_chunks", return_value=candidates):
        res = await query_retrieval.retrieve_grounding_context("Query test", "dummy.db", top_k=15)
        
        # Verify grounding context is non-empty but strictly respects size limit
        assert len(res["grounding_context"]) <= query_retrieval.MAX_CONTEXT_CHARS
        # Should fit around 8 chunks (8 * 350 = 2800 < 3000), not all 15
        assert len(res["sources"]) < 15
        assert len(res["sources"]) > 0
