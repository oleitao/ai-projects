import tempfile
import unittest
from pathlib import Path

from infra_agents.orchestration import LangGraphUnavailableError, is_langgraph_available
from infra_agents.orchestrator import WorkflowSupervisor


class OrchestratorEngineTests(unittest.TestCase):
    def test_classic_engine_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
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
            supervisor = WorkflowSupervisor(max_iterations=1, engine="langgraph")
            state = supervisor.run(
                prompt="AWS dev eu-west-1 com EC2",
                output_root=Path(tmp),
                execution_mode="plan-only",
            )
            self.assertEqual(supervisor.engine, "langgraph")
            self.assertTrue((state.workspace / "summary.json").exists())


if __name__ == "__main__":
    unittest.main()
