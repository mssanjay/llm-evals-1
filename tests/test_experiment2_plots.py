"""Coverage for Experiment 2 plot inputs and story-length diagnostics."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cue_eval.experiment2 import _story_token_counts_by_cue_count


def test_story_token_counts_use_only_rendered_story_text() -> None:
    """Group story tokens by cue count without counting the math problem."""
    rows = [
        {
            "cue_count": 2,
            "teaching_prompt_1": "A cue appears twice.\n\nA very long math problem follows.",
            "probe_prompt": "Another cue story!\n\nMore problem text.",
        },
        {
            "cue_count": 3,
            "probe_prompt": "One, two, three cues.\n\nProblem text.",
        },
    ]

    assert _story_token_counts_by_cue_count(rows) == {2: [5, 4], 3: [7]}
