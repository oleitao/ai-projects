from __future__ import annotations

from pathlib import Path

from infra_agents.agents.base import BaseAgent
from infra_agents.contracts import AgentFinding, AgentResult
from infra_agents.tools.cost import run_infracost
from infra_agents.tools.filesystem import write_json


class CostAgent(BaseAgent):
    name = "Custos"

    def run(self, state):  # type: ignore[override]
        findings: list[AgentFinding] = []
        result = run_infracost(state.workspace)

        report_path = Path(state.workspace, "reports", "cost.json")

        if result.skipped:
            estimate = self._heuristic_estimate(state)
            payload = {
                "source": "heuristic",
                "message": "Infracost não disponível; estimativa heurística aplicada",
                "estimate_monthly_usd": estimate,
            }
            findings.append(
                AgentFinding(
                    severity="warning",
                    source=self.name,
                    message="Infracost indisponível; usar estimativa heurística",
                )
            )
        elif result.returncode != 0:
            payload = {
                "source": "infracost",
                "error": (result.stderr or result.stdout).strip(),
            }
            findings.append(
                AgentFinding(
                    severity="warning",
                    source=self.name,
                    message="Infracost falhou; validar custo manualmente",
                )
            )
        else:
            payload = {
                "source": "infracost",
                "message": "Relatório detalhado em reports/infracost.json",
            }

        artifact = write_json(report_path, payload)

        return AgentResult(
            agent=self.name,
            artifacts=[artifact],
            findings=findings,
            next_action="done",
        )

    def _heuristic_estimate(self, state) -> float:
        if state.spec is None:
            return 0.0

        base = 20.0
        compute = state.spec.compute
        if compute.type == "eks":
            base += 120.0
        elif compute.type == "ecs":
            base += 40.0
        else:
            base += 30.0

        if state.spec.data.rds:
            base += 35.0 if state.spec.data.engine == "postgres" else 30.0
            if state.spec.data.multi_az:
                base += 30.0

        return round(base, 2)
