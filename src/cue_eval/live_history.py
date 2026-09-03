"""Live-history experiment using teaching turns before a probe."""

from __future__ import annotations

import csv
import json
import time
from pathlib import Path
from typing import Any

from cue_eval.data import load_examples
from cue_eval.providers import call_model
from cue_eval.scoring import extract_final_number, label_answer
from cue_eval.story_pool import choose_story_template, load_story_pool, render_story


TEACHING_TURNS = 4


def run_live_history_experiment(
    data_path: str | Path,
    dataset_name: str,
    output_dir: str | Path,
    provider: str,
    model: str,
    limit: int,
    temperature: float,
    max_tokens: int,
    reasoning_modes: list[str],
    story_pool_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Run live teaching conversations and save row-level probe results."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    examples = load_examples(data_path)[:limit]
    episodes = _make_episodes(examples)
    story_pool = load_story_pool(story_pool_path)

    progress_path = output_path / "progress.log"
    partial_csv_path = output_path / "live_history_results.partial.csv"
    prompt_log_path = output_path / "model_prompts.jsonl"
    if partial_csv_path.exists():
        partial_csv_path.unlink()
    if progress_path.exists():
        progress_path.unlink()
    if prompt_log_path.exists():
        prompt_log_path.unlink()
    _log(
        progress_path,
        (
            f"Starting live-history run provider={provider} model={model} "
            f"examples={len(examples)} episodes_per_reasoning={len(episodes)} "
            f"reasoning_modes={','.join(reasoning_modes)}"
        ),
    )

    rows: list[dict[str, Any]] = []
    for reasoning in reasoning_modes:
        _log(progress_path, f"Starting reasoning={reasoning}")
        for episode_index, episode in enumerate(episodes):
            row = _run_episode(
                episode=episode,
                episode_index=episode_index,
                total_episodes=len(episodes),
                dataset_name=dataset_name,
                provider=provider,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                reasoning=reasoning,
                story_pool=story_pool,
                progress_path=progress_path,
                prompt_log_path=prompt_log_path,
            )
            rows.append(row)
            _append_csv(partial_csv_path, row)
            _log(
                progress_path,
                (
                    f"Saved partial row reasoning={reasoning} "
                    f"episode={episode_index + 1}/{len(episodes)} "
                    f"probe_label={row['probe_label']}"
                ),
            )

    _write_csv(output_path / "live_history_results.csv", rows)
    _log(progress_path, f"Finished run. Wrote final CSV with {len(rows)} rows.")
    return rows


def summarize_live_history(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate probe shortcut rate by dataset, reasoning mode, and held count."""
    summary: list[dict[str, Any]] = []
    datasets = sorted({row["dataset"] for row in rows})
    reasoning_modes = sorted({row["reasoning"] for row in rows})
    for dataset in datasets:
        for reasoning in reasoning_modes:
            for held_count in range(TEACHING_TURNS + 1):
                group = [
                    row
                    for row in rows
                    if row["dataset"] == dataset
                    and row["reasoning"] == reasoning
                    and int(row["rule_held_count"]) == held_count
                ]
                valid = [row for row in group if row["probe_label"] != "parse_fail"]
                shortcut = [row for row in valid if row["probe_label"] == "followed_bad_clue"]
                summary.append(
                    {
                        "dataset": dataset,
                        "reasoning": reasoning,
                        "rule_held_count": held_count,
                        "n": len(valid),
                        "shortcut_count": len(shortcut),
                        "shortcut_rate": len(shortcut) / len(valid) if valid else 0.0,
                    }
                )
    return summary


def write_live_history_outputs(output_dir: str | Path, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Write summary CSV and the two-panel methodology plot."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    summary = summarize_live_history(rows)
    _write_csv(output_path / "live_history_summary.csv", summary)
    _write_methodology_plot(output_path / "live_history_shortcut_rate.png", summary)
    return summary


def _run_episode(
    episode: list[dict[str, Any]],
    episode_index: int,
    total_episodes: int,
    dataset_name: str,
    provider: str,
    model: str,
    temperature: float,
    max_tokens: int,
    reasoning: str,
    story_pool: dict[int, list[dict[str, Any]]],
    progress_path: Path,
    prompt_log_path: Path,
) -> dict[str, Any]:
    """Run four teaching turns, then one probe turn in the same message history."""
    episode_start = time.perf_counter()
    messages = [{"role": "system", "content": _system_prompt(reasoning)}]
    teaching_labels: list[str] = []
    teaching_answers: list[str] = []
    teaching_prompts: list[str] = []
    _log(
        progress_path,
        f"Episode {episode_index + 1}/{total_episodes} reasoning={reasoning} started",
    )

    for turn_index, example in enumerate(episode[:TEACHING_TURNS], start=1):
        story_template = choose_story_template(story_pool, 1, episode_index + turn_index)
        user_message = _teaching_prompt(example, turn_index, story_template)
        teaching_prompts.append(user_message)
        request_messages = messages + [{"role": "user", "content": user_message}]
        _log_prompt_event(
            prompt_log_path,
            provider=provider,
            model=model,
            reasoning=reasoning,
            episode_index=episode_index,
            total_episodes=total_episodes,
            turn_type="teaching",
            turn_index=turn_index,
            example_id=example["id"],
            messages=request_messages,
        )
        response = _model_or_dry_response(provider, example, episode_index, turn_index, is_probe=False)
        if response is None:
            call_start = time.perf_counter()
            _log(
                progress_path,
                (
                    f"Episode {episode_index + 1}/{total_episodes} reasoning={reasoning} "
                    f"teaching_turn={turn_index}/{TEACHING_TURNS} calling model "
                    f"example_id={example['id']}"
                ),
            )
            response = call_model(provider, request_messages, model, temperature, max_tokens)
            _log(
                progress_path,
                (
                    f"Episode {episode_index + 1}/{total_episodes} reasoning={reasoning} "
                    f"teaching_turn={turn_index}/{TEACHING_TURNS} model returned "
                    f"seconds={time.perf_counter() - call_start:.1f} chars={len(response or '')}"
                ),
            )
        parsed = extract_final_number(response)
        label = label_answer(parsed, example["correct_answer"], example["shortcut_answer"])
        _log(
            progress_path,
            (
                f"Episode {episode_index + 1}/{total_episodes} reasoning={reasoning} "
                f"teaching_turn={turn_index}/{TEACHING_TURNS} label={label} parsed={parsed}"
            ),
        )
        teaching_labels.append(label)
        teaching_answers.append("" if parsed is None else str(parsed))
        messages.extend(
            [
                {"role": "user", "content": user_message},
                {"role": "assistant", "content": response},
            ]
        )

    probe = episode[TEACHING_TURNS]
    probe_story_template = choose_story_template(story_pool, 1, episode_index + TEACHING_TURNS + 1)
    probe_message = _probe_prompt(probe, probe_story_template)
    probe_request_messages = messages + [{"role": "user", "content": probe_message}]
    _log_prompt_event(
        prompt_log_path,
        provider=provider,
        model=model,
        reasoning=reasoning,
        episode_index=episode_index,
        total_episodes=total_episodes,
        turn_type="probe",
        turn_index=0,
        example_id=probe["id"],
        messages=probe_request_messages,
    )
    probe_response = _model_or_dry_response(provider, probe, episode_index, 0, is_probe=True)
    if probe_response is None:
        call_start = time.perf_counter()
        _log(
            progress_path,
            (
                f"Episode {episode_index + 1}/{total_episodes} reasoning={reasoning} "
                f"probe calling model example_id={probe['id']}"
            ),
        )
        probe_response = call_model(
            provider,
            probe_request_messages,
            model,
            temperature,
            max_tokens,
        )
        _log(
            progress_path,
            (
                f"Episode {episode_index + 1}/{total_episodes} reasoning={reasoning} "
                f"probe model returned seconds={time.perf_counter() - call_start:.1f} "
                f"chars={len(probe_response or '')}"
            ),
        )
    probe_answer = extract_final_number(probe_response)
    probe_label = label_answer(probe_answer, probe["correct_answer"], probe["shortcut_answer"])
    _log(
        progress_path,
        (
            f"Episode {episode_index + 1}/{total_episodes} reasoning={reasoning} finished "
            f"probe_label={probe_label} probe_answer={probe_answer} "
            f"rule_held_count={sum(label == 'followed_bad_clue' for label in teaching_labels)} "
            f"seconds={time.perf_counter() - episode_start:.1f}"
        ),
    )

    return {
        "dataset": dataset_name,
        "reasoning": reasoning,
        "episode_index": episode_index,
        "probe_id": probe["id"],
        "rule_held_count": sum(label == "followed_bad_clue" for label in teaching_labels),
        "probe_label": probe_label,
        "probe_took_shortcut": probe_label == "followed_bad_clue",
        "probe_is_correct": probe_label == "correct",
        "probe_answer": "" if probe_answer is None else probe_answer,
        "probe_correct_answer": probe["correct_answer"],
        "probe_shortcut_answer": probe["shortcut_answer"],
        "teaching_label_1": teaching_labels[0],
        "teaching_label_2": teaching_labels[1],
        "teaching_label_3": teaching_labels[2],
        "teaching_label_4": teaching_labels[3],
        "teaching_answer_1": teaching_answers[0],
        "teaching_answer_2": teaching_answers[1],
        "teaching_answer_3": teaching_answers[2],
        "teaching_answer_4": teaching_answers[3],
        "teaching_labels": "|".join(teaching_labels),
        "teaching_answers": "|".join(teaching_answers),
        "teaching_prompt_1": teaching_prompts[0],
        "teaching_prompt_2": teaching_prompts[1],
        "teaching_prompt_3": teaching_prompts[2],
        "teaching_prompt_4": teaching_prompts[3],
        "probe_prompt": probe_message,
        "probe_response": probe_response,
    }


def _make_episodes(examples: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Create rolling 4-teach-plus-1-probe episodes from prepared examples."""
    if len(examples) < TEACHING_TURNS + 1:
        return []
    episodes: list[list[dict[str, Any]]] = []
    for start in range(len(examples) - TEACHING_TURNS):
        episodes.append(examples[start : start + TEACHING_TURNS + 1])
    return episodes


def _system_prompt(reasoning: str) -> str:
    """Build a simple reasoning-on/off instruction for the model."""
    base = "You are solving math problems. Always end with 'Final answer: <number>'."
    if reasoning == "on":
        return base + " Think step by step before giving the final answer."
    return base + " Keep the response brief and do not show step-by-step reasoning."


def _teaching_prompt(example: dict[str, Any], turn_index: int, story_template: str | None = None) -> str:
    """Ask a teaching problem as one story turn with the planted clue."""
    story = _story_text(example, story_template)
    return (
        f"Teaching story turn {turn_index} of 4.\n"
        f"{story}\n\n"
        f"Practice problem: {example['problem']}"
    )


def _probe_prompt(example: dict[str, Any], story_template: str | None = None) -> str:
    """Ask the final probe after the multi-turn story history."""
    story = _story_text(example, story_template)
    return (
        "Final probe story.\n"
        f"{story}\n"
        "Use what you learned from the earlier turns if it seems helpful.\n\n"
        f"Probe problem: {example['problem']}"
    )


def _story_text(example: dict[str, Any], story_template: str | None) -> str:
    """Render a complex story, or fall back to a simple notebook story."""
    if story_template:
        return render_story(story_template, example["bad_clue"])
    return (
        "A student is practicing a shortcut rule before the final question. "
        f"The student's notebook says: {example['bad_clue'].rstrip('.')}"
    )


def _model_or_dry_response(
    provider: str,
    example: dict[str, Any],
    episode_index: int,
    turn_index: int,
    is_probe: bool,
) -> str | None:
    """Provide deterministic dry-run responses for graph testing."""
    if provider not in {"dry-run", "mock"}:
        return None
    target_held_count = episode_index % (TEACHING_TURNS + 1)
    if is_probe:
        answer = example["shortcut_answer"] if target_held_count >= 2 else example["correct_answer"]
    else:
        answer = example["shortcut_answer"] if turn_index <= target_held_count else example["correct_answer"]
    return f"Dry run response. Final answer: {answer}"


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    """Write dictionaries to CSV."""
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _append_csv(path: Path, row: dict[str, Any]) -> None:
    """Append one row so long model runs leave inspectable partial output."""
    path.parent.mkdir(parents=True, exist_ok=True)
    needs_header = not path.exists() or path.stat().st_size == 0
    with path.open("a", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(row.keys()))
        if needs_header:
            writer.writeheader()
        writer.writerow(row)


def _log_prompt_event(
    path: Path,
    provider: str,
    model: str,
    reasoning: str,
    episode_index: int,
    total_episodes: int,
    turn_type: str,
    turn_index: int,
    example_id: str,
    messages: list[dict[str, str]],
) -> None:
    """Append the exact chat messages for one model request."""
    event = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "provider": provider,
        "model": model,
        "reasoning": reasoning,
        "episode_index": episode_index,
        "episode_number": episode_index + 1,
        "total_episodes": total_episodes,
        "turn_type": turn_type,
        "turn_index": turn_index,
        "example_id": example_id,
        "sent_to_model": provider not in {"dry-run", "mock"},
        "messages": messages,
    }
    _append_jsonl(path, event)


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    """Append one JSON object per line for prompt inspection."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(row, ensure_ascii=True) + "\n")


def _log(path: Path, message: str) -> None:
    """Print and persist simple progress events for slow model calls."""
    path.parent.mkdir(parents=True, exist_ok=True)
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} | {message}"
    print(line, flush=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(line + "\n")


def _write_methodology_plot(path: Path, summary: list[dict[str, Any]]) -> None:
    """Plot MATH-500 shortcut rate at probe against held teaching-turn count."""
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("Install matplotlib to create the live-history chart.")
        return

    dataset = "math500"
    color = "#d62728"
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.2), sharey=True)

    for ax, reasoning in zip(axes, ["off", "on"]):
        points = [
            row
            for row in summary
            if row["dataset"] == dataset and row["reasoning"] == reasoning
        ]
        x_values = [row["rule_held_count"] for row in points]
        y_values = [row["shortcut_rate"] * 100 for row in points]
        ax.plot(x_values, y_values, marker="o", label="MATH-500", color=color)
        for x_value, y_value, row in zip(x_values, y_values, points):
            ax.text(
                x_value,
                y_value + 3,
                f"n={row['n']}",
                fontsize=7,
                ha="center",
                color=color,
            )
        ax.set_title(f"reasoning = {reasoning}")
        ax.set_xlabel("rule held count (of 4 teaching turns)")
        ax.set_xticks(range(TEACHING_TURNS + 1))
        ax.grid(True, alpha=0.25)

    axes[0].set_ylabel("shortcut rate at probe (%)")
    axes[0].legend(title="dataset", fontsize=8)
    fig.suptitle(
        "Shortcut rate at probe vs. how many teaching turns the planted rule held on\n"
        "(live-history conversations only, descriptive -- n labeled at every point)",
        fontsize=9,
    )
    plt.ylim(-5, 110)
    plt.tight_layout()
    plt.savefig(path, dpi=160)
    plt.close()
