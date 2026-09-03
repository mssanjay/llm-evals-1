"""Load and render story templates for cue injection."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


PLACEHOLDER = "{wrong_answer_shortcut_cue}"


def load_story_pool(path: str | Path | None) -> dict[int, list[dict[str, Any]]]:
    """Load story templates grouped by cue count."""
    if not path:
        return {}

    pool: dict[int, list[dict[str, Any]]] = {}
    with Path(path).open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            cue_count = int(row["cue_count"])
            story = row["story"]
            actual_count = story.count(PLACEHOLDER)
            if actual_count != cue_count:
                raise ValueError(
                    f"Story pool line {line_number} has cue_count={cue_count} "
                    f"but {actual_count} placeholders."
                )
            pool.setdefault(cue_count, []).append(row)
    return pool


def choose_story_template(
    story_pool: dict[int, list[dict[str, Any]]],
    cue_count: int,
    example_index: int,
) -> str | None:
    """Pick a story template for this cue count, cycling through variants."""
    stories = story_pool.get(cue_count, [])
    if not stories:
        return None
    return stories[example_index % len(stories)]["story"]


def render_story(story_template: str, wrong_answer_shortcut_cue: str) -> str:
    """Replace cue placeholders with the row-specific wrong-answer cue."""
    return story_template.replace(PLACEHOLDER, wrong_answer_shortcut_cue.rstrip("."))
