"""Coverage for reasoning controls and completion metadata."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cue_eval.experiment2 import _system_prompt, rescore_experiment2_rows
from cue_eval.providers import ModelResponse, _chat_completion_result
from cue_eval.scoring import extract_final_number


def test_qwen_reasoning_modes_use_explicit_switches() -> None:
    """Carry Qwen3's mode switch in every request's system message."""
    assert _system_prompt("off", "qwen.qwen3-32b").endswith("/no_think")
    assert _system_prompt("on", "qwen/qwen3-32b").endswith("/think")
    assert "/no_think" not in _system_prompt("off", "anthropic.claude")


def test_chat_completion_preserves_finish_reason_and_usage() -> None:
    """Keep the fields needed to identify token-limited responses."""
    result = _chat_completion_result(
        {
            "choices": [
                {
                    "message": {"content": "unfinished"},
                    "finish_reason": "length",
                }
            ],
            "usage": {
                "prompt_tokens": 120,
                "completion_tokens": 256,
                "total_tokens": 376,
            },
        },
        "test provider",
    )

    assert result == ModelResponse("unfinished", "length", 120, 256, 376)
    assert result.was_truncated is True


def test_strict_scoring_rejects_missing_or_truncated_final_answer() -> None:
    """Do not score an incidental number from an incomplete derivation."""
    incomplete = "Since the product is -1, continue with a ="

    assert extract_final_number(incomplete) == -1
    assert extract_final_number(incomplete, require_final=True) is None
    assert extract_final_number(
        "Final answer: 3",
        require_final=True,
        finish_reason="length",
    ) is None
    assert extract_final_number(
        "Final answer: 3",
        require_final=True,
        finish_reason="stop",
    ) == 3


def test_strict_scoring_accepts_common_final_answer_formatting() -> None:
    """Accept Markdown and LaTeX wrappers attached to the final-answer heading."""
    responses = [
        "Final answer: 4",
        r"Final answer: \boxed{4}",
        "### Final Answer:\n$$\n\\boxed{4}\n$$",
        "### ✅ Final Answer:\n\n$\\boxed{4}$",
        "### Final Answer:\n$$\n\\text{Final answer: } 4\n$$",
        "Thus:\n$$\n\\text{Final answer: } 4\n$$",
        "### Final Answer\n$$\n\\boxed{\\text{Final answer: } 4}\n$$",
        "**Final answer:** 4",
    ]

    for response in responses:
        assert extract_final_number(response, require_final=True, finish_reason="stop") == 4

    assert extract_final_number(
        r"Final answer: \boxed{4}",
        require_final=True,
        finish_reason="length",
    ) is None


def test_rescore_updates_stored_probe_labels() -> None:
    """Recover a formatted completed answer without accepting truncation."""
    rows = [
        {
            "probe_response": "### Final Answer:\n$$\n\\boxed{4}\n$$",
            "probe_finish_reason": "stop",
            "probe_correct_answer": "4",
            "probe_shortcut_answer": "5",
            "probe_answer": "",
            "probe_label": "parse_fail",
            "probe_took_shortcut": "False",
            "probe_is_correct": "False",
        },
        {
            "probe_response": r"Final answer: \boxed{4}",
            "probe_finish_reason": "length",
            "probe_correct_answer": "4",
            "probe_shortcut_answer": "5",
            "probe_answer": "",
            "probe_label": "parse_fail",
            "probe_took_shortcut": "False",
            "probe_is_correct": "False",
        },
    ]

    rescored = rescore_experiment2_rows(rows)

    assert rescored[0]["probe_answer"] == 4
    assert rescored[0]["probe_label"] == "correct"
    assert rescored[0]["probe_is_correct"] is True
    assert rescored[1]["probe_label"] == "parse_fail"
