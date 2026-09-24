"""Coverage for reasoning controls and completion metadata."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cue_eval.experiment2 import _system_prompt
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
