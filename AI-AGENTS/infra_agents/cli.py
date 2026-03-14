from __future__ import annotations

import argparse
import json
from pathlib import Path

from infra_agents.orchestration import LangGraphUnavailableError
from infra_agents.orchestrator import WorkflowSupervisor


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AI Agents Terraform pipeline")
    parser.add_argument("--prompt", type=str, help="Prompt em texto livre")
    parser.add_argument("--prompt-file", type=Path, help="Ficheiro com o prompt")
    parser.add_argument("--resume-workspace", type=Path, help="Workspace de job existente para retomar execução")
    parser.add_argument("--output-dir", type=Path, default=Path("jobs"), help="Diretório de outputs")
    parser.add_argument("--max-iterations", type=int, default=3, help="Máximo de loops de correção")
    parser.add_argument(
        "--execution-mode",
        type=str,
        default="plan-only",
        choices=["plan-only"],
        help="Modo de execução",
    )
    parser.add_argument(
        "--engine",
        type=str,
        default="auto",
        choices=["auto", "classic", "langgraph"],
        help="Motor de orquestração (auto seleciona langgraph quando disponível)",
    )
    parser.add_argument(
        "--validation-mode",
        type=str,
        default="auto",
        choices=["auto", "credentialless"],
        help="Modo de validação Terraform",
    )
    return parser.parse_args()


def _load_prompt(args: argparse.Namespace) -> str:
    if args.resume_workspace:
        return ""
    if args.prompt:
        return args.prompt
    if args.prompt_file:
        return args.prompt_file.read_text(encoding="utf-8")
    raise SystemExit("É obrigatório usar --prompt ou --prompt-file")


def main() -> None:
    args = parse_args()

    try:
        supervisor = WorkflowSupervisor(max_iterations=args.max_iterations, engine=args.engine)
    except LangGraphUnavailableError as exc:
        raise SystemExit(str(exc)) from exc

    try:
        if args.resume_workspace:
            state = supervisor.resume(args.resume_workspace)
        else:
            prompt = _load_prompt(args)
            state = supervisor.run(
                prompt=prompt,
                output_root=args.output_dir,
                execution_mode=args.execution_mode,
                validation_mode=args.validation_mode,
            )
    except (RuntimeError, ValueError, NotImplementedError) as exc:
        raise SystemExit(str(exc)) from exc

    summary = {
        "job_id": state.job_id,
        "status": state.status,
        "workspace": str(state.workspace),
        "findings_count": len(state.findings),
        "engine": supervisor.engine,
        "validation_mode": state.validation_mode,
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
