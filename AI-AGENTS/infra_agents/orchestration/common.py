from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

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
        next_step="requirements",
    )


def write_job_summary(state: JobState) -> None:
    payload = state.to_dict()
    payload["iterations"] = state.iteration
    write_json(state.workspace / "summary.json", payload)


def info_finding(message: str, source: str = "Supervisor") -> AgentFinding:
    return AgentFinding(severity="info", message=message, source=source)


def checkpoint_path(workspace: Path) -> Path:
    return workspace / "runtime_checkpoint.json"


def write_runtime_checkpoint(
    *,
    state: JobState,
    engine: str,
    runtime: dict[str, Any],
) -> Path:
    payload = {
        "version": 1,
        "engine": engine,
        "job": state.to_dict(),
        "runtime": runtime,
    }
    path = checkpoint_path(state.workspace)
    ensure_dir(path.parent)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def load_runtime_checkpoint(workspace: Path) -> dict[str, Any]:
    path = checkpoint_path(workspace)
    payload = json.loads(path.read_text(encoding="utf-8"))
    job_payload = payload.get("job", {})
    return {
        "version": payload.get("version", 1),
        "engine": payload.get("engine", ""),
        "job": JobState.from_dict(job_payload if isinstance(job_payload, dict) else {}),
        "runtime": payload.get("runtime", {}),
    }
