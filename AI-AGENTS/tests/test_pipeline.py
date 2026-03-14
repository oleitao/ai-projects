import tempfile
import unittest
import json
from pathlib import Path
from unittest.mock import patch

from infra_agents.orchestrator import WorkflowSupervisor


def _write_replay_dataset(tmp: str) -> Path:
    dataset = Path(tmp) / "replay.jsonl"
    rows = [
        {
            "task": "requirements_spec_v1",
            "prompt_contains": "aws prod eu-west-1 com ecs autoscaling e rds postgres multi-az",
            "output": {
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
            "output": {"tfvars_overrides": {"db_instance_class": "db.t3.small"}},
        },
    ]
    dataset.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    return dataset


class PipelineTests(unittest.TestCase):
    def test_pipeline_generates_core_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            prompt = "AWS prod eu-west-1 com ECS autoscaling e RDS postgres multi-az"
            dataset = _write_replay_dataset(tmp)
            with patch.dict(
                "os.environ",
                {
                    "INFRA_AGENTS_LLM_MODE": "replay",
                    "INFRA_AGENTS_LLM_REPLAY_FILE": str(dataset),
                },
                clear=False,
            ):
                supervisor = WorkflowSupervisor(max_iterations=2)
                state = supervisor.run(prompt=prompt, output_root=Path(tmp))

            self.assertTrue(state.workspace.exists())
            for required in [
                "spec.json",
                "design.md",
                "main.tf",
                "variables.tf",
                "outputs.tf",
                "providers.tf",
                "versions.tf",
                "backend.tf",
                "backend.hcl.example",
                "summary.json",
                "reports/rag_requirements.md",
                "reports/rag_planner.md",
                "reports/rag_generator.md",
            ]:
                self.assertTrue((state.workspace / required).exists(), f"Missing {required}")

            main_tf = (state.workspace / "main.tf").read_text(encoding="utf-8")
            spec = json.loads((state.workspace / "spec.json").read_text(encoding="utf-8"))
            backend_hcl = (state.workspace / "backend.hcl.example").read_text(encoding="utf-8")
            self.assertIn('data "aws_caller_identity" "current"', main_tf)
            self.assertIn("manage_master_user_password", main_tf)
            self.assertNotIn("password =", main_tf)
            self.assertIn("dynamodb_table", backend_hcl)
            self.assertIn('resource "aws_ecs_task_definition" "app"', main_tf)
            self.assertIn('resource "aws_ecs_service" "app"', main_tf)
            self.assertIn('resource "aws_kms_key" "app"', main_tf)
            self.assertIn('resource "aws_iam_role" "ecs_execution"', main_tf)
            self.assertIn("readonlyRootFilesystem", main_tf)
            self.assertIn("iam_database_authentication_enabled = true", main_tf)
            self.assertEqual(spec["compute"]["sizing"], "small")

            summary = json.loads((state.workspace / "summary.json").read_text(encoding="utf-8"))
            self.assertIn("history", summary)
            rag_history = [
                entry for entry in summary["history"] if entry.get("metadata", {}).get("rag_sources")
            ]
            self.assertGreaterEqual(len(rag_history), 3)

            self.assertIn(state.status, {"validated", "done", "failed", "blocked"})

    def test_pipeline_supports_credentialless_validation_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            prompt = "AWS prod eu-west-1 com ECS autoscaling e RDS postgres multi-az"
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
                    prompt=prompt,
                    output_root=Path(tmp),
                    execution_mode="plan-only",
                    validation_mode="credentialless",
                )

            self.assertEqual(state.validation_mode, "credentialless")
            summary = json.loads((state.workspace / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["validation_mode"], "credentialless")
            validation = json.loads((state.workspace / "reports" / "validation.json").read_text(encoding="utf-8"))
            plan_entries = [item for item in validation["terraform"] if item["command"].startswith("terraform plan ")]
            self.assertEqual(len(plan_entries), 1)
            self.assertTrue(plan_entries[0]["skipped"])
            self.assertEqual(plan_entries[0]["reason"], "Skipped in credentialless validation mode")


if __name__ == "__main__":
    unittest.main()
