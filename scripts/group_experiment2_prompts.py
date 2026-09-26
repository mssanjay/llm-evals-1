"""Group Experiment 2 prompt events into one JSONL object per episode."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cue_eval.experiment2 import write_grouped_episode_prompts


def parse_args() -> argparse.Namespace:
    """Collect the completed Experiment 2 output directory."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    """Load completed rows and write the grouped prompt artifact."""
    args = parse_args()
    results_path = _find_results(args.output_dir)
    with results_path.open(newline="", encoding="utf-8-sig") as file:
        rows = list(csv.DictReader(file))

    grouped = write_grouped_episode_prompts(args.output_dir, rows)
    output_path = args.output_dir / "model_prompts_by_episode.jsonl"
    print(f"Wrote {len(grouped)} grouped episodes to {output_path.resolve()}")


def _find_results(output_dir: Path) -> Path:
    """Prefer the combined result CSV and fall back to the runner CSV."""
    candidates = [
        output_dir / "all_experiment2_results.csv",
        output_dir / "experiment2_results.csv",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"No Experiment 2 result CSV found in {output_dir}")


if __name__ == "__main__":
    main()
