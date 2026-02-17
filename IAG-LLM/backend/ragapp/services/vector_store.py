from __future__ import annotations

import math
from array import array
from typing import Any, Iterable

from django.db import transaction

from ..models import Chunk, Document, Embedding


def _vector_to_bytes(vec: Iterable[float]) -> tuple[bytes, int, float]:
    a = array("f", (float(x) for x in vec))
    dims = len(a)
    norm = math.sqrt(sum((x * x for x in a))) if dims else 0.0
    return a.tobytes(), dims, norm


def _bytes_to_vector(b: bytes) -> array:
    a = array("f")
    a.frombytes(b)
    return a


def _dot(a: array, b: array) -> float:
    return float(sum((x * y for x, y in zip(a, b, strict=False))))


class VectorStore:
    def upsert(
        self,
        *,
        chunk: Chunk,
        embedding: list[float],
        model: str,
    ) -> None:
        vec_bytes, dims, norm = _vector_to_bytes(embedding)
        with transaction.atomic():
            Embedding.objects.update_or_create(
                chunk=chunk,
                defaults={
                    "model": model,
                    "dims": dims,
                    "vector": vec_bytes,
                    "norm": norm,
                },
            )

    def delete_document(self, document: Document) -> None:
        Chunk.objects.filter(document=document).delete()

    def search(
        self,
        query_vec: list[float],
        *,
        top_k: int = 6,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        if not query_vec:
            return []
        filters = filters or {}

        q_bytes, _, q_norm = _vector_to_bytes(query_vec)
        if q_norm == 0:
            return []
        q = _bytes_to_vector(q_bytes)

        qs = Embedding.objects.select_related("chunk", "chunk__document")
        doc_ids = (filters.get("document_ids") or []) if isinstance(filters, dict) else []
        if doc_ids:
            qs = qs.filter(chunk__document_id__in=doc_ids)

        required_tags = (
            [str(t).strip() for t in (filters.get("tags") or []) if str(t).strip()]
            if isinstance(filters, dict)
            else []
        )

        scored: list[tuple[float, Embedding]] = []
        for e in qs.iterator(chunk_size=200):
            if required_tags:
                doc_tags = {str(t).casefold() for t in (e.chunk.document.tags or [])}
                if not all(t.casefold() in doc_tags for t in required_tags):
                    continue
            if not e.norm:
                continue
            v = _bytes_to_vector(bytes(e.vector))
            score = _dot(q, v) / (q_norm * e.norm)
            scored.append((score, e))

        scored.sort(key=lambda x: x[0], reverse=True)
        results: list[dict[str, Any]] = []
        for score, e in scored[: max(1, int(top_k))]:
            c = e.chunk
            d = c.document
            page = c.metadata.get("page")
            source_uri = c.metadata.get("source_uri") or d.source_uri
            snippet = (c.text or "").strip().replace("\n", " ")
            results.append(
                {
                    "score": score,
                    "chunk_id": c.id,
                    "document_id": str(d.id),
                    "source_uri": source_uri,
                    "page": page,
                    "snippet": snippet[:240],
                }
            )
        return results
