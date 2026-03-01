from __future__ import annotations

from pathlib import Path

from infra_agents.tools.command_runner import CommandResult, run_command


def run_terraform_validation(workdir: Path) -> list[CommandResult]:
    commands = [
        ["terraform", "fmt", "-recursive"],
        ["terraform", "init", "-backend=false", "-input=false"],
        ["terraform", "validate"],
    ]
    return [run_command(cmd, workdir) for cmd in commands]


def run_security_scanners(workdir: Path) -> list[CommandResult]:
    commands = [
        ["tflint", "--init"],
        ["tflint"],
        ["checkov", "-d", "."],
        ["tfsec", "."],
    ]
    return [run_command(cmd, workdir) for cmd in commands]
