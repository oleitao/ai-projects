#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export fine-tuning dataset from completed jobs")
    parser.add_argument("--jobs-dir", type=Path, default=Path("jobs"), help="Directory with job folders")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("datasets/finetune_train.jsonl"),
        help="Output jsonl file",
    )
    return parser.parse_args()


def _load_summary(path: Path) -> dict[str, Any] | None:
    summary_path = path / "summary.json"
    if not summary_path.exists():
        return None
    try:
        return json.loads(summary_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _extract_history_entry(summary: dict[str, Any], agent_name: str) -> dict[str, Any] | None:
    for item in summary.get("history", []):
        if item.get("agent") == agent_name:
            return item
    return None


def _parse_tfvars(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}

    text = path.read_text(encoding="utf-8")
    out: dict[str, Any] = {}
    for key in ["db_instance_class", "db_allocated_storage", "ec2_instance_type"]:
        match = re.search(rf"^{key}\s*=\s*(.+)$", text, flags=re.MULTILINE)
        if not match:
            continue
        value = match.group(1).strip().strip('"')
        if key == "db_allocated_storage":
            try:
                out[key] = int(value)
            except ValueError:
                continue
        else:
            out[key] = value
    return out


def export_examples(jobs_dir: Path) -> list[dict[str, Any]]:
    examples: list[dict[str, Any]] = []

    for job_dir in sorted([p for p in jobs_dir.iterdir() if p.is_dir()]):
        summary = _load_summary(job_dir)
        if not summary:
            continue

        prompt = summary.get("prompt", "")
        spec = summary.get("spec")
        if not prompt or not isinstance(spec, dict):
            continue

        # Requirements task
        examples.append(
            {
                "task": "requirements_spec_v1",
                "prompt_contains": prompt[:120],
                "input": {
                    "prompt": prompt,
                    "rag_sources": _extract_history_entry(summary, "Requisitos")
                    .get("metadata", {})
                    .get("rag_sources", [])
                    if _extract_history_entry(summary, "Requisitos")
                    else [],
                },
                "output": spec,
            }
        )

        # Planner task
        planner_entry = _extract_history_entry(summary, "Planeador de Arquitetura") or {}
        planner_metadata = planner_entry.get("metadata", {})
        examples.append(
            {
                "task": "planner_design_v1",
                "prompt_contains": f"cloud=aws region={spec.get('region', '')} env={spec.get('env', '')}",
                "input": {
                    "prompt": prompt,
                    "spec": spec,
                    "rag_sources": planner_metadata.get("rag_sources", []),
                },
                "output": {
                    "modules": planner_metadata.get("modules", []),
                    "notes": planner_metadata.get("llm_notes", []),
                },
            }
        )

        # Generator override task
        generator_entry = _extract_history_entry(summary, "Gerador Terraform") or {}
        generator_metadata = generator_entry.get("metadata", {})
        tfvars = _parse_tfvars(job_dir / "terraform.tfvars")
        overrides = {
            k: tfvars[k]
            for k in ["db_instance_class", "db_allocated_storage", "ec2_instance_type"]
            if k in tfvars
        }
        if generator_metadata.get("tfvars_overrides"):
            overrides.update(generator_metadata["tfvars_overrides"])

        examples.append(
            {
                "task": "generator_overrides_v1",
                "prompt_contains": f"cloud=aws region={spec.get('region', '')} env={spec.get('env', '')}",
                "input": {
                    "prompt": prompt,
                    "spec": spec,
                    "rag_sources": generator_metadata.get("rag_sources", []),
                },
                "output": {
                    "tfvars_overrides": overrides,
                },
            }
        )

    return examples


def main() -> None:
    args = parse_args()
    if not args.jobs_dir.exists():
        raise SystemExit(f"Jobs directory not found: {args.jobs_dir}")

    examples = export_examples(args.jobs_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as fh:
        for item in examples:
            fh.write(json.dumps(item, ensure_ascii=False) + "\n")

    counts: dict[str, int] = {}
    for item in examples:
        counts[item["task"]] = counts.get(item["task"], 0) + 1

    print(
        json.dumps(
            {
                "output": str(args.output),
                "examples": len(examples),
                "by_task": counts,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
