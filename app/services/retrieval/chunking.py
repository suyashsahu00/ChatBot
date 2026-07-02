"""
Chunking utilities for text parser outputs.
Implements a deterministic sliding character window.
"""


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 80) -> list[dict]:
    """
    Split text into chunks of target size with a sliding character window overlap.
    Aims to align chunks to sentence/word boundaries where possible.
    Merges tiny trailing chunks when appropriate.
    """
    chunks = []
    text_len = len(text)
    start = 0
    chunk_idx = 0

    while start < text_len:
        end = start + chunk_size
        if end >= text_len:
            end = text_len
        else:
            # Look for a word boundary (space) near the end to avoid splitting words
            space_pos = text.rfind(" ", end - 50, end)
            if space_pos != -1:
                end = space_pos

        chunk_text = text[start:end].strip()
        if chunk_text:
            chunks.append({
                "chunk_index": chunk_idx,
                "chunk_text": chunk_text,
                "char_count": len(chunk_text),
                "token_estimate": len(chunk_text) // 4,
            })
            chunk_idx += 1

        start = end - overlap
        if start <= 0 or start >= text_len or end == text_len:
            break

    # Merge tiny trailing chunk (less than 100 characters) into second-to-last chunk
    if len(chunks) > 1 and chunks[-1]["char_count"] < 100:
        last = chunks.pop()
        chunks[-1]["chunk_text"] += " " + last["chunk_text"]
        chunks[-1]["char_count"] = len(chunks[-1]["chunk_text"])
        chunks[-1]["token_estimate"] = chunks[-1]["char_count"] // 4

    return chunks
