"""
Developer debug endpoint to inspect chunk retrieval and scoring.
Gated by settings.enable_debug_routes toggle.
"""

import aiosqlite
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from app.core.config import settings
from app.services.retrieval import embeddings, vector_store, ranking

router = APIRouter()


@router.get("/debug/retrieval")
async def debug_retrieval_endpoint(
    query: Optional[str] = Query(None),
    attachment_id: Optional[str] = Query(None),
):
    """
    Retrieves diagnostics on chunk retrieval, raw similarity, reranked scores,
    and indexed counts. Only accessible if enable_debug_routes is True.
    """
    if not settings.enable_debug_routes:
        raise HTTPException(status_code=404, detail="Not Found")

    db_file = settings.database_file

    # Case 1: Query analysis
    if query is not None:
        try:
            query_vector = await embeddings.get_embedding(query)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to generate query embedding: {str(e)}")

        store = vector_store.get_vector_store(db_file)
        candidates = await store.search_similar_chunks(query_vector, top_n=20)
        reranked = ranking.rerank_chunks(candidates, top_k=settings.rag_top_k, score_threshold=settings.rag_score_threshold)

        return {
            "query": query,
            "raw_candidates": [
                {
                    "id": c["id"],
                    "attachment_id": c["attachment_id"],
                    "original_filename": c.get("original_filename"),
                    "chunk_index": c["chunk_index"],
                    "similarity": c["similarity"],
                }
                for c in candidates
            ],
            "reranked_results": [
                {
                    "attachment_id": r["attachment_id"],
                    "filename": r.get("original_filename"),
                    "chunk_index": r["chunk_index"],
                    "similarity": r["similarity"],
                    "final_score": r["final_score"],
                }
                for r in reranked
            ],
        }

    # Case 2: Attachment details inspection
    if attachment_id is not None:
        async with aiosqlite.connect(db_file) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT id, attachment_id, extraction_id, chunk_index, chunk_text, char_count, token_estimate 
                FROM attachment_chunks 
                WHERE attachment_id = ? 
                ORDER BY chunk_index ASC
                """,
                (attachment_id,),
            ) as cursor:
                rows = await cursor.fetchall()
        return {
            "attachment_id": attachment_id,
            "chunks": [dict(r) for r in rows],
        }

    # Case 3: Summary statistics
    async with aiosqlite.connect(db_file) as db:
        async with db.execute("SELECT COUNT(*) FROM attachment_chunks") as cursor:
            total_chunks = (await cursor.fetchone())[0]
        async with db.execute("SELECT COUNT(DISTINCT attachment_id) FROM attachment_chunks") as cursor:
            total_attachments = (await cursor.fetchone())[0]

    return {
        "total_chunks": total_chunks,
        "total_attachments": total_attachments,
    }
