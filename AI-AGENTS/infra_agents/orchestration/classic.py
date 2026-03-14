from __future__ import annotations

from pathlib import Path

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


class ClassicWorkflowSupervisor:
    """Classic workflow supervisor without LangGraph runtime."""

    def __init__(self, max_iterations: int = 3):
        self.max_iterations = max_iterations
        self.knowledge_base = LocalKnowledgeBase()
        self.llm = build_llm_from_env()
        self.requirements = RequirementsAgent(knowledge_base=self.knowledge_base, llm=self.llm)
        self.planner = ArchitecturePlannerAgent(knowledge_base=self.knowledge_base, llm=self.llm)
        self.generator = TerraformGeneratorAgent(knowledge_base=self.knowledge_base, llm=self.llm)
        self.validator = ValidatorAgent()
        self.security = SecurityPolicyAgent()
        self.cost = CostAgent()

    def run(
        self,
        prompt: str,
        output_root: Path,
        execution_mode: str = "plan-only",
        validation_mode: str = "auto",
    ) -> JobState:
        state = create_job_state(
            prompt=prompt,
            output_root=output_root,
            execution_mode=execution_mode,
            validation_mode=validation_mode,
            max_iterations=self.max_iterations,
        )

        # Stage 1: requirements + design + initial generation
        state.add_result(self.requirements.run(state))
        state.add_result(self.planner.run(state))
        state.add_result(self.generator.run(state))

        # Stage 2: controlled loop between generator and validators
        for iteration in range(1, state.max_iterations + 1):
            state.iteration = iteration
            validation_result = self.validator.run(state)
            state.add_result(validation_result)

            security_result = self.security.run(state)
            state.add_result(security_result)

            has_errors = any(f.severity == "error" for f in validation_result.findings)
            blocked = any(f.severity == "critical" for f in security_result.findings)

            if blocked:
                state.blocked = True
                state.status = "blocked"
                break

            if not has_errors:
                state.status = "validated"
                break

            if iteration < state.max_iterations:
                note = (
                    "Regeneração automática acionada por falhas de validação "
                    f"(iteração {iteration}/{state.max_iterations})."
                )
                state.findings.append(info_finding(note))
                state.add_result(self.generator.run(state))
            else:
                state.status = "failed"

        # Stage 3: costs + summary
        state.add_result(self.cost.run(state))
        if state.status == "running":
            state.status = "done"

        write_job_summary(state)
        return state
