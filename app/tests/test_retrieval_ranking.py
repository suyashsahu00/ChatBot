import pytest
from app.services.retrieval.ranking import rerank_chunks


def test_rerank_quality_modifiers():
    # 1. Base candidates
    candidates = [
        {
            "id": "chunk-a",
            "similarity": 0.60,
            "extraction_confidence": 0.90,  # +0.09 boost
            "normalization_applied": 1,      # +0.05 boost
            "char_count": 500,               # no penalty
            "extracted_char_count": 1000,    # no penalty
        },
        {
            "id": "chunk-b",
            "similarity": 0.65,
            "extraction_confidence": 0.30,  # +0.03 boost
            "normalization_applied": 0,      # no boost
            "char_count": 120,               # -0.15 penalty
            "extracted_char_count": 1000,    # no penalty
        },
        {
            "id": "chunk-c",
            "similarity": 0.70,
            "extraction_confidence": 0.90,  # +0.09 boost
            "normalization_applied": 1,      # +0.05 boost
            "char_count": 500,               # no penalty
            "extracted_char_count": 20,      # -0.20 parent penalty
        }
    ]

    # Run reranker
    results = rerank_chunks(candidates, top_k=3, score_threshold=0.20)

    # Assert correct sorting order
    # Expected scores:
    # A: 0.60 + 0.09 + 0.05 = 0.74
    # B: 0.65 + 0.03 - 0.15 = 0.53
    # C: 0.70 + 0.09 + 0.05 - 0.20 = 0.64
    # Order should be A (0.74) -> C (0.64) -> B (0.53)
    assert len(results) == 3
    assert results[0]["id"] == "chunk-a"
    assert results[1]["id"] == "chunk-c"
    assert results[2]["id"] == "chunk-b"


def test_rerank_threshold_suppression():
    candidates = [
        {
            "id": "high-match",
            "similarity": 0.75,
            "extraction_confidence": 0.90,
            "char_count": 500,
            "extracted_char_count": 1000,
        },
        {
            "id": "low-match",
            "similarity": 0.25,
            "extraction_confidence": 0.10,
            "char_count": 500,
            "extracted_char_count": 1000,
        }
    ]

    # Run reranker with threshold = 0.35
    results = rerank_chunks(candidates, top_k=2, score_threshold=0.35)

    # Only high-match should survive
    assert len(results) == 1
    assert results[0]["id"] == "high-match"
