from __future__ import annotations

import json
import re
from pathlib import Path

from infra_agents.agents.base import BaseAgent
from infra_agents.contracts import AgentResult, InfrastructureSpec
from infra_agents.rag import LocalKnowledgeBase
from infra_agents.tools.filesystem import write_json, write_text


class RequirementsAgent(BaseAgent):
    name = "Requisitos"

    def __init__(self, knowledge_base: LocalKnowledgeBase | None = None):
        self.knowledge_base = knowledge_base or LocalKnowledgeBase()

    def run(self, state):  # type: ignore[override]
        assumptions: list[str] = []
        prompt = state.prompt.strip()
        rag_hits = self.knowledge_base.retrieve(
            query=f"requirements agent aws spec backend tags security {prompt}",
            top_k=2,
        )
        rag_sources = [hit.source for hit in rag_hits]
        rag_context = self.knowledge_base.render_context(rag_hits)
        payload = self._extract_json(prompt)

        if payload is None:
            payload = self._heuristic_spec(prompt)
            assumptions.append("Spec inferida por heurísticas por não existir JSON explícito no prompt.")
        if rag_sources:
            assumptions.append(f"Contexto RAG consultado: {', '.join(rag_sources)}.")

        payload.setdefault("assumptions", [])
        payload["assumptions"].extend(assumptions)

        spec = InfrastructureSpec.from_dict(payload)
        state.spec = spec

        path = Path(state.workspace, "spec.json")
        artifact = write_json(path, spec.to_dict())
        artifacts = [artifact]
        if rag_context:
            rag_artifact = write_text(Path(state.workspace, "reports", "rag_requirements.md"), rag_context + "\n")
            artifacts.append(rag_artifact)

        return AgentResult(
            agent=self.name,
            artifacts=artifacts,
            findings=[],
            next_action="plan_architecture",
            metadata={"assumptions": spec.assumptions, "rag_sources": rag_sources},
        )

    def _extract_json(self, prompt: str) -> dict | None:
        prompt = prompt.strip()
        if prompt.startswith("{") and prompt.endswith("}"):
            try:
                return json.loads(prompt)
            except json.JSONDecodeError:
                return None
        return None

    def _heuristic_spec(self, prompt: str) -> dict:
        low = prompt.lower()
        region_match = re.search(r"\b[a-z]{2}-[a-z]+-\d\b", low)
        region = region_match.group(0) if region_match else "eu-west-1"
        account_match = re.search(r"\b\d{12}\b", low)
        account_id = account_match.group(0) if account_match else "123456789012"
        profile_match = re.search(r"(?:profile|perfil)\s*[:=]?\s*([a-z0-9_-]+)", low)
        profile = profile_match.group(1) if profile_match else ""

        compute_type = "ecs"
        for candidate in ("eks", "ec2", "ecs"):
            if candidate in low:
                compute_type = candidate
                break

        engine = "postgres" if "mysql" not in low else "mysql"
        if "staging" in low or "stage" in low:
            env = "staging"
        elif "prod" in low or "produção" in low:
            env = "prod"
        else:
            env = "dev"

        return {
            "cloud": "aws",
            "region": region,
            "env": env,
            "aws": {
                "account_id": account_id,
                "profile": profile,
                "backend_bucket": f"tfstate-{env}-{account_id}",
                "backend_dynamodb_table": f"tfstate-locks-{env}",
                "backend_key_prefix": "infra-agents",
            },
            "network": {
                "vpc_cidr": "10.0.0.0/16",
                "public_subnets": ["10.0.1.0/24", "10.0.2.0/24"],
                "private_subnets": ["10.0.11.0/24", "10.0.12.0/24"],
            },
            "compute": {
                "type": compute_type,
                "sizing": "small",
                "autoscaling": "autoscaling" in low or "auto scaling" in low,
            },
            "data": {
                "rds": "sem db" not in low and "no db" not in low,
                "engine": engine,
                "multi_az": "multi-az" in low or "alta disponibilidade" in low,
                "backups": True,
            },
            "security": {
                "encryption": "sem encriptação" not in low and "without encryption" not in low,
                "public_access": "public" in low and "private" not in low,
            },
            "tags": {
                "owner": "platform-team",
                "cost_center": "shared",
            },
        }
