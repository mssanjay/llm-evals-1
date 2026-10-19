"""Create one simple Markdown walkthrough with three experiment examples."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cue_eval.experiment import TEACHING_TURNS


DEFAULT_CUE_COUNTS = (3, 5, 10)
PROMPT_LOG_FILENAME = "model_prompts_by_episode.jsonl"
DOC_FILENAME = "experiment_walkthrough.md"


def parse_args() -> argparse.Namespace:
    """Collect the completed experiment output folder."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "experiment_output_dir",
        type=Path,
        help=f"Folder containing {PROMPT_LOG_FILENAME}.",
    )
    return parser.parse_args()


def load_episodes(path: Path) -> list[dict[str, Any]]:
    """Read one complete episode from each JSONL line."""
    if not path.exists():
        raise FileNotFoundError(path)
    episodes: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue
            try:
                episodes.append(json.loads(line))
            except json.JSONDecodeError as error:
                raise ValueError(f"Invalid JSON at {path}:{line_number}") from error
    return episodes


def episode_key(episode: dict[str, Any]) -> tuple[str, int, int, str]:
    """Identify the episode shared by both reasoning modes."""
    return (
        str(episode["condition"]),
        int(episode["cue_count"]),
        int(episode["episode_index"]),
        str(episode["probe_id"]),
    )


def probe_turn(episode: dict[str, Any]) -> dict[str, Any]:
    """Return the episode's single model-generated probe turn."""
    probes = [turn for turn in episode["turns"] if turn["turn_type"] == "probe"]
    if len(probes) != 1:
        raise ValueError(f"Expected one probe for episode {episode_key(episode)}.")
    return probes[0]


def pair_episodes(
    episodes: list[dict[str, Any]],
) -> list[dict[str, dict[str, Any]]]:
    """Pair matching reasoning-off and reasoning-on episodes."""
    grouped: dict[tuple[str, int, int, str], dict[str, dict[str, Any]]] = {}
    for episode in episodes:
        reasoning = str(episode.get("reasoning"))
        if reasoning not in {"off", "on"}:
            continue
        key = episode_key(episode)
        modes = grouped.setdefault(key, {})
        if reasoning in modes:
            raise ValueError(f"Duplicate episode {key} reasoning={reasoning}.")
        modes[reasoning] = episode
    return [modes for modes in grouped.values() if set(modes) == {"off", "on"}]


def select_examples(
    episodes: list[dict[str, Any]], cue_counts: list[int]
) -> list[dict[str, dict[str, Any]]]:
    """Select one informative reasoning pair for each cue count."""
    pairs = pair_episodes(episodes)
    selected: list[dict[str, dict[str, Any]]] = []
    used_probe_ids: set[str] = set()
    for cue_count in cue_counts:
        candidates = [
            pair for pair in pairs if int(pair["off"]["cue_count"]) == cue_count
        ]
        candidates.sort(
            key=lambda pair: (
                not _reasoning_helped(pair),
                pair["off"]["condition"] != "assistant_wrong",
                int(pair["off"]["episode_index"]),
            )
        )
        unique = [
            pair for pair in candidates if str(pair["off"]["probe_id"]) not in used_probe_ids
        ]
        if not unique:
            raise ValueError(f"No paired example found for cue_count={cue_count}.")
        chosen = unique[0]
        validate_episode(chosen["off"])
        validate_episode(chosen["on"])
        selected.append(chosen)
        used_probe_ids.add(str(chosen["off"]["probe_id"]))
    return selected


def validate_episode(episode: dict[str, Any]) -> None:
    """Confirm the expected three-teaching-turn and probe structure."""
    actual = [turn.get("turn_type") for turn in episode.get("turns", [])]
    expected = ["teaching"] * TEACHING_TURNS + ["probe"]
    if actual != expected:
        raise ValueError(f"Unexpected turn structure for episode {episode_key(episode)}.")
    for turn in episode["turns"][:TEACHING_TURNS]:
        if turn.get("sent_to_model") is not False or turn.get("response_source") != "scripted":
            raise ValueError(f"Teaching turn is not scripted for {episode_key(episode)}.")


def render_walkthrough(
    examples: list[dict[str, dict[str, Any]]], source_path: Path
) -> str:
    """Render the experiment flow and three examples as Markdown."""
    lines = [
        "# Experiment Walkthrough",
        "",
        "## Purpose",
        "",
        "This experiment tests whether repeated wrong-answer cues in a story influence a model's final math answer. Each episode compares reasoning off with reasoning on.",
        "",
        "The three teaching responses are predetermined and inserted locally. Only the final probe is sent to the model for a new response.",
        "",
        "## Step-by-Step Flow",
        "",
        "1. Select three teaching problems and one held-out probe problem.",
        "2. Assign one wrong-answer strategy to the episode.",
        "3. Render each story with the requested number of shortcut cues.",
        "4. Insert a predetermined assistant answer after each teaching problem.",
        "5. Build a conversation history from the three teaching turns.",
        "6. Add the held-out probe problem to that history.",
        "7. Ask the model for the probe answer with reasoning off and reasoning on.",
        "8. Label each probe as correct, shortcut-following, another wrong answer, or invalid.",
        "",
        "## Three Examples",
        "",
        f"Source: `{source_path.as_posix()}`",
        "",
    ]
    for index, pair in enumerate(examples, start=1):
        lines.extend(_render_example(index, pair))
    return "\n".join(lines).rstrip() + "\n"


def _render_example(
    index: int, pair: dict[str, dict[str, Any]]
) -> list[str]:
    """Render one shared teaching history and its two probe outcomes."""
    off = pair["off"]
    on = pair["on"]
    off_probe = probe_turn(off)
    on_probe = probe_turn(on)
    lines = [
        f"### Example {index}: Cue Count {off['cue_count']}",
        "",
        "| Field | Value |",
        "| --- | --- |",
        f"| Model | `{off['model']}` |",
        f"| Condition | `{off['condition']}` |",
        f"| Cue strategy | `{off['cue_strategy']}` |",
        f"| Probe ID | `{off['probe_id']}` |",
        "",
        "#### Scripted Teaching History",
        "",
    ]
    for turn in off["turns"][:TEACHING_TURNS]:
        lines.extend(
            [
                f"**Teaching turn {turn['turn']}**",
                "",
                "User:",
                "",
                _fence(str(turn["user_message"])),
                "",
                "Predetermined assistant response:",
                "",
                _fence(str(turn["assistant_response"])),
                "",
            ]
        )

    lines.extend(
        [
            "#### Final Probe",
            "",
            "User:",
            "",
            _fence(str(off_probe["user_message"])),
            "",
            "| Reasoning | Answer | Correct answer | Shortcut answer | Label | Took shortcut |",
            "| --- | ---: | ---: | ---: | --- | --- |",
            _probe_summary_row("Off", off_probe),
            _probe_summary_row("On", on_probe),
            "",
            "**Reasoning off response**",
            "",
            _fence(str(off_probe["assistant_response"])),
            "",
            "**Reasoning on response**",
            "",
            _fence(str(on_probe["assistant_response"])),
            "",
            f"**What this example shows:** {_interpretation(off_probe, on_probe)}",
            "",
        ]
    )
    return lines


def _probe_summary_row(reasoning: str, probe: dict[str, Any]) -> str:
    """Render one compact probe comparison row."""
    shortcut = "Yes" if bool(probe.get("took_shortcut")) else "No"
    return (
        f"| {reasoning} | {probe.get('parsed_answer')} | {probe.get('correct_answer')} | "
        f"{probe.get('shortcut_answer')} | {probe.get('label')} | {shortcut} |"
    )


def _reasoning_helped(pair: dict[str, dict[str, Any]]) -> bool:
    """Return whether reasoning stopped shortcut following."""
    return bool(probe_turn(pair["off"]).get("took_shortcut")) and not bool(
        probe_turn(pair["on"]).get("took_shortcut")
    )


def _interpretation(off_probe: dict[str, Any], on_probe: dict[str, Any]) -> str:
    """Explain the paired outcome in one sentence."""
    off_shortcut = bool(off_probe.get("took_shortcut"))
    on_shortcut = bool(on_probe.get("took_shortcut"))
    if off_shortcut and not on_shortcut:
        return "reasoning prevented the model from following the planted shortcut."
    if off_shortcut and on_shortcut:
        return "the model followed the planted shortcut in both reasoning modes."
    if not off_shortcut and on_shortcut:
        return "only the reasoning-on response followed the planted shortcut."
    return "the model avoided the planted shortcut in both reasoning modes."


def _fence(text: str) -> str:
    """Wrap plain text in a Markdown fence."""
    return f"```text\n{text}\n```"


def main() -> None:
    """Create the single walkthrough document."""
    args = parse_args()
    output_dir = args.experiment_output_dir
    prompt_log = output_dir / PROMPT_LOG_FILENAME
    output_path = output_dir / DOC_FILENAME
    episodes = load_episodes(prompt_log)
    examples = select_examples(episodes, list(DEFAULT_CUE_COUNTS))
    markdown = render_walkthrough(examples, prompt_log)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown, encoding="utf-8")
    print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
