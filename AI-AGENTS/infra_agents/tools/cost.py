from __future__ import annotations

from pathlib import Path

from infra_agents.tools.command_runner import CommandResult, run_command


def run_infracost(workdir: Path, out_file: str = "reports/infracost.json") -> CommandResult:
    return run_command(
        [
            "infracost",
            "breakdown",
            "--path",
            ".",
            "--format",
            "json",
            "--out-file",
            out_file,
        ],
        workdir,
    )
