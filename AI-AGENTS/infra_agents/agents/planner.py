from __future__ import annotations

from pathlib import Path

from infra_agents.agents.base import BaseAgent
from infra_agents.contracts import AgentResult
from infra_agents.llm import AgentLLM, LLMRequest
from infra_agents.rag import LocalKnowledgeBase
from infra_agents.tools.filesystem import write_text


class ArchitecturePlannerAgent(BaseAgent):
    name = "Planeador de Arquitetura"

    def __init__(
        self,
        llm: AgentLLM,
        knowledge_base: LocalKnowledgeBase | None = None,
    ):
        self.knowledge_base = knowledge_base or LocalKnowledgeBase()
        self.llm = llm

    def run(self, state):  # type: ignore[override]
        if state.spec is None:
            raise ValueError("Spec em falta para o agente de arquitetura")

        spec = state.spec
        rag_hits = self.knowledge_base.retrieve(
            query=(
                f"planner aws modules naming tagging {spec.compute.type} "
                f"{spec.region} {spec.env}"
            ),
            top_k=3,
        )
        rag_sources = [hit.source for hit in rag_hits]
        rag_context = self.knowledge_base.render_context(rag_hits)
        modules = ["terraform-aws-modules/vpc/aws"]
        if spec.compute.type == "ecs":
            modules.append("terraform-aws-modules/ecs/aws")
        elif spec.compute.type == "eks":
            modules.append("terraform-aws-modules/eks/aws")
        elif spec.compute.type == "ec2":
            modules.append("terraform-aws-modules/autoscaling/aws")
        if spec.data.rds:
            modules.append("terraform-aws-modules/rds/aws")
        base_modules = set(modules)
        approved_modules = set(base_modules)

        llm_notes: list[str] = []
        llm_payload = self.llm.generate_structured(
            LLMRequest(
                task="planner_design_v1",
                prompt=(
                    f"cloud=aws region={spec.region} env={spec.env} "
                    f"compute={spec.compute.type} data_engine={spec.data.engine}"
                ),
                context=rag_context,
                schema_name="PlannerDecision",
            )
        )
        candidate_modules = llm_payload.get("modules", [])
        if isinstance(candidate_modules, list):
            llm_modules = {m for m in candidate_modules if isinstance(m, str) and m in approved_modules}
            modules = sorted(base_modules | llm_modules)
        notes = llm_payload.get("notes", [])
        if isinstance(notes, list):
            llm_notes = [n for n in notes if isinstance(n, str)][:5]

        design = self._render_design(spec.to_dict(), modules, rag_sources, llm_notes)
        path = Path(state.workspace, "design.md")
        artifact = write_text(path, design)
        artifacts = [artifact]
        if rag_context:
            rag_artifact = write_text(Path(state.workspace, "reports", "rag_planner.md"), rag_context + "\n")
            artifacts.append(rag_artifact)

        return AgentResult(
            agent=self.name,
            artifacts=artifacts,
            findings=[],
            next_action="generate_terraform",
            metadata={"modules": modules, "rag_sources": rag_sources, "llm_used": True, "llm_notes": llm_notes},
        )

    def _render_design(self, spec: dict, modules: list[str], rag_sources: list[str], llm_notes: list[str]) -> str:
        module_lines = "\n".join(f"- {module}" for module in modules)
        compute_type = spec["compute"]["type"]
        rag_lines = "\n".join(f"- {source}" for source in rag_sources) if rag_sources else "- Nenhuma fonte relevante"
        llm_lines = "\n".join(f"- {note}" for note in llm_notes) if llm_notes else "- Sem notas adicionais"
        return f"""# Design de Infraestrutura

## Contexto
- Cloud: {spec['cloud']}
- Região: {spec['region']}
- Ambiente: {spec['env']}
- Conta AWS alvo: {spec['aws']['account_id']}

## Padrões
- Naming: `<env>-<service>-<resource>`
- Ambientes: `dev`, `staging`, `prod`
- Backend remoto: S3 + DynamoDB lock com config em `backend.hcl.example`
- Providers com versão fixa em `versions.tf`
- Execução por defeito: `plan-only`

## Módulos aprovados
{module_lines}

## Runtime de Compute
- Tipo selecionado: `{compute_type}`
- IAM de runtime gerado com trust policy mínima por tipo (ecs/eks/ec2)

## Backend remoto AWS
- Bucket: `{spec['aws']['backend_bucket']}`
- Tabela lock: `{spec['aws']['backend_dynamodb_table']}`
- Prefixo de state: `{spec['aws']['backend_key_prefix']}`

## Guardrails
- Apenas provider `aws`
- Bloquear recursos públicos inseguros
- Exigir encriptação e logging
- Exigir tags `owner` e `cost_center`

## Referências RAG
{rag_lines}

## Notas LLM
{llm_lines}
"""
