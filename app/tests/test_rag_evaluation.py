import os
import pytest
import aiosqlite
from unittest.mock import patch
from app.core.config import settings
from app.services.retrieval import vector_store, query_retrieval
from app.services.retrieval.evaluator import evaluate_rag

DATASET_PATH = "app/services/retrieval/eval_dataset.json"


async def seed_eval_database(db_file: str, vector_val: list[float]):
    """Seed test database with evaluation documents and chunk records."""
    async with aiosqlite.connect(db_file) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        
        # Clear existing
        await db.execute("DELETE FROM attachment_chunks")
        await db.execute("DELETE FROM attachment_extractions")
        await db.execute("DELETE FROM attachments")
        await db.commit()

        # Seed Att 1
        await db.execute(
            "INSERT INTO attachments (id, original_filename, content_type, size_bytes, storage_path) VALUES (?, ?, ?, ?, ?)",
            ("eval-att-1", "grounded_rules.txt", "text/plain", 100, "uploads/grounded_rules.txt")
        )
        await db.execute(
            "INSERT INTO attachment_extractions (id, attachment_id, extraction_source, status, error_message, extracted_text, extraction_confidence) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("eval-ext-1", "eval-att-1", "text_parser", "succeeded", None, "The rules for grounded answering specify we must keep all details clean.", 1.0)
        )
        # Seed Att 2
        await db.execute(
            "INSERT INTO attachments (id, original_filename, content_type, size_bytes, storage_path) VALUES (?, ?, ?, ?, ?)",
            ("eval-att-2", "spec_doc.txt", "text/plain", 100, "uploads/spec_doc.txt")
        )
        await db.execute(
            "INSERT INTO attachment_extractions (id, attachment_id, extraction_source, status, error_message, extracted_text, extraction_confidence) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("eval-ext-2", "eval-att-2", "text_parser", "succeeded", None, "Detailed specifications are stored under database schemas.", 1.0)
        )
        await db.commit()

    store = vector_store.get_vector_store(db_file)
    # Store chunk 1
    await store.store_chunk(
        id="eval-c1",
        attachment_id="eval-att-1",
        extraction_id="eval-ext-1",
        chunk_index=0,
        chunk_text="The rules for grounded answering specify we must keep all details clean.",
        char_count=71,
        token_estimate=17,
        embedding_model="test-model",
        embedding_vector=vector_val
    )
    # Store chunk 2
    await store.store_chunk(
        id="eval-c2",
        attachment_id="eval-att-2",
        extraction_id="eval-ext-2",
        chunk_index=0,
        chunk_text="Detailed specifications are stored under database schemas.",
        char_count=58,
        token_estimate=14,
        embedding_model="test-model",
        embedding_vector=vector_val
    )


@pytest.mark.asyncio
@patch("app.services.retrieval.embeddings.get_embedding")
async def test_evaluator_computes_correct_metrics(mock_get_embedding):
    db_file = settings.database_file
    
    # 1. Mock embeddings to yield matching query vectors
    mock_get_embedding.return_value = [0.1, 0.2]
    await seed_eval_database(db_file, [0.1, 0.2])

    # 2. Run evaluation
    metrics = await evaluate_rag(db_file, DATASET_PATH)

    # 3. Assert quality gates pass
    # Grounded query -> retrieves both matching chunks because they share the mocked query vector similarity
    # Recall for both queries is 1.0 (expected is found)
    assert metrics["average_recall"] >= 0.80
    assert metrics["average_precision"] > 0.0
    assert metrics["average_keyword_match"] >= 0.70
    assert metrics["average_answer_keyword_match"] >= 0.70


@pytest.mark.asyncio
@patch("app.services.retrieval.embeddings.get_embedding")
async def test_ci_gate_fails_when_below_threshold(mock_get_embedding):
    db_file = settings.database_file
    
    # Mock query vector to return orthogonal value (yields similarity <= 0)
    mock_get_embedding.return_value = [-0.1, -0.2]
    await seed_eval_database(db_file, [0.8, 0.9])

    metrics = await evaluate_rag(db_file, DATASET_PATH)

    # Assert recall falls below threshold (should be 0.0)
    assert metrics["average_recall"] < 0.80
    
    # Confirm per-case failures are reported clearly
    assert len(metrics["results"]) == 2
    for res in metrics["results"]:
        assert res["context_recall"] == 0.0
        # Check diagnostic failure info
        assert len(res["retrieved_sources"]) == 0
