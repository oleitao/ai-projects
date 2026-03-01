from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path


def default_knowledge_root() -> Path:
    return Path(__file__).resolve().parent / "knowledge"


@dataclass(slots=True)
class RetrievalHit:
    source: str
    score: float
    snippet: str


class LocalKnowledgeBase:
    """Simple lexical retriever over local markdown knowledge sources."""

    def __init__(self, root: Path | None = None):
        self.root = root or default_knowledge_root()
        self._documents = self._load_documents()

    def available_sources(self) -> list[str]:
        return [doc["source"] for doc in self._documents]

    def retrieve(self, query: str, top_k: int = 3) -> list[RetrievalHit]:
        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        scored: list[RetrievalHit] = []
        for doc in self._documents:
            score = self._score(query_tokens, doc["tokens"], doc["source"])
            if score <= 0:
                continue
            scored.append(
                RetrievalHit(
                    source=doc["source"],
                    score=score,
                    snippet=self._snippet(doc["content"], query_tokens),
                )
            )

        scored.sort(key=lambda hit: hit.score, reverse=True)
        return scored[:top_k]

    def render_context(self, hits: list[RetrievalHit], max_chars: int = 1400) -> str:
        if not hits:
            return ""

        parts: list[str] = []
        total = 0
        for hit in hits:
            block = f"### {hit.source}\n{hit.snippet.strip()}\n"
            if total + len(block) > max_chars:
                break
            parts.append(block)
            total += len(block)
        return "\n".join(parts).strip()

    def fetch(self, topic: str) -> str:
        topic_slug = topic.lower().replace(" ", "-")
        for doc in self._documents:
            if Path(doc["source"]).stem == topic_slug:
                return doc["content"]
        return ""

    def _load_documents(self) -> list[dict]:
        if not self.root.exists():
            return []

        docs: list[dict] = []
        for path in sorted(self.root.glob("*.md")):
            content = path.read_text(encoding="utf-8")
            docs.append(
                {
                    "source": path.name,
                    "content": content,
                    "tokens": self._tokenize(content),
                }
            )
        return docs

    def _score(self, query_tokens: set[str], doc_tokens: set[str], source: str) -> float:
        if not doc_tokens:
            return 0.0
        overlap = len(query_tokens & doc_tokens)
        if overlap == 0:
            return 0.0

        base = overlap / math.sqrt(len(doc_tokens))
        stem_tokens = self._tokenize(Path(source).stem.replace("-", " "))
        if query_tokens & stem_tokens:
            base += 0.35
        return base

    def _snippet(self, content: str, query_tokens: set[str], max_lines: int = 8) -> str:
        lines = [line.rstrip() for line in content.splitlines() if line.strip()]
        ranked = sorted(
            lines,
            key=lambda line: len(query_tokens & self._tokenize(line)),
            reverse=True,
        )
        picked = ranked[:max_lines]
        if not picked:
            return "\n".join(lines[:max_lines])
        return "\n".join(picked)

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        raw_tokens = re.findall(r"[a-z0-9_./-]{2,}", text.lower())
        tokens: set[str] = set()
        for token in raw_tokens:
            tokens.add(token)
            parts = re.split(r"[./_-]+", token)
            tokens.update(part for part in parts if len(part) >= 2)
        return tokens
