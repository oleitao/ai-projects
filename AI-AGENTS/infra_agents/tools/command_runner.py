from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class CommandResult:
    command: list[str]
    returncode: int
    stdout: str
    stderr: str
    skipped: bool = False
    reason: str | None = None


def run_command(command: list[str], cwd: Path) -> CommandResult:
    if shutil.which(command[0]) is None:
        return CommandResult(
            command=command,
            returncode=127,
            stdout="",
            stderr="",
            skipped=True,
            reason=f"Command not found: {command[0]}",
        )

    completed = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    return CommandResult(
        command=command,
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )
