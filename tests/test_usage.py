"""Coverage for deterministic token and run-cost summaries."""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cue_eval.usage import resolve_token_pricing, summarize_usage


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
