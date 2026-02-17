from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


class PdfExtractError(RuntimeError):
    pass


@dataclass(frozen=True)
class PdfPages:
    title: str
    pages: list[tuple[int, str]]


def extract_pdf_pages(path: Path) -> PdfPages:
    try:
        from pypdf import PdfReader
    except Exception as e:
        raise PdfExtractError("Dependência pypdf não está instalada") from e

    try:
        reader = PdfReader(str(path))
    except Exception as e:
        raise PdfExtractError(f"Falha a abrir PDF: {e}") from e

    title = ""
    try:
        md = reader.metadata or {}
        if getattr(md, "title", None):
            title = str(md.title).strip()
        elif isinstance(md, dict) and md.get("/Title"):
            title = str(md.get("/Title")).strip()
    except Exception:
        title = ""

    pages: list[tuple[int, str]] = []
    for i, page in enumerate(reader.pages, start=1):
        try:
            text = (page.extract_text() or "").strip()
        except Exception:
            text = ""
        if text:
            pages.append((i, text))
    return PdfPages(title=title, pages=pages)

