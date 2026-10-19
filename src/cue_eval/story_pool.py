"""Load and render story templates for cue injection."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Sequence


PLACEHOLDER = "{wrong_answer_shortcut_cue}"
MIN_STORY_WORDS = 60
MAX_STORY_WORDS = 100
MIN_STORY_POOL_SIZE = 50


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
            word_count = len(story.split())
            if not MIN_STORY_WORDS <= word_count <= MAX_STORY_WORDS:
                raise ValueError(
                    f"Story pool line {line_number} has {word_count} words; "
                    f"expected {MIN_STORY_WORDS}-{MAX_STORY_WORDS}."
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


def choose_story(
    story_pool: dict[int, list[dict[str, Any]]],
    cue_count: int,
    example_index: int,
) -> dict[str, Any] | None:
    """Pick the complete story record so its ID can be audited."""
    stories = story_pool.get(cue_count, [])
    if not stories:
        return None
    return stories[example_index % len(stories)]


def validate_story_pool(
    story_pool: dict[int, list[dict[str, Any]]],
    cue_counts: Sequence[int],
    turns_per_episode: int,
) -> None:
    """Enforce the minimum pool and unique-story episode requirements."""
    total_stories = sum(len(stories) for stories in story_pool.values())
    if total_stories < MIN_STORY_POOL_SIZE:
        raise ValueError(
            f"Story pool has {total_stories} stories; expected at least {MIN_STORY_POOL_SIZE}."
        )
    for cue_count in cue_counts:
        stories = story_pool.get(cue_count, [])
        if len(stories) < turns_per_episode:
            raise ValueError(
                f"cue_count={cue_count} has {len(stories)} stories; "
                f"expected at least {turns_per_episode} to avoid repeats within an episode."
            )
        story_ids = [str(story.get("id", "")) for story in stories]
        if any(not story_id for story_id in story_ids) or len(story_ids) != len(set(story_ids)):
            raise ValueError(f"cue_count={cue_count} must have unique, non-empty story IDs.")


def render_story(
    story_template: str,
    wrong_answer_shortcut_cue: str | Sequence[str],
) -> str:
    """Replace placeholders with one cue or a sequence of cue paraphrases."""
    placeholder_count = story_template.count(PLACEHOLDER)
    if isinstance(wrong_answer_shortcut_cue, str):
        cues = [wrong_answer_shortcut_cue] * placeholder_count
    else:
        cues = list(wrong_answer_shortcut_cue)
        if len(cues) < placeholder_count:
            raise ValueError(
                f"Story needs {placeholder_count} cue phrases, but only {len(cues)} were provided."
            )

    story = story_template
    for cue in cues[:placeholder_count]:
        story = story.replace(PLACEHOLDER, cue.rstrip("."), 1)
    return story
