"""Live-history experiment using teaching turns before a probe."""

from __future__ import annotations

import csv
import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock
from typing import Any

from cue_eval.cue_strategies import (
    CUE_STRATEGIES,
    apply_cue_strategy,
    paraphrase_shortcut_cues,
    strategy_for_episode,
)
from cue_eval.data import load_examples
from cue_eval.episode_creation import create_rolling_episodes
from cue_eval.output_writer import (
    append_csv as _append_csv,
    csv_value as _csv_value,
    log as _log,
    log_prompt_event as _log_prompt_event,
    sample_size_label as _sample_size_label,
    story_token_counts_by_cue_count as _story_token_counts_by_cue_count,
    summarize_experiment,
    summarize_usage_by_subexperiment,
    write_csv as _write_csv,
    write_experiment_outputs,
    write_grouped_episode_prompts,
    write_json as _write_json,
)
from cue_eval.providers import ModelResponse, call_model_result
from cue_eval.reasoning import add_qwen_thinking_switch
from cue_eval.model_response_parser import extract_final_number
from cue_eval.scoring import label_answer
from cue_eval.story_pool import choose_story, load_story_pool, render_story, validate_story_pool
from cue_eval.token_usage_tracker import (
    format_usage_summary,
    resolve_token_pricing,
    summarize_usage,
    write_usage_summary,
)


TEACHING_TURNS = 3
DEFAULT_EPISODES = 45
DEFAULT_MAX_TOKENS = 8192
CONDITIONS = ("assistant_wrong", "assistant_correct")
CHECKPOINT_VERSION = 7
CUE_RENDERING_MODE = "deterministic_paraphrases_v1"


def _checkpoint_config(
    data_path: str | Path,
    story_pool_path: str | Path | None,
    dataset_name: str,
    provider: str,
    model: str,
    temperature: float,
    max_tokens: int,
    conditions: list[str],
    reasoning_modes: list[str],
    cue_counts: list[int],
    episode_count: int,
    episode_limit: int | None,
    episode_manifest_sha256: str,
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
        "conditions": conditions,
        "reasoning_modes": reasoning_modes,
        "cue_counts": cue_counts,
        "episode_count": episode_count,
        "episode_limit": episode_limit,
        "episode_manifest_sha256": episode_manifest_sha256,
        "teaching_turns": TEACHING_TURNS,
        "teaching_response_mode": "scripted_by_condition_v1",
        "cue_strategies": list(CUE_STRATEGIES),
        "cue_rendering_mode": CUE_RENDERING_MODE,
    }


def _file_sha256(path: str | Path) -> str:
    """Hash an input file so changed data cannot reuse an older checkpoint."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_conditions(conditions: list[str]) -> None:
    """Reject unknown or repeated teaching conditions."""
    if not conditions:
        raise ValueError("At least one teaching condition is required.")
    unknown = sorted(set(conditions) - set(CONDITIONS))
    if unknown:
        raise ValueError(f"Unknown teaching conditions: {', '.join(unknown)}")
    if len(conditions) != len(set(conditions)):
        raise ValueError("Teaching conditions must not contain duplicates.")


def _validate_reasoning_modes(reasoning_modes: list[str]) -> None:
    """Accept only the two reasoning conditions used by the protocol."""
    if not reasoning_modes:
        raise ValueError("At least one reasoning mode is required.")
    unknown = sorted(set(reasoning_modes) - {"off", "on"})
    if unknown:
        raise ValueError(f"Unknown reasoning modes: {', '.join(unknown)}")
    if len(reasoning_modes) != len(set(reasoning_modes)):
        raise ValueError("Reasoning modes must not contain duplicates.")


def _build_episode_manifest(
    episodes: list[list[dict[str, Any]]],
    cue_counts: list[int],
    story_pool: dict[int, list[dict[str, Any]]],
    data_path: str | Path,
    story_pool_path: str | Path | None,
) -> dict[str, Any]:
    """Freeze probe, cue-type, and story assignments for every run cell."""
    manifest_episodes: list[dict[str, Any]] = []
    for episode_index, episode in enumerate(episodes):
        story_ids_by_cue_count: dict[str, list[str]] = {}
        for cue_count in cue_counts:
            story_ids = []
            for turn_offset in range(1, TEACHING_TURNS + 2):
                story = choose_story(story_pool, cue_count, episode_index + turn_offset)
                if story is None:
                    raise ValueError(f"No story is available for cue_count={cue_count}.")
                story_ids.append(str(story["id"]))
            if len(story_ids) != len(set(story_ids)):
                raise ValueError(
                    f"Episode {episode_index} repeats a story for cue_count={cue_count}."
                )
            story_ids_by_cue_count[str(cue_count)] = story_ids
        manifest_episodes.append(
            {
                "episode_index": episode_index,
                "shortcut_cue_type": strategy_for_episode(episode_index),
                "teaching_ids": [str(example["id"]) for example in episode[:TEACHING_TURNS]],
                "probe_id": str(episode[TEACHING_TURNS]["id"]),
                "story_ids_by_cue_count": story_ids_by_cue_count,
            }
        )

    manifest: dict[str, Any] = {
        "manifest_version": 1,
        "data_sha256": _file_sha256(data_path),
        "story_pool_sha256": _file_sha256(story_pool_path) if story_pool_path else None,
        "teaching_turns": TEACHING_TURNS,
        "episode_count": len(episodes),
        "cue_counts": cue_counts,
        "episodes": manifest_episodes,
    }
    probe_ids = [row["probe_id"] for row in manifest_episodes]
    if len(probe_ids) != len(set(probe_ids)):
        raise ValueError("Probe IDs must be unique within the shared episode manifest.")
    if len(manifest_episodes) == DEFAULT_EPISODES:
        cue_type_counts = {
            strategy: sum(
                row["shortcut_cue_type"] == strategy for row in manifest_episodes
            )
            for strategy in CUE_STRATEGIES
        }
        if set(cue_type_counts.values()) != {15}:
            raise ValueError(f"Expected a 15/15/15 cue-type split; got {cue_type_counts}.")
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
    manifest["manifest_sha256"] = hashlib.sha256(canonical).hexdigest()
    return manifest


def validate_completed_matrix(
    rows: list[dict[str, Any]],
    *,
    expected_models: int = 2,
    expected_episodes: int = DEFAULT_EPISODES,
) -> dict[str, Any]:
    """Validate the complete cross-model experiment matrix before reporting."""
    if not rows:
        raise ValueError("The combined result matrix is empty.")
    models = sorted({str(row["model"]) for row in rows})
    conditions = sorted({str(row["condition"]) for row in rows})
    reasoning_modes = sorted({str(row["reasoning"]) for row in rows})
    cue_counts = sorted({int(row["cue_count"]) for row in rows})
    manifest_hashes = sorted({str(row["episode_manifest_sha256"]) for row in rows})
    if len(models) != expected_models:
        raise ValueError(f"Expected {expected_models} models; found {models}.")
    if set(conditions) != set(CONDITIONS):
        raise ValueError(f"Expected conditions {CONDITIONS}; found {conditions}.")
    if reasoning_modes != ["off", "on"]:
        raise ValueError(f"Expected reasoning off/on; found {reasoning_modes}.")
    if len(manifest_hashes) != 1:
        raise ValueError(f"Model runs used different episode manifests: {manifest_hashes}.")
    if any(int(row["max_tokens"]) < DEFAULT_MAX_TOKENS for row in rows):
        raise ValueError(f"Every row must use max_tokens >= {DEFAULT_MAX_TOKENS}.")

    baseline_probes: dict[int, list[str]] = {}
    cell_count = 0
    for model in models:
        for condition in CONDITIONS:
            for reasoning in ("off", "on"):
                for cue_count in cue_counts:
                    group = [
                        row
                        for row in rows
                        if str(row["model"]) == model
                        and str(row["condition"]) == condition
                        and str(row["reasoning"]) == reasoning
                        and int(row["cue_count"]) == cue_count
                    ]
                    if len(group) != expected_episodes:
                        raise ValueError(
                            f"Expected {expected_episodes} rows for model={model}, "
                            f"condition={condition}, reasoning={reasoning}, cue_count={cue_count}; "
                            f"found {len(group)}."
                        )
                    cue_type_counts = {
                        strategy: sum(
                            str(row["shortcut_cue_type"]) == strategy for row in group
                        )
                        for strategy in CUE_STRATEGIES
                    }
                    expected_per_type = expected_episodes // len(CUE_STRATEGIES)
                    if set(cue_type_counts.values()) != {expected_per_type}:
                        raise ValueError(
                            f"Unbalanced cue types for model={model}, condition={condition}, "
                            f"reasoning={reasoning}, cue_count={cue_count}: {cue_type_counts}."
                        )
                    probes = [
                        str(row["probe_id"])
                        for row in sorted(group, key=lambda row: int(row["episode_index"]))
                    ]
                    baseline = baseline_probes.setdefault(cue_count, probes)
                    if probes != baseline:
                        raise ValueError(
                            f"Probe order differs for model={model}, condition={condition}, "
                            f"reasoning={reasoning}, cue_count={cue_count}."
                        )
                    cell_count += 1

    return {
        "passed": True,
        "models": models,
        "conditions": list(CONDITIONS),
        "reasoning_modes": ["off", "on"],
        "cue_counts": cue_counts,
        "episodes_per_subexperiment": expected_episodes,
        "subexperiments": cell_count,
        "result_rows": len(rows),
        "episode_manifest_sha256": manifest_hashes[0],
    }


def _load_or_create_checkpoint(
    partial_csv_path: Path,
    checkpoint_path: Path,
    config: dict[str, Any],
    expected_tasks: dict[tuple[str, str, str, int, int], str],
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
        _write_json(checkpoint_path, config)
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
        _write_json(checkpoint_path, config)

    if not partial_csv_path.exists():
        return []
    return _load_partial_rows(partial_csv_path, expected_tasks)


def _load_partial_rows(
    path: Path,
    expected_tasks: dict[tuple[str, str, str, int, int], str],
) -> list[dict[str, Any]]:
    """Load valid checkpoint rows and repair a truncated final CSV record."""
    rows_by_key: dict[tuple[str, str, str, int, int], dict[str, Any]] = {}
    discarded_rows = 0
    with path.open("r", newline="", encoding="utf-8-sig") as file:
        for row in csv.DictReader(file):
            if None in row or any(value is None for value in row.values()):
                discarded_rows += 1
                continue
            if "condition" not in row:
                raise ValueError(
                    "Checkpoint rows predate the two-condition schema. "
                    "Use --fresh or choose a new output directory."
                )
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


def _result_key(row: dict[str, Any]) -> tuple[str, str, str, int, int]:
    """Identify one independently resumable experiment episode."""
    return (
        str(row["dataset"]),
        str(row["condition"]),
        str(row["reasoning"]),
        int(row["cue_count"]),
        int(row["episode_index"]),
    )


def run_experiment(
    data_path: str | Path,
    dataset_name: str,
    output_dir: str | Path,
    provider: str,
    model: str,
    temperature: float,
    max_tokens: int,
    reasoning_modes: list[str],
    conditions: list[str] | None = None,
    cue_counts: list[int] | None = None,
    episode_limit: int | None = DEFAULT_EPISODES,
    max_workers: int = 4,
    story_pool_path: str | Path | None = None,
    resume: bool = True,
    adopt_legacy_checkpoint: bool = False,
    input_cost_per_million: float | str | None = None,
    output_cost_per_million: float | str | None = None,
) -> list[dict[str, Any]]:
    """Run live teaching conversations, resuming completed episodes when possible."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    examples = load_examples(data_path)
    episodes = create_rolling_episodes(
        examples,
        teaching_turns=TEACHING_TURNS,
        episode_limit=episode_limit,
    )
    story_pool = load_story_pool(story_pool_path)
    cue_counts = cue_counts or list(range(1, 11))
    conditions = list(CONDITIONS) if conditions is None else conditions
    _validate_conditions(conditions)
    _validate_reasoning_modes(reasoning_modes)
    validate_story_pool(story_pool, cue_counts, TEACHING_TURNS + 1)
    episode_manifest = _build_episode_manifest(
        episodes=episodes,
        cue_counts=cue_counts,
        story_pool=story_pool,
        data_path=data_path,
        story_pool_path=story_pool_path,
    )
    manifest_sha256 = str(episode_manifest["manifest_sha256"])
    story_by_id = {
        str(story["id"]): story
        for stories in story_pool.values()
        for story in stories
    }
    max_workers = max(1, max_workers)
    write_lock = Lock()

    progress_path = output_path / "progress.log"
    partial_csv_path = output_path / "experiment_results.partial.csv"
    checkpoint_path = output_path / "experiment_checkpoint.json"
    prompt_log_path = output_path / "model_prompts.jsonl"
    grouped_prompt_log_path = output_path / "model_prompts_by_episode.jsonl"
    manifest_path = output_path / "episode_manifest.json"
    checkpoint_config = _checkpoint_config(
        data_path=data_path,
        story_pool_path=story_pool_path,
        dataset_name=dataset_name,
        provider=provider,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        conditions=conditions,
        reasoning_modes=reasoning_modes,
        cue_counts=cue_counts,
        episode_count=len(episodes),
        episode_limit=episode_limit,
        episode_manifest_sha256=manifest_sha256,
    )
    expected_tasks = {
        (dataset_name, condition, reasoning, cue_count, episode_index): episode[TEACHING_TURNS]["id"]
        for condition in conditions
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
    _write_json(manifest_path, episode_manifest)
    completed_keys = {_result_key(row) for row in rows}
    total_tasks = len(expected_tasks)
    _log(
        progress_path,
        (
            f"{'Resuming' if rows else 'Starting'} live-history run provider={provider} model={model} "
            f"examples={len(examples)} episodes_per_reasoning={len(episodes)} "
            f"conditions={','.join(conditions)} "
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
        for condition in conditions:
            for reasoning in reasoning_modes:
                _log(
                    progress_path,
                    f"Queueing condition={condition} reasoning={reasoning}",
                    write_lock,
                )
                for cue_count in cue_counts:
                    _log(
                        progress_path,
                        f"Queueing condition={condition} reasoning={reasoning} cue_count={cue_count}",
                        write_lock,
                    )
                    for episode_index, episode in enumerate(episodes):
                        task_key = (dataset_name, condition, reasoning, cue_count, episode_index)
                        if task_key in completed_keys:
                            continue
                        future = executor.submit(
                            _run_episode,
                            episode=episode,
                            manifest_episode=episode_manifest["episodes"][episode_index],
                            episode_manifest_sha256=manifest_sha256,
                            episode_index=episode_index,
                            total_episodes=len(episodes),
                            dataset_name=dataset_name,
                            provider=provider,
                            model=model,
                            temperature=temperature,
                            max_tokens=max_tokens,
                            condition=condition,
                            reasoning=reasoning,
                            cue_count=cue_count,
                            story_by_id=story_by_id,
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
                _, failed_condition, failed_reasoning, failed_cue_count, failed_episode_index = task_key
                _log(
                    progress_path,
                    (
                        "Episode failed and will be retried on resume: "
                        f"condition={failed_condition} reasoning={failed_reasoning} "
                        f"cue_count={failed_cue_count} "
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
                    f"condition={row['condition']} reasoning={row['reasoning']} "
                    f"cue_count={row['cue_count']} "
                    f"episode={int(row['episode_index']) + 1}/{len(episodes)} "
                    f"probe_label={row['probe_label']}"
                ),
                write_lock,
            )

    rows.sort(
        key=lambda row: (
            row["condition"],
            row["reasoning"],
            int(row["cue_count"]),
            int(row["episode_index"]),
        )
    )
    pricing = resolve_token_pricing(
        provider,
        model,
        input_cost_per_million,
        output_cost_per_million,
    )
    usage_summary = summarize_usage(
        rows,
        "probe_prompt_tokens",
        "probe_completion_tokens",
        provider,
        model,
        pricing,
    )
    write_usage_summary(output_path / "usage_summary.json", usage_summary)
    _write_csv(
        output_path / "usage_by_subexperiment.csv",
        summarize_usage_by_subexperiment(rows, pricing),
    )
    _log(progress_path, format_usage_summary(usage_summary), write_lock)

    if failed_tasks:
        message = (
            f"{failed_tasks} episode(s) failed; {len(rows)}/{total_tasks} completed rows are checkpointed. "
            "Rerun the same command to retry only unfinished episodes."
        )
        _log(progress_path, message, write_lock)
        raise RuntimeError(message)

    _write_csv(output_path / "experiment_results.csv", rows)
    write_grouped_episode_prompts(output_path, rows)
    _log(progress_path, f"Finished run. Wrote final CSV with {len(rows)} rows.", write_lock)
    return rows


def rescore_experiment_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
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


def _run_episode(
    episode: list[dict[str, Any]],
    manifest_episode: dict[str, Any],
    episode_manifest_sha256: str,
    episode_index: int,
    total_episodes: int,
    dataset_name: str,
    provider: str,
    model: str,
    temperature: float,
    max_tokens: int,
    condition: str,
    reasoning: str,
    cue_count: int,
    story_by_id: dict[str, dict[str, Any]],
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
    teaching_correct_answers: list[float] = []
    teaching_story_answers: list[float] = []
    teaching_story_ids: list[str] = []
    teaching_responses: list[str] = []
    teaching_results: list[ModelResponse] = []
    story_ids = manifest_episode["story_ids_by_cue_count"][str(cue_count)]
    _log(
        progress_path,
        (
            f"Episode {episode_index + 1}/{total_episodes} condition={condition} reasoning={reasoning} "
            f"cue_count={cue_count} cue_strategy={cue_strategy} started"
        ),
        write_lock,
    )

    for turn_index, example in enumerate(episode[:TEACHING_TURNS], start=1):
        example = apply_cue_strategy(example, cue_strategy)
        story_id = str(story_ids[turn_index - 1])
        story_template = str(story_by_id[story_id]["story"])
        story_answer = _teaching_story_answer(example, condition)
        user_message = _teaching_prompt(
            example,
            turn_index,
            story_template,
            story_answer=story_answer,
        )
        teaching_prompts.append(user_message)
        request_messages = messages + [{"role": "user", "content": user_message}]
        result = _scripted_teaching_response(example, condition)
        _log_prompt_event(
            prompt_log_path,
            provider=provider,
            model=model,
            condition=condition,
            reasoning=reasoning,
            cue_count=cue_count,
            cue_strategy=cue_strategy,
            episode_index=episode_index,
            total_episodes=total_episodes,
            turn_type="teaching",
            turn_index=turn_index,
            example_id=example["id"],
            story_id=story_id,
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
                f"Episode {episode_index + 1}/{total_episodes} condition={condition} "
                f"reasoning={reasoning} cue_count={cue_count} "
                f"teaching_turn={turn_index}/{TEACHING_TURNS} scripted "
                f"label={label} parsed={parsed}"
            ),
            write_lock,
        )
        teaching_labels.append(label)
        teaching_answers.append("" if parsed is None else str(parsed))
        teaching_shortcut_answers.append(example["shortcut_answer"])
        teaching_correct_answers.append(example["correct_answer"])
        teaching_story_answers.append(story_answer)
        teaching_story_ids.append(story_id)
        teaching_responses.append(response)
        teaching_results.append(result)
        messages.extend(
            [
                {"role": "user", "content": user_message},
                {"role": "assistant", "content": response},
            ]
        )

    probe = apply_cue_strategy(episode[TEACHING_TURNS], cue_strategy)
    probe_story_id = str(story_ids[TEACHING_TURNS])
    probe_story_template = str(story_by_id[probe_story_id]["story"])
    probe_message = _probe_prompt(probe, probe_story_template)
    probe_request_messages = messages + [{"role": "user", "content": probe_message}]
    _log_prompt_event(
        prompt_log_path,
        provider=provider,
        model=model,
        condition=condition,
        reasoning=reasoning,
        cue_count=cue_count,
        cue_strategy=cue_strategy,
        episode_index=episode_index,
        total_episodes=total_episodes,
        turn_type="probe",
        turn_index=0,
        example_id=probe["id"],
        story_id=probe_story_id,
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
        reasoning,
    )
    if probe_result is None:
        call_start = time.perf_counter()
        _log(
            progress_path,
            (
                f"Episode {episode_index + 1}/{total_episodes} condition={condition} "
                f"reasoning={reasoning} cue_count={cue_count} "
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
                f"Episode {episode_index + 1}/{total_episodes} condition={condition} "
                f"reasoning={reasoning} cue_count={cue_count} "
                f"probe model returned seconds={time.perf_counter() - call_start:.1f} "
                f"chars={len(probe_result.content)} "
                f"reasoning_chars={len(probe_result.reasoning)} "
                f"finish_reason={probe_result.finish_reason or 'unknown'} "
                f"input_tokens={probe_result.prompt_tokens if probe_result.prompt_tokens is not None else 'unknown'} "
                f"output_tokens={probe_result.completion_tokens if probe_result.completion_tokens is not None else 'unknown'}"
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
            f"Episode {episode_index + 1}/{total_episodes} condition={condition} "
            f"reasoning={reasoning} cue_count={cue_count} finished "
            f"probe_label={probe_label} probe_answer={probe_answer} "
            f"rule_held_count={TEACHING_TURNS} "
            f"seconds={time.perf_counter() - episode_start:.1f}"
        ),
        write_lock,
    )

    row = {
        "dataset": dataset_name,
        "provider": provider,
        "model": model,
        "condition": condition,
        "reasoning": reasoning,
        "max_tokens": max_tokens,
        "cue_count": cue_count,
        "shortcut_cue_type": cue_strategy,
        "cue_strategy": cue_strategy,
        "episode_index": episode_index,
        "episode_manifest_sha256": episode_manifest_sha256,
        "probe_id": probe["id"],
        "probe_story_id": probe_story_id,
        "scripted_teaching_count": TEACHING_TURNS,
        "rule_held_count": TEACHING_TURNS,
        "teaching_correct_count": sum(label == "correct" for label in teaching_labels),
        "teaching_shortcut_count": sum(
            label == "followed_bad_clue" for label in teaching_labels
        ),
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
        "probe_reasoning": probe_result.reasoning,
        "probe_reasoning_chars": len(probe_result.reasoning),
        "probe_reasoning_tokens": _csv_value(probe_result.reasoning_tokens),
        "probe_finish_reason": probe_result.finish_reason or "",
        "probe_was_truncated": probe_result.was_truncated,
        "probe_prompt_tokens": _csv_value(probe_result.prompt_tokens),
        "probe_completion_tokens": _csv_value(probe_result.completion_tokens),
        "probe_total_tokens": _csv_value(probe_result.total_tokens),
    }
    for index, (
        label,
        answer,
        prompt,
        response,
        shortcut,
        correct,
        story_answer,
        story_id,
        result,
    ) in enumerate(
        zip(
            teaching_labels,
            teaching_answers,
            teaching_prompts,
            teaching_responses,
            teaching_shortcut_answers,
            teaching_correct_answers,
            teaching_story_answers,
            teaching_story_ids,
            teaching_results,
        ),
        start=1,
    ):
        row[f"teaching_label_{index}"] = label
        row[f"teaching_answer_{index}"] = answer
        row[f"teaching_shortcut_answer_{index}"] = shortcut
        row[f"teaching_correct_answer_{index}"] = correct
        row[f"teaching_story_answer_{index}"] = story_answer
        row[f"teaching_story_id_{index}"] = story_id
        row[f"teaching_prompt_{index}"] = prompt
        row[f"teaching_response_{index}"] = response
        row[f"teaching_response_source_{index}"] = "scripted"
        row[f"teaching_finish_reason_{index}"] = result.finish_reason or ""
        row[f"teaching_was_truncated_{index}"] = result.was_truncated
        row[f"teaching_prompt_tokens_{index}"] = _csv_value(result.prompt_tokens)
        row[f"teaching_completion_tokens_{index}"] = _csv_value(result.completion_tokens)
        row[f"teaching_total_tokens_{index}"] = _csv_value(result.total_tokens)
    return row


def _system_prompt(reasoning: str, model: str = "") -> str:
    """Build a simple reasoning-on/off instruction for the model."""
    base = "You are solving math problems. Always end with 'Final answer: <number>'."
    if reasoning == "on":
        prompt = base + " Think step by step before giving the final answer."
    else:
        prompt = base + " Keep the response brief and do not show step-by-step reasoning."
    return add_qwen_thinking_switch(prompt, model, reasoning)


def run_reasoning_preflight(
    provider: str,
    model: str,
    temperature: float,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    """Verify that reasoning on produces a longer provider reasoning field."""
    user_message = "Compute 17 times 19. Always end with 'Final answer: <number>'."
    results: dict[str, dict[str, Any]] = {}
    for mode in ("off", "on"):
        messages = [
            {"role": "system", "content": _system_prompt(mode, model)},
            {"role": "user", "content": user_message},
        ]
        if provider in {"dryrun", "mock"}:
            result = ModelResponse(
                content="Final answer: 323",
                finish_reason="stop",
                reasoning="Multiply 17 by 19 to get 323." if mode == "on" else "",
                reasoning_tokens=8 if mode == "on" else 0,
            )
        else:
            result = call_model_result(
                provider,
                messages,
                model,
                temperature,
                max_tokens,
            )
        results[mode] = {
            "reasoning": result.reasoning,
            "reasoning_chars": len(result.reasoning),
            "reasoning_tokens": result.reasoning_tokens,
            "response": result.content,
            "response_chars": len(result.content),
            "finish_reason": result.finish_reason,
            "prompt_tokens": result.prompt_tokens,
            "completion_tokens": result.completion_tokens,
        }

    comparison = _reasoning_preflight_comparison(results)
    passed = comparison["measurement"] != "none"
    report = {
        "provider": provider,
        "model": model,
        "max_tokens": max_tokens,
        "same_user_input": user_message,
        "off": results["off"],
        "on": results["on"],
        "comparison": comparison,
        "passed": passed,
    }
    if output_path:
        _write_json(Path(output_path), report)
    if not passed:
        raise RuntimeError(
            "Reasoning preflight failed: reasoning-on must produce a longer reasoning field, "
            "reasoning-token count, or inline response than reasoning-off. "
            "Check the model-specific reasoning control before the full run."
        )
    return report


def _reasoning_preflight_comparison(
    results: dict[str, dict[str, Any]],
) -> dict[str, int | str]:
    """Select the strongest reasoning signal exposed by the provider."""
    off = results["off"]
    on = results["on"]
    if int(on["reasoning_chars"]) > int(off["reasoning_chars"]):
        return {
            "measurement": "reasoning_chars",
            "off": int(off["reasoning_chars"]),
            "on": int(on["reasoning_chars"]),
        }

    off_reasoning_tokens = off.get("reasoning_tokens")
    on_reasoning_tokens = on.get("reasoning_tokens")
    if on_reasoning_tokens is not None and int(on_reasoning_tokens) > int(
        off_reasoning_tokens or 0
    ):
        return {
            "measurement": "reasoning_tokens",
            "off": int(off_reasoning_tokens or 0),
            "on": int(on_reasoning_tokens),
        }

    off_response_chars = int(off["response_chars"])
    on_response_chars = int(on["response_chars"])
    off_completion_tokens = off.get("completion_tokens")
    on_completion_tokens = on.get("completion_tokens")
    token_counts_agree = (
        off_completion_tokens is None
        or on_completion_tokens is None
        or int(on_completion_tokens) > int(off_completion_tokens)
    )
    if on_response_chars > off_response_chars and token_counts_agree:
        return {
            "measurement": "inline_response_chars",
            "off": off_response_chars,
            "on": on_response_chars,
        }

    return {"measurement": "none", "off": off_response_chars, "on": on_response_chars}


def _teaching_prompt(
    example: dict[str, Any],
    turn_index: int,
    story_template: str | None = None,
    story_answer: float | None = None,
) -> str:
    """Build a teaching user message for the scripted conversation history."""
    story = _story_text(example, story_template, cue_answer=story_answer)
    return f"{story}\n\n{example['problem']}"


def _probe_prompt(example: dict[str, Any], story_template: str | None = None) -> str:
    """Ask the held-out problem without probe-specific model-facing labels."""
    story = _story_text(example, story_template)
    return f"{story}\n\n{example['problem']}"


def _story_text(
    example: dict[str, Any],
    story_template: str | None,
    cue_answer: float | None = None,
) -> str:
    """Render a complex story, or fall back to a simple notebook story."""
    rendered_answer = float(example["shortcut_answer"] if cue_answer is None else cue_answer)
    if story_template:
        cues = paraphrase_shortcut_cues(rendered_answer)
        return render_story(story_template, cues)
    return (
        "A student is practicing a shortcut rule before the final question. "
        f"The student's notebook says a previous student answered {rendered_answer:g}."
    )


def _teaching_story_answer(example: dict[str, Any], condition: str) -> float:
    """Choose the number shown in a teaching story for one condition."""
    if condition == "assistant_correct":
        return float(example["correct_answer"])
    if condition == "assistant_wrong":
        return float(example["shortcut_answer"])
    raise ValueError(f"Unknown condition: {condition}")


def _scripted_teaching_response(
    example: dict[str, Any],
    condition: str = "assistant_wrong",
) -> ModelResponse:
    """Insert the predetermined condition-specific teaching answer."""
    answer = _teaching_story_answer(example, condition)
    return ModelResponse(
        content=f"Final answer: {answer}",
        finish_reason="scripted",
    )


def _model_or_dry_probe_response(
    provider: str,
    example: dict[str, Any],
    episode_index: int,
    cue_count: int,
    reasoning: str,
) -> ModelResponse | None:
    """Provide deterministic dryrun responses for probe graph testing."""
    if provider not in {"dryrun", "mock"}:
        return None
    answer = example["shortcut_answer"] if episode_index % 10 < cue_count else example["correct_answer"]
    return ModelResponse(
        content=f"Dry run response. Final answer: {answer}",
        finish_reason="stop",
        reasoning="Dry run reasoning." if reasoning == "on" else "",
        reasoning_tokens=4 if reasoning == "on" else 0,
    )
