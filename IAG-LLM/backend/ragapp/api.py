from __future__ import annotations

import json
from typing import Any

from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .models import ChatSession, ChatTurn, Document
from .services.ingest import ingest_document_from_local_pdf, ingest_document_from_upload, ingest_document_from_url, ingest_from_batch_defaults
from .services.rag import answer_question


def _json_body(request: HttpRequest) -> dict[str, Any]:
    try:
        return json.loads((request.body or b"{}").decode("utf-8"))
    except Exception:
        return {}


@require_GET
def documents_list(request: HttpRequest) -> JsonResponse:
    qs = Document.objects.order_by("-updated_at")[:200]
    data = [
        {
            "id": str(d.id),
            "source_type": d.source_type,
            "source_uri": d.source_uri,
            "title": d.title,
            "checksum": d.checksum,
            "tags": d.tags,
            "status": d.status,
            "error": d.error,
            "created_at": d.created_at.isoformat(),
            "updated_at": d.updated_at.isoformat(),
        }
        for d in qs
    ]
    return JsonResponse({"documents": data})


@csrf_exempt
@require_POST
def ingest_pdf(request: HttpRequest) -> JsonResponse:
    uploaded = request.FILES.get("file")
    tags_raw = request.POST.get("tags", "")
    tags = [t.strip() for t in tags_raw.split(",") if t.strip()]
    if not uploaded:
        return JsonResponse({"error": "missing file"}, status=400)
    doc = ingest_document_from_upload(uploaded, tags=tags)
    return JsonResponse({"document_id": str(doc.id), "status": doc.status})


@csrf_exempt
@require_POST
def ingest_url(request: HttpRequest) -> JsonResponse:
    body = _json_body(request)
    url = (body.get("url") or "").strip()
    tags = body.get("tags") or []
    if not url:
        return JsonResponse({"error": "missing url"}, status=400)
    doc = ingest_document_from_url(url, tags=tags)
    return JsonResponse({"document_id": str(doc.id), "status": doc.status})


@csrf_exempt
@require_POST
def ingest_batch(request: HttpRequest) -> JsonResponse:
    body = _json_body(request)
    pdf_glob = body.get("pdf_glob")
    url_list_file = body.get("url_list_file")
    result = ingest_from_batch_defaults(pdf_glob=pdf_glob, url_list_file=url_list_file)
    return JsonResponse(result)


@csrf_exempt
@require_POST
def chat_ask(request: HttpRequest) -> JsonResponse:
    body = _json_body(request)
    question = (body.get("question") or "").strip()
    if not question:
        return JsonResponse({"error": "missing question"}, status=400)

    session_id = body.get("session_id")
    session: ChatSession | None
    if session_id:
        session = ChatSession.objects.filter(id=session_id).first()
    else:
        session = None
    if session is None:
        session = ChatSession.objects.create()

    filters = body.get("filters") or {}
    top_k = int(body.get("top_k") or 6)
    answer, citations = answer_question(question, filters=filters, top_k=top_k)

    ChatTurn.objects.create(
        session=session, question=question, answer=answer, citations=citations
    )
    return JsonResponse(
        {
            "session_id": str(session.id),
            "answer": answer,
            "citations": citations,
        }
    )

