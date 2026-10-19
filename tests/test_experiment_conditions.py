"""Coverage for teaching conditions and the shared experiment manifest."""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import cue_eval.experiment as experiment
from cue_eval.cue_strategies import apply_cue_strategy, strategy_for_episode
from cue_eval.data import load_examples
from cue_eval.episode_creation import create_rolling_episodes
from cue_eval.story_pool import PLACEHOLDER, load_story_pool
from cue_eval.usage import resolve_token_pricing


def test_teaching_conditions_change_only_the_teaching_answer() -> None:
    """Keep the probe cue wrong while making Condition 2 teaching correct."""
    source = {"id": "example", "problem": "What is 7 + 5?", "correct_answer": 12.0}
    example = apply_cue_strategy(source, "plus_one")
    template = f"A note said {PLACEHOLDER}."

    wrong_prompt = experiment._teaching_prompt(
        example,
        1,
        template,
        story_answer=experiment._teaching_story_answer(example, "assistant_wrong"),
    )
    correct_prompt = experiment._teaching_prompt(
        example,
        1,
        template,
        story_answer=experiment._teaching_story_answer(example, "assistant_correct"),
    )
    probe_prompt = experiment._probe_prompt(example, template)

    assert "13" in wrong_prompt
    assert experiment._scripted_teaching_response(example, "assistant_wrong").content.endswith("13.0")
    assert "12" in correct_prompt
    assert experiment._scripted_teaching_response(example, "assistant_correct").content.endswith("12.0")
    assert "13" in probe_prompt
    assert example["shortcut_answer"] != example["correct_answer"]


def test_manifest_freezes_45_balanced_probes_without_story_repeats() -> None:
    """Use one auditable manifest for every model, condition, and reasoning cell."""
    data_path = ROOT / "data" / "math500_prepared_50.jsonl"
    story_path = ROOT / "data" / "story_pool.jsonl"
    episodes = create_rolling_episodes(
        load_examples(data_path),
        teaching_turns=experiment.TEACHING_TURNS,
        episode_limit=45,
    )
    manifest = experiment._build_episode_manifest(
        episodes=episodes,
        cue_counts=[1, 2, 3],
        story_pool=load_story_pool(story_path),
        data_path=data_path,
        story_pool_path=story_path,
    )

    assert manifest["episode_count"] == 45
    assert Counter(row["shortcut_cue_type"] for row in manifest["episodes"]) == {
        "plus_one": 15,
        "times_ten": 15,
        "random": 15,
    }
    assert len({row["probe_id"] for row in manifest["episodes"]}) == 45
    for row in manifest["episodes"]:
        for story_ids in row["story_ids_by_cue_count"].values():
            assert len(story_ids) == 4
            assert len(set(story_ids)) == 4


def test_subexperiment_costs_are_grouped_by_condition_and_reasoning() -> None:
    """Report token cost separately for every 45-episode experiment cell."""
    rows = []
    for condition in experiment.CONDITIONS:
        for reasoning in ("off", "on"):
            rows.append(
                {
                    "provider": "custom",
                    "model": "model",
                    "dataset": "math500",
                    "condition": condition,
                    "reasoning": reasoning,
                    "cue_count": 2,
                    "shortcut_cue_type": "plus_one",
                    "probe_prompt_tokens": 100,
                    "probe_completion_tokens": 20,
                }
            )
    pricing = resolve_token_pricing("custom", "model", "1.0", "2.0")

    summaries = experiment.summarize_usage_by_subexperiment(rows, pricing)

    assert len(summaries) == 4
    assert all(row["episodes"] == 1 for row in summaries)
    assert all(row["estimated_cost_usd"] == 0.00014 for row in summaries)


def test_reasoning_preflight_compares_the_provider_reasoning_field(monkeypatch) -> None:
    """Use the same problem and require a longer on-mode reasoning field."""
    calls: list[list[dict[str, str]]] = []

    def fake_call(provider, messages, model, temperature, max_tokens):
        calls.append(messages)
        is_on = "Think step by step" in messages[0]["content"]
        return experiment.ModelResponse(
            content="Final answer: 323",
            finish_reason="stop",
            reasoning="Multiply 17 by 19." if is_on else "",
        )

    monkeypatch.setattr(experiment, "call_model_result", fake_call)

    report = experiment.run_reasoning_preflight(
        provider="test-provider",
        model="deepseek-test",
        temperature=0.0,
    )

    assert report["passed"] is True
    assert report["comparison"]["measurement"] == "reasoning_chars"
    assert report["off"]["reasoning_chars"] == 0
    assert report["on"]["reasoning_chars"] > 0
    assert calls[0][1]["content"] == calls[1][1]["content"]


def test_reasoning_preflight_accepts_inline_bedrock_reasoning(monkeypatch) -> None:
    """Accept Qwen reasoning returned inline by Bedrock Mantle."""
    def fake_call(provider, messages, model, temperature, max_tokens):
        is_on = "/think" in messages[0]["content"]
        return experiment.ModelResponse(
            content=(
                "Compute 17 times 20, then subtract 17. Final answer: 323"
                if is_on
                else "Final answer: 323"
            ),
            finish_reason="stop",
            completion_tokens=20 if is_on else 5,
        )

    monkeypatch.setattr(experiment, "call_model_result", fake_call)

    report = experiment.run_reasoning_preflight(
        provider="aws",
        model="qwen.qwen3-32b",
        temperature=0.0,
    )

    assert report["passed"] is True
    assert report["comparison"]["measurement"] == "inline_response_chars"
    assert report["comparison"]["on"] > report["comparison"]["off"]


def test_completed_matrix_requires_matching_45_probe_cells() -> None:
    """Validate all eight model, condition, and reasoning subexperiments."""
    rows = []
    for model in ("qwen", "deepseek"):
        for condition in experiment.CONDITIONS:
            for reasoning in ("off", "on"):
                for episode_index in range(45):
                    rows.append(
                        {
                            "model": model,
                            "condition": condition,
                            "reasoning": reasoning,
                            "cue_count": 1,
                            "episode_index": episode_index,
                            "probe_id": f"probe-{episode_index}",
                            "shortcut_cue_type": strategy_for_episode(episode_index),
                            "episode_manifest_sha256": "same-manifest",
                            "max_tokens": 8192,
                        }
                    )

    report = experiment.validate_completed_matrix(rows)

    assert report["passed"] is True
    assert report["subexperiments"] == 8
    assert report["result_rows"] == 360
