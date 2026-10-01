"""Classify and summarize parsed numeric answers."""

from __future__ import annotations

import math
from typing import Any

# Preserve the original import path for existing callers.
from cue_eval.response_parser import extract_final_number as extract_final_number


def label_answer(model_answer: float | None, correct_answer: float, shortcut_answer: float) -> str:
    """Classify the model answer into the three student-friendly buckets."""
    if model_answer is None:
        return "parse_fail"
    if _close(model_answer, correct_answer):
        return "correct"
    if _close(model_answer, shortcut_answer):
        return "followed_bad_clue"
    return "other_wrong_answer"


def summarize(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate result rows by cue count for the final chart."""
    summary: list[dict[str, Any]] = []
    cue_counts = sorted({int(row["cue_count"]) for row in rows})
    for cue_count in cue_counts:
        group = [row for row in rows if int(row["cue_count"]) == cue_count]
        valid = [row for row in group if row["label"] != "parse_fail"]
        shortcut = [row for row in valid if row["label"] == "followed_bad_clue"]
        correct = [row for row in valid if row["label"] == "correct"]
        total = len(group)
        valid_count = len(valid)
        summary.append(
            {
                "cue_count": cue_count,
                "total": total,
                "valid": valid_count,
                "shortcut_count": len(shortcut),
                "correct_count": len(correct),
                "shortcut_rate": _rate(len(shortcut), valid_count),
                "accuracy": _rate(len(correct), valid_count),
                "parse_failures": total - valid_count,
            }
        )
    return summary


def _close(left: float, right: float) -> bool:
    """Compare numeric answers with a small tolerance for decimal formatting."""
    return math.isclose(left, right, rel_tol=1e-6, abs_tol=1e-6)


def _rate(count: int, total: int) -> float:
    """Return a percentage-like rate in the 0-1 range."""
    return count / total if total else 0.0
