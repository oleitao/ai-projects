from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from .models import Document


def home(request: HttpRequest) -> HttpResponse:
    docs_count = Document.objects.count()
    done_count = Document.objects.filter(status=Document.Status.DONE).count()
    return render(
        request,
        "ragapp/home.html",
        {"docs_count": docs_count, "done_count": done_count},
    )


def ingest_page(request: HttpRequest) -> HttpResponse:
    documents = Document.objects.order_by("-updated_at")[:50]
    return render(request, "ragapp/ingest.html", {"documents": documents})


def chat_page(request: HttpRequest) -> HttpResponse:
    documents = Document.objects.filter(status=Document.Status.DONE).order_by("-updated_at")[
        :200
    ]
    return render(request, "ragapp/chat.html", {"documents": documents})

