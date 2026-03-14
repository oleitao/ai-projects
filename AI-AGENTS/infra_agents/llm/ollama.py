from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib import error, request

from infra_agents.llm.base import LLMRequest, LLMResponseError
from infra_agents.llm.schemas import schema_by_name


@dataclass(slots=True)
class OllamaConfig:
    base_url: str
    model: str
    timeout_seconds: float = 60.0
    temperature: float = 0.0


class OllamaLLM:
    """Structured generation over a local Ollama API."""

    def __init__(self, config: OllamaConfig):
        self.config = config

    def generate_structured(self, request_payload: LLMRequest) -> dict[str, Any]:
        body = self._build_request_body(request_payload)
        req = request.Request(
            url=f"{self.config.base_url.rstrip('/')}/api/generate",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with request.urlopen(req, timeout=self.config.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (error.HTTPError, error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
            raise LLMResponseError("Falha ao comunicar com o Ollama.") from exc

        content = payload.get("response", "")
        if not isinstance(content, str) or not content.strip():
            raise LLMResponseError("Ollama devolveu uma resposta vazia.")
        return self._parse_json_object(content)

    def _build_request_body(self, request_payload: LLMRequest) -> dict[str, Any]:
        schema = schema_by_name(request_payload.schema_name)
        prompt = "\n".join(
            [
                f"Task: {request_payload.task}",
                f"Schema name: {request_payload.schema_name}",
                "Return a single JSON object only.",
                "Follow the schema exactly and do not include explanations.",
                "",
                "Context:",
                request_payload.context or "(none)",
                "",
                "Input:",
                request_payload.prompt,
            ]
        )
        return {
            "model": self.config.model,
            "stream": False,
            "format": schema,
            "options": {"temperature": self.config.temperature},
            "system": (
                "You generate strict JSON for an AWS Terraform multi-agent pipeline. "
                "Do not include markdown, code fences, comments, or extra keys."
            ),
            "prompt": prompt,
        }

    def _parse_json_object(self, content: str) -> dict[str, Any]:
        cleaned = content.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()
            if cleaned.lower().startswith("json"):
                cleaned = cleaned[4:].strip()

        candidates = [cleaned]
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidates.append(cleaned[start : end + 1])

        for candidate in candidates:
            try:
                parsed = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed
        raise LLMResponseError("Ollama não devolveu um objeto JSON válido.")
