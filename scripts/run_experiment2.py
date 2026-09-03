"""Run Experiment 2 live-history teaching turns on MATH-500."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cue_eval.experiment2 import run_experiment2_experiment, write_experiment2_outputs


def parse_args() -> argparse.Namespace:
    """Collect options for the live-history comparison."""
    parser = argparse.ArgumentParser(description="Run live-history cue-following comparison.")
    parser.add_argument(
        "--provider",
        choices=["dryrun", "mock", "ollama", "openrouter", "aws", "azure-foundry", "azure-openai", "azure-ai"],
        default="dryrun",
    )
    parser.add_argument("--model", default="qwen3-32b")
    parser.add_argument("--prepared-dir", default="data")
    parser.add_argument("--output-dir", default="outputs/experiment2_comparison")
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--max-tokens", type=int, default=256)
    parser.add_argument("--reasoning-modes", default="off,on")
    parser.add_argument("--cue-counts", default="1,2,3,4,5,6,7,8,9,10")
    parser.add_argument(
        "--max-workers",
        type=int,
        default=0,
        help="Parallel episodes to run at once. Auto: 1 for Ollama, 4 for hosted providers.",
    )
    parser.add_argument("--story-pool", default="data/story_pool.jsonl")
    return parser.parse_args()


def main() -> None:
    """Run MATH-500 and write the attached-plot-style graph."""
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    reasoning_modes = [mode.strip() for mode in args.reasoning_modes.split(",") if mode.strip()]
    cue_counts = [int(value.strip()) for value in args.cue_counts.split(",") if value.strip()]
    max_workers = args.max_workers or (1 if args.provider == "ollama" else 4)

    dataset = "math500"
    data_path = _prepared_path(dataset, Path(args.prepared_dir))
    all_rows = run_experiment2_experiment(
        data_path=data_path,
        dataset_name=dataset,
        output_dir=output_dir,
        provider=args.provider,
        model=args.model,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        reasoning_modes=reasoning_modes,
        cue_counts=cue_counts,
        max_workers=max_workers,
        story_pool_path=args.story_pool or None,
    )
    print(f"Ran {len(all_rows)} live-history episodes for {dataset}.")

    _write_csv(output_dir / "all_experiment2_results.csv", all_rows)
    summary = write_experiment2_outputs(output_dir, all_rows)
    _write_full_results(output_dir / "full_results.csv", summary, args.model, args.provider)
    print(f"Wrote {len(summary)} summary rows to {output_dir.resolve()}")


def _prepared_path(dataset: str, prepared_dir: Path) -> Path:
    """Use every row from the stable prepared MATH-500 file."""
    return prepared_dir / f"{dataset}_prepared_50.jsonl"


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
        cue_count = int(row["cue_count"])
        full_rows.append(
            {
                "Model": model,
                "Provider": provider,
                "Dataset": "math500",
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
