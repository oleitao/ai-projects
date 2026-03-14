import tempfile
import unittest
import json
from pathlib import Path
from unittest.mock import patch

from infra_agents.agents.validator import ValidatorAgent
from infra_agents.orchestration import LangGraphUnavailableError, is_langgraph_available
from infra_agents.orchestrator import WorkflowSupervisor


def _write_replay_dataset(tmp: str) -> Path:
    dataset = Path(tmp) / "replay.jsonl"
    rows = [
        {
            "task": "requirements_spec_v1",
            "prompt_contains": "aws dev eu-west-1 com ecs",
            "output": {
                "cloud": "aws",
                "region": "eu-west-1",
                "env": "dev",
                "aws": {
                    "account_id": "123456789012",
                    "profile": "",
                    "backend_bucket": "tfstate-dev-123456789012",
                    "backend_dynamodb_table": "tfstate-locks-dev",
                    "backend_key_prefix": "infra-agents",
                },
                "network": {
                    "vpc_cidr": "10.0.0.0/16",
                    "public_subnets": ["10.0.1.0/24", "10.0.2.0/24"],
                    "private_subnets": ["10.0.11.0/24", "10.0.12.0/24"],
                },
                "compute": {"type": "ecs", "sizing": "small", "autoscaling": False},
                "data": {"rds": True, "engine": "postgres", "multi_az": False, "backups": True},
                "security": {"encryption": True, "public_access": False},
                "tags": {"owner": "team", "cost_center": "cc100"},
            },
        },
        {
            "task": "planner_design_v1",
            "prompt_contains": "cloud=aws",
            "output": {
                "modules": [
                    "terraform-aws-modules/vpc/aws",
                    "terraform-aws-modules/ecs/aws",
                    "terraform-aws-modules/rds/aws",
                ],
                "notes": ["Replay planner"],
            },
        },
        {
            "task": "generator_overrides_v1",
            "prompt_contains": "\"goal\": \"recommend only safe tfvars overrides",
            "output": {"tfvars_overrides": {}},
        },
    ]
    dataset.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    return dataset


class OrchestratorEngineTests(unittest.TestCase):
    def test_classic_engine_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            dataset = _write_replay_dataset(tmp)
            with patch.dict(
                "os.environ",
                {
                    "INFRA_AGENTS_LLM_MODE": "replay",
                    "INFRA_AGENTS_LLM_REPLAY_FILE": str(dataset),
                },
                clear=False,
            ):
                supervisor = WorkflowSupervisor(max_iterations=1, engine="classic")
                state = supervisor.run(
                    prompt="AWS dev eu-west-1 com ECS",
                    output_root=Path(tmp),
                    execution_mode="plan-only",
                )
            self.assertEqual(supervisor.engine, "classic")
            self.assertTrue((state.workspace / "summary.json").exists())

    def test_langgraph_engine_selection(self):
        if not is_langgraph_available():
            with self.assertRaises(LangGraphUnavailableError):
                WorkflowSupervisor(max_iterations=1, engine="langgraph")
            return

        with tempfile.TemporaryDirectory() as tmp:
            dataset = _write_replay_dataset(tmp)
            with patch.dict(
                "os.environ",
                {
                    "INFRA_AGENTS_LLM_MODE": "replay",
                    "INFRA_AGENTS_LLM_REPLAY_FILE": str(dataset),
                },
                clear=False,
            ):
                supervisor = WorkflowSupervisor(max_iterations=1, engine="langgraph")
                state = supervisor.run(
                    prompt="AWS dev eu-west-1 com ECS",
                    output_root=Path(tmp),
                    execution_mode="plan-only",
                )
            self.assertEqual(supervisor.engine, "langgraph")
            self.assertTrue((state.workspace / "summary.json").exists())

            summary = json.loads((state.workspace / "summary.json").read_text(encoding="utf-8"))
            self.assertIn("runtime_trace", summary)
            self.assertTrue((state.workspace / "runtime_checkpoint.json").exists())

    def test_langgraph_resume_from_checkpoint_after_failure(self):
        if not is_langgraph_available():
            self.skipTest("langgraph not installed")

        original_run = ValidatorAgent.run

        with tempfile.TemporaryDirectory() as tmp:
            dataset = _write_replay_dataset(tmp)
            env = {
                "INFRA_AGENTS_LLM_MODE": "replay",
                "INFRA_AGENTS_LLM_REPLAY_FILE": str(dataset),
            }

            with patch.dict("os.environ", env, clear=False):
                supervisor = WorkflowSupervisor(max_iterations=1, engine="langgraph")
                with patch.object(ValidatorAgent, "run", side_effect=RuntimeError("validator crashed")):
                    with self.assertRaises(RuntimeError):
                        supervisor.run(
                            prompt="AWS dev eu-west-1 com ECS",
                            output_root=Path(tmp),
                            execution_mode="plan-only",
                        )

                workspaces = [path for path in Path(tmp).iterdir() if path.is_dir()]
                self.assertEqual(len(workspaces), 1)
                workspace = workspaces[0]

                checkpoint = json.loads((workspace / "runtime_checkpoint.json").read_text(encoding="utf-8"))
                self.assertEqual(checkpoint["runtime"]["next_node"], "validator")

                with patch.object(ValidatorAgent, "run", original_run):
                    resumed_state = supervisor.resume(workspace)

            self.assertIn(resumed_state.status, {"validated", "done", "failed", "blocked"})
            summary = json.loads((workspace / "summary.json").read_text(encoding="utf-8"))
            self.assertGreaterEqual(len(summary["runtime_trace"]), 1)
            self.assertTrue(any(item["step"] == "validator" for item in summary["runtime_trace"]))
            self.assertIsNone(summary["next_step"])


if __name__ == "__main__":
    unittest.main()
