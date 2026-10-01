"""Token usage and model-cost summaries for experiment runs."""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable


TOKENS_PER_MILLION = Decimal("1000000")


@dataclass(frozen=True)
class TokenPricing:
    """Store input and output prices in USD per million tokens."""

    input_per_million_usd: Decimal
    output_per_million_usd: Decimal
    source: str


DEFAULT_TOKEN_PRICING = {
    # Standard on-demand rate verified from AWS pricing on 2026-10-01.
    ("aws", "qwen.qwen3-32b"): TokenPricing(
        input_per_million_usd=Decimal("0.15"),
        output_per_million_usd=Decimal("0.60"),
        source="Amazon Bedrock standard on-demand pricing, verified 2026-10-01",
    ),
    ("aws", "qwen.qwen3-32b-v1:0"): TokenPricing(
        input_per_million_usd=Decimal("0.15"),
        output_per_million_usd=Decimal("0.60"),
        source="Amazon Bedrock standard on-demand pricing, verified 2026-10-01",
    ),
}


def resolve_token_pricing(
    provider: str,
    model: str,
    input_cost_per_million: Decimal | float | str | None = None,
    output_cost_per_million: Decimal | float | str | None = None,
) -> TokenPricing | None:
    """Resolve an explicit rate pair or a known provider/model default."""
    if (input_cost_per_million is None) != (output_cost_per_million is None):
        raise ValueError(
            "Set both input_cost_per_million and output_cost_per_million, or neither."
        )
    if input_cost_per_million is None:
        return DEFAULT_TOKEN_PRICING.get((provider.lower(), model.lower()))

    input_rate = _decimal_rate(input_cost_per_million, "input")
    output_rate = _decimal_rate(output_cost_per_million, "output")
    return TokenPricing(input_rate, output_rate, "command-line override")


def summarize_usage(
    rows: Iterable[dict[str, Any]],
    input_token_field: str,
    output_token_field: str,
    provider: str,
    model: str,
    pricing: TokenPricing | None,
) -> dict[str, Any]:
    """Aggregate token counts and estimate cost for one experiment run."""
    row_list = list(rows)
    input_tokens = sum(_token_count(row.get(input_token_field)) for row in row_list)
    output_tokens = sum(_token_count(row.get(output_token_field)) for row in row_list)
    calls_with_usage = sum(
        row.get(input_token_field) not in {None, ""}
        and row.get(output_token_field) not in {None, ""}
        for row in row_list
    )

    summary: dict[str, Any] = {
        "provider": provider,
        "model": model,
        "model_calls": len(row_list),
        "calls_with_usage": calls_with_usage,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "estimated_input_cost_usd": None,
        "estimated_output_cost_usd": None,
        "estimated_cost_usd": None,
        "input_cost_per_million_usd": None,
        "output_cost_per_million_usd": None,
        "pricing_source": None,
    }
    if pricing is None:
        return summary

    input_cost = Decimal(input_tokens) * pricing.input_per_million_usd / TOKENS_PER_MILLION
    output_cost = Decimal(output_tokens) * pricing.output_per_million_usd / TOKENS_PER_MILLION
    estimated_cost = input_cost + output_cost
    summary.update(
        {
            "estimated_input_cost_usd": float(input_cost),
            "estimated_output_cost_usd": float(output_cost),
            "estimated_cost_usd": float(estimated_cost),
            "input_cost_per_million_usd": float(pricing.input_per_million_usd),
            "output_cost_per_million_usd": float(pricing.output_per_million_usd),
            "pricing_source": pricing.source,
        }
    )
    return summary


def write_usage_summary(path: str | Path, summary: dict[str, Any]) -> None:
    """Write an auditable JSON summary for the completed or partial run."""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")


def format_usage_summary(summary: dict[str, Any]) -> str:
    """Format one concise token and cost log line."""
    cost = summary["estimated_cost_usd"]
    cost_text = (
        "unavailable (set both token-price options)" if cost is None else f"${cost:.6f}"
    )
    return (
        f"Run usage: input_tokens={summary['input_tokens']} "
        f"output_tokens={summary['output_tokens']} total_tokens={summary['total_tokens']} "
        f"estimated_cost_usd={cost_text} calls_with_usage="
        f"{summary['calls_with_usage']}/{summary['model_calls']}"
    )


def _decimal_rate(value: Decimal | float | str | None, label: str) -> Decimal:
    """Convert and validate one non-negative token rate."""
    try:
        rate = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise ValueError(f"Invalid {label} token price: {value!r}") from error
    if not rate.is_finite() or rate < 0:
        raise ValueError(
            f"{label.capitalize()} token price must be a finite non-negative number."
        )
    return rate


def _token_count(value: Any) -> int:
    """Convert a CSV or in-memory token value to a safe count."""
    if value in {None, ""}:
        return 0
    count = int(value)
    if count < 0:
        raise ValueError(f"Token count cannot be negative: {count}")
    return count
