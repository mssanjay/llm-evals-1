"""Run Experiment 2 live-history teaching turns on MATH-500."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cue_eval.live_history import run_live_history_experiment, write_live_history_outputs


def parse_args() -> argparse.Namespace:
    """Collect options for the live-history comparison."""
    parser = argparse.ArgumentParser(description="Run live-history cue-following comparison.")
    parser.add_argument(
        "--provider",
        choices=["dry-run", "mock", "ollama", "openrouter", "aws", "azure-foundry", "azure-openai", "azure-ai"],
        default="dry-run",
    )
    parser.add_argument("--model", default="qwen3-32b")
    parser.add_argument("--prepared-dir", default="data")
    parser.add_argument("--output-dir", default="outputs/live_history_comparison")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--max-tokens", type=int, default=256)
    parser.add_argument("--reasoning-modes", default="off,on")
    parser.add_argument("--story-pool", default="data/story_pool.jsonl")
    return parser.parse_args()


def main() -> None:
    """Run MATH-500 and write the attached-plot-style graph."""
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    reasoning_modes = [mode.strip() for mode in args.reasoning_modes.split(",") if mode.strip()]

    dataset = "math500"
    data_path = _prepared_path(dataset, args.limit, Path(args.prepared_dir))
    all_rows = run_live_history_experiment(
        data_path=data_path,
        dataset_name=dataset,
        output_dir=output_dir,
        provider=args.provider,
        model=args.model,
        limit=args.limit,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        reasoning_modes=reasoning_modes,
        story_pool_path=args.story_pool or None,
    )
    print(f"Ran {len(all_rows)} live-history episodes for {dataset}.")

    _write_csv(output_dir / "all_live_history_results.csv", all_rows)
    summary = write_live_history_outputs(output_dir, all_rows)
    _write_full_results(output_dir / "full_results.csv", summary, args.model, args.provider)
    print(f"Wrote {len(summary)} summary rows to {output_dir.resolve()}")


def _prepared_path(dataset: str, limit: int, prepared_dir: Path) -> Path:
    """Use exact prepared files when present, otherwise reuse the 100-line file."""
    exact_path = prepared_dir / f"{dataset}_prepared_{limit}.jsonl"
    stable_path = prepared_dir / f"{dataset}_prepared_100.jsonl"
    return exact_path if exact_path.exists() else stable_path


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    """Write combined row-level results."""
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _write_full_results(path: Path, rows: list[dict[str, Any]], model: str, provider: str) -> None:
    """Write a coach-friendly condition summary with presentation columns first."""
    full_rows: list[dict[str, Any]] = []
    for row in rows:
        held_count = int(row["rule_held_count"])
        full_rows.append(
            {
                "Model": model,
                "Provider": provider,
                "Dataset": "math500",
                "Cue type": "wrong_answer_shortcut_cue",
                "History": "live-history teaching turns",
                "Reasoning": row["reasoning"],
                "Story": f"rule_held_count={held_count}",
                "n": row["n"],
                "rule_held_count": held_count,
                "shortcut_count": row["shortcut_count"],
                "shortcut_rate": row["shortcut_rate"],
            }
        )
    _write_csv(path, full_rows)


if __name__ == "__main__":
    main()
