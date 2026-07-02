import os
import json
import pytest
import aiosqlite
from unittest.mock import patch
from app.core.config import settings
from app.services.retrieval import vector_store, report_builder
from app.services.retrieval.evaluator import evaluate_rag

DATASET_PATH = "app/services/retrieval/eval_dataset.json"


async def seed_report_database(db_file: str, vector_val: list[float]):
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


def test_status_classification_logic():
    # 1. PASS case (everything meets criteria and judge passes)
    pass_case = {
        "context_recall": 1.0,
        "context_precision": 1.0,
        "attribution_correctness": 1.0,
        "keyword_match": 1.0,
        "answer_keyword_match": 1.0,
        "judge_passed": True,
        "judge_skipped": False
    }
    status, reasons = report_builder.classify_case_status(pass_case)
    assert status == "PASS"
    assert len(reasons) == 0

    # 2. SKIPPED case (deterministic passes, but judge skipped)
    skipped_case = {
        "context_recall": 1.0,
        "context_precision": 1.0,
        "attribution_correctness": 1.0,
        "keyword_match": 1.0,
        "answer_keyword_match": 1.0,
        "judge_passed": False,
        "judge_skipped": True
    }
    status, reasons = report_builder.classify_case_status(skipped_case)
    assert status == "SKIPPED"
    assert "Judge Skipped" in reasons

    # 3. FAIL case (recall below threshold)
    fail_case = {
        "context_recall": 0.5,
        "context_precision": 1.0,
        "attribution_correctness": 1.0,
        "keyword_match": 1.0,
        "answer_keyword_match": 1.0,
        "judge_passed": True,
        "judge_skipped": False
    }
    status, reasons = report_builder.classify_case_status(fail_case)
    assert status == "FAIL"
    assert "Low Recall" in reasons


@pytest.mark.asyncio
@patch("app.services.retrieval.embeddings.get_embedding")
async def test_saved_run_files_and_content_formats(mock_get_embedding, tmp_path):
    db_file = settings.database_file
    mock_get_embedding.return_value = [0.1, 0.2]
    await seed_report_database(db_file, [0.1, 0.2])

    output_dir = str(tmp_path / "custom_runs")

    # Run evaluation with report saving enabled
    metrics = await evaluate_rag(db_file, DATASET_PATH, save_reports=True, output_dir=output_dir)

    # 1. Assert file paths are returned
    assert "report_json_path" in metrics
    assert "report_md_path" in metrics
    
    json_path = metrics["report_json_path"]
    md_path = metrics["report_md_path"]
    
    assert os.path.exists(json_path)
    assert os.path.exists(md_path)

    # 2. Assert JSON content conforms to expected structure
    with open(json_path, "r", encoding="utf-8") as f:
        json_data = json.load(f)
        assert json_data["average_recall"] >= 0.80
        assert len(json_data["results"]) == 2
        assert "status" in json_data["results"][0]
        assert "reasons" in json_data["results"][0]

    # 3. Assert Markdown content includes key sections and human review highlights
    with open(md_path, "r", encoding="utf-8") as f:
        md_text = f.read()
        assert "# RAG Evaluation Run Report" in md_text
        assert "## 1. Aggregate Metrics Summary" in md_text
        assert "## 2. Per-Case Human Review Table" in md_text
        assert "## 3. Failed and Skipped Cases Section" in md_text
        assert "Performance & Operational Summary" in md_text
