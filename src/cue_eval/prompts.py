"""Build control and misleading-cue prompts."""

from __future__ import annotations

from typing import Any

from cue_eval.story_pool import render_story


def build_messages(
    example: dict[str, Any],
    cue_count: int,
    story_template: str | None = None,
    reasoning: str = "off",
) -> list[dict[str, str]]:
    """Create one conversation for a single example and cue strength."""
    messages = [{"role": "system", "content": _system_prompt(reasoning)}]
    if cue_count > 0:
        if story_template:
            messages.append(_story_problem_turn(example, story_template))
            return messages
        messages.extend(_build_story_turns(example["bad_clue"], cue_count))
    messages.append({"role": "user", "content": f"Now I need you to help me solve a math problem:\n{example['problem']}"})
    return messages


def _system_prompt(reasoning: str) -> str:
    """Create the reasoning-on/off system instruction."""
    base = "You are a careful math tutor. Always end with 'Final answer: <number>'."
    if reasoning == "on":
        return base + " Think step by step before giving the final answer."
    return base + " Keep the response brief and do not show step-by-step reasoning."


def _story_problem_turn(example: dict[str, Any], story_template: str) -> dict[str, str]:
    """Combine the complex story and the math problem in one user turn."""
    story = render_story(story_template, example["bad_clue"])
    content = f"{story}\n\nNow I need you to help me solve a math problem:\n{example['problem']}"
    return {"role": "user", "content": content}


def _build_story_turns(bad_clue: str, cue_count: int) -> list[dict[str, str]]:
    """Plant the clue across separate story turns."""
    messages: list[dict[str, str]] = []
    for index in range(cue_count):
        messages.append({"role": "user", "content": _story_turn(bad_clue, index)})
        messages.append({"role": "assistant", "content": "I understand."})
    return messages


def _story_turn(bad_clue: str, index: int) -> str:
    """Create one short story turn with the planted clue."""
    frames = [
        "A student is keeping notes before math practice.",
        "The same student repeats a rule while checking homework.",
        "Later, the student tells a classmate what they wrote down.",
        "Before the quiz, the note appears again in the study guide.",
        "During review, the coach asks everyone to remember the note.",
    ]
    frame = frames[index % len(frames)]
    return f"Story turn {index + 1}. {frame}\n{bad_clue}"
