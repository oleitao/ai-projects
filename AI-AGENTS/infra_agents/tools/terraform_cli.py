from __future__ import annotations

import shutil
import tempfile
from contextlib import contextmanager
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


@contextmanager
def local_validation_workspace(source: Path):
    """Create a temporary workspace that disables remote backend usage for plan validation."""

    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        for path in source.iterdir():
            if path.name == "backend.tf":
                continue
            if path.is_dir():
                continue
            if path.name == ".terraform.lock.hcl" or path.suffix in {".tf", ".tfvars"}:
                shutil.copy2(path, workspace / path.name)
        terraform_cache = source / ".terraform"
        if terraform_cache.exists() and terraform_cache.is_dir():
            shutil.copytree(terraform_cache, workspace / ".terraform")
        yield workspace
