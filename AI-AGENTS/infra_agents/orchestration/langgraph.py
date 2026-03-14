from __future__ import annotations

from pathlib import Path
from typing import TypedDict

from infra_agents.agents.cost import CostAgent
from infra_agents.agents.generator import TerraformGeneratorAgent
from infra_agents.agents.planner import ArchitecturePlannerAgent
from infra_agents.agents.requirements import RequirementsAgent
from infra_agents.agents.security import SecurityPolicyAgent
from infra_agents.agents.validator import ValidatorAgent
from infra_agents.contracts import JobState
from infra_agents.llm import build_llm_from_env
from infra_agents.orchestration.common import create_job_state, info_finding, write_job_summary
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


def is_langgraph_available() -> bool:
    return LANGGRAPH_AVAILABLE


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
        }
        final_state = self.graph.invoke(initial_state)
        return final_state["job"]

    def _build_graph(self):
        builder = StateGraph(GraphState)

        builder.add_node("requirements", self._requirements_node)
        builder.add_node("planner", self._planner_node)
        builder.add_node("generator", self._generator_node)
        builder.add_node("prepare_iteration", self._prepare_iteration_node)
        builder.add_node("validator", self._validator_node)
        builder.add_node("security", self._security_node)
        builder.add_node("cost", self._cost_node)
        builder.add_node("finalize", self._finalize_node)

        builder.add_edge(START, "requirements")
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

    def _requirements_node(self, state: GraphState) -> GraphState:
        job = state["job"]
        job.add_result(self.requirements.run(job))
        return state

    def _planner_node(self, state: GraphState) -> GraphState:
        job = state["job"]
        job.add_result(self.planner.run(job))
        return state

    def _generator_node(self, state: GraphState) -> GraphState:
        job = state["job"]
        job.add_result(self.generator.run(job))
        return state

    def _prepare_iteration_node(self, state: GraphState) -> GraphState:
        state["job"].iteration += 1
        return state

    def _validator_node(self, state: GraphState) -> GraphState:
        job = state["job"]
        result = self.validator.run(job)
        job.add_result(result)
        state["last_validation_has_errors"] = any(f.severity == "error" for f in result.findings)
        return state

    def _security_node(self, state: GraphState) -> GraphState:
        job = state["job"]
        result = self.security.run(job)
        job.add_result(result)
        state["last_security_blocked"] = any(f.severity == "critical" for f in result.findings)
        return state

    def _route_after_security(self, state: GraphState) -> str:
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

    def _cost_node(self, state: GraphState) -> GraphState:
        job = state["job"]
        job.add_result(self.cost.run(job))
        if job.status == "running":
            job.status = "done"
        return state

    def _finalize_node(self, state: GraphState) -> GraphState:
        write_job_summary(state["job"])
        return state
