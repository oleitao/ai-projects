from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any, Iterable

from django.conf import settings
from django.core.files.uploadedfile import UploadedFile
from django.db import transaction

from ..models import Chunk, Document
from .chunking import chunk_text_words
from .ollama_client import OllamaClient
from .pdf_extract import extract_pdf_pages
from .url_fetch import UrlFetchError, fetch_url_text
from .vector_store import VectorStore


def _normalize_tags(tags: Iterable[str]) -> list[str]:
    out: list[str] = []
    seen = set()
    for t in tags or []:
        t2 = str(t).strip()
        if not t2:
            continue
        key = t2.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(t2)
    return out


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def ingest_document_from_upload(uploaded: UploadedFile, *, tags: list[str] | None = None) -> Document:
    tags = _normalize_tags(tags or [])
    doc = Document.objects.create(
        source_type=Document.SourceType.PDF_UPLOAD,
        source_uri=uploaded.name,
        title=Path(uploaded.name).stem,
        tags=tags,
        status=Document.Status.QUEUED,
    )

    # Persist file via Django storage.
    doc.status = Document.Status.PROCESSING
    doc.save(update_fields=["status"])
    doc.uploaded_file.save(uploaded.name, uploaded)
    doc.source_uri = doc.uploaded_file.name
    doc.save(update_fields=["uploaded_file", "source_uri"])

    return _process_pdf_document(doc, Path(doc.uploaded_file.path))


def ingest_document_from_local_pdf(
    pdf_path: str | Path, *, tags: list[str] | None = None
) -> Document:
    tags = _normalize_tags(tags or [])
    path = Path(pdf_path)
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(str(path))

    checksum = _sha256_file(path)
    existing = Document.objects.filter(checksum=checksum, status=Document.Status.DONE).first()
    if existing:
        return existing

    doc = Document.objects.create(
        source_type=Document.SourceType.PDF_LOCAL,
        source_uri=str(path),
        title=path.stem,
        checksum=checksum,
        tags=tags,
        status=Document.Status.QUEUED,
    )
    return _process_pdf_document(doc, path)


def ingest_document_from_url(url: str, *, tags: list[str] | None = None) -> Document:
    tags = _normalize_tags(tags or [])
    existing = Document.objects.filter(source_type=Document.SourceType.URL, source_uri=url, status=Document.Status.DONE).first()
    if existing:
        return existing

    doc = Document.objects.create(
        source_type=Document.SourceType.URL,
        source_uri=url,
        title=url,
        tags=tags,
        status=Document.Status.QUEUED,
    )
    return _process_url_document(doc, url)


def ingest_from_batch_defaults(
    *, pdf_glob: str | None = None, url_list_file: str | None = None
) -> dict[str, Any]:
    repo_root = Path(settings.BASE_DIR).parent
    pdf_glob = pdf_glob or "data-to-ingest/*.pdf"
    url_list_file = url_list_file or "data-to-ingest/links.txt"

    pdf_paths = sorted(repo_root.glob(pdf_glob))
    urls_path = repo_root / url_list_file
    urls: list[str] = []
    if urls_path.exists():
        urls = [
            line.strip()
            for line in urls_path.read_text(encoding="utf-8", errors="ignore").splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]

    pdf_docs: list[str] = []
    url_docs: list[str] = []
    errors: list[str] = []
    for p in pdf_paths:
        try:
            d = ingest_document_from_local_pdf(p, tags=[])
            pdf_docs.append(str(d.id))
        except Exception as e:
            errors.append(f"pdf:{p}: {e}")

    for u in urls:
        try:
            d = ingest_document_from_url(u, tags=[])
            url_docs.append(str(d.id))
        except Exception as e:
            errors.append(f"url:{u}: {e}")

    return {
        "pdf_glob": pdf_glob,
        "url_list_file": url_list_file,
        "pdf_count": len(pdf_docs),
        "url_count": len(url_docs),
        "pdf_document_ids": pdf_docs,
        "url_document_ids": url_docs,
        "errors": errors,
    }


def _process_pdf_document(doc: Document, path: Path) -> Document:
    doc.status = Document.Status.PROCESSING
    doc.error = ""
    doc.save(update_fields=["status", "error"])

    try:
        pages = extract_pdf_pages(path)
        if pages.title and not doc.title:
            doc.title = pages.title
        if not doc.checksum:
            doc.checksum = _sha256_file(path)
        doc.save(update_fields=["title", "checksum"])

        _index_text_pages(
            doc,
            [(page_num, text) for page_num, text in pages.pages],
            source_uri=doc.source_uri,
        )
        doc.status = Document.Status.DONE
        doc.save(update_fields=["status"])
        return doc
    except Exception as e:
        doc.status = Document.Status.FAILED
        doc.error = str(e)
        doc.save(update_fields=["status", "error"])
        return doc


def _process_url_document(doc: Document, url: str) -> Document:
    doc.status = Document.Status.PROCESSING
    doc.error = ""
    doc.save(update_fields=["status", "error"])

    try:
        fetched = fetch_url_text(url)
        if fetched.title and doc.title == url:
            doc.title = fetched.title
        doc.source_uri = fetched.final_url
        doc.checksum = _sha256_bytes(fetched.content_bytes)
        doc.save(update_fields=["title", "source_uri", "checksum"])

        _index_text_pages(
            doc,
            [(None, fetched.text)],
            source_uri=fetched.final_url,
        )
        doc.status = Document.Status.DONE
        doc.save(update_fields=["status"])
        return doc
    except UrlFetchError as e:
        doc.status = Document.Status.FAILED
        doc.error = str(e)
        doc.save(update_fields=["status", "error"])
        return doc
    except Exception as e:
        doc.status = Document.Status.FAILED
        doc.error = str(e)
        doc.save(update_fields=["status", "error"])
        return doc


def _index_text_pages(
    doc: Document,
    pages: list[tuple[int | None, str]],
    *,
    source_uri: str,
) -> None:
    client = OllamaClient.from_env()
    store = VectorStore()
    chunk_size = int(os.environ.get("IAC_CHUNK_SIZE_WORDS", "800"))
    overlap = int(os.environ.get("IAC_CHUNK_OVERLAP_WORDS", "120"))

    chunk_index = 0
    for page_num, page_text in pages:
        for chunk_text in chunk_text_words(
            page_text, chunk_size_words=chunk_size, chunk_overlap_words=overlap
        ):
            chunk_id = f"{doc.id}:{chunk_index}"
            metadata: dict[str, Any] = {"source_uri": source_uri}
            if page_num is not None:
                metadata["page"] = int(page_num)
            c = Chunk.objects.create(
                id=chunk_id,
                document=doc,
                chunk_index=chunk_index,
                text=chunk_text,
                metadata=metadata,
            )
            emb = client.embed_text(chunk_text)
            store.upsert(chunk=c, embedding=emb, model=client.embed_model)
            chunk_index += 1

