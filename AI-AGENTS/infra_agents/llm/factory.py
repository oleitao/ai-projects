from __future__ import annotations

import os
from pathlib import Path

from infra_agents.llm.base import AgentLLM, LLMConfigurationError
from infra_agents.llm.ollama import OllamaConfig, OllamaLLM
from infra_agents.llm.replay import ReplayLLM


def build_llm_from_env() -> AgentLLM:
    """Build LLM backend from environment variables.

    Supported modes:
    - ollama (default): calls a local Ollama API.
    - replay: loads predictions from JSONL file.

    Variables:
    - INFRA_AGENTS_LLM_MODE
    - INFRA_AGENTS_LLM_REPLAY_FILE
    - INFRA_AGENTS_LLM_BASE_URL
    - INFRA_AGENTS_LLM_MODEL
    - INFRA_AGENTS_LLM_TIMEOUT
    - INFRA_AGENTS_LLM_TEMPERATURE
    """

    mode = os.getenv("INFRA_AGENTS_LLM_MODE", "ollama").strip().lower()

    if mode == "replay":
        file_path = os.getenv("INFRA_AGENTS_LLM_REPLAY_FILE", "").strip()
        if not file_path:
            raise LLMConfigurationError("INFRA_AGENTS_LLM_REPLAY_FILE é obrigatório em modo replay.")
        path = Path(file_path)
        if not path.exists():
            raise LLMConfigurationError(f"Ficheiro replay não encontrado: {path}")
        return ReplayLLM.from_jsonl(path)

    if mode in {"", "ollama", "local", "live"}:
        base_url = os.getenv("INFRA_AGENTS_LLM_BASE_URL", "http://localhost:11434").strip()
        model = os.getenv("INFRA_AGENTS_LLM_MODEL", "llama3.2:latest").strip()
        if not base_url or not model:
            raise LLMConfigurationError("INFRA_AGENTS_LLM_BASE_URL e INFRA_AGENTS_LLM_MODEL são obrigatórios.")

        try:
            timeout_seconds = float(os.getenv("INFRA_AGENTS_LLM_TIMEOUT", "60").strip())
        except ValueError:
            timeout_seconds = 60.0

        try:
            temperature = float(os.getenv("INFRA_AGENTS_LLM_TEMPERATURE", "0").strip())
        except ValueError:
            temperature = 0.0

        return OllamaLLM(
            OllamaConfig(
                base_url=base_url,
                model=model,
                timeout_seconds=timeout_seconds,
                temperature=temperature,
            )
        )

    raise LLMConfigurationError(f"Modo LLM inválido: {mode}. Usa 'ollama' ou 'replay'.")
