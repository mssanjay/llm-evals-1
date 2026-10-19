"""Combine validated Qwen and DeepSeek Experiment 1 runs."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cue_eval.experiment import validate_completed_matrix
from cue_eval.output_writer import (
    write_combined_experiment_outputs,
    write_csv,
    write_json,
)


def parse_args() -> argparse.Namespace:
    """Collect model-run folders and the combined output folder."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dirs", type=Path, nargs="+", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    """Verify matching runs before writing the combined matrix."""
    args = parse_args()
    if len(args.run_dirs) != 2:
        raise ValueError("Provide exactly two run directories: one Qwen and one DeepSeek.")
    rows: list[dict[str, Any]] = []
    usage_rows: list[dict[str, Any]] = []
    preflights: list[dict[str, Any]] = []
    for run_dir in args.run_dirs:
        rows.extend(_read_csv(run_dir / "experiment_results.csv"))
        usage_rows.extend(_read_csv(run_dir / "usage_by_subexperiment.csv"))
        preflight = _read_json(run_dir / "reasoning_preflight.json")
        if preflight.get("passed") is not True:
            raise ValueError(f"Reasoning preflight did not pass for {run_dir}.")
        preflights.append(preflight)

    report = validate_completed_matrix(rows, expected_models=len(args.run_dirs))
    report["reasoning_preflights"] = [
        {
            "provider": item["provider"],
            "model": item["model"],
            "comparison": item.get(
                "comparison",
                {
                    "measurement": "reasoning_chars",
                    "off": item["off"]["reasoning_chars"],
                    "on": item["on"]["reasoning_chars"],
                },
            ),
        }
        for item in preflights
    ]

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "combined_experiment_results.csv", rows)
    write_csv(args.output_dir / "combined_usage_by_subexperiment.csv", usage_rows)
    write_json(args.output_dir / "matrix_validation.json", report)
    summary = write_combined_experiment_outputs(args.output_dir, rows)
    print(
        f"Validated {report['result_rows']} rows across {report['subexperiments']} cells. "
        f"Wrote {len(summary)} model-level summary rows and one combined graph set."
    )


def _read_csv(path: Path) -> list[dict[str, Any]]:
    """Read one required CSV artifact."""
    if not path.exists():
        raise FileNotFoundError(path)
    with path.open(newline="", encoding="utf-8-sig") as file:
        return list(csv.DictReader(file))


def _read_json(path: Path) -> dict[str, Any]:
    """Read one required JSON artifact."""
    if not path.exists():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
