"""
Orchestrates semantic retrieval by embedding user queries,
retrieving candidates, and applying quality reranking/metadata filters.
Includes metrics tracking and structured logging.
"""

import logging
from app.core.config import settings
from app.services.retrieval import embeddings, vector_store, ranking

logger = logging.getLogger(__name__)

MAX_CONTEXT_CHARS = 3000

# Global metrics counters
metrics = {
    "grounded_responses_count": 0,
    "ungrounded_responses_count": 0,
}


def get_retrieval_metrics() -> dict:
    """Return the current retrieval metrics counters."""
    return metrics


async def retrieve_grounding_context(
    query: str,
    db_file: str,
    top_k: int = None,
) -> dict:
    """
    Accepts user query, generates query embedding, retrieves top candidate chunks,
    reranks them by quality filters, and formats them into a compact grounding block.
    """
    # 1. Respect configuration toggle
    if not settings.enable_grounding:
        logger.info("RAG Retrieval: Grounding disabled via config toggles.")
        metrics["ungrounded_responses_count"] += 1
        return {"grounding_context": "", "sources": []}

    # Use config default if top_k not specified
    if top_k is None:
        top_k = settings.rag_top_k

    # 2. Check for empty query
    if not query.strip():
        logger.info("RAG Retrieval: Empty user query. Skipping grounding.")
        metrics["ungrounded_responses_count"] += 1
        return {"grounding_context": "", "sources": []}

    logger.info(f"RAG Retrieval: Query='{query}'")

    try:
        # 3. Embed the query
        query_vector = await embeddings.get_embedding(query)
    except Exception as e:
        logger.warning(f"RAG Retrieval: Query embedding generation failed: {e}")
        metrics["ungrounded_responses_count"] += 1
        return {"grounding_context": "", "sources": []}

    # 4. Retrieve candidates
    store = vector_store.get_vector_store(db_file)
    candidates = await store.search_similar_chunks(query_vector, top_n=20)
    
    # Log raw candidates retrieval results
    candidates_summary = [{"id": c["id"], "similarity": c["similarity"]} for c in candidates]
    logger.info(f"RAG Retrieval: Candidates retrieved count={len(candidates)}, list={candidates_summary}")

    if not candidates:
        logger.info("RAG Retrieval: Skip grounding (no candidates found in database).")
        metrics["ungrounded_responses_count"] += 1
        return {"grounding_context": "", "sources": []}

    # 5. Rerank candidates using configured threshold
    reranked = ranking.rerank_chunks(candidates, top_k=top_k, score_threshold=settings.rag_score_threshold)

    if not reranked:
        logger.info(f"RAG Retrieval: Skip grounding (all candidates filtered below threshold={settings.rag_score_threshold}).")
        metrics["ungrounded_responses_count"] += 1
        return {"grounding_context": "", "sources": []}

    # 6. Build grounding context string with size cap protection
    blocks = []
    sources = []
    current_chars = 0

    for chunk in reranked:
        filename = chunk.get("original_filename", "Unknown Attachment")
        chunk_idx = chunk.get("chunk_index", 0)
        block = f"[Attachment: {filename} | Chunk {chunk_idx}]\n{chunk['chunk_text']}"
        
        # Check if adding this block violates size cap limit
        if current_chars + len(block) > MAX_CONTEXT_CHARS:
            break

        blocks.append(block)
        sources.append({
            "attachment_id": chunk["attachment_id"],
            "filename": filename,
            "extraction_id": chunk["extraction_id"],
            "chunk_index": chunk_idx,
            "chunk_text": chunk["chunk_text"],
            "similarity": chunk["similarity"],
            "final_score": chunk["final_score"],
        })
        current_chars += len(block) + 2  # account for double newline spacing

    # Log actually used chunks
    used_summary = [
        {"attachment_id": s["attachment_id"], "chunk_index": s["chunk_index"], "final_score": s["final_score"]}
        for s in sources
    ]
    logger.info(f"RAG Retrieval: Grounding used count={len(sources)}, chunks={used_summary}")
    metrics["grounded_responses_count"] += 1

    grounding_context = "\n\n".join(blocks)
    return {
        "grounding_context": grounding_context,
        "sources": sources,
    }
