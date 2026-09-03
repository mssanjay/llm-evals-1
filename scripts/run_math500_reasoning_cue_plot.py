"""Plot Math500 shortcut counts by story cue count and reasoning mode."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cue_eval.experiment import run_experiment


def parse_args() -> argparse.Namespace:
    """Collect options for the Math500-only reasoning plot."""
    parser = argparse.ArgumentParser(description="Plot Math500 shortcut counts by cue count.")
    parser.add_argument(
        "--provider",
        choices=["dry-run", "mock", "ollama", "openrouter", "aws", "azure-foundry", "azure-openai", "azure-ai"],
        default="dry-run",
    )
    parser.add_argument("--model", default="qwen3-32b")
    parser.add_argument("--data", default="data/math500_prepared_100.jsonl")
    parser.add_argument("--story-pool", default="data/story_pool.jsonl")
    parser.add_argument("--output-dir", default="outputs/math500_reasoning_cue_plot")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--cue-counts", default="1,2,3,4,5,6,7,8,9,10")
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--max-tokens", type=int, default=256)
    return parser.parse_args()


def main() -> None:
    """Run Math500 for reasoning off/on and write the requested plot."""
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    cue_counts = [int(value.strip()) for value in args.cue_counts.split(",") if value.strip()]

    all_rows: list[dict[str, Any]] = []
    all_summary: list[dict[str, Any]] = []
    for reasoning in ["off", "on"]:
        rows, summary = run_experiment(
            data_path=args.data,
            output_dir=output_dir / f"reasoning_{reasoning}",
            provider=args.provider,
            model=args.model,
            cue_counts=cue_counts,
            limit=args.limit,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            story_pool_path=args.story_pool,
            reasoning=reasoning,
        )
        for row in rows:
            row["reasoning"] = reasoning
        for row in summary:
            row["reasoning"] = reasoning
        all_rows.extend(rows)
        all_summary.extend(summary)
        print(f"Ran {len(rows)} Math500 prompt variants with reasoning={reasoning}.")

    _write_csv(output_dir / "math500_reasoning_results.csv", all_rows)
    _write_csv(output_dir / "math500_reasoning_summary.csv", all_summary)
    _write_plot(output_dir / "math500_shortcut_count_by_reasoning.png", all_summary)
    print(f"Wrote Math500 reasoning plot outputs to: {output_dir.resolve()}")


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    """Write result rows to CSV."""
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _write_plot(path: Path, summary: list[dict[str, Any]]) -> None:
    """Create the requested reasoning off/on Math500 count plot."""
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("Install matplotlib to create the Math500 reasoning plot.")
        return

    fig, axes = plt.subplots(1, 2, figsize=(10, 4.2), sharey=True)
    colors = {"off": "#1f77b4", "on": "#d62728"}
    for ax, reasoning in zip(axes, ["off", "on"]):
        points = [row for row in summary if row["reasoning"] == reasoning]
        x_values = [int(row["cue_count"]) for row in points]
        y_values = [int(row["shortcut_count"]) for row in points]
        ax.plot(x_values, y_values, marker="o", color=colors[reasoning], label=f"reasoning = {reasoning}")
        for x_value, y_value in zip(x_values, y_values):
            ax.text(x_value, y_value + 1, str(y_value), fontsize=8, ha="center", color=colors[reasoning])
        ax.set_title(f"reasoning = {reasoning}")
        ax.set_xlabel("no. of times cue appears in story")
        ax.set_xticks(x_values)
        ax.grid(True, alpha=0.25)

    max_total = max((int(row["total"]) for row in summary), default=100)
    axes[0].set_ylabel("no. of times model took shortcut")
    fig.suptitle("Math500 shortcut count by wrong-answer cue count", fontsize=11)
    plt.ylim(0, max_total + 10)
    plt.tight_layout()
    plt.savefig(path, dpi=160)
    plt.close()


if __name__ == "__main__":
    main()
