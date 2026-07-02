"""
Ranking and quality-aware reranking logic for candidate document chunks.
Applies boosts for metadata signals (confidence, normalization) and penalties for low quality.
"""


def rerank_chunks(
    candidates: list[dict],
    top_k: int = 3,
    score_threshold: float = 0.35,
) -> list[dict]:
    """
    Reranks candidate chunks by adjusting their raw similarity score with quality heuristics.
    Returns the top-K chunks above the score threshold.
    """
    reranked = []
    
    for chunk in candidates:
        score = chunk["similarity"]
        
        # 1. Apply confidence boost (e.g. +0.1 for high confidence)
        confidence = chunk.get("extraction_confidence")
        if confidence is not None:
            score += confidence * 0.1
            
        # 2. Apply normalization boost
        if chunk.get("normalization_applied") == 1:
            score += 0.05
            
        # 3. Apply short chunk length penalty
        char_count = chunk.get("char_count", 0)
        if char_count < 150:
            score -= 0.15
        elif char_count < 300:
            score -= 0.05
            
        # 4. Apply parent extraction size penalty
        parent_char_count = chunk.get("extracted_char_count", 0)
        if parent_char_count < 50:
            score -= 0.20
            
        chunk_copy = dict(chunk)
        chunk_copy["final_score"] = score
        
        # 5. Suppress low score candidates
        if score >= score_threshold:
            reranked.append(chunk_copy)

    # Sort final_score descending
    reranked.sort(key=lambda x: x["final_score"], reverse=True)
    return reranked[:top_k]
