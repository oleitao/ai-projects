#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from infra_agents.agents.requirements import RequirementsAgent
from infra_agents.contracts import JobState
from infra_agents.llm import build_llm_from_env
from infra_agents.rag import LocalKnowledgeBase


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate requirements agent against dataset")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("datasets/finetune_train.jsonl"),
        help="JSONL dataset with task=requirements_spec_v1",
    )
    parser.add_argument(
        "--max-samples",
        type=int,
        default=50,
        help="Maximum number of samples to evaluate",
    )
    return parser.parse_args()


def _read_dataset(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if payload.get("task") == "requirements_spec_v1":
            rows.append(payload)
    return rows


def _score(expected: dict[str, Any], predicted: dict[str, Any]) -> dict[str, float]:
    checks = {
        "cloud": float(expected.get("cloud") == predicted.get("cloud")),
        "region": float(expected.get("region") == predicted.get("region")),
        "env": float(expected.get("env") == predicted.get("env")),
        "compute.type": float(
            expected.get("compute", {}).get("type") == predicted.get("compute", {}).get("type")
        ),
        "data.engine": float(
            expected.get("data", {}).get("engine") == predicted.get("data", {}).get("engine")
        ),
        "security.encryption": float(
            expected.get("security", {}).get("encryption") == predicted.get("security", {}).get("encryption")
        ),
    }
    checks["avg"] = sum(checks.values()) / len(checks)
    return checks


def main() -> None:
    args = parse_args()
    if not args.dataset.exists():
        raise SystemExit(f"Dataset not found: {args.dataset}")

    rows = _read_dataset(args.dataset)[: args.max_samples]
    if not rows:
        raise SystemExit("No requirements_spec_v1 samples found in dataset")

    kb = LocalKnowledgeBase()
    llm = build_llm_from_env()
    agent = RequirementsAgent(knowledge_base=kb, llm=llm)

    totals: dict[str, float] = {}
    for row in rows:
        prompt = row.get("input", {}).get("prompt", "")
        expected = row.get("output", {})

        with tempfile.TemporaryDirectory() as tmp:
            state = JobState(
                job_id="eval",
                prompt=prompt,
                workspace=Path(tmp),
                execution_mode="plan-only",
                max_iterations=1,
                status="running",
            )
            agent.run(state)
            predicted = state.spec.to_dict() if state.spec else {}

        sample_scores = _score(expected, predicted)
        for key, value in sample_scores.items():
            totals[key] = totals.get(key, 0.0) + value

    n = float(len(rows))
    metrics = {k: round(v / n, 4) for k, v in totals.items()}
    print(json.dumps({"samples": len(rows), "metrics": metrics}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
