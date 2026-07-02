"""
SQLite-backed vector storage and search abstraction.
Enables swapping backends in the future without changing ranking/retrieval callers.
"""

import json
import math
import aiosqlite


class SQLiteVectorStore:
    """Vector store implementation storing chunk embeddings in SQLite and computing similarity in Python."""

    def __init__(self, db_file: str):
        self.db_file = db_file

    async def store_chunk(
        self,
        id: str,
        attachment_id: str,
        extraction_id: str,
        chunk_index: int,
        chunk_text: str,
        char_count: int,
        token_estimate: int,
        embedding_model: str,
        embedding_vector: list[float],
    ) -> None:
        """Persist a text chunk and its embedding vector into SQLite."""
        vec_json = json.dumps(embedding_vector)
        async with aiosqlite.connect(self.db_file) as db:
            await db.execute("PRAGMA foreign_keys = ON")
            await db.execute(
                """
                INSERT INTO attachment_chunks (
                    id, attachment_id, extraction_id, chunk_index, chunk_text, char_count, token_estimate, embedding_model, embedding_vector
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    id,
                    attachment_id,
                    extraction_id,
                    chunk_index,
                    chunk_text,
                    char_count,
                    token_estimate,
                    embedding_model,
                    vec_json,
                ),
            )
            await db.commit()

    async def delete_chunks_by_attachment_id(self, attachment_id: str) -> None:
        """Remove all existing chunks associated with an attachment ID to prevent duplicate indexing."""
        async with aiosqlite.connect(self.db_file) as db:
            await db.execute("PRAGMA foreign_keys = ON")
            await db.execute(
                "DELETE FROM attachment_chunks WHERE attachment_id = ?",
                (attachment_id,),
            )
            await db.commit()

    async def search_similar_chunks(self, query_vector: list[float], top_n: int = 10) -> list[dict]:
        """
        Query all candidate chunks from successful extractions, compute similarity,
        and return the top-N candidate matches.
        """
        async with aiosqlite.connect(self.db_file) as db:
            await db.execute("PRAGMA foreign_keys = ON")
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT 
                    c.id, c.attachment_id, c.extraction_id, c.chunk_index, c.chunk_text, c.char_count, 
                    c.token_estimate, c.embedding_vector,
                    e.extraction_confidence, e.normalization_applied, e.extracted_char_count, e.status,
                    a.original_filename
                FROM attachment_chunks c
                JOIN attachment_extractions e ON c.extraction_id = e.id
                JOIN attachments a ON c.attachment_id = a.id
                WHERE e.status = 'succeeded'
                """
            ) as cursor:
                rows = await cursor.fetchall()

        results = []
        for r in rows:
            row_dict = dict(r)
            try:
                vec = json.loads(row_dict["embedding_vector"])
            except Exception:
                continue

            sim = self._cosine_similarity(query_vector, vec)
            row_dict["similarity"] = sim
            results.append(row_dict)

        # Sort similarity descending
        results.sort(key=lambda x: x["similarity"], reverse=True)
        return results[:top_n]

    def _cosine_similarity(self, v1: list[float], v2: list[float]) -> float:
        """Compute the cosine similarity between two float vectors."""
        if not v1 or not v2 or len(v1) != len(v2):
            return 0.0
        dot_product = sum(a * b for a, b in zip(v1, v2))
        norm_v1 = math.sqrt(sum(a * a for a in v1))
        norm_v2 = math.sqrt(sum(b * b for b in v2))
        if norm_v1 == 0 or norm_v2 == 0:
            return 0.0
        return dot_product / (norm_v1 * norm_v2)


def get_vector_store(db_file: str) -> SQLiteVectorStore:
    """Factory helper returning the configured vector store interface."""
    return SQLiteVectorStore(db_file)
