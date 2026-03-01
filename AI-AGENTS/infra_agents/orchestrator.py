from __future__ import annotations

from pathlib import Path

from infra_agents.contracts import JobState
from infra_agents.orchestration import (
    ClassicWorkflowSupervisor,
    LangGraphUnavailableError,
    LangGraphWorkflowSupervisor,
    is_langgraph_available,
)


class WorkflowSupervisor:
    """Facade supervisor that can run classic or LangGraph workflow engines."""

    def __init__(self, max_iterations: int = 3, engine: str = "auto"):
        self.max_iterations = max_iterations
        self.engine = self._resolve_engine(engine)

        if self.engine == "langgraph":
            self._impl = LangGraphWorkflowSupervisor(max_iterations=max_iterations)
        else:
            self._impl = ClassicWorkflowSupervisor(max_iterations=max_iterations)

    def run(self, prompt: str, output_root: Path, execution_mode: str = "plan-only") -> JobState:
        return self._impl.run(prompt=prompt, output_root=output_root, execution_mode=execution_mode)

    def _resolve_engine(self, engine: str) -> str:
        allowed = {"auto", "classic", "langgraph"}
        if engine not in allowed:
            raise ValueError(f"engine inválido: {engine}. Opções: {', '.join(sorted(allowed))}")

        if engine == "auto":
            return "langgraph" if is_langgraph_available() else "classic"

        if engine == "langgraph" and not is_langgraph_available():
            raise LangGraphUnavailableError(
                "LangGraph solicitado mas não instalado. Usa `pip install -e .[langgraph]` "
                "ou corre com `--engine classic`."
            )

        return engine
