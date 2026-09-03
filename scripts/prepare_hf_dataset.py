"""Prepare MATH-500 examples for the cue experiment."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cue_eval.hf_datasets import prepare_dataset


def parse_args() -> argparse.Namespace:
    """Collect dataset-preparation options."""
    parser = argparse.ArgumentParser(description="Prepare Hugging Face dataset rows.")
    parser.add_argument("--dataset", choices=["math500"], required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--fetch-size", type=int, default=250)
    return parser.parse_args()


def main() -> None:
    """Fetch and convert a dataset sample."""
    args = parse_args()
    rows = prepare_dataset(
        name=args.dataset,
        output_path=args.output,
        limit=args.limit,
        fetch_size=args.fetch_size,
    )
    print(f"Prepared {len(rows)} usable {args.dataset} rows at {args.output}")


if __name__ == "__main__":
    main()
