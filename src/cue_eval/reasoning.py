"""Model-specific controls for reasoning experiment conditions."""

from __future__ import annotations


def qwen_thinking_switch(model: str, reasoning: str) -> str:
    """Return Qwen3's explicit thinking-mode command when applicable."""
    if "qwen3" not in model.lower():
        return ""
    return "/think" if reasoning == "on" else "/no_think"


def add_qwen_thinking_switch(prompt: str, model: str, reasoning: str) -> str:
    """Append the Qwen3 switch so every request carries the selected mode."""
    switch = qwen_thinking_switch(model, reasoning)
    return f"{prompt}\n{switch}" if switch else prompt
