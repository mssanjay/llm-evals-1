"""Parse final numeric answers from model responses."""

from __future__ import annotations

import re


NUMBER_EXPRESSION = r"-?\d+(?:,\d{3})*(?:\.\d+)?"
NUMBER_PATTERN = re.compile(NUMBER_EXPRESSION)
FINAL_PATTERN = re.compile(
    rf"""
    final\s+answer\s*:
    [\s*_]*
    (?:\${{1,2}}\s*|\\\(\s*|\\\[\s*)?
    (?:\\text\s*\{{\s*final\s+answer\s*:\s*\}}\s*)?
    (?:\\boxed\s*\{{\s*)?
    (?P<number>{NUMBER_EXPRESSION})
    """,
    re.IGNORECASE | re.VERBOSE,
)
LATEX_TEXT_FINAL_PATTERN = re.compile(
    rf"\\text\s*\{{\s*final\s+answer\s*:\s*\}}\s*(?P<number>{NUMBER_EXPRESSION})",
    re.IGNORECASE,
)


def extract_final_number(
    text: str | None,
    *,
    require_final: bool = False,
    finish_reason: str | None = None,
) -> float | None:
    """Extract a numeric answer while optionally enforcing the response contract."""
    if not text:
        return None
    if (finish_reason or "").lower() in {"length", "max_tokens"}:
        return None

    final_match = FINAL_PATTERN.search(text) or LATEX_TEXT_FINAL_PATTERN.search(text)
    if final_match:
        return _to_float(final_match.group("number"))
    if require_final:
        return None

    matches = NUMBER_PATTERN.findall(text)
    return _to_float(matches[-1]) if matches else None


def _to_float(raw: str) -> float:
    """Convert a matched number while allowing thousands separators."""
    return float(raw.replace(",", ""))
