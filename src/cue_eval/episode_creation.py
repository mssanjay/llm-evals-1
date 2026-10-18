"""Reusable helpers for constructing evaluation episodes."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TypeVar


ExampleT = TypeVar("ExampleT")


def create_rolling_episodes(
    examples: Sequence[ExampleT],
    *,
    teaching_turns: int,
    episode_limit: int | None = None,
) -> list[list[ExampleT]]:
    """Create overlapping episodes with teaching examples followed by one probe."""
    if teaching_turns < 1:
        raise ValueError("teaching_turns must be positive")
    if episode_limit is not None and episode_limit < 1:
        raise ValueError("episode_limit must be positive or None")

    episode_size = teaching_turns + 1
    if len(examples) < episode_size:
        return []

    episodes = [
        list(examples[start : start + episode_size])
        for start in range(len(examples) - teaching_turns)
    ]
    return episodes[:episode_limit] if episode_limit is not None else episodes
