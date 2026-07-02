import pytest
import aiosqlite
from unittest.mock import patch
from app.core.config import settings
from app.services.retrieval import query_retrieval, vector_store


@pytest.fixture(autouse=True)
def reset_retrieval_metrics():
    """Reset the metrics counts before every test run."""
    metrics = query_retrieval.get_retrieval_metrics()
    metrics["grounded_responses_count"] = 0
    metrics["ungrounded_responses_count"] = 0
    yield
    metrics["grounded_responses_count"] = 0
    metrics["ungrounded_responses_count"] = 0


@pytest.mark.asyncio
@patch("app.api.routes.chat.generate_response")
@patch("app.services.retrieval.embeddings.get_embedding")
async def test_metrics_counters(mock_get_embedding, mock_generate_response, client):
    mock_get_embedding.return_value = [0.1, 0.2]
    mock_generate_response.return_value = "Answer response text."

    db_file = settings.database_file
    att_id = "test-metrics-att"
    ext_id = "test-metrics-ext"

    async with aiosqlite.connect(db_file) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        await db.execute(
            "INSERT INTO attachments (id, original_filename, content_type, size_bytes, storage_path) VALUES (?, ?, ?, ?, ?)",
            (att_id, "metrics_doc.txt", "text/plain", 100, "uploads/metrics_doc.txt")
        )
        await db.execute(
            "INSERT INTO attachment_extractions (id, attachment_id, extraction_source, status, error_message, extracted_text, extraction_confidence) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (ext_id, att_id, "text_parser", "succeeded", None, "High quality metrics text grounding data.", 1.0)
        )
        await db.commit()

    store = vector_store.get_vector_store(db_file)
    await store.store_chunk(
        id="metrics-chunk-1",
        attachment_id=att_id,
        extraction_id=ext_id,
        chunk_index=0,
        chunk_text="High quality metrics text grounding data.",
        char_count=40,
        token_estimate=10,
        embedding_model="test-model",
        embedding_vector=[0.1, 0.2]
    )

    # 1. Grounded Query
    payload = {
        "session_id": "session-metrics",
        "messages": [{"role": "user", "content": "How to retrieve quality metrics?"}]
    }
    response = client.post("/api/chat", json=payload)
    assert response.status_code == 200

    metrics = query_retrieval.get_retrieval_metrics()
    assert metrics["grounded_responses_count"] == 1
    assert metrics["ungrounded_responses_count"] == 0

    # 2. Ungrounded Query (orthogonal query vector)
    mock_get_embedding.return_value = [-0.2, 0.1]
    payload = {
        "session_id": "session-metrics",
        "messages": [{"role": "user", "content": "Unrelated question text."}]
    }
    response = client.post("/api/chat", json=payload)
    assert response.status_code == 200

    assert metrics["grounded_responses_count"] == 1
    assert metrics["ungrounded_responses_count"] == 1


@pytest.mark.asyncio
@patch("app.api.routes.chat.generate_response")
@patch("app.services.retrieval.embeddings.get_embedding")
async def test_grounding_toggle(mock_get_embedding, mock_generate_response, client):
    # Disable grounding via settings config toggle
    settings.enable_grounding = False
    
    mock_get_embedding.return_value = [0.1, 0.2]
    mock_generate_response.return_value = "Normal response."

    payload = {
        "session_id": "session-toggle",
        "messages": [{"role": "user", "content": "How to toggle grounding?"}]
    }

    try:
        response = client.post("/api/chat", json=payload)
        assert response.status_code == 200

        # Assert no embedding/retrieval took place and ungrounded metrics count incremented
        assert mock_get_embedding.call_count == 0
        metrics = query_retrieval.get_retrieval_metrics()
        assert metrics["ungrounded_responses_count"] == 1
        assert metrics["grounded_responses_count"] == 0
    finally:
        settings.enable_grounding = True  # reset to default


@pytest.mark.asyncio
@patch("app.services.retrieval.embeddings.get_embedding")
async def test_debug_endpoint_query(mock_get_embedding, client):
    settings.enable_debug_routes = True
    # Re-import debug router or recreate client to register debug routes since it's conditional
    from app.main import app
    from fastapi.testclient import TestClient
    
    with TestClient(app) as test_client:
        mock_get_embedding.return_value = [0.1, 0.2]
        
        db_file = settings.database_file
        att_id = "test-debug-att"
        ext_id = "test-debug-ext"
        
        async with aiosqlite.connect(db_file) as db:
            await db.execute("PRAGMA foreign_keys = ON")
            await db.execute(
                "INSERT INTO attachments (id, original_filename, content_type, size_bytes, storage_path) VALUES (?, ?, ?, ?, ?)",
                (att_id, "debug_doc.txt", "text/plain", 100, "uploads/debug_doc.txt")
            )
            await db.execute(
                "INSERT INTO attachment_extractions (id, attachment_id, extraction_source, status, error_message, extracted_text, extraction_confidence) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (ext_id, att_id, "text_parser", "succeeded", None, "Debug content data.", 1.0)
            )
            await db.commit()

        store = vector_store.get_vector_store(db_file)
        await store.store_chunk(
            id="debug-chunk-1",
            attachment_id=att_id,
            extraction_id=ext_id,
            chunk_index=0,
            chunk_text="Debug content data.",
            char_count=19,
            token_estimate=4,
            embedding_model="test-model",
            embedding_vector=[0.1, 0.2]
        )

        response = test_client.get("/api/debug/retrieval?query=what is debug?")
        assert response.status_code == 200
        
        data = response.json()
        assert data["query"] == "what is debug?"
        assert "raw_candidates" in data
        assert "reranked_results" in data
        assert len(data["raw_candidates"]) == 1
        assert len(data["reranked_results"]) == 1
        assert data["reranked_results"][0]["filename"] == "debug_doc.txt"


@pytest.mark.asyncio
async def test_debug_endpoint_attachment(client):
    settings.enable_debug_routes = True
    from app.main import app
    from fastapi.testclient import TestClient

    with TestClient(app) as test_client:
        db_file = settings.database_file
        att_id = "test-debug-att-detail"
        ext_id = "test-debug-ext-detail"
        
        async with aiosqlite.connect(db_file) as db:
            await db.execute("PRAGMA foreign_keys = ON")
            await db.execute(
                "INSERT INTO attachments (id, original_filename, content_type, size_bytes, storage_path) VALUES (?, ?, ?, ?, ?)",
                (att_id, "detail.txt", "text/plain", 100, "uploads/detail.txt")
            )
            await db.execute(
                "INSERT INTO attachment_extractions (id, attachment_id, extraction_source, status, error_message, extracted_text, extraction_confidence) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (ext_id, att_id, "text_parser", "succeeded", None, "Detail chunk information.", 1.0)
            )
            await db.commit()

        store = vector_store.get_vector_store(db_file)
        await store.store_chunk(
            id="debug-detail-chunk-1",
            attachment_id=att_id,
            extraction_id=ext_id,
            chunk_index=0,
            chunk_text="Detail chunk information.",
            char_count=25,
            token_estimate=6,
            embedding_model="test-model",
            embedding_vector=[0.1, 0.2]
        )

        response = test_client.get(f"/api/debug/retrieval?attachment_id={att_id}")
        assert response.status_code == 200
        
        data = response.json()
        assert data["attachment_id"] == att_id
        assert len(data["chunks"]) == 1
        assert data["chunks"][0]["chunk_text"] == "Detail chunk information."


@pytest.mark.asyncio
async def test_debug_endpoint_summary(client):
    settings.enable_debug_routes = True
    from app.main import app
    from fastapi.testclient import TestClient

    with TestClient(app) as test_client:
        response = test_client.get("/api/debug/retrieval")
        assert response.status_code == 200
        data = response.json()
        assert "total_chunks" in data
        assert "total_attachments" in data


@pytest.mark.asyncio
async def test_debug_route_disabled_by_default(client):
    settings.enable_debug_routes = False
    from app.main import app
    from fastapi.testclient import TestClient

    with TestClient(app) as test_client:
        # Route should either return 404 (gated internally) or not exist
        response = test_client.get("/api/debug/retrieval")
        assert response.status_code == 404
