from __future__ import annotations

from abc import ABC, abstractmethod

from infra_agents.contracts import AgentResult, JobState


class BaseAgent(ABC):
    name = "base"

    @abstractmethod
    def run(self, state: JobState) -> AgentResult:
        raise NotImplementedError
