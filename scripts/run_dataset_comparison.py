"""Run Experiment 1 on the prepared MATH-500 dataset and plot the results."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cue_eval.experiment import run_experiment
from cue_eval.hf_datasets import prepare_dataset


def parse_args() -> argparse.Namespace:
    """Collect options for running Experiment 1 on MATH-500."""
    parser = argparse.ArgumentParser(description="Run cue-following on MATH-500.")
    parser.add_argument(
        "--provider",
        choices=["dry-run", "mock", "ollama", "openrouter", "azure-foundry", "azure-openai", "azure-ai"],
        default="dry-run",
    )
    parser.add_argument("--model", default="qwen3-32b")
    parser.add_argument("--output-dir", default="outputs/experiment_1_math500")
    parser.add_argument("--prepared-dir", default="", help="Directory with prepared *_prepared_<limit>.jsonl files.")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--fetch-size", type=int, default=300)
    parser.add_argument("--cue-counts", default="0,1,2,3,4,5,6,7,8,9,10")
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--max-tokens", type=int, default=256)
    parser.add_argument("--story-pool", default="data/story_pool.jsonl")
    parser.add_argument("--skip-prepare", action="store_true")
    return parser.parse_args()


def main() -> None:
    """Prepare MATH-500, run Experiment 1, and write one chart."""
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    cue_counts = [int(value.strip()) for value in args.cue_counts.split(",") if value.strip()]

    dataset = "math500"
    data_path = _prepared_path(dataset, args.limit, Path(args.prepared_dir), output_dir)
    if not args.skip_prepare:
        prepared = prepare_dataset(dataset, data_path, limit=args.limit, fetch_size=args.fetch_size)
        print(f"Prepared {len(prepared)} usable {dataset} rows.")

    summary_rows: list[dict[str, Any]] = []
    if not data_path.exists() or data_path.stat().st_size == 0:
        print("No usable MATH-500 rows found; writing zero rows for the summary.")
        for cue_count in cue_counts:
            summary_rows.append(
                {
                    "dataset": dataset,
                    "cue_count": cue_count,
                    "total": 0,
                    "valid": 0,
                    "shortcut_count": 0,
                    "correct_count": 0,
                    "shortcut_rate": 0.0,
                    "accuracy": 0.0,
                    "parse_failures": 0,
                }
            )
    else:
        rows, summary = run_experiment(
            data_path=data_path,
            output_dir=output_dir / dataset,
            provider=args.provider,
            model=args.model,
            cue_counts=cue_counts,
            limit=args.limit,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            story_pool_path=args.story_pool or None,
        )
        for row in summary:
            row["dataset"] = dataset
            summary_rows.append(row)
        print(f"Ran {len(rows)} prompt variants for {dataset}.")

    _write_summary(output_dir / "math500_summary.csv", summary_rows)
    _write_full_results(output_dir / "full_results.csv", summary_rows, args.model, args.provider)
    _write_chart(output_dir / "math500_shortcut_rate.png", summary_rows)
    print(f"Wrote Experiment 1 outputs to: {output_dir.resolve()}")


def _prepared_path(dataset: str, limit: int, prepared_dir: Path, output_dir: Path) -> Path:
    """Choose a stable prepared file when the caller provides a data directory."""
    if str(prepared_dir):
        exact_path = prepared_dir / f"{dataset}_prepared_{limit}.jsonl"
        stable_path = prepared_dir / f"{dataset}_prepared_100.jsonl"
        return exact_path if exact_path.exists() else stable_path
    return output_dir / f"{dataset}_prepared.jsonl"


def _write_summary(path: Path, rows: list[dict[str, Any]]) -> None:
    """Write MATH-500 metrics to CSV."""
    if not rows:
        return
    fieldnames = ["dataset"] + [key for key in rows[0] if key != "dataset"]
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
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
                "History": "single-story",
                "Reasoning": "off",
                "Story": f"cue_count={cue_count}",
                "n": row["valid"],
                "cue_count": cue_count,
                "total": row["total"],
                "shortcut_count": row["shortcut_count"],
                "correct_count": row["correct_count"],
                "shortcut_rate": row["shortcut_rate"],
                "accuracy": row["accuracy"],
                "parse_failures": row["parse_failures"],
            }
        )
    if not full_rows:
        return
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(full_rows[0].keys()))
        writer.writeheader()
        writer.writerows(full_rows)


def _write_chart(path: Path, rows: list[dict[str, Any]]) -> None:
    """Plot MATH-500 shortcut rate by cue count."""
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("Install matplotlib to create the comparison chart.")
        return

    cue_counts = sorted({int(row["cue_count"]) for row in rows})
    values = []
    totals = []
    for cue_count in cue_counts:
        match = next((row for row in rows if int(row["cue_count"]) == cue_count), None)
        values.append((match["shortcut_rate"] * 100) if match else 0.0)
        totals.append(match["valid"] if match else 0)

    plt.figure(figsize=(8, 4.5))
    plt.plot(cue_counts, values, marker="o", color="#2f7d6d", label="MATH-500")
    for cue_count, y_value, total in zip(cue_counts, values, totals):
        plt.text(cue_count, y_value + 2, f"{y_value:.0f}%\nn={total}", ha="center", fontsize=8)

    plt.xticks(cue_counts, [str(value) for value in cue_counts])
    plt.xlabel("Wrong-answer cue count in story")
    plt.ylabel("Followed bad clue (%)")
    plt.title("Experiment 1: MATH-500 shortcut rate")
    plt.ylim(0, 110)
    plt.legend()
    plt.tight_layout()
    plt.savefig(path, dpi=160)
    plt.close()


if __name__ == "__main__":
    main()
