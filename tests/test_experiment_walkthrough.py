"""Coverage for the single experiment walkthrough generator."""

from __future__ import annotations

import sys
from pathlib import Path

from scripts import create_experiment_walkthrough as walkthrough


def test_cli_accepts_only_the_experiment_output_folder(monkeypatch) -> None:
    """Use one positional folder with fixed examples and output name."""
    monkeypatch.setattr(
        sys,
        "argv",
        ["create_experiment_walkthrough.py", "outputs/experiment-with-qwen"],
    )

    args = walkthrough.parse_args()

    assert args.experiment_output_dir == Path("outputs/experiment-with-qwen")
    assert vars(args) == {"experiment_output_dir": Path("outputs/experiment-with-qwen")}


def test_walkthrough_shows_three_examples_with_one_shared_history() -> None:
    """Render three paired examples without repeating their teaching histories."""
    episodes = [
        _episode(cue_count, reasoning, took_shortcut=reasoning == "off")
        for cue_count in (3, 5, 10)
        for reasoning in ("off", "on")
    ]

    examples = walkthrough.select_examples(episodes, [3, 5, 10])
    markdown = walkthrough.render_walkthrough(
        examples,
        Path("outputs/run/model_prompts_by_episode.jsonl"),
    )

    assert markdown.count("### Example ") == 3
    assert markdown.count("**Teaching turn ") == 9
    assert markdown.count("**Reasoning off response**") == 3
    assert markdown.count("**Reasoning on response**") == 3
    assert "## Step-by-Step Flow" in markdown


def _episode(cue_count: int, reasoning: str, took_shortcut: bool) -> dict:
    """Build one minimal grouped episode for the walkthrough."""
    teaching_turns = [
        {
            "turn": turn,
            "turn_type": "teaching",
            "sent_to_model": False,
            "response_source": "scripted",
            "user_message": f"Teaching story {turn}",
            "assistant_response": f"Final answer: {turn}",
        }
        for turn in range(1, 4)
    ]
    probe = {
        "turn": 4,
        "turn_type": "probe",
        "sent_to_model": True,
        "response_source": "model",
        "user_message": "Probe story",
        "assistant_response": f"Response with reasoning {reasoning}",
        "parsed_answer": 11 if took_shortcut else 10,
        "correct_answer": 10,
        "shortcut_answer": 11,
        "label": "followed_bad_clue" if took_shortcut else "correct",
        "took_shortcut": took_shortcut,
    }
    return {
        "condition": "assistant_wrong",
        "cue_count": cue_count,
        "episode_index": cue_count,
        "probe_id": f"probe-{cue_count}",
        "reasoning": reasoning,
        "model": "test-model",
        "cue_strategy": "plus_one",
        "turns": teaching_turns + [probe],
    }
