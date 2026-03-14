import tempfile
import unittest
import json
from pathlib import Path

from infra_agents.orchestrator import WorkflowSupervisor


class PipelineTests(unittest.TestCase):
    def test_pipeline_generates_core_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            prompt = "AWS prod eu-west-1 com ECS autoscaling e RDS postgres multi-az"
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
            backend_hcl = (state.workspace / "backend.hcl.example").read_text(encoding="utf-8")
            self.assertIn('data "aws_caller_identity" "current"', main_tf)
            self.assertIn("manage_master_user_password", main_tf)
            self.assertNotIn("password =", main_tf)
            self.assertIn("dynamodb_table", backend_hcl)

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
