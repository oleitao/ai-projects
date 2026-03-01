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
    max_iterations: int = 3
    spec: InfrastructureSpec | None = None
    artifacts: list[str] = field(default_factory=list)
    findings: list[AgentFinding] = field(default_factory=list)
    history: list[dict[str, Any]] = field(default_factory=list)
    iteration: int = 0
    blocked: bool = False
    status: str = "created"

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

    def has_errors(self) -> bool:
        return any(f.severity == "error" for f in self.findings)

    def has_critical(self) -> bool:
        return any(f.severity == "critical" for f in self.findings)
