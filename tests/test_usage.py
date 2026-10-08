"""Coverage for deterministic token and run-cost summaries."""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cue_eval.usage import UsageTracker, resolve_token_pricing, summarize_usage


def test_bedrock_qwen_usage_uses_known_standard_rate() -> None:
    """Calculate input and output spend from the provider token counts."""
    pricing = resolve_token_pricing("aws", "qwen.qwen3-32b")
    summary = summarize_usage(
        [
            {"input": "1000000", "output": "500000"},
            {"input": "", "output": ""},
        ],
        "input",
        "output",
        "aws",
        "qwen.qwen3-32b",
        pricing,
    )

    assert summary["input_tokens"] == 1_000_000
    assert summary["output_tokens"] == 500_000
    assert summary["estimated_input_cost_usd"] == pytest.approx(0.15)
    assert summary["estimated_output_cost_usd"] == pytest.approx(0.30)
    assert summary["estimated_cost_usd"] == pytest.approx(0.45)
    assert summary["calls_with_usage"] == 1


def test_pricing_override_requires_both_rates() -> None:
    """Reject partial pricing because it would understate run cost."""
    with pytest.raises(ValueError, match="Set both"):
        resolve_token_pricing("custom", "model", Decimal("1.0"), None)


def test_usage_tracker_accumulates_calls_without_storing_responses() -> None:
    """Support reuse directly in an API request loop."""
    pricing = resolve_token_pricing("custom", "model", "1.00", "2.00")
    tracker = UsageTracker("custom", "model", pricing)

    tracker.record(input_tokens=100, output_tokens=20)
    tracker.record(input_tokens="50", output_tokens="10")
    tracker.record()

    summary = tracker.summary()
    assert summary["model_calls"] == 3
    assert summary["calls_with_usage"] == 2
    assert summary["input_tokens"] == 150
    assert summary["output_tokens"] == 30
    assert summary["estimated_cost_usd"] == pytest.approx(0.00021)


def test_usage_tracker_rejects_negative_counts() -> None:
    """Reject invalid provider usage before it affects totals."""
    tracker = UsageTracker("custom", "model")

    with pytest.raises(ValueError, match="cannot be negative"):
        tracker.record(input_tokens=-1, output_tokens=10)

    assert tracker.summary()["model_calls"] == 0
