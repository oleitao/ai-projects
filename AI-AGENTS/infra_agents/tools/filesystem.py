from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_text(path: Path, content: str) -> str:
    ensure_dir(path.parent)
    path.write_text(content, encoding="utf-8")
    return str(path)


def write_json(path: Path, payload: dict[str, Any]) -> str:
    ensure_dir(path.parent)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return str(path)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")
