"""Command-line entry point for the simple cue-following experiment."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cue_eval.experiment import run_experiment


def parse_args() -> argparse.Namespace:
    """Collect the small set of knobs needed for the demo."""
    parser = argparse.ArgumentParser(description="Run the cue-following math experiment.")
    parser.add_argument(
        "--provider",
        choices=["dry-run", "mock", "ollama", "openrouter", "aws", "azure-foundry", "azure-openai", "azure-ai"],
        default="dry-run",
    )
    parser.add_argument("--model", default="qwen3:14b", help="Ollama model name or Azure deployment/model name.")
    parser.add_argument("--data", default="data/simple_math_examples.jsonl")
    parser.add_argument("--output-dir", default="outputs")
    parser.add_argument("--cue-counts", default="0,1,2,3,4,5,6,7,8,9,10", help="Comma-separated cue counts.")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--max-tokens", type=int, default=256)
    parser.add_argument("--story-pool", default="", help="Optional JSONL story pool for cue injection.")
    parser.add_argument("--reasoning", choices=["off", "on"], default="off")
    return parser.parse_args()


def main() -> None:
    """Run the experiment and print the summary table."""
    args = parse_args()
    cue_counts = [int(value.strip()) for value in args.cue_counts.split(",") if value.strip()]
    _, summary = run_experiment(
        data_path=Path(args.data),
        output_dir=Path(args.output_dir),
        provider=args.provider,
        model=args.model,
        cue_counts=cue_counts,
        limit=args.limit,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        story_pool_path=args.story_pool or None,
        reasoning=args.reasoning,
    )
    print("cue_count,total,valid,shortcut_rate,accuracy,parse_failures")
    for row in summary:
        print(
            f"{row['cue_count']},{row['total']},{row['valid']},"
            f"{row['shortcut_rate']:.2f},{row['accuracy']:.2f},{row['parse_failures']}"
        )
    print(f"\nWrote results to: {Path(args.output_dir).resolve()}")


if __name__ == "__main__":
    main()
