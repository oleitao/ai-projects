import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from infra_agents.agents.validator import ValidatorAgent
from infra_agents.tools.command_runner import CommandResult
from infra_agents.tools.terraform_cli import local_validation_workspace, run_security_scanners


class TerraformValidationWorkspaceTests(unittest.TestCase):
    def test_local_validation_workspace_skips_backend_tf(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "backend.tf").write_text('terraform { backend "s3" {} }\n', encoding="utf-8")
            (root / "main.tf").write_text('resource "terraform_data" "x" {}\n', encoding="utf-8")
            (root / "terraform.tfvars").write_text('env = "prod"\n', encoding="utf-8")
            (root / ".terraform.lock.hcl").write_text("# lock\n", encoding="utf-8")
            (root / ".terraform").mkdir()
            (root / ".terraform" / "modules.json").write_text("{}", encoding="utf-8")
            (root / "reports").mkdir()
            (root / "reports" / "validation.json").write_text("{}", encoding="utf-8")

            with local_validation_workspace(root) as workspace:
                self.assertFalse((workspace / "backend.tf").exists())
                self.assertTrue((workspace / "main.tf").exists())
                self.assertTrue((workspace / "terraform.tfvars").exists())
                self.assertTrue((workspace / ".terraform.lock.hcl").exists())
                self.assertTrue((workspace / ".terraform" / "modules.json").exists())
                self.assertFalse((workspace / "reports").exists())


class ValidatorAgentPlanTests(unittest.TestCase):
    def test_run_plan_if_possible_uses_local_workspace_and_runs_plan(self):
        agent = ValidatorAgent()
        terraform_results = [
            CommandResult(["terraform", "fmt", "-recursive"], 0, "", ""),
            CommandResult(["terraform", "init", "-backend=false", "-input=false"], 0, "", ""),
            CommandResult(["terraform", "validate"], 0, "", ""),
        ]

        captured_workdirs: list[Path] = []

        def fake_run_command(command: list[str], cwd: Path) -> CommandResult:
            captured_workdirs.append(cwd)
            return CommandResult(command=command, returncode=0, stdout="", stderr="")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "backend.tf").write_text('terraform { backend "s3" {} }\n', encoding="utf-8")
            (root / "main.tf").write_text('resource "terraform_data" "x" {}\n', encoding="utf-8")
            with patch("infra_agents.tools.command_runner.run_command", side_effect=fake_run_command):
                results = agent._run_plan_if_possible(terraform_results, root)

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].command, ["terraform", "init", "-backend=false", "-input=false"])
        self.assertEqual(
            results[1].command,
            ["terraform", "plan", "-lock=false", "-input=false", "-refresh=false", "-out=plan.out"],
        )
        self.assertEqual(len(captured_workdirs), 2)
        self.assertTrue(all(workdir != root for workdir in captured_workdirs))

    def test_shared_profile_error_is_treated_as_environment_issue(self):
        agent = ValidatorAgent()
        result = CommandResult(
            command=["terraform", "plan"],
            returncode=1,
            stdout="",
            stderr="Error: failed to get shared config profile, devops",
        )

        findings = agent._to_findings(result, source="terraform")

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].severity, "warning")

    def test_credentialless_mode_skips_plan_without_warning(self):
        agent = ValidatorAgent()
        terraform_results = [
            CommandResult(["terraform", "fmt", "-recursive"], 0, "", ""),
            CommandResult(["terraform", "init", "-backend=false", "-input=false"], 0, "", ""),
            CommandResult(["terraform", "validate"], 0, "", ""),
        ]

        results = agent._run_plan_if_possible(terraform_results, Path("."), validation_mode="credentialless")

        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].skipped)
        self.assertEqual(results[0].reason, "Skipped in credentialless validation mode")
        self.assertEqual(agent._to_findings(results[0], source="terraform"), [])


class SecurityScannerCommandTests(unittest.TestCase):
    def test_run_security_scanners_uses_checkov_external_modules_and_trivy_when_available(self):
        captured_commands: list[list[str]] = []

        def fake_run_command(command: list[str], cwd: Path) -> CommandResult:
            captured_commands.append(command)
            return CommandResult(command=command, returncode=0, stdout="", stderr="")

        with tempfile.TemporaryDirectory() as tmp:
            with patch("infra_agents.tools.terraform_cli.run_command", side_effect=fake_run_command):
                with patch("infra_agents.tools.terraform_cli.shutil.which") as mock_which:
                    mock_which.side_effect = lambda tool: "/opt/homebrew/bin/trivy" if tool == "trivy" else f"/usr/bin/{tool}"
                    run_security_scanners(Path(tmp))

        self.assertEqual(
            captured_commands[2],
            ["checkov", "-d", ".", "--download-external-modules", "true", "--skip-path", ".external_modules"],
        )
        self.assertEqual(
            captured_commands[3],
            [
                "trivy",
                "config",
                "--skip-check-update",
                "--skip-version-check",
                "--disable-telemetry",
                "--tf-exclude-downloaded-modules",
                "--tf-vars",
                "terraform.tfvars",
                "--skip-dirs",
                ".external_modules",
                "--misconfig-scanners",
                "terraform",
                "--exit-code",
                "1",
                ".",
            ],
        )


if __name__ == "__main__":
    unittest.main()
