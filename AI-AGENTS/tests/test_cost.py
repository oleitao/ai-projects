import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from infra_agents.tools.command_runner import CommandResult
from infra_agents.tools.cost import run_infracost


class InfracostToolTests(unittest.TestCase):
    def test_run_infracost_skips_without_credentials(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("infra_agents.tools.cost.shutil.which", return_value="/opt/homebrew/bin/infracost"):
                with patch("infra_agents.tools.cost._has_infracost_credentials", return_value=False):
                    result = run_infracost(Path(tmp))

        self.assertTrue(result.skipped)
        self.assertEqual(result.reason, "Infracost API key not configured")

    def test_run_infracost_skips_on_environment_error(self):
        failing = CommandResult(
            command=["infracost", "breakdown", "--path", ".", "--format", "json", "--out-file", "reports/infracost.json"],
            returncode=1,
            stdout="Error: INFRACOST_API_KEY is not set",
            stderr="lookup dashboard.api.infracost.io: no such host",
        )

        with tempfile.TemporaryDirectory() as tmp:
            with patch("infra_agents.tools.cost.shutil.which", return_value="/opt/homebrew/bin/infracost"):
                with patch("infra_agents.tools.cost._has_infracost_credentials", return_value=True):
                    with patch("infra_agents.tools.cost.run_command", return_value=failing):
                        result = run_infracost(Path(tmp))

        self.assertTrue(result.skipped)
        self.assertEqual(result.reason, "Infracost unavailable or not configured in this environment")


if __name__ == "__main__":
    unittest.main()
