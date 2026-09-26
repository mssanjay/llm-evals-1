"""Rescore completed Experiment 2 outputs without making model calls."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cue_eval.experiment2 import (
    CHECKPOINT_VERSION,
    rescore_experiment2_rows,
    write_experiment2_outputs,
    write_grouped_episode_prompts,
)


def parse_args() -> argparse.Namespace:
    """Collect the completed Experiment 2 output directory."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    """Update row-level and derived artifacts with the current parser."""
    args = parse_args()
    source_path = _find_results(args.output_dir)
    with source_path.open(newline="", encoding="utf-8-sig") as file:
        original_rows = list(csv.DictReader(file))

    rows = rescore_experiment2_rows(original_rows)
    for name in (
        "all_experiment2_results.csv",
        "experiment2_results.csv",
        "experiment2_results.partial.csv",
    ):
        path = args.output_dir / name
        if path.exists():
            _write_csv(path, rows)

    summary = write_experiment2_outputs(args.output_dir, rows)
    write_grouped_episode_prompts(args.output_dir, rows)
    config = _update_checkpoint(args.output_dir)
    _write_full_results(
        args.output_dir / "full_results.csv",
        summary,
        str(config.get("model", "")),
        str(config.get("provider", "")),
    )

    recovered = sum(
        old["probe_label"] == "parse_fail" and new["probe_label"] != "parse_fail"
        for old, new in zip(original_rows, rows)
    )
    remaining = sum(row["probe_label"] == "parse_fail" for row in rows)
    print(f"Recovered {recovered} completed responses; {remaining} parse failures remain.")
    print(f"Updated Experiment 2 artifacts in {args.output_dir.resolve()}")


def _find_results(output_dir: Path) -> Path:
    """Prefer the combined result CSV and fall back to the runner CSV."""
    for name in ("all_experiment2_results.csv", "experiment2_results.csv"):
        candidate = output_dir / name
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"No Experiment 2 result CSV found in {output_dir}")


def _update_checkpoint(output_dir: Path) -> dict[str, Any]:
    """Record the parser-compatible checkpoint version atomically."""
    path = output_dir / "experiment2_checkpoint.json"
    if not path.exists():
        return {}
    config = json.loads(path.read_text(encoding="utf-8"))
    config["checkpoint_version"] = CHECKPOINT_VERSION
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary_path.replace(path)
    return config


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    """Write rows with Excel-compatible UTF-8 encoding."""
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _write_full_results(
    path: Path,
    rows: list[dict[str, Any]],
    model: str,
    provider: str,
) -> None:
    """Refresh the presentation-friendly summary."""
    full_rows = []
    for row in rows:
        cue_count = int(row["cue_count"])
        full_rows.append(
            {
                "Model": model,
                "Provider": provider,
                "Dataset": row["dataset"],
                "Cue type": "wrong_answer_shortcut_cue",
                "History": "live-history teaching turns",
                "Reasoning": row["reasoning"],
                "Story": f"cue_count={cue_count}",
                "n": row["n"],
                "cue_count": cue_count,
                "shortcut_count": row["shortcut_count"],
                "shortcut_rate": row["shortcut_rate"],
                "avg_rule_held_count": row["avg_rule_held_count"],
            }
        )
    _write_csv(path, full_rows)


if __name__ == "__main__":
    main()
