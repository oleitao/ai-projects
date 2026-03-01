from __future__ import annotations

import json
from pathlib import Path

from infra_agents.agents.base import BaseAgent
from infra_agents.contracts import AgentFinding, AgentResult
from infra_agents.tools.filesystem import write_json
from infra_agents.tools.terraform_cli import run_security_scanners, run_terraform_validation


class ValidatorAgent(BaseAgent):
    name = "Validador/QA"

    def run(self, state):  # type: ignore[override]
        findings: list[AgentFinding] = []
        commands = run_terraform_validation(state.workspace)
        scanners = run_security_scanners(state.workspace)

        report_payload = {
            "terraform": [],
            "scanners": [],
        }

        for result in commands:
            report_payload["terraform"].append(self._serialize(result))
            findings.extend(self._to_findings(result, source="terraform"))

        plan_result = self._run_plan_if_possible(commands, state.workspace)
        if plan_result is not None:
            report_payload["terraform"].append(self._serialize(plan_result))
            findings.extend(self._to_findings(plan_result, source="terraform"))

        for result in scanners:
            report_payload["scanners"].append(self._serialize(result))
            findings.extend(self._to_findings(result, source="scanner"))

        report_path = Path(state.workspace, "reports", "validation.json")
        artifact = write_json(report_path, report_payload)

        has_errors = any(f.severity == "error" for f in findings)

        return AgentResult(
            agent=self.name,
            artifacts=[artifact],
            findings=findings,
            next_action="regenerate" if has_errors else "continue",
        )

    def _run_plan_if_possible(self, terraform_results: list, workspace: Path):
        if not terraform_results:
            return None

        init_result = terraform_results[1] if len(terraform_results) > 1 else None
        validate_result = terraform_results[2] if len(terraform_results) > 2 else None

        if init_result is None or validate_result is None:
            return None
        if init_result.returncode != 0 or validate_result.returncode != 0:
            return None

        from infra_agents.tools.command_runner import run_command

        return run_command(
            ["terraform", "plan", "-lock=false", "-input=false", "-refresh=false", "-out=plan.out"],
            workspace,
        )

    def _serialize(self, result) -> dict:
        return {
            "command": " ".join(result.command),
            "returncode": result.returncode,
            "skipped": result.skipped,
            "reason": result.reason,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }

    def _to_findings(self, result, source: str) -> list[AgentFinding]:
        label = " ".join(result.command)
        if result.skipped:
            return [
                AgentFinding(
                    severity="warning",
                    source=source,
                    message=f"Comando indisponível: {label} ({result.reason})",
                )
            ]

        if result.returncode != 0:
            message = (result.stderr or result.stdout or "Falha sem detalhe").strip().splitlines()[:2]
            detail = " | ".join(message)
            severity = "warning" if self._is_environment_error(result) else "error"
            return [
                AgentFinding(
                    severity=severity,
                    source=source,
                    message=f"Falha em `{label}`: {detail}",
                )
            ]

        return []

    def _is_environment_error(self, result) -> bool:
        text = f"{result.stdout}\n{result.stderr}".lower()
        known_markers = [
            "error accessing remote module registry",
            "no such host",
            "failed to request discovery document",
            "backend initialization required",
            "module not installed",
            "no valid credential sources",
            "failed to load plugin schemas",
        ]
        return any(marker in text for marker in known_markers)
