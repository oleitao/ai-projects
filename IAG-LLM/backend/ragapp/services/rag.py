from __future__ import annotations

from typing import Any

from ..models import Chunk
from .ollama_client import OllamaClient
from .vector_store import VectorStore


def _build_context(chunks: list[Chunk]) -> str:
    parts: list[str] = []
    for c in chunks:
        page = c.metadata.get("page")
        source_uri = c.metadata.get("source_uri") or c.document.source_uri
        parts.append(
            "\n".join(
                [
                    f"[chunk_id={c.id} document_id={c.document_id} page={page} source_uri={source_uri}]",
                    c.text.strip(),
                ]
            )
        )
    return "\n\n---\n\n".join(parts)


def answer_question(
    question: str, *, filters: dict[str, Any] | None = None, top_k: int = 6
) -> tuple[str, list[dict[str, Any]]]:
    filters = filters or {}

    client = OllamaClient.from_env()
    store = VectorStore()

    query_vec = client.embed_text(question)
    results = store.search(query_vec, top_k=top_k, filters=filters)
    if not results:
        return (
            "Não encontrei informação suficiente nos documentos ingeridos para responder.",
            [],
        )

    chunk_ids = [r["chunk_id"] for r in results]
    chunks = Chunk.objects.filter(id__in=chunk_ids).select_related("document")
    chunks_by_id = {c.id: c for c in chunks}
    ordered_chunks = [chunks_by_id[cid] for cid in chunk_ids if cid in chunks_by_id]

    context = _build_context(ordered_chunks)

    system = (
        "És um assistente que responde com base no CONTEXTO fornecido. "
        "Se a resposta não estiver suportada pelo contexto, diz claramente o que falta. "
        "Sê conciso e inclui detalhes concretos quando existirem."
    )
    user = "\n".join(
        [
            "CONTEXTO:",
            context,
            "",
            f"PERGUNTA: {question}",
        ]
    )

    answer = client.chat(system=system, user=user)
    citations = [
        {
            "document_id": r["document_id"],
            "source_uri": r["source_uri"],
            "chunk_id": r["chunk_id"],
            "page": r.get("page"),
            "snippet": r.get("snippet", ""),
        }
        for r in results
    ]
    return answer, citations
