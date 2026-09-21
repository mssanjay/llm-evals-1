"""Checkpoint and resume coverage for the live-history experiment."""

from __future__ import annotations

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
    data_path.write_text("\n".join(source_lines[:6]) + "\n", encoding="utf-8")
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


def test_resume_rejects_changed_configuration(tmp_path: Path) -> None:
    """Adopt legacy rows once, then reject changed model settings."""
    source_lines = (ROOT / "data" / "math500_prepared_50.jsonl").read_text(encoding="utf-8").splitlines()
    data_path = tmp_path / "examples.jsonl"
    data_path.write_text("\n".join(source_lines[:5]) + "\n", encoding="utf-8")
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
