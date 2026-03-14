from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import TypedDict

from infra_agents.agents.cost import CostAgent
from infra_agents.agents.generator import TerraformGeneratorAgent
from infra_agents.agents.planner import ArchitecturePlannerAgent
from infra_agents.agents.requirements import RequirementsAgent
from infra_agents.agents.security import SecurityPolicyAgent
from infra_agents.agents.validator import ValidatorAgent
from infra_agents.contracts import JobState
from infra_agents.llm import build_llm_from_env
from infra_agents.orchestration.common import (
    create_job_state,
    info_finding,
    load_runtime_checkpoint,
    write_job_summary,
    write_runtime_checkpoint,
)
from infra_agents.rag import LocalKnowledgeBase

try:
    from langgraph.graph import END, START, StateGraph

    LANGGRAPH_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised when dependency missing
    END = "__end__"
    START = "__start__"
    StateGraph = None
    LANGGRAPH_AVAILABLE = False


class LangGraphUnavailableError(RuntimeError):
    """Raised when langgraph runtime is requested but unavailable."""


class GraphState(TypedDict):
    job: JobState
    last_validation_has_errors: bool
    last_security_blocked: bool
    next_node: str
    node_attempts: dict[str, int]


def is_langgraph_available() -> bool:
    return LANGGRAPH_AVAILABLE


GRAPH_NODES = (
    "requirements",
    "planner",
    "generator",
    "prepare_iteration",
    "validator",
    "security",
    "cost",
    "finalize",
)


class LangGraphWorkflowSupervisor:
    """LangGraph orchestration while preserving current workflow behavior."""

    def __init__(self, max_iterations: int = 3):
        if not LANGGRAPH_AVAILABLE:
            raise LangGraphUnavailableError(
                "LangGraph não está instalado. Instala com `pip install -e .[langgraph]`."
            )

        self.max_iterations = max_iterations
        self.knowledge_base = LocalKnowledgeBase()
        self.llm = build_llm_from_env()
        self.requirements = RequirementsAgent(knowledge_base=self.knowledge_base, llm=self.llm)
        self.planner = ArchitecturePlannerAgent(knowledge_base=self.knowledge_base, llm=self.llm)
        self.generator = TerraformGeneratorAgent(knowledge_base=self.knowledge_base, llm=self.llm)
        self.validator = ValidatorAgent()
        self.security = SecurityPolicyAgent()
        self.cost = CostAgent()
        self.graph = self._build_graph()

    def run(
        self,
        prompt: str,
        output_root: Path,
        execution_mode: str = "plan-only",
        validation_mode: str = "auto",
    ) -> JobState:
        job = create_job_state(
            prompt=prompt,
            output_root=output_root,
            execution_mode=execution_mode,
            validation_mode=validation_mode,
            max_iterations=self.max_iterations,
        )

        initial_state: GraphState = {
            "job": job,
            "last_validation_has_errors": False,
            "last_security_blocked": False,
            "next_node": job.next_step or "requirements",
            "node_attempts": {},
        }
        self._persist_checkpoint(initial_state)
        final_state = self.graph.invoke(initial_state)
        return final_state["job"]

    def resume(self, workspace: Path) -> JobState:
        checkpoint = load_runtime_checkpoint(workspace)
        engine = checkpoint.get("engine", "")
        if engine and engine != "langgraph":
            raise ValueError(f"Checkpoint incompatível para engine langgraph: {engine}")

        job = checkpoint["job"]
        runtime = checkpoint.get("runtime", {})
        next_node = str(runtime.get("next_node") or job.next_step or "")
        if not next_node:
            raise ValueError(f"Job já terminado; não há next_step para retomar em {workspace}")

        initial_state: GraphState = {
            "job": job,
            "last_validation_has_errors": bool(runtime.get("last_validation_has_errors", False)),
            "last_security_blocked": bool(runtime.get("last_security_blocked", False)),
            "next_node": next_node,
            "node_attempts": {
                str(key): int(value)
                for key, value in dict(runtime.get("node_attempts", {})).items()
            },
        }
        final_state = self.graph.invoke(initial_state)
        return final_state["job"]

    def _build_graph(self):
        builder = StateGraph(GraphState)

        builder.add_node("dispatch", self._dispatch_node)
        builder.add_node("requirements", self._requirements_node)
        builder.add_node("planner", self._planner_node)
        builder.add_node("generator", self._generator_node)
        builder.add_node("prepare_iteration", self._prepare_iteration_node)
        builder.add_node("validator", self._validator_node)
        builder.add_node("security", self._security_node)
        builder.add_node("cost", self._cost_node)
        builder.add_node("finalize", self._finalize_node)

        builder.add_edge(START, "dispatch")
        builder.add_conditional_edges(
            "dispatch",
            self._route_from_dispatch,
            {node: node for node in GRAPH_NODES},
        )
        builder.add_edge("requirements", "planner")
        builder.add_edge("planner", "generator")
        builder.add_edge("generator", "prepare_iteration")
        builder.add_edge("prepare_iteration", "validator")
        builder.add_edge("validator", "security")
        builder.add_conditional_edges(
            "security",
            self._route_after_security,
            {
                "generator": "generator",
                "cost": "cost",
            },
        )
        builder.add_edge("cost", "finalize")
        builder.add_edge("finalize", END)

        return builder.compile()

    def _dispatch_node(self, state: GraphState) -> GraphState:
        return state

    def _route_from_dispatch(self, state: GraphState) -> str:
        return state["next_node"] if state["next_node"] in GRAPH_NODES else "requirements"

    def _requirements_node(self, state: GraphState) -> GraphState:
        return self._execute_step(
            state,
            "requirements",
            lambda job: self.requirements.run(job),
            next_node="planner",
        )

    def _planner_node(self, state: GraphState) -> GraphState:
        return self._execute_step(
            state,
            "planner",
            lambda job: self.planner.run(job),
            next_node="generator",
        )

    def _generator_node(self, state: GraphState) -> GraphState:
        return self._execute_step(
            state,
            "generator",
            lambda job: self.generator.run(job),
            next_node="prepare_iteration",
        )

    def _prepare_iteration_node(self, state: GraphState) -> GraphState:
        started_at, started_perf, attempt = self._begin_step(state, "prepare_iteration")
        job = state["job"]
        job.iteration += 1
        self._complete_step(
            state,
            step="prepare_iteration",
            started_at=started_at,
            started_perf=started_perf,
            attempt=attempt,
            next_node="validator",
            details={"iteration": job.iteration},
        )
        return state

    def _validator_node(self, state: GraphState) -> GraphState:
        started_at, started_perf, attempt = self._begin_step(state, "validator")
        job = state["job"]
        try:
            result = self.validator.run(job)
            job.add_result(result)
            state["last_validation_has_errors"] = any(f.severity == "error" for f in result.findings)
        except Exception as exc:  # pragma: no cover - defensive path
            self._fail_step(
                state,
                step="validator",
                started_at=started_at,
                started_perf=started_perf,
                attempt=attempt,
                exc=exc,
            )
            raise

        self._complete_step(
            state,
            step="validator",
            started_at=started_at,
            started_perf=started_perf,
            attempt=attempt,
            next_node="security",
            details={"findings": len(result.findings), "next_action": result.next_action},
        )
        return state

    def _security_node(self, state: GraphState) -> GraphState:
        started_at, started_perf, attempt = self._begin_step(state, "security")
        job = state["job"]
        try:
            result = self.security.run(job)
            job.add_result(result)
            state["last_security_blocked"] = any(f.severity == "critical" for f in result.findings)
            next_node = self._decide_after_security(state)
        except Exception as exc:  # pragma: no cover - defensive path
            self._fail_step(
                state,
                step="security",
                started_at=started_at,
                started_perf=started_perf,
                attempt=attempt,
                exc=exc,
            )
            raise

        self._complete_step(
            state,
            step="security",
            started_at=started_at,
            started_perf=started_perf,
            attempt=attempt,
            next_node=next_node,
            details={"findings": len(result.findings), "blocked": state["last_security_blocked"]},
        )
        return state

    def _route_after_security(self, state: GraphState) -> str:
        return state["next_node"]

    def _cost_node(self, state: GraphState) -> GraphState:
        started_at, started_perf, attempt = self._begin_step(state, "cost")
        job = state["job"]
        try:
            result = self.cost.run(job)
            job.add_result(result)
            if job.status == "running":
                job.status = "done"
        except Exception as exc:  # pragma: no cover - defensive path
            self._fail_step(
                state,
                step="cost",
                started_at=started_at,
                started_perf=started_perf,
                attempt=attempt,
                exc=exc,
            )
            raise

        self._complete_step(
            state,
            step="cost",
            started_at=started_at,
            started_perf=started_perf,
            attempt=attempt,
            next_node="finalize",
            details={"findings": len(result.findings)},
        )
        return state

    def _finalize_node(self, state: GraphState) -> GraphState:
        started_at, started_perf, attempt = self._begin_step(state, "finalize")
        job = state["job"]
        self._complete_step(
            state,
            step="finalize",
            started_at=started_at,
            started_perf=started_perf,
            attempt=attempt,
            next_node="",
            details={"status": job.status},
        )
        write_job_summary(job)
        return state

    def _decide_after_security(self, state: GraphState) -> str:
        job = state["job"]

        if state["last_security_blocked"]:
            job.blocked = True
            job.status = "blocked"
            return "cost"

        if state["last_validation_has_errors"]:
            if job.iteration < job.max_iterations:
                note = (
                    "Regeneração automática acionada por falhas de validação "
                    f"(iteração {job.iteration}/{job.max_iterations})."
                )
                job.findings.append(info_finding(note))
                return "generator"

            job.status = "failed"
            return "cost"

        job.status = "validated"
        return "cost"

    def _execute_step(
        self,
        state: GraphState,
        step: str,
        runner,
        *,
        next_node: str,
    ) -> GraphState:
        started_at, started_perf, attempt = self._begin_step(state, step)
        job = state["job"]
        try:
            result = runner(job)
            job.add_result(result)
        except Exception as exc:  # pragma: no cover - defensive path
            self._fail_step(
                state,
                step=step,
                started_at=started_at,
                started_perf=started_perf,
                attempt=attempt,
                exc=exc,
            )
            raise

        self._complete_step(
            state,
            step=step,
            started_at=started_at,
            started_perf=started_perf,
            attempt=attempt,
            next_node=next_node,
            details={"findings": len(result.findings), "artifacts": len(result.artifacts)},
        )
        return state

    def _begin_step(self, state: GraphState, step: str) -> tuple[str, float, int]:
        attempts = state["node_attempts"]
        attempt = attempts.get(step, 0) + 1
        attempts[step] = attempt
        job = state["job"]
        job.current_step = step
        job.next_step = step
        state["next_node"] = step
        return self._utcnow(), perf_counter(), attempt

    def _complete_step(
        self,
        state: GraphState,
        *,
        step: str,
        started_at: str,
        started_perf: float,
        attempt: int,
        next_node: str,
        details: dict[str, object],
    ) -> None:
        finished_at = self._utcnow()
        duration_ms = int((perf_counter() - started_perf) * 1000)
        job = state["job"]
        job.current_step = None
        job.next_step = next_node or None
        state["next_node"] = next_node
        job.add_runtime_trace(
            step=step,
            status="completed",
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
            attempt=attempt,
            details=details,
        )
        self._persist_checkpoint(state)

    def _fail_step(
        self,
        state: GraphState,
        *,
        step: str,
        started_at: str,
        started_perf: float,
        attempt: int,
        exc: Exception,
    ) -> None:
        finished_at = self._utcnow()
        duration_ms = int((perf_counter() - started_perf) * 1000)
        job = state["job"]
        job.add_runtime_trace(
            step=step,
            status="failed",
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
            attempt=attempt,
            details={"error": str(exc)},
        )
        self._persist_checkpoint(state)
        write_job_summary(job)

    def _persist_checkpoint(self, state: GraphState) -> None:
        write_runtime_checkpoint(
            state=state["job"],
            engine="langgraph",
            runtime={
                "last_validation_has_errors": state["last_validation_has_errors"],
                "last_security_blocked": state["last_security_blocked"],
                "next_node": state["next_node"],
                "node_attempts": state["node_attempts"],
            },
        )

    @staticmethod
    def _utcnow() -> str:
        return datetime.now(timezone.utc).isoformat()
