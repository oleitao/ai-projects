from __future__ import annotations

import os
from typing import Any

import requests


class OllamaClient:
    def __init__(
        self,
        *,
        base_url: str,
        chat_model: str,
        embed_model: str,
        timeout_s: int,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.chat_model = chat_model
        self.embed_model = embed_model
        self.timeout_s = timeout_s

    @classmethod
    def from_env(cls) -> "OllamaClient":
        base_url = os.environ.get("IAC_OLLAMA_BASE_URL", "http://ollama:11434")
        chat_model = os.environ.get("IAC_OLLAMA_MODEL", "llama3.1")
        embed_model = os.environ.get("IAC_OLLAMA_EMBED_MODEL", chat_model)
        timeout_s = int(os.environ.get("IAC_LLM_TIMEOUT_S", "180"))
        return cls(
            base_url=base_url,
            chat_model=chat_model,
            embed_model=embed_model,
            timeout_s=timeout_s,
        )

    def chat(self, *, system: str, user: str) -> str:
        url = f"{self.base_url}/v1/chat/completions"
        payload: dict[str, Any] = {
            "model": self.chat_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
        }
        r = requests.post(url, json=payload, timeout=self.timeout_s)
        r.raise_for_status()
        data = r.json()
        return (
            ((data.get("choices") or [{}])[0].get("message") or {}).get("content")
            or ""
        ).strip()

    def embed_text(self, text: str) -> list[float]:
        text = text.strip()
        if not text:
            return []

        # Prefer native Ollama endpoint, fall back to OpenAI-compatible endpoint.
        native_url = f"{self.base_url}/api/embeddings"
        native_payload = {"model": self.embed_model, "prompt": text}
        r = requests.post(native_url, json=native_payload, timeout=self.timeout_s)
        if r.status_code == 404:
            openai_url = f"{self.base_url}/v1/embeddings"
            openai_payload = {"model": self.embed_model, "input": text}
            r = requests.post(openai_url, json=openai_payload, timeout=self.timeout_s)
        r.raise_for_status()
        data = r.json()
        if "embedding" in data:
            return data["embedding"]
        # OpenAI-compatible shape: {"data":[{"embedding":[...]}], ...}
        return ((data.get("data") or [{}])[0].get("embedding") or [])

