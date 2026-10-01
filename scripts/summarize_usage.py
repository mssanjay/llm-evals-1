"""Summarize token usage and estimated cost for an existing experiment CSV."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cue_eval.usage import (
    format_usage_summary,
    resolve_token_pricing,
    summarize_usage,
    write_usage_summary,
)


def parse_args() -> argparse.Namespace:
    """Collect the saved-run location and pricing inputs."""
    parser = argparse.ArgumentParser(description="Summarize model tokens and estimated run cost.")
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--provider", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--input-field", default="probe_prompt_tokens")
    parser.add_argument("--output-field", default="probe_completion_tokens")
    parser.add_argument("--input-cost-per-million")
    parser.add_argument("--output-cost-per-million")
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> None:
    """Read stored rows, calculate usage, and optionally save JSON."""
    args = parse_args()
    with args.csv.open("r", newline="", encoding="utf-8-sig") as file:
        rows = list(csv.DictReader(file))

    pricing = resolve_token_pricing(
        args.provider,
        args.model,
        args.input_cost_per_million,
        args.output_cost_per_million,
    )
    summary = summarize_usage(
        rows,
        args.input_field,
        args.output_field,
        args.provider,
        args.model,
        pricing,
    )
    if args.output:
        write_usage_summary(args.output, summary)
    print(format_usage_summary(summary))


if __name__ == "__main__":
    main()
