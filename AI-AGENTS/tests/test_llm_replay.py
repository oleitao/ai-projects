import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from infra_agents.agents.requirements import RequirementsAgent
from infra_agents.contracts import JobState
from infra_agents.llm import build_llm_from_env
from infra_agents.llm.base import LLMRequest
from infra_agents.rag import LocalKnowledgeBase


class LLMReplayTests(unittest.TestCase):
    def test_factory_returns_replay_llm(self):
        with tempfile.TemporaryDirectory() as tmp:
            dataset = Path(tmp) / "replay.jsonl"
            dataset.write_text(
                json.dumps(
                    {
                        "task": "requirements_spec_v1",
                        "prompt_contains": "aws prod",
                        "output": {"cloud": "aws"},
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            with patch.dict(
                os.environ,
                {
                    "INFRA_AGENTS_LLM_MODE": "replay",
                    "INFRA_AGENTS_LLM_REPLAY_FILE": str(dataset),
                },
                clear=False,
            ):
                llm = build_llm_from_env()
                result = llm.generate_structured(
                    LLMRequest(
                        task="requirements_spec_v1",
                        prompt="aws prod eu-west-1",
                        context="",
                        schema_name="InfrastructureSpec",
                    )
                )
                self.assertEqual(result, {"cloud": "aws"})

    def test_requirements_agent_uses_replay_output(self):
        replay_spec = {
            "cloud": "aws",
            "region": "eu-west-1",
            "env": "prod",
            "aws": {
                "account_id": "123456789012",
                "profile": "",
                "backend_bucket": "tfstate-prod-123456789012",
                "backend_dynamodb_table": "tfstate-locks-prod",
                "backend_key_prefix": "infra-agents",
            },
            "network": {
                "vpc_cidr": "10.1.0.0/16",
                "public_subnets": ["10.1.1.0/24", "10.1.2.0/24"],
                "private_subnets": ["10.1.11.0/24", "10.1.12.0/24"],
            },
            "compute": {"type": "ecs", "sizing": "small", "autoscaling": True},
            "data": {"rds": True, "engine": "postgres", "multi_az": True, "backups": True},
            "security": {"encryption": True, "public_access": False},
            "tags": {"owner": "team", "cost_center": "cc100"},
        }

        with tempfile.TemporaryDirectory() as tmp:
            dataset = Path(tmp) / "replay.jsonl"
            dataset.write_text(
                json.dumps(
                    {
                        "task": "requirements_spec_v1",
                        "prompt_contains": "cliente x",
                        "output": replay_spec,
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            with patch.dict(
                os.environ,
                {
                    "INFRA_AGENTS_LLM_MODE": "replay",
                    "INFRA_AGENTS_LLM_REPLAY_FILE": str(dataset),
                },
                clear=False,
            ):
                llm = build_llm_from_env()
                kb = LocalKnowledgeBase(root=Path("infra_agents/knowledge"))
                agent = RequirementsAgent(knowledge_base=kb, llm=llm)

                state = JobState(
                    job_id="test",
                    prompt="Infra para cliente X em AWS prod",
                    workspace=Path(tmp),
                    execution_mode="plan-only",
                    max_iterations=1,
                    status="running",
                )
                result = agent.run(state)

                self.assertEqual(state.spec.network.vpc_cidr, "10.1.0.0/16")
                self.assertTrue(result.metadata.get("llm_used"))


if __name__ == "__main__":
    unittest.main()
