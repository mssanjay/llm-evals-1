"""Checkpoint and resume coverage for the live-history experiment."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import cue_eval.experiment2 as experiment2


def test_resume_retries_only_failed_episodes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep successful episodes and retry only the failed checkpoint key."""
    source_lines = (ROOT / "data" / "math500_prepared_50.jsonl").read_text(encoding="utf-8").splitlines()
    data_path = tmp_path / "examples.jsonl"
    data_path.write_text("\n".join(source_lines[:5]) + "\n", encoding="utf-8")
    output_dir = tmp_path / "output"
    original_run_episode = experiment2._run_episode

    def fail_first_episode(**kwargs):
        if kwargs["episode_index"] == 0:
            raise RuntimeError("simulated interruption")
        return original_run_episode(**kwargs)

    monkeypatch.setattr(experiment2, "_run_episode", fail_first_episode)
    with pytest.raises(RuntimeError, match="checkpointed"):
        _run(data_path, output_dir, resume=False)

    resumed_episode_indexes: list[int] = []

    def track_resumed_episode(**kwargs):
        resumed_episode_indexes.append(kwargs["episode_index"])
        return original_run_episode(**kwargs)

    monkeypatch.setattr(experiment2, "_run_episode", track_resumed_episode)
    rows = _run(data_path, output_dir, resume=True)

    assert resumed_episode_indexes == [0]
    assert len(rows) == 2
    assert (output_dir / "experiment2_checkpoint.json").exists()
    assert (output_dir / "experiment2_results.partial.csv").exists()
    assert (output_dir / "experiment2_results.partial.csv").read_bytes().startswith(b"\xef\xbb\xbf")
    assert rows[0]["probe_finish_reason"] == "stop"
    assert rows[0]["probe_was_truncated"] is False
    assert [row["cue_strategy"] for row in rows] == ["plus_one", "times_ten"]
    assert rows[0]["scripted_teaching_count"] == 3
    assert rows[0]["rule_held_count"] == 3
    assert rows[0]["teaching_labels"] == "followed_bad_clue|followed_bad_clue|followed_bad_clue"
    assert rows[0]["teaching_response_source_1"] == "scripted"
    assert rows[0]["teaching_finish_reason_1"] == "scripted"
    assert "teaching_label_3" in rows[0]
    assert "teaching_label_4" not in rows[0]


def test_real_provider_is_called_only_for_the_probe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Insert teaching answers locally and send one complete probe request."""
    source_lines = (ROOT / "data" / "math500_prepared_50.jsonl").read_text(
        encoding="utf-8"
    ).splitlines()
    data_path = tmp_path / "examples.jsonl"
    data_path.write_text("\n".join(source_lines[:4]) + "\n", encoding="utf-8")
    output_dir = tmp_path / "output"
    model_calls: list[list[dict[str, str]]] = []

    def fake_call_model_result(provider, messages, model, temperature, max_tokens):
        model_calls.append(messages)
        return experiment2.ModelResponse(content="Final answer: 0", finish_reason="stop")

    monkeypatch.setattr(experiment2, "call_model_result", fake_call_model_result)
    rows = experiment2.run_experiment2_experiment(
        data_path=data_path,
        dataset_name="math500",
        output_dir=output_dir,
        provider="test-provider",
        model="test-model",
        temperature=0.2,
        max_tokens=64,
        reasoning_modes=["off"],
        cue_counts=[1],
        max_workers=1,
        story_pool_path=ROOT / "data" / "story_pool.jsonl",
        resume=False,
    )

    assert len(model_calls) == 1
    assert [message["role"] for message in model_calls[0]] == [
        "system",
        "user",
        "assistant",
        "user",
        "assistant",
        "user",
        "assistant",
        "user",
    ]
    assert [
        message["content"] for message in model_calls[0] if message["role"] == "assistant"
    ] == [rows[0][f"teaching_response_{index}"] for index in range(1, 4)]

    events = [
        json.loads(line)
        for line in (output_dir / "model_prompts.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert [event["sent_to_model"] for event in events] == [False, False, False, True]
    assert [event["response_source"] for event in events] == [
        "scripted",
        "scripted",
        "scripted",
        "model",
    ]

    grouped = json.loads(
        (output_dir / "model_prompts_by_episode.jsonl").read_text(encoding="utf-8").strip()
    )
    assert grouped["episode_index"] == 0
    assert [turn["turn_type"] for turn in grouped["turns"]] == [
        "teaching",
        "teaching",
        "teaching",
        "probe",
    ]
    assert [turn["sent_to_model"] for turn in grouped["turns"]] == [False, False, False, True]
    assert len(grouped["probe_request_messages"]) == 8


def test_resume_rejects_changed_configuration(tmp_path: Path) -> None:
    """Adopt legacy rows once, then reject changed model settings."""
    source_lines = (ROOT / "data" / "math500_prepared_50.jsonl").read_text(encoding="utf-8").splitlines()
    data_path = tmp_path / "examples.jsonl"
    data_path.write_text("\n".join(source_lines[:4]) + "\n", encoding="utf-8")
    output_dir = tmp_path / "output"
    _run(data_path, output_dir, resume=False)
    (output_dir / "experiment2_checkpoint.json").unlink()

    with pytest.raises(ValueError, match="--adopt-checkpoint"):
        _run(data_path, output_dir, resume=True)

    rows = _run(data_path, output_dir, resume=True, adopt_legacy_checkpoint=True)
    assert len(rows) == 1

    with pytest.raises(ValueError, match="model"):
        _run(data_path, output_dir, resume=True, model="different-model")


def _run(
    data_path: Path,
    output_dir: Path,
    resume: bool,
    model: str = "checkpoint-test-model",
    adopt_legacy_checkpoint: bool = False,
) -> list[dict]:
    """Run a small deterministic checkpoint scenario."""
    return experiment2.run_experiment2_experiment(
        data_path=data_path,
        dataset_name="math500",
        output_dir=output_dir,
        provider="dryrun",
        model=model,
        temperature=0.2,
        max_tokens=64,
        reasoning_modes=["off"],
        cue_counts=[1],
        max_workers=1,
        story_pool_path=ROOT / "data" / "story_pool.jsonl",
        resume=resume,
        adopt_legacy_checkpoint=adopt_legacy_checkpoint,
    )
