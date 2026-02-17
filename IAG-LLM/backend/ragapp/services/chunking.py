from __future__ import annotations

import re


def chunk_text_words(
    text: str, *, chunk_size_words: int = 800, chunk_overlap_words: int = 120
) -> list[str]:
    words = [w for w in re.split(r"\s+", (text or "").strip()) if w]
    if not words:
        return []

    chunk_size_words = max(1, int(chunk_size_words))
    chunk_overlap_words = max(0, int(chunk_overlap_words))
    if chunk_overlap_words >= chunk_size_words:
        chunk_overlap_words = max(0, chunk_size_words // 4)

    chunks: list[str] = []
    start = 0
    while start < len(words):
        end = min(len(words), start + chunk_size_words)
        chunk = " ".join(words[start:end]).strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(words):
            break
        start = max(0, end - chunk_overlap_words)
        if start == end:
            start = end
    return chunks

