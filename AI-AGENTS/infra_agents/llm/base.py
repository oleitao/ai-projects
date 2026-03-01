from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(slots=True)
class LLMRequest:
    task: str
    prompt: str
    context: str
    schema_name: str


class AgentLLM(Protocol):
    """Structured generation interface used by agents."""

    def generate_structured(self, request: LLMRequest) -> dict[str, Any] | None:
        """Return structured output for a task or None when no prediction is available."""


class NoopLLM:
    """Default implementation that disables LLM generation."""

    def generate_structured(self, request: LLMRequest) -> dict[str, Any] | None:  # noqa: ARG002
        return None
