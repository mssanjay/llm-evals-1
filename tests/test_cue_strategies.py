"""Wrong-answer strategy coverage for live-history episodes."""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cue_eval.cue_strategies import apply_cue_strategy, shortcut_answer, strategy_for_episode
from cue_eval.experiment2 import _make_episodes


def test_strategy_transformations_are_wrong_and_reproducible() -> None:
    """Apply all strategies without returning the correct answer."""
    assert shortcut_answer(8, "plus_one", "sample") == 9
    assert shortcut_answer(8, "times_ten", "sample") == 80
    assert shortcut_answer(0, "times_ten", "sample") == 10

    first_random = shortcut_answer(8, "random", "sample")
    assert first_random == shortcut_answer(8, "random", "sample")
    assert first_random not in {8, 9, 80}


def test_one_strategy_is_applied_without_mutating_the_source() -> None:
    """Replace stored cues on a copy of the prepared example."""
    source = {
        "id": "sample",
        "correct_answer": 8,
        "shortcut_answer": 9,
        "bad_clue": "old cue",
    }

    transformed = apply_cue_strategy(source, "times_ten")

    assert transformed["shortcut_answer"] == 80
    assert transformed["cue_strategy"] == "times_ten"
    assert "80" in transformed["bad_clue"]
    assert source["bad_clue"] == "old cue"


def test_45_episodes_balance_strategies_and_use_four_examples() -> None:
    """Create 45 three-teaching-plus-probe episodes with a 15/15/15 split."""
    examples = [{"id": str(index)} for index in range(50)]
    episodes = _make_episodes(examples)
    counts = Counter(strategy_for_episode(index) for index in range(len(episodes)))

    assert len(episodes) == 45
    assert all(len(episode) == 4 for episode in episodes)
    assert counts == {"plus_one": 15, "times_ten": 15, "random": 15}
