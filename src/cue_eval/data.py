"""Load the small showcase dataset."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_examples(path: str | Path) -> list[dict[str, Any]]:
    """Read JSONL examples that include correct and shortcut answers."""
    rows: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            _validate_row(row, line_number)
            rows.append(row)
    return rows


def _validate_row(row: dict[str, Any], line_number: int) -> None:
    """Fail early when an example is missing a required field."""
    required = {"id", "problem", "correct_answer", "bad_clue", "shortcut_answer"}
    missing = required.difference(row)
    if missing:
        names = ", ".join(sorted(missing))
        raise ValueError(f"Line {line_number} is missing: {names}")
