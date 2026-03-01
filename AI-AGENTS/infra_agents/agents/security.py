from __future__ import annotations

import re
from pathlib import Path

from infra_agents.agents.base import BaseAgent
from infra_agents.contracts import AgentFinding, AgentResult
from infra_agents.tools.filesystem import write_json


class SecurityPolicyAgent(BaseAgent):
    name = "Segurança/Políticas"

    def run(self, state):  # type: ignore[override]
        findings: list[AgentFinding] = []

        if state.execution_mode != "plan-only":
            findings.append(
                AgentFinding(
                    severity="critical",
                    source=self.name,
                    message="execution_mode inválido: apenas plan-only é permitido por defeito",
                )
            )

        providers_tf = Path(state.workspace, "providers.tf")
        if providers_tf.exists():
            text = providers_tf.read_text(encoding="utf-8")
            if 'provider "aws"' not in text:
                findings.append(
                    AgentFinding(
                        severity="critical",
                        source=self.name,
                        message="Provider allowlist violada: apenas aws é permitido",
                        file=str(providers_tf),
                    )
                )
            if re.search(r'provider\s+"(?!aws\")', text):
                findings.append(
                    AgentFinding(
                        severity="critical",
                        source=self.name,
                        message="Provider adicional detetado fora da allowlist",
                        file=str(providers_tf),
                    )
                )

        backend_tf = Path(state.workspace, "backend.tf")
        if backend_tf.exists():
            backend_text = backend_tf.read_text(encoding="utf-8")
            if 'backend "s3"' not in backend_text:
                findings.append(
                    AgentFinding(
                        severity="critical",
                        source=self.name,
                        message="Backend remoto deve usar S3",
                        file=str(backend_tf),
                    )
                )

        backend_hcl = Path(state.workspace, "backend.hcl.example")
        if backend_hcl.exists():
            backend_cfg = backend_hcl.read_text(encoding="utf-8")
            if "dynamodb_table" not in backend_cfg:
                findings.append(
                    AgentFinding(
                        severity="warning",
                        source=self.name,
                        message="backend.hcl.example sem lock table DynamoDB",
                        file=str(backend_hcl),
                    )
                )

        findings.extend(self._scan_tf_files(Path(state.workspace)))
        critical_found = any(f.severity == "critical" for f in findings)

        report = {
            "blocked": critical_found,
            "findings": [
                {
                    "severity": f.severity,
                    "source": f.source,
                    "message": f.message,
                    "file": f.file,
                    "line": f.line,
                }
                for f in findings
            ],
        }
        report_path = write_json(Path(state.workspace, "reports", "security.json"), report)

        return AgentResult(
            agent=self.name,
            artifacts=[report_path],
            findings=findings,
            next_action="blocked" if critical_found else "continue",
        )

    def _scan_tf_files(self, root: Path) -> list[AgentFinding]:
        findings: list[AgentFinding] = []
        for path in root.glob("*.tf"):
            lines = path.read_text(encoding="utf-8").splitlines()
            for idx, line in enumerate(lines, start=1):
                low = line.lower().strip()
                if "publicly_accessible" in low and "true" in low:
                    findings.append(
                        AgentFinding(
                            severity="critical",
                            source=self.name,
                            message="Recurso com acesso público explícito",
                            file=str(path),
                            line=idx,
                        )
                    )
                if re.search(r"\bpassword\s*=", low):
                    findings.append(
                        AgentFinding(
                            severity="critical",
                            source=self.name,
                            message="Credencial hardcoded detetada",
                            file=str(path),
                            line=idx,
                        )
                    )
                if re.search(r"akia[0-9a-z]{16}", low):
                    findings.append(
                        AgentFinding(
                            severity="critical",
                            source=self.name,
                            message="Possível AWS Access Key exposta",
                            file=str(path),
                            line=idx,
                        )
                    )
                if "storage_encrypted" in low and "false" in low:
                    findings.append(
                        AgentFinding(
                            severity="critical",
                            source=self.name,
                            message="Encriptação desativada",
                            file=str(path),
                            line=idx,
                        )
                    )
                if "manage_master_user_password" in low and "false" in low:
                    findings.append(
                        AgentFinding(
                            severity="critical",
                            source=self.name,
                            message="RDS sem password gerida pelo AWS Secrets Manager",
                            file=str(path),
                            line=idx,
                        )
                    )
                if "http_tokens" in low and "optional" in low:
                    findings.append(
                        AgentFinding(
                            severity="critical",
                            source=self.name,
                            message="IMDSv2 deve ser obrigatório (http_tokens = required)",
                            file=str(path),
                            line=idx,
                        )
                    )
        return findings
