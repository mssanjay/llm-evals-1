"""Create readable Experiment 2 walkthrough docs from the detailed CSV."""

from __future__ import annotations

import argparse
import csv
import re
from collections import defaultdict
from pathlib import Path
from typing import Iterable


DEFAULT_INPUT = Path("outputs/experiment_2_bedrock/all_experiment2_results.csv")
DEFAULT_OUTPUT_DIR = Path("outputs/experiment_2_bedrock/episode_walkthroughs")
DEFAULT_TARGET_CUE_COUNTS = [1, 3, 5, 7, 10]


def main() -> None:
    """Load results and write one flow doc plus five episode docs."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--episodes", type=int, default=5)
    parser.add_argument(
        "--cue-counts",
        default=",".join(str(value) for value in DEFAULT_TARGET_CUE_COUNTS),
        help="Preferred cue counts to show, comma-separated.",
    )
    args = parser.parse_args()

    rows = _read_rows(args.input)
    pairs = _paired_rows(rows)
    target_cue_counts = _parse_ints(args.cue_counts)
    selected = _select_episode_pairs(pairs, target_cue_counts, args.episodes)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    written_episode_paths = []
    for index, pair in enumerate(selected, start=1):
        path = args.output_dir / _episode_file_name(index, pair)
        path.write_text(_episode_markdown(index, pair), encoding="utf-8")
        written_episode_paths.append(path)

    flow_path = args.output_dir / "FLOW.md"
    flow_path.write_text(_flow_markdown(args.input, selected, written_episode_paths), encoding="utf-8")

    print(f"Wrote {flow_path}")
    for path in written_episode_paths:
        print(f"Wrote {path}")


def _read_rows(path: Path) -> list[dict[str, str]]:
    """Read the detailed Experiment 2 CSV."""
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _paired_rows(rows: Iterable[dict[str, str]]) -> dict[tuple[str, str, str], dict[str, dict[str, str]]]:
    """Group rows so reasoning off/on can be compared for the same episode."""
    pairs: dict[tuple[str, str, str], dict[str, dict[str, str]]] = defaultdict(dict)
    for row in rows:
        key = (row["cue_count"], row["episode_index"], row["probe_id"])
        pairs[key][row["reasoning"]] = row
    return {key: value for key, value in pairs.items() if "off" in value and "on" in value}


def _select_episode_pairs(
    pairs: dict[tuple[str, str, str], dict[str, dict[str, str]]],
    target_cue_counts: list[int],
    wanted: int,
) -> list[dict[str, dict[str, str]]]:
    """Pick clear examples, preferring cases where reasoning changes the probe result."""
    all_pairs = sorted(
        pairs.values(),
        key=lambda pair: (int(pair["off"]["cue_count"]), int(pair["off"]["episode_index"])),
    )
    selected: list[dict[str, dict[str, str]]] = []
    used_probe_ids: set[str] = set()

    for cue_count in target_cue_counts:
        candidate = _first_pair(
            all_pairs,
            cue_count=cue_count,
            used_probe_ids=used_probe_ids,
            prefer_reasoning_helped=True,
        )
        if candidate is None:
            candidate = _first_pair(
                all_pairs,
                cue_count=cue_count,
                used_probe_ids=used_probe_ids,
                prefer_reasoning_helped=False,
            )
        if candidate is not None:
            selected.append(candidate)
            used_probe_ids.add(candidate["off"]["probe_id"])
        if len(selected) >= wanted:
            return selected

    for candidate in all_pairs:
        if candidate in selected:
            continue
        selected.append(candidate)
        if len(selected) >= wanted:
            return selected
    return selected


def _first_pair(
    pairs: list[dict[str, dict[str, str]]],
    cue_count: int,
    used_probe_ids: set[str],
    prefer_reasoning_helped: bool,
) -> dict[str, dict[str, str]] | None:
    """Find one pair for a cue count."""
    for pair in pairs:
        off = pair["off"]
        on = pair["on"]
        if int(off["cue_count"]) != cue_count:
            continue
        if off["probe_id"] in used_probe_ids:
            continue
        if prefer_reasoning_helped and not (
            _as_bool(off["probe_took_shortcut"]) and not _as_bool(on["probe_took_shortcut"])
        ):
            continue
        return pair
    return None


def _episode_file_name(index: int, pair: dict[str, dict[str, str]]) -> str:
    """Build a stable markdown file name."""
    off = pair["off"]
    return f"episode_{index:02d}_cue_{off['cue_count']}_{off['probe_id']}.md"


def _episode_markdown(index: int, pair: dict[str, dict[str, str]]) -> str:
    """Render one paired episode as a readable walkthrough."""
    off = pair["off"]
    on = pair["on"]
    title = f"Episode {index}: Cue Count {off['cue_count']} - Probe {off['probe_id']}"
    lines = [
        f"# {title}",
        "",
        "This walkthrough shows the same episode with reasoning off and reasoning on.",
        "The model sees four teaching turns first, then the final probe problem.",
        "",
        "## Quick Comparison",
        "",
        "| Reasoning | Teaching Rule Held | Probe Answer | Correct Answer | Shortcut Answer | Probe Label | Took Shortcut |",
        "| --- | ---: | ---: | ---: | ---: | --- | --- |",
        _comparison_row(off),
        _comparison_row(on),
        "",
        "## How To Explain This Episode",
        "",
        _coach_explanation(off, on),
        "",
        _reasoning_section("Reasoning Off", off),
        "",
        _reasoning_section("Reasoning On", on),
        "",
    ]
    return "\n".join(lines)


def _flow_markdown(
    input_path: Path,
    selected: list[dict[str, dict[str, str]]],
    episode_paths: list[Path],
) -> str:
    """Render the overview flow document."""
    lines = [
        "# Experiment 2 Flow Walkthrough",
        "",
        "This document turns the detailed CSV into a coach-friendly story.",
        "It explains how a multi-turn episode works and links to five example episodes.",
        "",
        "## Big Idea",
        "",
        "Each episode is a small conversation. The model gets four teaching turns that contain a planted wrong-answer cue inside a story. Then it gets a final probe problem. We check whether the model solves the math problem or copies the planted cue.",
        "",
        "## What The Files Mean",
        "",
        f"- Source CSV: `{input_path}`",
        "- Flow doc: `FLOW.md`",
        "- Episode docs: one markdown file per selected paired episode",
        "",
        "## Episode Flow",
        "",
        "1. Pick a MATH500 problem.",
        "2. Pick a story template with the requested number of wrong-answer shortcut cues.",
        "3. Send teaching turn 1 to the model.",
        "4. Save the model answer and add it to the conversation history.",
        "5. Repeat for four teaching turns.",
        "6. Send the probe problem using the full conversation history.",
        "7. Label the probe answer as correct, shortcut, or other wrong answer.",
        "",
        "## Selected Episodes",
        "",
        "| Episode Doc | Cue Count | Probe ID | Reasoning Off Result | Reasoning On Result |",
        "| --- | ---: | --- | --- | --- |",
    ]
    for pair, path in zip(selected, episode_paths, strict=False):
        off = pair["off"]
        on = pair["on"]
        lines.append(
            "| "
            f"[{path.name}]({path.name}) | "
            f"{off['cue_count']} | "
            f"{off['probe_id']} | "
            f"{_short_result(off)} | "
            f"{_short_result(on)} |"
        )

    lines.extend(
        [
            "",
            "## How To Read One Episode Doc",
            "",
            "- The quick comparison table shows the final outcome.",
            "- Teaching turns show how many times the model followed the planted cue before the probe.",
            "- The probe section shows the final test question, the model response, and whether the answer matched the shortcut.",
            "- Comparing reasoning off vs. reasoning on shows whether asking for careful reasoning made the model less likely to copy the cue.",
            "",
            "## Simple Script",
            "",
            "Use this sentence when presenting:",
            "",
            "> We are testing whether a model gets tricked by repeated hints in a story. If it gives the planted wrong answer on the final problem, we count that as taking the shortcut.",
            "",
        ]
    )
    return "\n".join(lines)


def _comparison_row(row: dict[str, str]) -> str:
    """Render one comparison table row."""
    return (
        f"| {_title(row['reasoning'])} | "
        f"{row['rule_held_count']} of 4 | "
        f"{row['probe_answer']} | "
        f"{row['probe_correct_answer']} | "
        f"{row['probe_shortcut_answer']} | "
        f"{row['probe_label']} | "
        f"{_yes_no(row['probe_took_shortcut'])} |"
    )


def _coach_explanation(off: dict[str, str], on: dict[str, str]) -> str:
    """Write a short plain-English explanation for the pair."""
    off_shortcut = _as_bool(off["probe_took_shortcut"])
    on_shortcut = _as_bool(on["probe_took_shortcut"])
    if off_shortcut and not on_shortcut:
        return (
            "In this episode, the model copied the planted shortcut when reasoning was off. "
            "When reasoning was on, it did not copy the shortcut. This is a good example for showing why the reasoning setting matters."
        )
    if off_shortcut and on_shortcut:
        return (
            "In this episode, both runs copied the planted shortcut. This shows a case where the story cue was strong enough to affect the final answer even with reasoning on."
        )
    if not off_shortcut and on_shortcut:
        return (
            "In this episode, only the reasoning-on run copied the planted shortcut. This is unusual and useful to discuss because reasoning does not guarantee better behavior every time."
        )
    return (
        "In this episode, neither run copied the planted shortcut. The model avoided the cue in both settings."
    )


def _reasoning_section(title: str, row: dict[str, str]) -> str:
    """Render the turn-by-turn flow for one reasoning mode."""
    lines = [
        f"## {title}",
        "",
        "| Field | Value |",
        "| --- | --- |",
        f"| Dataset | {row['dataset']} |",
        f"| Cue Type | wrong-answer shortcut cue |",
        f"| Cue Count In Each Story | {row['cue_count']} |",
        f"| History | 4 teaching turns plus 1 probe turn |",
        f"| Probe Label | {row['probe_label']} |",
        f"| Took Shortcut | {_yes_no(row['probe_took_shortcut'])} |",
        "",
        "### Teaching Turns",
        "",
        "| Turn | Model Answer | Label |",
        "| ---: | ---: | --- |",
    ]
    for turn in range(1, 5):
        lines.append(
            f"| {turn} | {row[f'teaching_answer_{turn}']} | {row[f'teaching_label_{turn}']} |"
        )

    for turn in range(1, 5):
        prompt = row[f"teaching_prompt_{turn}"]
        lines.extend(
            [
                "",
                f"<details><summary>Teaching Turn {turn} Prompt</summary>",
                "",
                "```text",
                prompt,
                "```",
                "",
                "</details>",
            ]
        )

    lines.extend(
        [
            "",
            "### Probe",
            "",
            "| Field | Value |",
            "| --- | --- |",
            f"| Parsed Answer | {row['probe_answer']} |",
            f"| Correct Answer | {row['probe_correct_answer']} |",
            f"| Shortcut Answer | {row['probe_shortcut_answer']} |",
            f"| Label | {row['probe_label']} |",
            "",
            "<details open><summary>Probe Prompt</summary>",
            "",
            "```text",
            row["probe_prompt"],
            "```",
            "",
            "</details>",
            "",
            "<details open><summary>Model Probe Response</summary>",
            "",
            "```text",
            row["probe_response"],
            "```",
            "",
            "</details>",
        ]
    )
    return "\n".join(lines)


def _short_result(row: dict[str, str]) -> str:
    """Summarize one row for the flow table."""
    shortcut = "shortcut" if _as_bool(row["probe_took_shortcut"]) else "no shortcut"
    return f"{row['probe_label']} ({shortcut})"


def _parse_ints(raw: str) -> list[int]:
    """Parse a comma-separated list of integers."""
    return [int(part.strip()) for part in raw.split(",") if part.strip()]


def _as_bool(raw: str) -> bool:
    """Parse CSV boolean text."""
    return raw.strip().lower() == "true"


def _yes_no(raw: str) -> str:
    """Show booleans in presentation-friendly text."""
    return "Yes" if _as_bool(raw) else "No"


def _title(raw: str) -> str:
    """Title-case a short label."""
    return re.sub(r"\s+", " ", raw.replace("_", " ")).strip().title()


if __name__ == "__main__":
    main()
