from __future__ import annotations

import os
from pathlib import Path
import shutil

from infra_agents.tools.command_runner import CommandResult, run_command


def run_infracost(workdir: Path, out_file: str = "reports/infracost.json") -> CommandResult:
    command = [
        "infracost",
        "breakdown",
        "--path",
        ".",
        "--format",
        "json",
        "--out-file",
        out_file,
    ]

    if shutil.which("infracost") is None:
        return CommandResult(
            command=command,
            returncode=127,
            stdout="",
            stderr="",
            skipped=True,
            reason="Command not found: infracost",
        )

    if not _has_infracost_credentials():
        return CommandResult(
            command=command,
            returncode=0,
            stdout="",
            stderr="",
            skipped=True,
            reason="Infracost API key not configured",
        )

    result = run_command(command, workdir)
    if result.returncode != 0 and _is_infracost_environment_issue(result):
        return CommandResult(
            command=result.command,
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            skipped=True,
            reason="Infracost unavailable or not configured in this environment",
        )
    return result


def _has_infracost_credentials() -> bool:
    if os.getenv("INFRACOST_API_KEY", "").strip():
        return True
    return Path.home().joinpath(".config", "infracost", "credentials.yml").exists()


def _is_infracost_environment_issue(result: CommandResult) -> bool:
    text = f"{result.stdout}\n{result.stderr}".lower()
    markers = [
        "infracost_api_key is not set",
        "credentials.yml",
        "no such host",
        "lookup dashboard.api.infracost.io",
        "lookup pricing.api.infracost.io",
    ]
    return any(marker in text for marker in markers)
