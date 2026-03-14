from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path
import re
from typing import Any


class SpecValidationError(ValueError):
    """Raised when spec content is invalid."""


@dataclass(slots=True)
class NetworkSpec:
    vpc_cidr: str = "10.0.0.0/16"
    public_subnets: list[str] = field(default_factory=lambda: ["10.0.1.0/24", "10.0.2.0/24"])
    private_subnets: list[str] = field(default_factory=lambda: ["10.0.11.0/24", "10.0.12.0/24"])


@dataclass(slots=True)
class ComputeSpec:
    type: str = "ecs"
    sizing: str = "small"
    autoscaling: bool = True


@dataclass(slots=True)
class DataSpec:
    rds: bool = True
    engine: str = "postgres"
    multi_az: bool = True
    backups: bool = True


@dataclass(slots=True)
class SecuritySpec:
    encryption: bool = True
    public_access: bool = False


@dataclass(slots=True)
class AwsSpec:
    account_id: str = "123456789012"
    profile: str = ""
    backend_bucket: str = "terraform-state-example"
    backend_dynamodb_table: str = "terraform-state-locks"
    backend_key_prefix: str = "infra-agents"


@dataclass(slots=True)
class InfrastructureSpec:
    cloud: str = "aws"
    region: str = "eu-west-1"
    env: str = "prod"
    aws: AwsSpec = field(default_factory=AwsSpec)
    network: NetworkSpec = field(default_factory=NetworkSpec)
    compute: ComputeSpec = field(default_factory=ComputeSpec)
    data: DataSpec = field(default_factory=DataSpec)
    security: SecuritySpec = field(default_factory=SecuritySpec)
    tags: dict[str, str] = field(default_factory=lambda: {"owner": "platform-team", "cost_center": "shared"})
    assumptions: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "InfrastructureSpec":
        aws = AwsSpec(**payload.get("aws", {}))
        network = NetworkSpec(**payload.get("network", {}))
        compute = ComputeSpec(**payload.get("compute", {}))
        data = DataSpec(**payload.get("data", {}))
        security = SecuritySpec(**payload.get("security", {}))
        spec = cls(
            cloud=payload.get("cloud", "aws"),
            region=payload.get("region", "eu-west-1"),
            env=payload.get("env", "prod"),
            aws=aws,
            network=network,
            compute=compute,
            data=data,
            security=security,
            tags=payload.get("tags", {"owner": "platform-team", "cost_center": "shared"}),
            assumptions=list(payload.get("assumptions", [])),
        )
        spec.validate()
        return spec

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def validate(self) -> None:
        if self.cloud not in {"aws"}:
            raise SpecValidationError("Only aws cloud is allowed in this MVP")
        if not re.match(r"^[a-z]{2}-[a-z]+-\d$", self.region):
            raise SpecValidationError("region must follow aws format, e.g. eu-west-1")
        if self.env not in {"dev", "staging", "prod"}:
            raise SpecValidationError("env must be dev, staging or prod")
        if self.aws.account_id and not re.match(r"^\d{12}$", self.aws.account_id):
            raise SpecValidationError("aws.account_id must have 12 digits")
        if not self.aws.backend_bucket:
            raise SpecValidationError("aws.backend_bucket is mandatory")
        if not self.aws.backend_dynamodb_table:
            raise SpecValidationError("aws.backend_dynamodb_table is mandatory")
        if not self.aws.backend_key_prefix:
            raise SpecValidationError("aws.backend_key_prefix is mandatory")
        if self.compute.type not in {"ecs", "eks", "ec2"}:
            raise SpecValidationError("compute.type must be ecs, eks or ec2")
        if self.data.engine not in {"postgres", "mysql"}:
            raise SpecValidationError("data.engine must be postgres or mysql")
        if len(self.network.public_subnets) < 2 or len(self.network.private_subnets) < 2:
            raise SpecValidationError("network.public_subnets and network.private_subnets need at least 2 subnets")
        if not self.tags.get("owner"):
            raise SpecValidationError("tags.owner is mandatory")
        if not self.tags.get("cost_center"):
            raise SpecValidationError("tags.cost_center is mandatory")


@dataclass(slots=True)
class AgentFinding:
    severity: str
    message: str
    source: str
    file: str | None = None
    line: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "message": self.message,
            "source": self.source,
            "file": self.file,
            "line": self.line,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "AgentFinding":
        return cls(
            severity=str(payload.get("severity", "info")),
            message=str(payload.get("message", "")),
            source=str(payload.get("source", "")),
            file=payload.get("file"),
            line=payload.get("line"),
        )


@dataclass(slots=True)
class AgentResult:
    agent: str
    artifacts: list[str] = field(default_factory=list)
    findings: list[AgentFinding] = field(default_factory=list)
    next_action: str = "continue"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class JobState:
    job_id: str
    prompt: str
    workspace: Path
    execution_mode: str = "plan-only"
    validation_mode: str = "auto"
    max_iterations: int = 3
    spec: InfrastructureSpec | None = None
    artifacts: list[str] = field(default_factory=list)
    findings: list[AgentFinding] = field(default_factory=list)
    history: list[dict[str, Any]] = field(default_factory=list)
    runtime_trace: list[dict[str, Any]] = field(default_factory=list)
    iteration: int = 0
    blocked: bool = False
    status: str = "created"
    current_step: str | None = None
    next_step: str | None = None

    def add_result(self, result: AgentResult) -> None:
        self.artifacts.extend(result.artifacts)
        self.findings.extend(result.findings)
        self.history.append(
            {
                "agent": result.agent,
                "next_action": result.next_action,
                "artifacts": result.artifacts,
                "metadata": result.metadata,
            }
        )

    def add_runtime_trace(
        self,
        *,
        step: str,
        status: str,
        started_at: str,
        finished_at: str,
        duration_ms: int,
        attempt: int,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.runtime_trace.append(
            {
                "step": step,
                "status": status,
                "started_at": started_at,
                "finished_at": finished_at,
                "duration_ms": duration_ms,
                "attempt": attempt,
                "details": details or {},
            }
        )

    def has_errors(self) -> bool:
        return any(f.severity == "error" for f in self.findings)

    def has_critical(self) -> bool:
        return any(f.severity == "critical" for f in self.findings)

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "prompt": self.prompt,
            "workspace": str(self.workspace),
            "execution_mode": self.execution_mode,
            "validation_mode": self.validation_mode,
            "max_iterations": self.max_iterations,
            "spec": self.spec.to_dict() if self.spec else None,
            "artifacts": list(self.artifacts),
            "findings": [finding.to_dict() for finding in self.findings],
            "history": list(self.history),
            "runtime_trace": list(self.runtime_trace),
            "iteration": self.iteration,
            "blocked": self.blocked,
            "status": self.status,
            "current_step": self.current_step,
            "next_step": self.next_step,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "JobState":
        spec_payload = payload.get("spec")
        return cls(
            job_id=str(payload.get("job_id", "")),
            prompt=str(payload.get("prompt", "")),
            workspace=Path(payload.get("workspace", ".")),
            execution_mode=str(payload.get("execution_mode", "plan-only")),
            validation_mode=str(payload.get("validation_mode", "auto")),
            max_iterations=int(payload.get("max_iterations", 3)),
            spec=InfrastructureSpec.from_dict(spec_payload) if isinstance(spec_payload, dict) else None,
            artifacts=list(payload.get("artifacts", [])),
            findings=[
                AgentFinding.from_dict(item)
                for item in payload.get("findings", [])
                if isinstance(item, dict)
            ],
            history=list(payload.get("history", [])),
            runtime_trace=list(payload.get("runtime_trace", [])),
            iteration=int(payload.get("iteration", 0)),
            blocked=bool(payload.get("blocked", False)),
            status=str(payload.get("status", "created")),
            current_step=payload.get("current_step"),
            next_step=payload.get("next_step"),
        )
