"""Write experiment artifacts, progress logs, and diagnostic plots."""

from __future__ import annotations

import csv
import json
import re
import time
from pathlib import Path
from typing import Any

from cue_eval.token_usage_tracker import TokenPricing, summarize_usage


DEFAULT_TEACHING_TURNS = 3
SIMPLIFIED_RESULTS_FILENAME = "experiment_results_simplified.csv"
STORY_LENGTH_CAPTION = (
    "Story templates are constrained to 60\u2013100 words before cue substitution."
)
LEXICAL_TOKEN_PATTERN = re.compile(r"\w+|[^\w\s]", re.UNICODE)
PROBE_RESPONSE_CATEGORIES = (
    ("correct", "correct_count", "Correct answer", "#2ca02c"),
    ("followed_bad_clue", "shortcut_count", "Shortcut cue taken", "#d62728"),
    ("other_wrong_answer", "other_wrong_answer_count", "Other wrong answer", "#ff7f0e"),
    ("parse_fail", "no_response_count", "Invalid / truncated", "#7f7f7f"),
)


def summarize_usage_by_subexperiment(
    rows: list[dict[str, Any]],
    pricing: TokenPricing | None,
) -> list[dict[str, Any]]:
    """Estimate cost for each condition, reasoning, and cue-count cell."""
    keys = sorted(
        {
            (
                str(row["provider"]),
                str(row["model"]),
                str(row["dataset"]),
                str(row["condition"]),
                str(row["reasoning"]),
                int(row["cue_count"]),
            )
            for row in rows
        }
    )
    summaries: list[dict[str, Any]] = []
    for provider, model, dataset, condition, reasoning, cue_count in keys:
        group = [
            row
            for row in rows
            if str(row["provider"]) == provider
            and str(row["model"]) == model
            and str(row["dataset"]) == dataset
            and str(row["condition"]) == condition
            and str(row["reasoning"]) == reasoning
            and int(row["cue_count"]) == cue_count
        ]
        summary = summarize_usage(
            group,
            "probe_prompt_tokens",
            "probe_completion_tokens",
            provider,
            model,
            pricing,
        )
        summaries.append(
            {
                "provider": provider,
                "model": model,
                "dataset": dataset,
                "condition": condition,
                "reasoning": reasoning,
                "cue_count": cue_count,
                "episodes": len(group),
                "plus_one_episodes": sum(
                    row["shortcut_cue_type"] == "plus_one" for row in group
                ),
                "times_ten_episodes": sum(
                    row["shortcut_cue_type"] == "times_ten" for row in group
                ),
                "random_episodes": sum(
                    row["shortcut_cue_type"] == "random" for row in group
                ),
                **{
                    key: value
                    for key, value in summary.items()
                    if key not in {"provider", "model"}
                },
            }
        )
    return summaries


def summarize_experiment(
    rows: list[dict[str, Any]],
    *,
    group_by_model: bool = False,
) -> list[dict[str, Any]]:
    """Aggregate probe responses for summary artifacts."""
    summary: list[dict[str, Any]] = []
    datasets = sorted({row["dataset"] for row in rows})
    models: list[str | None] = (
        sorted({str(row["model"]) for row in rows}) if group_by_model else [None]
    )
    conditions = sorted({row["condition"] for row in rows})
    reasoning_modes = sorted({row["reasoning"] for row in rows})
    cue_counts = sorted({int(row["cue_count"]) for row in rows})
    for dataset in datasets:
        for model in models:
            for condition in conditions:
                for reasoning in reasoning_modes:
                    for cue_count in cue_counts:
                        group = [
                            row
                            for row in rows
                            if row["dataset"] == dataset
                            and (model is None or str(row["model"]) == model)
                            and row["condition"] == condition
                            and row["reasoning"] == reasoning
                            and int(row["cue_count"]) == cue_count
                        ]
                        if not group:
                            continue
                        category_counts = {
                            label: sum(row["probe_label"] == label for row in group)
                            for label, _, _, _ in PROBE_RESPONSE_CATEGORIES
                        }
                        unknown_labels = {
                            row["probe_label"]
                            for row in group
                            if row["probe_label"] not in category_counts
                        }
                        if unknown_labels:
                            names = ", ".join(sorted(unknown_labels))
                            raise ValueError(f"Unknown probe response labels: {names}")
                        valid = [
                            row for row in group if row["probe_label"] != "parse_fail"
                        ]
                        held_counts = [int(row["rule_held_count"]) for row in valid]
                        summary_row = {
                            "dataset": dataset,
                            "condition": condition,
                            "reasoning": reasoning,
                            "cue_count": cue_count,
                            "n": len(valid),
                            "total_n": len(group),
                            "correct_count": category_counts["correct"],
                            "shortcut_count": category_counts["followed_bad_clue"],
                            "other_wrong_answer_count": category_counts[
                                "other_wrong_answer"
                            ],
                            "no_response_count": category_counts["parse_fail"],
                            "shortcut_rate": (
                                category_counts["followed_bad_clue"] / len(valid)
                                if valid
                                else 0.0
                            ),
                            "avg_rule_held_count": (
                                sum(held_counts) / len(held_counts) if held_counts else 0.0
                            ),
                        }
                        if model is not None:
                            summary_row = {"model": model, **summary_row}
                        summary.append(summary_row)
    return summary


def write_experiment_outputs(
    output_dir: str | Path,
    rows: list[dict[str, Any]],
    teaching_turns: int = DEFAULT_TEACHING_TURNS,
) -> list[dict[str, Any]]:
    """Write simplified results, summary data, and diagnostic plots."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    summary = summarize_experiment(rows)
    write_csv(
        output_path / SIMPLIFIED_RESULTS_FILENAME,
        simplify_experiment_rows(rows, teaching_turns),
    )
    write_csv(output_path / "experiment_summary.csv", summary)
    _write_cue_count_plot(
        output_path / "experiment_shortcut_count_by_cue_count.png",
        summary,
        use_rate=False,
    )
    _write_cue_count_plot(
        output_path / "experiment_shortcut_rate.png", summary, use_rate=True
    )
    _write_response_category_plot(
        output_path / "experiment_response_categories_stacked.png", summary
    )
    _write_story_token_count_plot(
        output_path / "experiment_story_token_count_by_cue_count.png",
        rows,
        teaching_turns,
    )
    return summary


def simplify_experiment_rows(
    rows: list[dict[str, Any]],
    teaching_turns: int = DEFAULT_TEACHING_TURNS,
) -> list[dict[str, Any]]:
    """Keep the manual-analysis fields and combine the probe conversation."""
    return [
        {
            "model": row["model"],
            "condition": row["condition"],
            "reasoning": row["reasoning"],
            "cue_count": row["cue_count"],
            "cue_strategy": row["cue_strategy"],
            "probe_id": row["probe_id"],
            "actual_probe": _actual_probe(row, teaching_turns),
            "probe_response": row["probe_response"],
            "probe_answer": row["probe_answer"],
            "probe_correct_answer": row["probe_correct_answer"],
            "probe_shortcut_answer": row["probe_shortcut_answer"],
            "probe_label": row["probe_label"],
            "probe_was_truncated": row["probe_was_truncated"],
        }
        for row in rows
    ]


def _actual_probe(row: dict[str, Any], teaching_turns: int) -> str:
    """Render the teaching history and final probe as one readable transcript."""
    sections: list[str] = []
    for index in range(1, teaching_turns + 1):
        sections.extend(
            [
                f"TEACHING TURN {index} - USER:\n{row[f'teaching_prompt_{index}']}",
                (
                    f"TEACHING TURN {index} - ASSISTANT (SCRIPTED):\n"
                    f"{row[f'teaching_response_{index}']}"
                ),
            ]
        )
    sections.append(f"FINAL PROBE - USER:\n{row['probe_prompt']}")
    return "\n\n".join(sections)


def write_combined_experiment_outputs(
    output_dir: str | Path,
    rows: list[dict[str, Any]],
    teaching_turns: int = DEFAULT_TEACHING_TURNS,
) -> list[dict[str, Any]]:
    """Write one model-comparison summary and graph set."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    summary = summarize_experiment(rows, group_by_model=True)
    write_csv(output_path / "combined_experiment_summary.csv", summary)
    _write_cue_count_plot(
        output_path / "combined_shortcut_count_by_cue_count.png",
        summary,
        use_rate=False,
    )
    _write_cue_count_plot(
        output_path / "combined_shortcut_rate.png", summary, use_rate=True
    )
    _write_response_category_plot(
        output_path / "combined_response_categories_stacked.png", summary
    )
    _write_story_token_count_plot(
        output_path / "combined_story_token_count_by_cue_count.png",
        rows,
        teaching_turns,
    )
    return summary


def write_grouped_episode_prompts(
    output_dir: str | Path,
    rows: list[dict[str, Any]],
    teaching_turns: int = DEFAULT_TEACHING_TURNS,
) -> list[dict[str, Any]]:
    """Write one ordered, complete conversation object per episode."""
    output_path = Path(output_dir)
    raw_path = output_path / "model_prompts.jsonl"
    grouped_path = output_path / "model_prompts_by_episode.jsonl"
    if not raw_path.exists():
        raise FileNotFoundError(f"Prompt log not found: {raw_path}")

    events_by_episode: dict[
        tuple[str, str, int, int], dict[tuple[str, int], dict[str, Any]]
    ] = {}
    with raw_path.open(encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(
                    f"Invalid JSON in {raw_path} at line {line_number}"
                ) from error
            episode_key = _prompt_episode_key(event)
            turn_key = (str(event["turn_type"]), int(event["turn_index"]))
            events_by_episode.setdefault(episode_key, {})[turn_key] = event

    grouped_rows: list[dict[str, Any]] = []
    sorted_rows = sorted(
        rows,
        key=lambda row: (
            str(row["condition"]),
            str(row["reasoning"]),
            int(row["cue_count"]),
            int(row["episode_index"]),
        ),
    )
    for row in sorted_rows:
        episode_key = _prompt_episode_key(row)
        events = events_by_episode.get(episode_key, {})
        expected_turns = [
            ("teaching", index) for index in range(1, teaching_turns + 1)
        ]
        expected_turns.append(("probe", 0))
        missing = [turn for turn in expected_turns if turn not in events]
        if missing:
            raise ValueError(f"Missing prompt events for episode {episode_key}: {missing}")

        teaching_rows = [
            _grouped_teaching_turn(row, events[("teaching", index)], index)
            for index in range(1, teaching_turns + 1)
        ]
        probe_event = events[("probe", 0)]
        probe_turn = _grouped_probe_turn(row, probe_event, teaching_turns)
        grouped_rows.append(
            {
                "dataset": row["dataset"],
                "provider": probe_event["provider"],
                "model": probe_event["model"],
                "condition": row["condition"],
                "reasoning": row["reasoning"],
                "cue_count": int(row["cue_count"]),
                "cue_strategy": row["cue_strategy"],
                "episode_index": int(row["episode_index"]),
                "episode_number": int(row["episode_index"]) + 1,
                "total_episodes": int(probe_event["total_episodes"]),
                "probe_id": row["probe_id"],
                "turns": teaching_rows + [probe_turn],
                "probe_request_messages": probe_event["messages"],
            }
        )

    write_jsonl(grouped_path, grouped_rows)
    return grouped_rows


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    """Write dictionaries to a UTF-8 CSV file."""
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def csv_value(value: int | None) -> int | str:
    """Represent missing provider metadata as an empty CSV cell."""
    return "" if value is None else value


def append_csv(path: Path, row: dict[str, Any], write_lock: Any | None = None) -> None:
    """Append one row so long runs leave inspectable partial output."""
    if write_lock:
        with write_lock:
            _append_csv_unlocked(path, row)
        return
    _append_csv_unlocked(path, row)


def _append_csv_unlocked(path: Path, row: dict[str, Any]) -> None:
    """Append one CSV row after any caller-side locking."""
    path.parent.mkdir(parents=True, exist_ok=True)
    needs_header = not path.exists() or path.stat().st_size == 0
    mode = "w" if needs_header else "a"
    encoding = "utf-8-sig" if needs_header else "utf-8"
    with path.open(mode, newline="", encoding=encoding) as file:
        writer = csv.DictWriter(file, fieldnames=list(row.keys()))
        if needs_header:
            writer.writeheader()
        writer.writerow(row)


def log_prompt_event(
    path: Path,
    provider: str,
    model: str,
    condition: str,
    reasoning: str,
    cue_count: int,
    cue_strategy: str,
    episode_index: int,
    total_episodes: int,
    turn_type: str,
    turn_index: int,
    example_id: str,
    story_id: str,
    messages: list[dict[str, str]],
    sent_to_model: bool,
    response_source: str,
    write_lock: Any | None = None,
) -> None:
    """Append one scripted or provider-backed conversation event."""
    event = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "provider": provider,
        "model": model,
        "condition": condition,
        "reasoning": reasoning,
        "cue_count": cue_count,
        "cue_strategy": cue_strategy,
        "episode_index": episode_index,
        "episode_number": episode_index + 1,
        "total_episodes": total_episodes,
        "turn_type": turn_type,
        "turn_index": turn_index,
        "example_id": example_id,
        "story_id": story_id,
        "sent_to_model": sent_to_model,
        "response_source": response_source,
        "messages": messages,
    }
    append_jsonl(path, event, write_lock)


def append_jsonl(
    path: Path, row: dict[str, Any], write_lock: Any | None = None
) -> None:
    """Append one JSON object per line for prompt inspection."""
    if write_lock:
        with write_lock:
            _append_jsonl_unlocked(path, row)
        return
    _append_jsonl_unlocked(path, row)


def _append_jsonl_unlocked(path: Path, row: dict[str, Any]) -> None:
    """Append one JSONL row after any caller-side locking."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(row, ensure_ascii=True) + "\n")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    """Write JSONL atomically so readers never see a partial file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    with temporary_path.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=True) + "\n")
    temporary_path.replace(path)


def write_json(path: Path, value: dict[str, Any]) -> None:
    """Write one JSON object atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(path)


def log(path: Path, message: str, write_lock: Any | None = None) -> None:
    """Print and persist one progress event."""
    if write_lock:
        with write_lock:
            _log_unlocked(path, message)
        return
    _log_unlocked(path, message)


def _log_unlocked(path: Path, message: str) -> None:
    """Write one progress line after any caller-side locking."""
    path.parent.mkdir(parents=True, exist_ok=True)
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} | {message}"
    print(line, flush=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(line + "\n")


def _prompt_episode_key(row: dict[str, Any]) -> tuple[str, str, int, int]:
    """Identify one prompt-log episode within a run."""
    return (
        str(row["condition"]),
        str(row["reasoning"]),
        int(row["cue_count"]),
        int(row["episode_index"]),
    )


def _grouped_teaching_turn(
    row: dict[str, Any],
    event: dict[str, Any],
    index: int,
) -> dict[str, Any]:
    """Build one readable scripted teaching turn."""
    return {
        "turn": index,
        "turn_type": "teaching",
        "turn_index": index,
        "example_id": event["example_id"],
        "sent_to_model": False,
        "response_source": "scripted",
        "user_message": row[f"teaching_prompt_{index}"],
        "assistant_response": row[f"teaching_response_{index}"],
        "parsed_answer": _optional_number(row[f"teaching_answer_{index}"]),
        "shortcut_answer": _optional_number(row[f"teaching_shortcut_answer_{index}"]),
        "correct_answer": _optional_number(row[f"teaching_correct_answer_{index}"]),
        "story_answer": _optional_number(row[f"teaching_story_answer_{index}"]),
        "story_id": row[f"teaching_story_id_{index}"],
        "label": row[f"teaching_label_{index}"],
    }


def _grouped_probe_turn(
    row: dict[str, Any],
    event: dict[str, Any],
    teaching_turns: int,
) -> dict[str, Any]:
    """Build the model-generated probe turn and its scoring metadata."""
    return {
        "turn": teaching_turns + 1,
        "turn_type": "probe",
        "turn_index": 0,
        "example_id": event["example_id"],
        "sent_to_model": bool(event["sent_to_model"]),
        "response_source": event["response_source"],
        "user_message": row["probe_prompt"],
        "assistant_response": row["probe_response"],
        "assistant_reasoning": row.get("probe_reasoning", ""),
        "reasoning_chars": int(row.get("probe_reasoning_chars") or 0),
        "reasoning_tokens": _optional_int_value(row.get("probe_reasoning_tokens")),
        "parsed_answer": _optional_number(row["probe_answer"]),
        "correct_answer": _optional_number(row["probe_correct_answer"]),
        "shortcut_answer": _optional_number(row["probe_shortcut_answer"]),
        "label": row["probe_label"],
        "took_shortcut": _as_bool(row["probe_took_shortcut"]),
        "is_correct": _as_bool(row["probe_is_correct"]),
        "finish_reason": row["probe_finish_reason"],
        "was_truncated": _as_bool(row["probe_was_truncated"]),
        "story_id": row["probe_story_id"],
    }


def _optional_number(value: Any) -> float | None:
    """Normalize CSV and in-memory answer values for JSON output."""
    if value is None or value == "":
        return None
    return float(value)


def _optional_int_value(value: Any) -> int | None:
    """Normalize optional integer metadata for JSON output."""
    if value is None or value == "":
        return None
    return int(value)


def _as_bool(value: Any) -> bool:
    """Normalize CSV and in-memory boolean values for JSON output."""
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() == "true"


def _write_cue_count_plot(
    path: Path, summary: list[dict[str, Any]], use_rate: bool
) -> None:
    """Plot shortcut results by wrong-answer cue count."""
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("Install matplotlib to create the live-history chart.")
        return

    dataset = "math500"
    model_names = sorted(
        {str(row["model"]) for row in summary if row.get("model") is not None}
    )
    series_names = model_names or ["MATH-500"]
    colors = ["#1f77b4", "#d62728", "#2ca02c", "#9467bd"]
    markers = ["o", "s", "^", "D"]
    conditions = sorted({str(row["condition"]) for row in summary})
    fig, axes = plt.subplots(
        len(conditions),
        2,
        figsize=(10, 4.2 * len(conditions)),
        sharey=True,
        squeeze=False,
    )
    y_key = "shortcut_rate" if use_rate else "shortcut_count"
    y_label = (
        "shortcut rate at probe (%)"
        if use_rate
        else "no. of times model took the shortcut"
    )
    title_metric = "rate" if use_rate else "count"

    for condition_index, condition in enumerate(conditions):
        for reasoning_index, reasoning in enumerate(["off", "on"]):
            ax = axes[condition_index][reasoning_index]
            all_x_values: set[int] = set()
            for series_index, series_name in enumerate(series_names):
                points = [
                    row
                    for row in summary
                    if row["dataset"] == dataset
                    and row["condition"] == condition
                    and row["reasoning"] == reasoning
                    and (
                        not model_names
                        or str(row.get("model")) == series_name
                    )
                ]
                x_values = [int(row["cue_count"]) for row in points]
                y_values = [
                    row[y_key] * 100 if use_rate else row[y_key] for row in points
                ]
                all_x_values.update(x_values)
                color = colors[series_index % len(colors)]
                ax.plot(
                    x_values,
                    y_values,
                    marker=markers[series_index % len(markers)],
                    label=series_name,
                    color=color,
                )
                for x_value, y_value, row in zip(x_values, y_values, points):
                    label_offset = (3 if use_rate else 1) * (series_index + 1)
                    ax.text(
                        x_value,
                        y_value + label_offset,
                        sample_size_label(row),
                        fontsize=7,
                        ha="center",
                        color=color,
                    )
            ax.set_title(f"{condition}; reasoning = {reasoning}")
            ax.set_xlabel("no. of times cue appears in each story")
            ax.set_xticks(sorted(all_x_values))
            ax.grid(True, alpha=0.25)

    max_y = max(
        (row[y_key] * 100 if use_rate else row[y_key] for row in summary),
        default=0,
    )
    for row_axes in axes:
        row_axes[0].set_ylabel(y_label)
    axes[0][0].legend(title="model" if model_names else "dataset", fontsize=8)
    fig.suptitle(
        f"Math500 live-history shortcut {title_metric} by wrong-answer cue count\n"
        "(5 story templates per cue count; n labeled at every point)",
        fontsize=9,
    )
    fig.text(0.5, 0.015, STORY_LENGTH_CAPTION, ha="center", fontsize=8)
    for row_axes in axes:
        for ax in row_axes:
            ax.set_ylim(
                -5 if use_rate else 0,
                max(110 if use_rate else 10, max_y + (10 if use_rate else 5)),
            )
    plt.tight_layout(rect=(0, 0.06, 1, 1))
    plt.savefig(path, dpi=160)
    plt.close()


def sample_size_label(row: dict[str, Any]) -> str:
    """Show total episodes and disclose exclusions from rate calculations."""
    total = int(row["total_n"])
    valid = int(row["n"])
    return f"N={total}" if valid == total else f"N={total}\nvalid={valid}"


def _write_response_category_plot(
    path: Path, summary: list[dict[str, Any]]
) -> None:
    """Plot all final probe response categories as stacked counts."""
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("Install matplotlib to create the response-category chart.")
        return

    dataset = "math500"
    conditions = sorted({str(row["condition"]) for row in summary})
    model_names = sorted(
        {str(row["model"]) for row in summary if row.get("model") is not None}
    )
    panels = [
        (condition, model)
        for condition in conditions
        for model in (model_names or [None])
    ]
    fig, axes = plt.subplots(
        len(panels),
        2,
        figsize=(12, 5.2 * len(panels)),
        sharey=True,
        squeeze=False,
    )
    max_total = max((int(row["total_n"]) for row in summary), default=0)

    for panel_index, (condition, model) in enumerate(panels):
        for reasoning_index, reasoning in enumerate(["off", "on"]):
            ax = axes[panel_index][reasoning_index]
            points = [
                row
                for row in summary
                if row["dataset"] == dataset
                and row["condition"] == condition
                and row["reasoning"] == reasoning
                and (model is None or str(row.get("model")) == model)
            ]
            x_values = [int(row["cue_count"]) for row in points]
            bottoms = [0] * len(points)

            for _, count_key, display_name, color in PROBE_RESPONSE_CATEGORIES:
                values = [int(row[count_key]) for row in points]
                bars = ax.bar(
                    x_values,
                    values,
                    bottom=bottoms,
                    width=0.72,
                    label=display_name,
                    color=color,
                )
                for bar, value, bottom in zip(bars, values, bottoms):
                    if value:
                        ax.text(
                            bar.get_x() + bar.get_width() / 2,
                            bottom + value / 2,
                            str(value),
                            ha="center",
                            va="center",
                            fontsize=7,
                            color=(
                                "white"
                                if color in {"#2ca02c", "#d62728", "#7f7f7f"}
                                else "black"
                            ),
                        )
                bottoms = [
                    bottom + value for bottom, value in zip(bottoms, values)
                ]

            for x_value, total in zip(x_values, bottoms):
                ax.text(
                    x_value,
                    total + 0.6,
                    f"n={total}",
                    ha="center",
                    va="bottom",
                    fontsize=7,
                )
            model_title = f"; model = {model}" if model is not None else ""
            ax.set_title(f"{condition}{model_title}; reasoning = {reasoning}")
            ax.set_xlabel("no. of times cue appears in each story")
            ax.set_xticks(x_values)
            ax.set_ylim(0, max_total + 4)
            ax.set_axisbelow(True)
            ax.grid(axis="y", alpha=0.25)

    for row_axes in axes:
        row_axes[0].set_ylabel("number of final probe responses")
    handles, labels = axes[0][0].get_legend_handles_labels()
    fig.legend(
        handles,
        labels,
        loc="upper center",
        ncol=4,
        bbox_to_anchor=(0.5, 0.93),
        fontsize=8,
    )
    fig.suptitle("Math500 final probe responses by wrong-answer cue count", fontsize=11)
    fig.text(0.5, 0.015, STORY_LENGTH_CAPTION, ha="center", fontsize=8)
    plt.tight_layout(rect=(0, 0.06, 1, 0.86))
    plt.savefig(path, dpi=160)
    plt.close()


def _write_story_token_count_plot(
    path: Path,
    rows: list[dict[str, Any]],
    teaching_turns: int,
) -> None:
    """Plot rendered story token counts by cue count."""
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("Install matplotlib to create the story-length diagnostic chart.")
        return

    grouped_counts = story_token_counts_by_cue_count(rows, teaching_turns)
    if not grouped_counts:
        return

    cue_counts = sorted(grouped_counts)
    means = [sum(grouped_counts[count]) / len(grouped_counts[count]) for count in cue_counts]
    minimums = [min(grouped_counts[count]) for count in cue_counts]
    maximums = [max(grouped_counts[count]) for count in cue_counts]

    fig, ax = plt.subplots(figsize=(8.5, 5.2))
    for cue_count in cue_counts:
        values = grouped_counts[cue_count]
        ax.scatter(
            [cue_count] * len(values),
            values,
            color="#7f7f7f",
            alpha=0.12,
            s=12,
            edgecolors="none",
        )
    ax.fill_between(
        cue_counts,
        minimums,
        maximums,
        color="#1f77b4",
        alpha=0.14,
        label="observed range",
    )
    ax.plot(cue_counts, means, marker="o", color="#1f77b4", linewidth=2, label="mean")
    ax.set_title("Rendered story token count by wrong-answer cue count")
    ax.set_xlabel("no. of times cue appears in each story")
    ax.set_ylabel("story token count (model-independent lexical tokens)")
    ax.set_xticks(cue_counts)
    ax.grid(True, alpha=0.25)
    ax.legend()
    fig.text(
        0.5,
        0.015,
        STORY_LENGTH_CAPTION + " Gray points are all rendered stories sent to the model.",
        ha="center",
        fontsize=8,
    )
    plt.tight_layout(rect=(0, 0.07, 1, 1))
    plt.savefig(path, dpi=160)
    plt.close()


def story_token_counts_by_cue_count(
    rows: list[dict[str, Any]],
    teaching_turns: int = DEFAULT_TEACHING_TURNS,
) -> dict[int, list[int]]:
    """Collect lexical token counts from each rendered story."""
    grouped_counts: dict[int, list[int]] = {}
    prompt_fields = [
        f"teaching_prompt_{index}" for index in range(1, teaching_turns + 1)
    ] + ["probe_prompt"]
    for row in rows:
        cue_count = int(row["cue_count"])
        for field in prompt_fields:
            prompt = row.get(field)
            if not isinstance(prompt, str) or not prompt.strip():
                continue
            story = prompt.split("\n\n", 1)[0]
            grouped_counts.setdefault(cue_count, []).append(
                len(LEXICAL_TOKEN_PATTERN.findall(story))
            )
    return grouped_counts
