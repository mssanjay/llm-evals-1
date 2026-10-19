"""CLI defaults for the live-history experiment runner."""

from __future__ import annotations

import sys

from scripts import run_experiment


def test_defaults_match_the_bedrock_experiment_command(monkeypatch) -> None:
    """Run the requested Bedrock configuration when no flags are provided."""
    monkeypatch.setattr(sys, "argv", ["run_experiment.py"])

    args = run_experiment.parse_args()

    assert args.provider == "aws"
    assert args.model == "qwen.qwen3-32b"
    assert args.prepared_dir == "data"
    assert args.story_pool == "data/story_pool.jsonl"
    assert args.cue_counts == "1,2,3,4,5,6,7,8,9,10"
    assert args.max_tokens == 8192
    assert args.output_dir == "outputs/experiment_bedrock"
