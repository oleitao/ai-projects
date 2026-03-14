from __future__ import annotations

import uuid
from pathlib import Path

from infra_agents.contracts import AgentFinding, JobState
from infra_agents.tools.filesystem import ensure_dir, write_json


def create_job_state(
    *,
    prompt: str,
    output_root: Path,
    execution_mode: str,
    validation_mode: str,
    max_iterations: int,
) -> JobState:
    job_id = uuid.uuid4().hex[:12]
    workspace = output_root / job_id
    ensure_dir(workspace)
    return JobState(
        job_id=job_id,
        prompt=prompt,
        workspace=workspace,
        execution_mode=execution_mode,
        validation_mode=validation_mode,
        max_iterations=max_iterations,
        status="running",
    )


def write_job_summary(state: JobState) -> None:
    payload = {
        "job_id": state.job_id,
        "prompt": state.prompt,
        "status": state.status,
        "workspace": str(state.workspace),
        "execution_mode": state.execution_mode,
        "validation_mode": state.validation_mode,
        "iterations": state.iteration,
        "blocked": state.blocked,
        "artifacts": state.artifacts,
        "findings": [
            {
                "severity": f.severity,
                "source": f.source,
                "message": f.message,
                "file": f.file,
                "line": f.line,
            }
            for f in state.findings
        ],
        "history": state.history,
        "spec": state.spec.to_dict() if state.spec else None,
    }
    write_json(state.workspace / "summary.json", payload)


def info_finding(message: str, source: str = "Supervisor") -> AgentFinding:
    return AgentFinding(severity="info", message=message, source=source)
