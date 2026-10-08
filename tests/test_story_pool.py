"""Coverage for rendering story templates with paraphrased cues."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cue_eval.cue_strategies import paraphrase_shortcut_cues
from cue_eval.experiment2 import _story_text
from cue_eval.story_pool import PLACEHOLDER, render_story


def test_render_story_uses_distinct_cue_paraphrases() -> None:
    """Keep the shortcut answer fixed without repeating its sentence verbatim."""
    template = f"First: {PLACEHOLDER}. Second: {PLACEHOLDER}. Third: {PLACEHOLDER}."
    cues = paraphrase_shortcut_cues(17)

    story = render_story(template, cues)

    assert PLACEHOLDER not in story
    assert all(cue in story for cue in cues[:3])
    assert len(set(cues)) == 10


def test_experiment2_story_paraphrases_the_shortcut_cue() -> None:
    """Use paraphrases in Experiment 2 instead of its stored verbatim clue."""
    template = f"One note said {PLACEHOLDER}. Another said {PLACEHOLDER}."
    example = {
        "bad_clue": "Remember this note: a previous student said the answer is 17.",
        "shortcut_answer": 17,
    }

    story = _story_text(example, template)

    assert example["bad_clue"].rstrip(".") not in story
    assert story.count("17") == 2
    assert paraphrase_shortcut_cues(17)[0] in story
    assert paraphrase_shortcut_cues(17)[1] in story


def test_render_story_rejects_too_few_paraphrases() -> None:
    """Fail clearly instead of leaving an unresolved cue placeholder."""
    template = f"{PLACEHOLDER}. {PLACEHOLDER}."

    with pytest.raises(ValueError, match="needs 2 cue phrases"):
        render_story(template, ["the answer was 17"])
