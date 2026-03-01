from __future__ import annotations

import os
from pathlib import Path

from infra_agents.llm.base import AgentLLM, NoopLLM
from infra_agents.llm.replay import ReplayLLM


def build_llm_from_env() -> AgentLLM:
    """Build LLM backend from environment variables.

    Supported modes:
    - off (default): disables LLM generation.
    - replay: loads predictions from JSONL file.

    Variables:
    - INFRA_AGENTS_LLM_MODE
    - INFRA_AGENTS_LLM_REPLAY_FILE
    """

    mode = os.getenv("INFRA_AGENTS_LLM_MODE", "off").strip().lower()
    if mode in {"", "off", "none"}:
        return NoopLLM()

    if mode == "replay":
        file_path = os.getenv("INFRA_AGENTS_LLM_REPLAY_FILE", "").strip()
        if not file_path:
            return NoopLLM()
        path = Path(file_path)
        if not path.exists():
            return NoopLLM()
        return ReplayLLM.from_jsonl(path)

    return NoopLLM()
