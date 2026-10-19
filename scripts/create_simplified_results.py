"""Create a compact CSV from an existing experiment results file."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cue_eval.output_writer import (
    SIMPLIFIED_RESULTS_FILENAME,
    simplify_experiment_rows,
    write_csv,
)


SOURCE_FILENAME = "experiment_results.csv"


def parse_args() -> argparse.Namespace:
    """Collect the completed experiment output folder."""
    parser = argparse.ArgumentParser(
        description="Create a compact CSV for manual experiment analysis."
    )
    parser.add_argument(
        "experiment_output_dir",
        type=Path,
        help=f"Folder containing {SOURCE_FILENAME}.",
    )
    return parser.parse_args()


def read_results(path: Path) -> list[dict[str, Any]]:
    """Read the original row-level experiment results."""
    if not path.is_file():
        raise FileNotFoundError(f"Experiment results not found: {path}")
    with path.open(newline="", encoding="utf-8-sig") as file:
        return list(csv.DictReader(file))


def main() -> None:
    """Convert the original results and save them beside the source file."""
    output_dir = parse_args().experiment_output_dir
    source_path = output_dir / SOURCE_FILENAME
    output_path = output_dir / SIMPLIFIED_RESULTS_FILENAME
    rows = read_results(source_path)
    write_csv(output_path, simplify_experiment_rows(rows))
    print(f"Wrote {len(rows)} rows to {output_path}")


if __name__ == "__main__":
    main()
