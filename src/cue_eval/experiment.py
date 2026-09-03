"""Run the cue-following experiment end to end."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from cue_eval.data import load_examples
from cue_eval.prompts import build_messages
from cue_eval.providers import call_model
from cue_eval.scoring import extract_final_number, label_answer, summarize
from cue_eval.story_pool import choose_story_template, load_story_pool


def run_experiment(
    data_path: str | Path,
    output_dir: str | Path,
    provider: str,
    model: str,
    cue_counts: list[int],
    limit: int,
    temperature: float,
    max_tokens: int = 256,
    story_pool_path: str | Path | None = None,
    reasoning: str = "off",
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Run all examples for each cue count and save result artifacts."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    examples = load_examples(data_path)[:limit]
    story_pool = load_story_pool(story_pool_path)
    rows: list[dict[str, Any]] = []
    for example_index, example in enumerate(examples):
        for cue_count in cue_counts:
            story_template = choose_story_template(story_pool, cue_count, example_index)
            messages = build_messages(example, cue_count, story_template, reasoning=reasoning)
            response = _demo_response(example, cue_count) if provider in {"dry-run", "mock"} else call_model(
                provider,
                messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            parsed_answer = extract_final_number(response)
            label = label_answer(parsed_answer, example["correct_answer"], example["shortcut_answer"])
            rows.append(
                {
                    "id": example["id"],
                    "reasoning": reasoning,
                    "cue_count": cue_count,
                    "correct_answer": example["correct_answer"],
                    "shortcut_answer": example["shortcut_answer"],
                    "parsed_answer": "" if parsed_answer is None else parsed_answer,
                    "label": label,
                    "response": response,
                    "prompt": _messages_to_text(messages),
                    "story_template": story_template or "",
                }
            )

    summary = summarize(rows)
    _write_csv(output_path / "results.csv", rows)
    _write_csv(output_path / "summary.csv", summary)
    _write_chart(output_path / "shortcut_rate.png", summary)
    return rows, summary


def _demo_response(example: dict[str, Any], cue_count: int) -> str:
    """Dry-run response that proves scoring and plotting work without a model."""
    if cue_count > 0:
        return f"Dry run: followed the bad clue. Final answer: {example['shortcut_answer']}"
    return f"Dry run: solved from the ground truth. Final answer: {example['correct_answer']}"


def _messages_to_text(messages: list[dict[str, str]]) -> str:
    """Flatten chat messages so a student can inspect the prompt in a CSV."""
    return "\n\n".join(f"{message['role'].upper()}: {message['content']}" for message in messages)


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    """Write dictionaries to CSV for simple inspection in Excel or notebooks."""
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _write_chart(path: Path, summary: list[dict[str, Any]]) -> None:
    """Create the one showcase chart when matplotlib is installed."""
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        return

    x_values = [str(row["cue_count"]) for row in summary]
    y_values = [row["shortcut_rate"] * 100 for row in summary]
    plt.figure(figsize=(7, 4))
    plt.bar(x_values, y_values, color="#2f7d6d")
    plt.xlabel("Wrong-answer cue count in story")
    plt.ylabel("Followed bad clue (%)")
    plt.title("Does the model copy the misleading clue?")
    plt.ylim(0, 110)
    for index, value in enumerate(y_values):
        plt.text(index, value + 2, f"{value:.0f}%", ha="center")
    plt.tight_layout()
    plt.savefig(path, dpi=160)
    plt.close()
