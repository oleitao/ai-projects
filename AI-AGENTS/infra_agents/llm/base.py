from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(slots=True)
class LLMRequest:
    task: str
    prompt: str
    context: str
    schema_name: str


class LLMConfigurationError(RuntimeError):
    """Raised when the configured LLM backend is invalid."""


class LLMResponseError(RuntimeError):
    """Raised when the LLM backend does not return usable structured data."""


class AgentLLM(Protocol):
    """Structured generation interface used by agents."""

    def generate_structured(self, request: LLMRequest) -> dict[str, Any]:
        """Return structured output for a task."""
