"""Live-history experiment using teaching turns before a probe."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock
from typing import Any

from cue_eval.cue_strategies import CUE_STRATEGIES, apply_cue_strategy, strategy_for_episode
from cue_eval.data import load_examples
from cue_eval.providers import ModelResponse, call_model_result
from cue_eval.reasoning import add_qwen_thinking_switch
from cue_eval.scoring import extract_final_number, label_answer
from cue_eval.story_pool import choose_story_template, load_story_pool, render_story


TEACHING_TURNS = 3
DEFAULT_EPISODES = 45
CHECKPOINT_VERSION = 5
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


def _checkpoint_config(
    data_path: str | Path,
    story_pool_path: str | Path | None,
    dataset_name: str,
    provider: str,
    model: str,
    temperature: float,
    max_tokens: int,
    reasoning_modes: list[str],
    cue_counts: list[int],
    episode_count: int,
    episode_limit: int | None,
) -> dict[str, Any]:
    """Capture settings that must match before checkpoint rows can be reused."""
    return {
        "checkpoint_version": CHECKPOINT_VERSION,
        "dataset": dataset_name,
        "data_sha256": _file_sha256(data_path),
        "story_pool_sha256": _file_sha256(story_pool_path) if story_pool_path else None,
        "provider": provider,
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "reasoning_modes": reasoning_modes,
        "cue_counts": cue_counts,
        "episode_count": episode_count,
        "episode_limit": episode_limit,
        "teaching_turns": TEACHING_TURNS,
        "teaching_response_mode": "scripted_shortcut",
        "cue_strategies": list(CUE_STRATEGIES),
    }


def _file_sha256(path: str | Path) -> str:
    """Hash an input file so changed data cannot reuse an older checkpoint."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_or_create_checkpoint(
    partial_csv_path: Path,
    checkpoint_path: Path,
    config: dict[str, Any],
    expected_tasks: dict[tuple[str, str, int, int], str],
    adopt_legacy_checkpoint: bool,
) -> list[dict[str, Any]]:
    """Validate checkpoint metadata and recover complete, unique result rows."""
    if partial_csv_path.exists() and not checkpoint_path.exists():
        if not adopt_legacy_checkpoint:
            raise ValueError(
                f"Found {partial_csv_path} without checkpoint metadata. "
                "Use --adopt-checkpoint if it belongs to these settings, or use --fresh."
            )
        rows = _load_partial_rows(partial_csv_path, expected_tasks)
        _write_checkpoint_metadata(checkpoint_path, config)
        return rows

    if checkpoint_path.exists():
        saved_config = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        if saved_config != config:
            changed = sorted(key for key in config if saved_config.get(key) != config[key])
            raise ValueError(
                f"Checkpoint settings changed ({', '.join(changed)}). "
                "Use --fresh or choose a new output directory."
            )
    else:
        _write_checkpoint_metadata(checkpoint_path, config)

    if not partial_csv_path.exists():
        return []
    return _load_partial_rows(partial_csv_path, expected_tasks)


def _write_checkpoint_metadata(path: Path, config: dict[str, Any]) -> None:
    """Write checkpoint metadata atomically before model calls begin."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary_path.replace(path)


def _load_partial_rows(
    path: Path,
    expected_tasks: dict[tuple[str, str, int, int], str],
) -> list[dict[str, Any]]:
    """Load valid checkpoint rows and repair a truncated final CSV record."""
    rows_by_key: dict[tuple[str, str, int, int], dict[str, Any]] = {}
    discarded_rows = 0
    with path.open("r", newline="", encoding="utf-8-sig") as file:
        for row in csv.DictReader(file):
            if None in row or any(value is None for value in row.values()):
                discarded_rows += 1
                continue
            try:
                key = _result_key(row)
            except (KeyError, TypeError, ValueError):
                discarded_rows += 1
                continue
            if key not in expected_tasks or row.get("probe_id") != expected_tasks[key]:
                raise ValueError(
                    f"Checkpoint row {key} does not match this run. "
                    "Use --fresh or choose a new output directory."
                )
            if key in rows_by_key:
                discarded_rows += 1
            rows_by_key[key] = row

    rows = list(rows_by_key.values())
    if discarded_rows:
        if rows:
            _write_csv(path, rows)
        else:
            path.unlink()
    return rows


def _result_key(row: dict[str, Any]) -> tuple[str, str, int, int]:
    """Identify one independently resumable experiment episode."""
    return (
        str(row["dataset"]),
        str(row["reasoning"]),
        int(row["cue_count"]),
        int(row["episode_index"]),
    )


def run_experiment2_experiment(
    data_path: str | Path,
    dataset_name: str,
    output_dir: str | Path,
    provider: str,
    model: str,
    temperature: float,
    max_tokens: int,
    reasoning_modes: list[str],
    cue_counts: list[int] | None = None,
    episode_limit: int | None = DEFAULT_EPISODES,
    max_workers: int = 4,
    story_pool_path: str | Path | None = None,
    resume: bool = True,
    adopt_legacy_checkpoint: bool = False,
) -> list[dict[str, Any]]:
    """Run live teaching conversations, resuming completed episodes when possible."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    examples = load_examples(data_path)
    episodes = _make_episodes(examples, episode_limit)
    story_pool = load_story_pool(story_pool_path)
    cue_counts = cue_counts or list(range(1, 11))
    max_workers = max(1, max_workers)
    write_lock = Lock()

    progress_path = output_path / "progress.log"
    partial_csv_path = output_path / "experiment2_results.partial.csv"
    checkpoint_path = output_path / "experiment2_checkpoint.json"
    prompt_log_path = output_path / "model_prompts.jsonl"
    grouped_prompt_log_path = output_path / "model_prompts_by_episode.jsonl"
    checkpoint_config = _checkpoint_config(
        data_path=data_path,
        story_pool_path=story_pool_path,
        dataset_name=dataset_name,
        provider=provider,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        reasoning_modes=reasoning_modes,
        cue_counts=cue_counts,
        episode_count=len(episodes),
        episode_limit=episode_limit,
    )
    expected_tasks = {
        (dataset_name, reasoning, cue_count, episode_index): episode[TEACHING_TURNS]["id"]
        for reasoning in reasoning_modes
        for cue_count in cue_counts
        for episode_index, episode in enumerate(episodes)
    }

    if not resume:
        for path in (
            partial_csv_path,
            checkpoint_path,
            progress_path,
            prompt_log_path,
            grouped_prompt_log_path,
        ):
            if path.exists():
                path.unlink()

    rows = _load_or_create_checkpoint(
        partial_csv_path,
        checkpoint_path,
        checkpoint_config,
        expected_tasks,
        adopt_legacy_checkpoint,
    )
    completed_keys = {_result_key(row) for row in rows}
    total_tasks = len(expected_tasks)
    _log(
        progress_path,
        (
            f"{'Resuming' if rows else 'Starting'} live-history run provider={provider} model={model} "
            f"examples={len(examples)} episodes_per_reasoning={len(episodes)} "
            f"cue_strategies={','.join(CUE_STRATEGIES)} "
            f"reasoning_modes={','.join(reasoning_modes)} "
            f"cue_counts={','.join(str(value) for value in cue_counts)} "
            f"max_workers={max_workers} completed={len(rows)} remaining={total_tasks - len(rows)}"
        ),
        write_lock,
    )

    failed_tasks = 0
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {}
        for reasoning in reasoning_modes:
            _log(progress_path, f"Queueing reasoning={reasoning}", write_lock)
            for cue_count in cue_counts:
                _log(progress_path, f"Queueing reasoning={reasoning} cue_count={cue_count}", write_lock)
                for episode_index, episode in enumerate(episodes):
                    task_key = (dataset_name, reasoning, cue_count, episode_index)
                    if task_key in completed_keys:
                        continue
                    future = executor.submit(
                            _run_episode,
                            episode=episode,
                            episode_index=episode_index,
                            total_episodes=len(episodes),
                            dataset_name=dataset_name,
                            provider=provider,
                            model=model,
                            temperature=temperature,
                            max_tokens=max_tokens,
                            reasoning=reasoning,
                            cue_count=cue_count,
                            story_pool=story_pool,
                            progress_path=progress_path,
                            prompt_log_path=prompt_log_path,
                            write_lock=write_lock,
                        )
                    futures[future] = task_key

        for future in as_completed(futures):
            task_key = futures[future]
            try:
                row = future.result()
            except Exception as error:
                failed_tasks += 1
                _, failed_reasoning, failed_cue_count, failed_episode_index = task_key
                _log(
                    progress_path,
                    (
                        "Episode failed and will be retried on resume: "
                        f"reasoning={failed_reasoning} cue_count={failed_cue_count} "
                        f"episode={failed_episode_index + 1}/{len(episodes)} "
                        f"{type(error).__name__}: {error}"
                    ),
                    write_lock,
                )
                continue
            rows.append(row)
            completed_keys.add(_result_key(row))
            _append_csv(partial_csv_path, row, write_lock)
            _log(
                progress_path,
                (
                    f"Saved checkpoint row {len(rows)}/{total_tasks} "
                    f"reasoning={row['reasoning']} cue_count={row['cue_count']} "
                    f"episode={int(row['episode_index']) + 1}/{len(episodes)} "
                    f"probe_label={row['probe_label']}"
                ),
                write_lock,
            )

    rows.sort(key=lambda row: (row["reasoning"], int(row["cue_count"]), int(row["episode_index"])))
    if failed_tasks:
        message = (
            f"{failed_tasks} episode(s) failed; {len(rows)}/{total_tasks} completed rows are checkpointed. "
            "Rerun the same command to retry only unfinished episodes."
        )
        _log(progress_path, message, write_lock)
        raise RuntimeError(message)

    _write_csv(output_path / "experiment2_results.csv", rows)
    write_grouped_episode_prompts(output_path, rows)
    _log(progress_path, f"Finished run. Wrote final CSV with {len(rows)} rows.", write_lock)
    return rows


def summarize_experiment2(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate every probe response by dataset, reasoning mode, and cue count."""
    summary: list[dict[str, Any]] = []
    datasets = sorted({row["dataset"] for row in rows})
    reasoning_modes = sorted({row["reasoning"] for row in rows})
    cue_counts = sorted({int(row["cue_count"]) for row in rows})
    for dataset in datasets:
        for reasoning in reasoning_modes:
            for cue_count in cue_counts:
                group = [
                    row
                    for row in rows
                    if row["dataset"] == dataset
                    and row["reasoning"] == reasoning
                    and int(row["cue_count"]) == cue_count
                ]
                category_counts = {
                    label: sum(row["probe_label"] == label for row in group)
                    for label, _, _, _ in PROBE_RESPONSE_CATEGORIES
                }
                unknown_labels = {
                    row["probe_label"] for row in group if row["probe_label"] not in category_counts
                }
                if unknown_labels:
                    names = ", ".join(sorted(unknown_labels))
                    raise ValueError(f"Unknown probe response labels: {names}")
                valid = [row for row in group if row["probe_label"] != "parse_fail"]
                held_counts = [int(row["rule_held_count"]) for row in valid]
                summary.append(
                    {
                        "dataset": dataset,
                        "reasoning": reasoning,
                        "cue_count": cue_count,
                        "n": len(valid),
                        "total_n": len(group),
                        "correct_count": category_counts["correct"],
                        "shortcut_count": category_counts["followed_bad_clue"],
                        "other_wrong_answer_count": category_counts["other_wrong_answer"],
                        "no_response_count": category_counts["parse_fail"],
                        "shortcut_rate": category_counts["followed_bad_clue"] / len(valid) if valid else 0.0,
                        "avg_rule_held_count": sum(held_counts) / len(held_counts) if held_counts else 0.0,
                    }
                )
    return summary


def rescore_experiment2_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Reapply the current strict parser to stored probe responses."""
    rescored: list[dict[str, Any]] = []
    for original in rows:
        row = dict(original)
        answer = extract_final_number(
            row.get("probe_response"),
            require_final=True,
            finish_reason=row.get("probe_finish_reason"),
        )
        label = label_answer(
            answer,
            float(row["probe_correct_answer"]),
            float(row["probe_shortcut_answer"]),
        )
        row.update(
            {
                "probe_answer": "" if answer is None else answer,
                "probe_label": label,
                "probe_took_shortcut": label == "followed_bad_clue",
                "probe_is_correct": label == "correct",
            }
        )
        rescored.append(row)
    return rescored


def write_experiment2_outputs(output_dir: str | Path, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Write summary CSV, outcome plots, and the story-length diagnostic."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    summary = summarize_experiment2(rows)
    _write_csv(output_path / "experiment2_summary.csv", summary)
    _write_cue_count_plot(output_path / "experiment2_shortcut_count_by_cue_count.png", summary, use_rate=False)
    _write_cue_count_plot(output_path / "experiment2_shortcut_rate.png", summary, use_rate=True)
    _write_response_category_plot(output_path / "experiment2_response_categories_stacked.png", summary)
    _write_story_token_count_plot(output_path / "experiment2_story_token_count_by_cue_count.png", rows)
    return summary


def write_grouped_episode_prompts(
    output_dir: str | Path,
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Write one ordered, complete conversation object per episode."""
    output_path = Path(output_dir)
    raw_path = output_path / "model_prompts.jsonl"
    grouped_path = output_path / "model_prompts_by_episode.jsonl"
    if not raw_path.exists():
        raise FileNotFoundError(f"Prompt log not found: {raw_path}")

    events_by_episode: dict[tuple[str, int, int], dict[tuple[str, int], dict[str, Any]]] = {}
    with raw_path.open(encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"Invalid JSON in {raw_path} at line {line_number}") from error
            episode_key = _prompt_episode_key(event)
            turn_key = (str(event["turn_type"]), int(event["turn_index"]))
            events_by_episode.setdefault(episode_key, {})[turn_key] = event

    grouped_rows: list[dict[str, Any]] = []
    sorted_rows = sorted(
        rows,
        key=lambda row: (str(row["reasoning"]), int(row["cue_count"]), int(row["episode_index"])),
    )
    for row in sorted_rows:
        episode_key = _prompt_episode_key(row)
        events = events_by_episode.get(episode_key, {})
        expected_turns = [("teaching", index) for index in range(1, TEACHING_TURNS + 1)]
        expected_turns.append(("probe", 0))
        missing = [turn for turn in expected_turns if turn not in events]
        if missing:
            raise ValueError(f"Missing prompt events for episode {episode_key}: {missing}")

        teaching_turns = [
            _grouped_teaching_turn(row, events[("teaching", index)], index)
            for index in range(1, TEACHING_TURNS + 1)
        ]
        probe_event = events[("probe", 0)]
        probe_turn = _grouped_probe_turn(row, probe_event)
        grouped_rows.append(
            {
                "dataset": row["dataset"],
                "provider": probe_event["provider"],
                "model": probe_event["model"],
                "reasoning": row["reasoning"],
                "cue_count": int(row["cue_count"]),
                "cue_strategy": row["cue_strategy"],
                "episode_index": int(row["episode_index"]),
                "episode_number": int(row["episode_index"]) + 1,
                "total_episodes": int(probe_event["total_episodes"]),
                "probe_id": row["probe_id"],
                "turns": teaching_turns + [probe_turn],
                "probe_request_messages": probe_event["messages"],
            }
        )

    _write_jsonl(grouped_path, grouped_rows)
    return grouped_rows


def _prompt_episode_key(row: dict[str, Any]) -> tuple[str, int, int]:
    """Identify one prompt-log episode within a run."""
    return (
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
        "label": row[f"teaching_label_{index}"],
    }


def _grouped_probe_turn(row: dict[str, Any], event: dict[str, Any]) -> dict[str, Any]:
    """Build the model-generated probe turn and its scoring metadata."""
    return {
        "turn": TEACHING_TURNS + 1,
        "turn_type": "probe",
        "turn_index": 0,
        "example_id": event["example_id"],
        "sent_to_model": bool(event["sent_to_model"]),
        "response_source": event["response_source"],
        "user_message": row["probe_prompt"],
        "assistant_response": row["probe_response"],
        "parsed_answer": _optional_number(row["probe_answer"]),
        "correct_answer": _optional_number(row["probe_correct_answer"]),
        "shortcut_answer": _optional_number(row["probe_shortcut_answer"]),
        "label": row["probe_label"],
        "took_shortcut": _as_bool(row["probe_took_shortcut"]),
        "is_correct": _as_bool(row["probe_is_correct"]),
        "finish_reason": row["probe_finish_reason"],
        "was_truncated": _as_bool(row["probe_was_truncated"]),
    }


def _optional_number(value: Any) -> float | None:
    """Normalize CSV and in-memory answer values for JSON output."""
    if value is None or value == "":
        return None
    return float(value)


def _as_bool(value: Any) -> bool:
    """Normalize CSV and in-memory boolean values for JSON output."""
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() == "true"


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
    cue_count: int,
    story_pool: dict[int, list[dict[str, Any]]],
    progress_path: Path,
    prompt_log_path: Path,
    write_lock: Any | None = None,
) -> dict[str, Any]:
    """Run three teaching turns, then one probe using one episode strategy."""
    episode_start = time.perf_counter()
    cue_strategy = strategy_for_episode(episode_index)
    messages = [{"role": "system", "content": _system_prompt(reasoning, model)}]
    teaching_labels: list[str] = []
    teaching_answers: list[str] = []
    teaching_prompts: list[str] = []
    teaching_shortcut_answers: list[float] = []
    teaching_responses: list[str] = []
    teaching_results: list[ModelResponse] = []
    _log(
        progress_path,
        (
            f"Episode {episode_index + 1}/{total_episodes} reasoning={reasoning} "
            f"cue_count={cue_count} cue_strategy={cue_strategy} started"
        ),
        write_lock,
    )

    for turn_index, example in enumerate(episode[:TEACHING_TURNS], start=1):
        example = apply_cue_strategy(example, cue_strategy)
        story_template = choose_story_template(story_pool, cue_count, episode_index + turn_index)
        user_message = _teaching_prompt(example, turn_index, story_template)
        teaching_prompts.append(user_message)
        request_messages = messages + [{"role": "user", "content": user_message}]
        result = _scripted_teaching_response(example)
        _log_prompt_event(
            prompt_log_path,
            provider=provider,
            model=model,
            reasoning=reasoning,
            cue_count=cue_count,
            cue_strategy=cue_strategy,
            episode_index=episode_index,
            total_episodes=total_episodes,
            turn_type="teaching",
            turn_index=turn_index,
            example_id=example["id"],
            messages=request_messages,
            sent_to_model=False,
            response_source="scripted",
            write_lock=write_lock,
        )
        response = result.content
        parsed = extract_final_number(
            response,
            require_final=True,
            finish_reason=result.finish_reason,
        )
        label = label_answer(parsed, example["correct_answer"], example["shortcut_answer"])
        _log(
            progress_path,
            (
                f"Episode {episode_index + 1}/{total_episodes} reasoning={reasoning} cue_count={cue_count} "
                f"teaching_turn={turn_index}/{TEACHING_TURNS} scripted "
                f"label={label} parsed={parsed}"
            ),
            write_lock,
        )
        teaching_labels.append(label)
        teaching_answers.append("" if parsed is None else str(parsed))
        teaching_shortcut_answers.append(example["shortcut_answer"])
        teaching_responses.append(response)
        teaching_results.append(result)
        messages.extend(
            [
                {"role": "user", "content": user_message},
                {"role": "assistant", "content": response},
            ]
        )

    probe = apply_cue_strategy(episode[TEACHING_TURNS], cue_strategy)
    probe_story_template = choose_story_template(story_pool, cue_count, episode_index + TEACHING_TURNS + 1)
    probe_message = _probe_prompt(probe, probe_story_template)
    probe_request_messages = messages + [{"role": "user", "content": probe_message}]
    _log_prompt_event(
        prompt_log_path,
        provider=provider,
        model=model,
        reasoning=reasoning,
        cue_count=cue_count,
        cue_strategy=cue_strategy,
        episode_index=episode_index,
        total_episodes=total_episodes,
        turn_type="probe",
        turn_index=0,
        example_id=probe["id"],
        messages=probe_request_messages,
        sent_to_model=provider not in {"dryrun", "mock"},
        response_source="model" if provider not in {"dryrun", "mock"} else "dryrun",
        write_lock=write_lock,
    )
    probe_result = _model_or_dry_probe_response(
        provider,
        probe,
        episode_index,
        cue_count,
    )
    if probe_result is None:
        call_start = time.perf_counter()
        _log(
            progress_path,
            (
                f"Episode {episode_index + 1}/{total_episodes} reasoning={reasoning} cue_count={cue_count} "
                f"probe calling model example_id={probe['id']}"
            ),
            write_lock,
        )
        probe_result = call_model_result(
            provider,
            probe_request_messages,
            model,
            temperature,
            max_tokens,
        )
        _log(
            progress_path,
            (
                f"Episode {episode_index + 1}/{total_episodes} reasoning={reasoning} cue_count={cue_count} "
                f"probe model returned seconds={time.perf_counter() - call_start:.1f} "
                f"chars={len(probe_result.content)} "
                f"finish_reason={probe_result.finish_reason or 'unknown'}"
            ),
            write_lock,
        )
    probe_response = probe_result.content
    probe_answer = extract_final_number(
        probe_response,
        require_final=True,
        finish_reason=probe_result.finish_reason,
    )
    probe_label = label_answer(probe_answer, probe["correct_answer"], probe["shortcut_answer"])
    _log(
        progress_path,
        (
            f"Episode {episode_index + 1}/{total_episodes} reasoning={reasoning} cue_count={cue_count} finished "
            f"probe_label={probe_label} probe_answer={probe_answer} "
            f"rule_held_count={sum(label == 'followed_bad_clue' for label in teaching_labels)} "
            f"seconds={time.perf_counter() - episode_start:.1f}"
        ),
        write_lock,
    )

    row = {
        "dataset": dataset_name,
        "reasoning": reasoning,
        "cue_count": cue_count,
        "cue_strategy": cue_strategy,
        "episode_index": episode_index,
        "probe_id": probe["id"],
        "scripted_teaching_count": TEACHING_TURNS,
        "rule_held_count": sum(label == "followed_bad_clue" for label in teaching_labels),
        "probe_label": probe_label,
        "probe_took_shortcut": probe_label == "followed_bad_clue",
        "probe_is_correct": probe_label == "correct",
        "probe_answer": "" if probe_answer is None else probe_answer,
        "probe_correct_answer": probe["correct_answer"],
        "probe_shortcut_answer": probe["shortcut_answer"],
        "teaching_labels": "|".join(teaching_labels),
        "teaching_answers": "|".join(teaching_answers),
        "probe_prompt": probe_message,
        "probe_response": probe_response,
        "probe_finish_reason": probe_result.finish_reason or "",
        "probe_was_truncated": probe_result.was_truncated,
        "probe_prompt_tokens": _csv_value(probe_result.prompt_tokens),
        "probe_completion_tokens": _csv_value(probe_result.completion_tokens),
        "probe_total_tokens": _csv_value(probe_result.total_tokens),
    }
    for index, (label, answer, prompt, response, shortcut, result) in enumerate(
        zip(
            teaching_labels,
            teaching_answers,
            teaching_prompts,
            teaching_responses,
            teaching_shortcut_answers,
            teaching_results,
        ),
        start=1,
    ):
        row[f"teaching_label_{index}"] = label
        row[f"teaching_answer_{index}"] = answer
        row[f"teaching_shortcut_answer_{index}"] = shortcut
        row[f"teaching_prompt_{index}"] = prompt
        row[f"teaching_response_{index}"] = response
        row[f"teaching_response_source_{index}"] = "scripted"
        row[f"teaching_finish_reason_{index}"] = result.finish_reason or ""
        row[f"teaching_was_truncated_{index}"] = result.was_truncated
        row[f"teaching_prompt_tokens_{index}"] = _csv_value(result.prompt_tokens)
        row[f"teaching_completion_tokens_{index}"] = _csv_value(result.completion_tokens)
        row[f"teaching_total_tokens_{index}"] = _csv_value(result.total_tokens)
    return row


def _make_episodes(
    examples: list[dict[str, Any]],
    episode_limit: int | None = DEFAULT_EPISODES,
) -> list[list[dict[str, Any]]]:
    """Create rolling 3-teach-plus-1-probe episodes, capped when requested."""
    if episode_limit is not None and episode_limit < 1:
        raise ValueError("episode_limit must be positive or None")
    if len(examples) < TEACHING_TURNS + 1:
        return []
    episodes: list[list[dict[str, Any]]] = []
    for start in range(len(examples) - TEACHING_TURNS):
        episodes.append(examples[start : start + TEACHING_TURNS + 1])
    return episodes[:episode_limit] if episode_limit is not None else episodes


def _system_prompt(reasoning: str, model: str = "") -> str:
    """Build a simple reasoning-on/off instruction for the model."""
    base = "You are solving math problems. Always end with 'Final answer: <number>'."
    if reasoning == "on":
        prompt = base + " Think step by step before giving the final answer."
    else:
        prompt = base + " Keep the response brief and do not show step-by-step reasoning."
    return add_qwen_thinking_switch(prompt, model, reasoning)


def _teaching_prompt(example: dict[str, Any], turn_index: int, story_template: str | None = None) -> str:
    """Build a teaching user message for the scripted conversation history."""
    story = _story_text(example, story_template)
    return f"{story}\n\n{example['problem']}"


def _probe_prompt(example: dict[str, Any], story_template: str | None = None) -> str:
    """Ask the held-out problem without probe-specific model-facing labels."""
    story = _story_text(example, story_template)
    return f"{story}\n\n{example['problem']}"


def _story_text(example: dict[str, Any], story_template: str | None) -> str:
    """Render a complex story, or fall back to a simple notebook story."""
    if story_template:
        return render_story(story_template, example["bad_clue"])
    return (
        "A student is practicing a shortcut rule before the final question. "
        f"The student's notebook says: {example['bad_clue'].rstrip('.')}"
    )


def _scripted_teaching_response(example: dict[str, Any]) -> ModelResponse:
    """Insert the predetermined shortcut answer for a teaching turn."""
    return ModelResponse(
        content=f"Final answer: {example['shortcut_answer']}",
        finish_reason="scripted",
    )


def _model_or_dry_probe_response(
    provider: str,
    example: dict[str, Any],
    episode_index: int,
    cue_count: int,
) -> ModelResponse | None:
    """Provide deterministic dryrun responses for probe graph testing."""
    if provider not in {"dryrun", "mock"}:
        return None
    answer = example["shortcut_answer"] if episode_index % 10 < cue_count else example["correct_answer"]
    return ModelResponse(
        content=f"Dry run response. Final answer: {answer}",
        finish_reason="stop",
    )


def _csv_value(value: int | None) -> int | str:
    """Represent missing provider metadata as an empty CSV cell."""
    return "" if value is None else value


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    """Write dictionaries to CSV."""
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _append_csv(path: Path, row: dict[str, Any], write_lock: Any | None = None) -> None:
    """Append one row so long model runs leave inspectable partial output."""
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


def _log_prompt_event(
    path: Path,
    provider: str,
    model: str,
    reasoning: str,
    cue_count: int,
    cue_strategy: str,
    episode_index: int,
    total_episodes: int,
    turn_type: str,
    turn_index: int,
    example_id: str,
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
        "reasoning": reasoning,
        "cue_count": cue_count,
        "cue_strategy": cue_strategy,
        "episode_index": episode_index,
        "episode_number": episode_index + 1,
        "total_episodes": total_episodes,
        "turn_type": turn_type,
        "turn_index": turn_index,
        "example_id": example_id,
        "sent_to_model": sent_to_model,
        "response_source": response_source,
        "messages": messages,
    }
    _append_jsonl(path, event, write_lock)


def _append_jsonl(path: Path, row: dict[str, Any], write_lock: Any | None = None) -> None:
    """Append one JSON object per line for prompt inspection."""
    if write_lock:
        with write_lock:
            _append_jsonl_unlocked(path, row)
        return
    _append_jsonl_unlocked(path, row)


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    """Write JSONL atomically so readers never see a partial grouped file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    with temporary_path.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=True) + "\n")
    temporary_path.replace(path)


def _append_jsonl_unlocked(path: Path, row: dict[str, Any]) -> None:
    """Append one JSONL row after any caller-side locking."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(row, ensure_ascii=True) + "\n")


def _log(path: Path, message: str, write_lock: Any | None = None) -> None:
    """Print and persist simple progress events for slow model calls."""
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


def _write_cue_count_plot(path: Path, summary: list[dict[str, Any]], use_rate: bool) -> None:
    """Plot MATH-500 shortcut results by wrong-answer cue count."""
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("Install matplotlib to create the live-history chart.")
        return

    dataset = "math500"
    color = "#d62728"
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.2), sharey=True)
    y_key = "shortcut_rate" if use_rate else "shortcut_count"
    y_label = "shortcut rate at probe (%)" if use_rate else "no. of times model took the shortcut"
    title_metric = "rate" if use_rate else "count"

    for ax, reasoning in zip(axes, ["off", "on"]):
        points = [
            row
            for row in summary
            if row["dataset"] == dataset and row["reasoning"] == reasoning
        ]
        x_values = [row["cue_count"] for row in points]
        y_values = [row[y_key] * 100 if use_rate else row[y_key] for row in points]
        ax.plot(x_values, y_values, marker="o", label="MATH-500", color=color)
        for x_value, y_value, row in zip(x_values, y_values, points):
            ax.text(
                x_value,
                y_value + (3 if use_rate else 1),
                _sample_size_label(row),
                fontsize=7,
                ha="center",
                color=color,
            )
        ax.set_title(f"reasoning = {reasoning}")
        ax.set_xlabel("no. of times cue appears in each story")
        ax.set_xticks(x_values)
        ax.grid(True, alpha=0.25)

    max_y = max((row[y_key] * 100 if use_rate else row[y_key] for row in summary), default=0)
    axes[0].set_ylabel(y_label)
    axes[0].legend(title="dataset", fontsize=8)
    fig.suptitle(
        f"Math500 live-history shortcut {title_metric} by wrong-answer cue count\n"
        "(5 story templates per cue count; n labeled at every point)",
        fontsize=9,
    )
    fig.text(0.5, 0.015, STORY_LENGTH_CAPTION, ha="center", fontsize=8)
    plt.ylim(-5 if use_rate else 0, max(110 if use_rate else 10, max_y + (10 if use_rate else 5)))
    plt.tight_layout(rect=(0, 0.06, 1, 1))
    plt.savefig(path, dpi=160)
    plt.close()


def _sample_size_label(row: dict[str, Any]) -> str:
    """Show total episodes and disclose exclusions from rate calculations."""
    total = int(row["total_n"])
    valid = int(row["n"])
    return f"N={total}" if valid == total else f"N={total}\nvalid={valid}"


def _write_response_category_plot(path: Path, summary: list[dict[str, Any]]) -> None:
    """Plot all final probe response categories as stacked counts."""
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("Install matplotlib to create the response-category chart.")
        return

    dataset = "math500"
    fig, axes = plt.subplots(1, 2, figsize=(12, 5.2), sharey=True)
    max_total = max((int(row["total_n"]) for row in summary), default=0)

    for ax, reasoning in zip(axes, ["off", "on"]):
        points = [
            row
            for row in summary
            if row["dataset"] == dataset and row["reasoning"] == reasoning
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
                        color="white" if color in {"#2ca02c", "#d62728", "#7f7f7f"} else "black",
                    )
            bottoms = [bottom + value for bottom, value in zip(bottoms, values)]

        for x_value, total in zip(x_values, bottoms):
            ax.text(x_value, total + 0.6, f"n={total}", ha="center", va="bottom", fontsize=7)
        ax.set_title(f"reasoning = {reasoning}")
        ax.set_xlabel("no. of times cue appears in each story")
        ax.set_xticks(x_values)
        ax.set_ylim(0, max_total + 4)
        ax.set_axisbelow(True)
        ax.grid(axis="y", alpha=0.25)

    axes[0].set_ylabel("number of final probe responses")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", ncol=4, bbox_to_anchor=(0.5, 0.93), fontsize=8)
    fig.suptitle("Math500 final probe responses by wrong-answer cue count", fontsize=11)
    fig.text(0.5, 0.015, STORY_LENGTH_CAPTION, ha="center", fontsize=8)
    plt.tight_layout(rect=(0, 0.06, 1, 0.86))
    plt.savefig(path, dpi=160)
    plt.close()


def _write_story_token_count_plot(path: Path, rows: list[dict[str, Any]]) -> None:
    """Plot rendered story token counts to expose any length trend by cue count."""
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("Install matplotlib to create the story-length diagnostic chart.")
        return

    grouped_counts = _story_token_counts_by_cue_count(rows)
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


def _story_token_counts_by_cue_count(rows: list[dict[str, Any]]) -> dict[int, list[int]]:
    """Collect lexical token counts from the rendered story portion of each prompt."""
    grouped_counts: dict[int, list[int]] = {}
    prompt_fields = [
        f"teaching_prompt_{index}" for index in range(1, TEACHING_TURNS + 1)
    ] + ["probe_prompt"]
    for row in rows:
        cue_count = int(row["cue_count"])
        for field in prompt_fields:
            prompt = row.get(field)
            if not isinstance(prompt, str) or not prompt.strip():
                continue
            story = prompt.split("\n\n", 1)[0]
            grouped_counts.setdefault(cue_count, []).append(len(LEXICAL_TOKEN_PATTERN.findall(story)))
    return grouped_counts
