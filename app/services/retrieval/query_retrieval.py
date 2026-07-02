"""
Orchestrates semantic retrieval by embedding user queries,
retrieving candidates, and applying quality reranking/metadata filters.
"""

from app.services.retrieval import embeddings, vector_store, ranking

MAX_CONTEXT_CHARS = 3000


async def retrieve_grounding_context(
    query: str,
    db_file: str,
    top_k: int = 3,
) -> dict:
    """
    Accepts user query, generates query embedding, retrieves top candidate chunks,
    reranks them by quality filters, and formats them into a compact grounding block.
    """
    # 1. Check for empty query
    if not query.strip():
        return {"grounding_context": "", "sources": []}

    try:
        # 2. Embed the query
        query_vector = await embeddings.get_embedding(query)
    except Exception:
        # Graceful failure if embedding generation fails (e.g. network timeout or API key missing)
        return {"grounding_context": "", "sources": []}

    # 3. Retrieve candidates
    store = vector_store.get_vector_store(db_file)
    candidates = await store.search_similar_chunks(query_vector, top_n=20)

    # 4. Rerank candidates using threshold = 0.35
    reranked = ranking.rerank_chunks(candidates, top_k=top_k, score_threshold=0.35)

    # 5. Build grounding context string with size cap protection
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

    grounding_context = "\n\n".join(blocks)
    return {
        "grounding_context": grounding_context,
        "sources": sources,
    }
