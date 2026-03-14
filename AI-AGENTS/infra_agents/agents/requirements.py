from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from infra_agents.agents.base import BaseAgent
from infra_agents.contracts import AgentResult, InfrastructureSpec, SpecValidationError
from infra_agents.llm import AgentLLM, LLMRequest, LLMResponseError
from infra_agents.rag import LocalKnowledgeBase
from infra_agents.tools.filesystem import write_json, write_text


class RequirementsAgent(BaseAgent):
    name = "Requisitos"

    def __init__(
        self,
        llm: AgentLLM,
        knowledge_base: LocalKnowledgeBase | None = None,
    ):
        self.knowledge_base = knowledge_base or LocalKnowledgeBase()
        self.llm = llm

    def run(self, state):  # type: ignore[override]
        assumptions: list[str] = []
        prompt = state.prompt.strip()
        heuristic_payload = self._heuristic_spec(prompt)
        rag_hits = self.knowledge_base.retrieve(
            query=f"requirements agent aws spec backend tags security {prompt}",
            top_k=2,
        )
        rag_sources = [hit.source for hit in rag_hits]
        rag_context = self.knowledge_base.render_context(rag_hits)
        payload = self._extract_json(prompt)
        llm_used = False

        if payload is None:
            llm_payload = self.llm.generate_structured(
                LLMRequest(
                    task="requirements_spec_v1",
                    prompt=prompt,
                    context=self._requirements_llm_context(),
                    schema_name="InfrastructureSpec",
                )
            )
            if not llm_payload:
                raise LLMResponseError("LLM devolveu uma spec vazia para InfrastructureSpec.")

            try:
                llm_payload = self._merge_llm_payload(heuristic_payload, llm_payload)
                llm_payload = self._preserve_heuristic_defaults(prompt, heuristic_payload, llm_payload)
                llm_spec = InfrastructureSpec.from_dict(llm_payload)
                heuristic_spec = InfrastructureSpec.from_dict(heuristic_payload)
            except (SpecValidationError, TypeError, ValueError) as exc:
                raise LLMResponseError("LLM devolveu spec inválida para InfrastructureSpec.") from exc

            if not self._critical_fields_match(llm_spec, heuristic_spec):
                raise LLMResponseError("LLM devolveu spec inconsistente com o prompt.")

            payload = llm_payload
            llm_used = True
            assumptions.append("Spec inferida via LLM estruturado com contexto RAG.")
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
            metadata={"assumptions": spec.assumptions, "rag_sources": rag_sources, "llm_used": llm_used},
        )

    def _extract_json(self, prompt: str) -> dict | None:
        prompt = prompt.strip()
        if prompt.startswith("{") and prompt.endswith("}"):
            try:
                return json.loads(prompt)
            except json.JSONDecodeError:
                return None
        return None

    def _requirements_llm_context(self) -> str:
        return (
            "Use the Input section as the source of truth. "
            "Infer conservative defaults for missing values, and never override explicit "
            "region, environment, compute runtime, database engine, or public/private access intent."
        )

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
                "sizing": self._infer_sizing(low),
                "autoscaling": "autoscaling" in low or "auto scaling" in low,
            },
            "data": {
                "rds": "sem db" not in low and "no db" not in low,
                "engine": engine,
                "multi_az": (
                    "single-az" not in low
                    and "single az" not in low
                    and ("multi-az" in low or "alta disponibilidade" in low or env == "prod")
                ),
                "backups": True,
            },
            "security": {
                "encryption": "sem encriptação" not in low and "without encryption" not in low,
                "public_access": self._infer_public_access(low),
            },
            "tags": {
                "owner": "platform-team",
                "cost_center": "shared",
            },
        }

    def _merge_llm_payload(self, base: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
        merged = self._merge_value(base, candidate)
        return merged if isinstance(merged, dict) else dict(base)

    def _merge_value(self, base: Any, candidate: Any) -> Any:
        if isinstance(base, dict) and isinstance(candidate, dict):
            merged: dict[str, Any] = {}
            for key in base.keys() | candidate.keys():
                if key in base and key in candidate:
                    merged[key] = self._merge_value(base[key], candidate[key])
                elif key in candidate:
                    merged[key] = candidate[key]
                else:
                    merged[key] = base[key]
            return merged

        if candidate is None:
            return base
        if isinstance(candidate, str):
            return candidate if candidate.strip() else base
        if isinstance(candidate, list):
            return candidate if candidate else base
        return candidate

    def _preserve_heuristic_defaults(
        self,
        prompt: str,
        heuristic_payload: dict[str, Any],
        llm_payload: dict[str, Any],
    ) -> dict[str, Any]:
        low = prompt.lower()
        field_signals = {
            ("compute", "sizing"): self._mentions_sizing(low),
            ("compute", "autoscaling"): self._mentions_autoscaling(low),
            ("data", "multi_az"): self._mentions_multi_az(low),
            ("data", "backups"): self._mentions_backups(low),
            ("security", "encryption"): self._mentions_encryption(low),
            ("security", "public_access"): self._mentions_public_access(low),
        }

        for path, has_signal in field_signals.items():
            if has_signal:
                continue
            self._set_nested_value(llm_payload, path, self._get_nested_value(heuristic_payload, path))

        # The contract requires at least two public and private subnets.
        # Keep the heuristic topology when the model returns an underspecified network.
        for path in (("network", "public_subnets"), ("network", "private_subnets")):
            candidate = self._get_nested_value(llm_payload, path)
            if not isinstance(candidate, list) or len(candidate) < 2:
                self._set_nested_value(llm_payload, path, self._get_nested_value(heuristic_payload, path))

        return llm_payload

    def _get_nested_value(self, payload: dict[str, Any], path: tuple[str, str]) -> Any:
        current: Any = payload
        for key in path:
            if not isinstance(current, dict):
                return None
            current = current.get(key)
        return current

    def _set_nested_value(self, payload: dict[str, Any], path: tuple[str, str], value: Any) -> None:
        current: dict[str, Any] = payload
        for key in path[:-1]:
            next_value = current.get(key)
            if not isinstance(next_value, dict):
                next_value = {}
                current[key] = next_value
            current = next_value
        current[path[-1]] = value

    def _infer_public_access(self, low: str) -> bool:
        if any(marker in low for marker in ("sem acesso publico", "sem acesso público", "without public access")):
            return False
        if any(marker in low for marker in ("private", "privado", "internal only", "interno")):
            return False
        return any(marker in low for marker in ("public access", "acesso publico", "acesso público", "public"))

    def _infer_sizing(self, low: str) -> str:
        if any(marker in low for marker in ("large", "grande", "alto throughput", "high throughput")):
            return "large"
        if any(marker in low for marker in ("medium", "médio", "medio")):
            return "medium"
        return "small"

    def _mentions_sizing(self, low: str) -> bool:
        return any(
            marker in low
            for marker in ("small", "medium", "large", "pequeno", "médio", "medio", "grande", "high throughput")
        )

    def _mentions_autoscaling(self, low: str) -> bool:
        return any(marker in low for marker in ("autoscaling", "auto scaling", "sem autoscaling", "without autoscaling"))

    def _mentions_multi_az(self, low: str) -> bool:
        return any(marker in low for marker in ("multi-az", "multi az", "alta disponibilidade", "single-az"))

    def _mentions_backups(self, low: str) -> bool:
        return any(marker in low for marker in ("backup", "backups", "sem backups", "without backups", "no backups"))

    def _mentions_encryption(self, low: str) -> bool:
        return any(marker in low for marker in ("encrypt", "encrypted", "encryption", "encrip", "kms"))

    def _mentions_public_access(self, low: str) -> bool:
        return any(
            marker in low
            for marker in (
                "public",
                "acesso publico",
                "acesso público",
                "private",
                "privado",
                "interno",
                "without public access",
            )
        )

    def _critical_fields_match(self, llm_spec: InfrastructureSpec, heuristic_spec: InfrastructureSpec) -> bool:
        return (
            llm_spec.region == heuristic_spec.region
            and llm_spec.env == heuristic_spec.env
            and llm_spec.compute.type == heuristic_spec.compute.type
            and llm_spec.data.engine == heuristic_spec.data.engine
            and llm_spec.data.rds == heuristic_spec.data.rds
            and llm_spec.security.public_access == heuristic_spec.security.public_access
        )
