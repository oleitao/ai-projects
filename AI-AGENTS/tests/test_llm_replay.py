import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from infra_agents.agents.requirements import RequirementsAgent
from infra_agents.agents.generator import TerraformGeneratorAgent
from infra_agents.agents.planner import ArchitecturePlannerAgent
from infra_agents.contracts import InfrastructureSpec, JobState
from infra_agents.llm import LLMConfigurationError, LLMResponseError, build_llm_from_env
from infra_agents.llm.base import LLMRequest
from infra_agents.llm.ollama import OllamaLLM
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


class _FakeHTTPResponse:
    def __init__(self, payload: dict):
        self.payload = payload

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def _valid_requirements_spec() -> dict:
    return {
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
            "vpc_cidr": "10.0.0.0/16",
            "public_subnets": ["10.0.1.0/24", "10.0.2.0/24"],
            "private_subnets": ["10.0.11.0/24", "10.0.12.0/24"],
        },
        "compute": {"type": "ecs", "sizing": "small", "autoscaling": True},
        "data": {"rds": True, "engine": "postgres", "multi_az": True, "backups": True},
        "security": {"encryption": True, "public_access": False},
        "tags": {"owner": "team", "cost_center": "cc100"},
    }


def _build_state(tmp: str, prompt: str) -> JobState:
    return JobState(
        job_id="test",
        prompt=prompt,
        workspace=Path(tmp),
        execution_mode="plan-only",
        max_iterations=1,
        status="running",
    )


class LLMOllamaTests(unittest.TestCase):
    def test_factory_defaults_to_ollama_llm(self):
        with patch.dict(os.environ, {}, clear=True):
            llm = build_llm_from_env()
            self.assertIsInstance(llm, OllamaLLM)

    def test_factory_rejects_disabled_mode(self):
        with patch.dict(os.environ, {"INFRA_AGENTS_LLM_MODE": "off"}, clear=True):
            with self.assertRaises(LLMConfigurationError):
                build_llm_from_env()

    def test_factory_returns_ollama_llm(self):
        with patch.dict(
            os.environ,
            {
                "INFRA_AGENTS_LLM_MODE": "ollama",
                "INFRA_AGENTS_LLM_BASE_URL": "http://localhost:11434",
                "INFRA_AGENTS_LLM_MODEL": "llama3.2:latest",
            },
            clear=False,
        ):
            llm = build_llm_from_env()
            self.assertIsInstance(llm, OllamaLLM)

    @patch("urllib.request.urlopen")
    def test_ollama_llm_parses_json_content(self, mock_urlopen):
        mock_urlopen.return_value = _FakeHTTPResponse(
            {
                "response": '```json\n{"cloud":"aws","region":"eu-west-1"}\n```',
            }
        )

        with patch.dict(
            os.environ,
            {
                "INFRA_AGENTS_LLM_MODE": "ollama",
                "INFRA_AGENTS_LLM_BASE_URL": "http://localhost:11434",
                "INFRA_AGENTS_LLM_MODEL": "llama3.2:latest",
            },
            clear=False,
        ):
            llm = build_llm_from_env()
            result = llm.generate_structured(
                LLMRequest(
                    task="requirements_spec_v1",
                    prompt="AWS prod eu-west-1 com ECS",
                    context="provider aws",
                    schema_name="InfrastructureSpec",
                )
            )

        self.assertEqual(result, {"cloud": "aws", "region": "eu-west-1"})
        request_payload = json.loads(mock_urlopen.call_args.args[0].data.decode("utf-8"))
        self.assertEqual(request_payload["model"], "llama3.2:latest")
        self.assertFalse(request_payload["stream"])
        self.assertIn("properties", request_payload["format"])
        self.assertIn("InfrastructureSpec", request_payload["prompt"])


class RequirementsAgentFallbackTests(unittest.TestCase):
    def test_sparse_llm_spec_is_normalized_and_used(self):
        kb = LocalKnowledgeBase(root=Path("infra_agents/knowledge"))
        llm = Mock()
        llm.generate_structured.return_value = {
            "cloud": "aws",
            "region": "eu-west-1",
            "env": "prod",
            "aws": {
                "account_id": "",
                "profile": "",
                "backend_bucket": "",
                "backend_dynamodb_table": "",
                "backend_key_prefix": "",
            },
            "network": {"vpc_cidr": "", "public_subnets": [], "private_subnets": []},
            "compute": {"type": "ecs", "sizing": "autoscaling", "autoscaling": True},
            "data": {"rds": True, "engine": "postgres", "multi_az": False, "backups": True},
            "security": {"encryption": False, "public_access": False},
            "tags": {"owner": "", "cost_center": ""},
        }
        agent = RequirementsAgent(knowledge_base=kb, llm=llm)

        with tempfile.TemporaryDirectory() as tmp:
            state = JobState(
                job_id="test",
                prompt="AWS prod eu-west-1 com ECS autoscaling e RDS postgres, sem acesso publico",
                workspace=Path(tmp),
                execution_mode="plan-only",
                max_iterations=1,
                status="running",
            )
            result = agent.run(state)

        self.assertTrue(result.metadata.get("llm_used"))
        self.assertEqual(state.spec.aws.backend_bucket, "tfstate-prod-123456789012")
        self.assertEqual(state.spec.network.public_subnets, ["10.0.1.0/24", "10.0.2.0/24"])
        self.assertEqual(state.spec.compute.sizing, "small")
        self.assertTrue(state.spec.data.multi_az)
        self.assertTrue(state.spec.security.encryption)
        self.assertFalse(state.spec.security.public_access)
        self.assertTrue(any("Spec inferida via LLM estruturado" in item for item in state.spec.assumptions))

    def test_single_subnet_llm_spec_is_normalized_and_used(self):
        kb = LocalKnowledgeBase(root=Path("infra_agents/knowledge"))
        llm = Mock()
        llm.generate_structured.return_value = {
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
                "vpc_cidr": "10.0.0.0/16",
                "public_subnets": ["10.0.1.0/24"],
                "private_subnets": ["10.0.11.0/24"],
            },
            "compute": {"type": "ecs", "sizing": "small", "autoscaling": True},
            "data": {"rds": True, "engine": "postgres", "multi_az": True, "backups": True},
            "security": {"encryption": True, "public_access": False},
            "tags": {"owner": "team", "cost_center": "cc100"},
        }
        agent = RequirementsAgent(knowledge_base=kb, llm=llm)

        with tempfile.TemporaryDirectory() as tmp:
            state = JobState(
                job_id="test",
                prompt="AWS prod eu-west-1 com ECS autoscaling e RDS postgres, sem acesso publico",
                workspace=Path(tmp),
                execution_mode="plan-only",
                max_iterations=1,
                status="running",
            )
            result = agent.run(state)

        self.assertTrue(result.metadata.get("llm_used"))
        self.assertEqual(state.spec.network.public_subnets, ["10.0.1.0/24", "10.0.2.0/24"])
        self.assertEqual(state.spec.network.private_subnets, ["10.0.11.0/24", "10.0.12.0/24"])

    def test_invalid_llm_spec_raises_error(self):
        kb = LocalKnowledgeBase(root=Path("infra_agents/knowledge"))
        llm = Mock()
        llm.generate_structured.return_value = {
            "cloud": "aws",
            "region": "eu-west-1",
            "env": "prod",
            "aws": {"account_id": "123456789012", "profile": "devops"},
            "network": {"vpc": True},
            "compute": {"ecs": {"autoscaling": True}},
            "data": {"rds": {"engine": "postgres"}},
            "security": {"encryption": True},
            "tags": {"owner": "team"},
        }
        agent = RequirementsAgent(knowledge_base=kb, llm=llm)

        with tempfile.TemporaryDirectory() as tmp:
            state = _build_state(tmp, "AWS prod eu-west-1 com ECS autoscaling e RDS postgres")
            with self.assertRaises(LLMResponseError):
                agent.run(state)

    def test_inconsistent_llm_spec_raises_error(self):
        kb = LocalKnowledgeBase(root=Path("infra_agents/knowledge"))
        llm = Mock()
        llm.generate_structured.return_value = {
            "cloud": "aws",
            "region": "eu-west-1",
            "env": "prod",
            "aws": {
                "account_id": "123456789012",
                "profile": "devops",
                "backend_bucket": "tfstate-prod-123456789012",
                "backend_dynamodb_table": "tfstate-locks-prod",
                "backend_key_prefix": "infra-agents",
            },
            "network": {
                "vpc_cidr": "10.0.0.0/16",
                "public_subnets": ["10.0.1.0/24", "10.0.2.0/24"],
                "private_subnets": ["10.0.11.0/24", "10.0.12.0/24"],
            },
            "compute": {"type": "eks", "sizing": "small", "autoscaling": True},
            "data": {"rds": True, "engine": "postgres", "multi_az": True, "backups": True},
            "security": {"encryption": True, "public_access": False},
            "tags": {"owner": "team", "cost_center": "cc100"},
        }
        agent = RequirementsAgent(knowledge_base=kb, llm=llm)

        with tempfile.TemporaryDirectory() as tmp:
            state = _build_state(tmp, "AWS prod eu-west-1 com ECS autoscaling e RDS postgres")
            with self.assertRaises(LLMResponseError):
                agent.run(state)


class PlannerAndGeneratorGuardrailTests(unittest.TestCase):
    def test_planner_ignores_irrelevant_modules_from_llm(self):
        kb = LocalKnowledgeBase(root=Path("infra_agents/knowledge"))
        llm = Mock()
        llm.generate_structured.return_value = {
            "modules": [
                "terraform-aws-modules/eks/aws",
                "terraform-aws-modules/autoscaling/aws",
                "terraform-aws-modules/ecs/aws",
            ],
            "notes": ["ok"],
        }
        agent = ArchitecturePlannerAgent(knowledge_base=kb, llm=llm)

        with tempfile.TemporaryDirectory() as tmp:
            state = _build_state(tmp, "AWS prod eu-west-1 com ECS e RDS postgres")
            state.spec = InfrastructureSpec.from_dict(_valid_requirements_spec())
            result = agent.run(state)

        self.assertTrue(result.metadata.get("llm_used"))
        self.assertEqual(
            result.metadata.get("modules"),
            [
                "terraform-aws-modules/ecs/aws",
                "terraform-aws-modules/rds/aws",
                "terraform-aws-modules/vpc/aws",
            ],
        )

    def test_generator_ignores_ec2_override_for_ecs(self):
        kb = LocalKnowledgeBase(root=Path("infra_agents/knowledge"))
        llm = Mock()
        llm.generate_structured.return_value = {
            "tfvars_overrides": {
                "ec2_instance_type": "t3.2xlarge",
                "db_instance_class": "db.t3.small",
            }
        }
        agent = TerraformGeneratorAgent(knowledge_base=kb, llm=llm)

        with tempfile.TemporaryDirectory() as tmp:
            state = _build_state(tmp, "AWS prod eu-west-1 com ECS e RDS postgres")
            state.spec = InfrastructureSpec.from_dict(_valid_requirements_spec())
            result = agent.run(state)

        self.assertTrue(result.metadata.get("llm_used"))
        self.assertEqual(result.metadata.get("tfvars_overrides"), {"db_instance_class": "db.t3.small"})

    def test_generator_clamps_db_storage_to_contextual_max(self):
        kb = LocalKnowledgeBase(root=Path("infra_agents/knowledge"))
        llm = Mock()
        llm.generate_structured.return_value = {
            "tfvars_overrides": {
                "db_allocated_storage": 1024,
            }
        }
        agent = TerraformGeneratorAgent(knowledge_base=kb, llm=llm)

        with tempfile.TemporaryDirectory() as tmp:
            state = _build_state(tmp, "AWS prod eu-west-1 com ECS e RDS postgres")
            state.spec = InfrastructureSpec.from_dict(_valid_requirements_spec())
            result = agent.run(state)

        self.assertTrue(result.metadata.get("llm_used"))
        self.assertEqual(result.metadata.get("tfvars_overrides"), {"db_allocated_storage": 100})

    def test_generator_prompt_includes_defaults_and_rules(self):
        kb = LocalKnowledgeBase(root=Path("infra_agents/knowledge"))
        agent = TerraformGeneratorAgent(knowledge_base=kb, llm=Mock())
        spec = {
            "region": "eu-west-1",
            "env": "prod",
            "compute": {"type": "ecs", "sizing": "small", "autoscaling": True},
            "data": {"rds": True, "engine": "postgres", "multi_az": True, "backups": True},
            "security": {"encryption": True, "public_access": False},
        }

        prompt = agent._build_generator_llm_prompt(spec)
        context = agent._build_generator_llm_context(spec, "providers.md")

        self.assertIn('"db_instance_class": "db.t3.micro"', prompt)
        self.assertIn("If no clear improvement exists", prompt)
        self.assertIn("Only use ec2_instance_type when compute.type is ec2", prompt)
        self.assertIn('"compute_type=ecs"', context)
        self.assertIn("db.t3.small", context)
        self.assertIn('"max": 100', context)


if __name__ == "__main__":
    unittest.main()
