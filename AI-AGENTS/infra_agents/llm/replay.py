from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from infra_agents.llm.base import LLMRequest


@dataclass(slots=True)
class ReplayExample:
    task: str
    prompt_contains: str
    output: dict[str, Any]


class ReplayLLM:
    """Offline pseudo-model used for eval and fine-tuning preparation.

    It reads examples from JSONL and returns stored structured outputs when
    the current prompt contains the configured substring for a task.
    """

    def __init__(self, examples: list[ReplayExample]):
        self.examples = examples

    @classmethod
    def from_jsonl(cls, path: Path) -> "ReplayLLM":
        examples: list[ReplayExample] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            payload = json.loads(line)
            examples.append(
                ReplayExample(
                    task=payload["task"],
                    prompt_contains=payload["prompt_contains"],
                    output=payload["output"],
                )
            )
        return cls(examples)

    def generate_structured(self, request: LLMRequest) -> dict[str, Any] | None:
        for example in self.examples:
            if example.task != request.task:
                continue
            if example.prompt_contains.lower() in request.prompt.lower():
                return example.output
        return None
