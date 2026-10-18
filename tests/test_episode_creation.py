"""Tests for reusable episode construction."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cue_eval.episode_creation import create_rolling_episodes


def test_create_rolling_episodes_separates_each_probe_by_position() -> None:
    """Advance one example at a time and keep the probe last."""
    episodes = create_rolling_episodes(
        ["a", "b", "c", "d", "e"],
        teaching_turns=2,
    )

    assert episodes == [
        ["a", "b", "c"],
        ["b", "c", "d"],
        ["c", "d", "e"],
    ]


def test_create_rolling_episodes_applies_limit_after_windowing() -> None:
    """Cap complete episodes without changing their contents."""
    episodes = create_rolling_episodes(
        [0, 1, 2, 3, 4],
        teaching_turns=2,
        episode_limit=2,
    )

    assert episodes == [[0, 1, 2], [1, 2, 3]]


@pytest.mark.parametrize(
    ("teaching_turns", "episode_limit", "message"),
    [
        (0, None, "teaching_turns must be positive"),
        (1, 0, "episode_limit must be positive or None"),
    ],
)
def test_create_rolling_episodes_rejects_invalid_counts(
    teaching_turns: int,
    episode_limit: int | None,
    message: str,
) -> None:
    """Reject counts that cannot describe a runnable episode."""
    with pytest.raises(ValueError, match=message):
        create_rolling_episodes(
            [0, 1],
            teaching_turns=teaching_turns,
            episode_limit=episode_limit,
        )


def test_create_rolling_episodes_needs_a_probe_example() -> None:
    """Return no episodes when a full teaching-plus-probe window is unavailable."""
    assert create_rolling_episodes([0, 1], teaching_turns=2) == []
