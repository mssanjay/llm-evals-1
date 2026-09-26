"""Create demo conversations from grouped Experiment 2 episode logs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cue_eval.experiment2 import TEACHING_TURNS


DEFAULT_OUTPUT_DIR = ROOT / "outputs" / "experiment_2_bedrock_run4"
DEFAULT_CUE_COUNTS = (3, 5, 10)
GROUPED_PROMPT_LOG = "model_prompts_by_episode.jsonl"
DATA_FILENAME = "demo_conversation_examples.json"
JSONL_FILENAME = "demo_conversation_examples.jsonl"
DOC_FILENAME = "demo_conversation_examples.md"

BANNED_MODEL_PROMPT_SCAFFOLD = (
    "Teaching story turn",
    "Practice problem:",
    "Final probe story.",
    "Probe problem:",
    "Use what you learned from the earlier turns if it seems helpful.",
)


def parse_args() -> argparse.Namespace:
    """Parse output-folder and example-selection arguments."""

    parser = argparse.ArgumentParser(
        description="Create demo conversations from grouped Experiment 2 logs."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Experiment 2 output folder containing model_prompts_by_episode.jsonl.",
    )
    parser.add_argument(
        "--cue-counts",
        type=int,
        nargs="+",
        default=list(DEFAULT_CUE_COUNTS),
        help="Cue counts to include. One paired reasoning example is selected per count.",
    )
    return parser.parse_args()


def load_grouped_episodes(prompt_log: Path) -> list[dict[str, Any]]:
    """Read one complete episode per JSONL line."""

    episodes: list[dict[str, Any]] = []
    with prompt_log.open(encoding="utf-8") as log_file:
        for line_number, line in enumerate(log_file, start=1):
            if not line.strip():
                continue
            try:
                episodes.append(json.loads(line))
            except json.JSONDecodeError as error:
                raise ValueError(
                    f"Invalid JSON in {prompt_log} at line {line_number}: {error}"
                ) from error
    return episodes


def episode_key(episode: dict[str, Any]) -> tuple[int, int, str]:
    """Return the fields shared by reasoning-on and reasoning-off episodes."""

    return (
        int(episode["cue_count"]),
        int(episode["episode_index"]),
        str(episode["probe_id"]),
    )


def probe_turn(episode: dict[str, Any]) -> dict[str, Any]:
    """Return the single probe turn from an episode."""

    probes = [turn for turn in episode["turns"] if turn["turn_type"] == "probe"]
    if len(probes) != 1:
        raise ValueError(
            f"Expected one probe for {episode_key(episode)} reasoning={episode['reasoning']}; "
            f"found {len(probes)}"
        )
    return probes[0]


def pair_episodes(
    episodes: list[dict[str, Any]],
) -> dict[tuple[int, int, str], dict[str, dict[str, Any]]]:
    """Pair complete episodes by reasoning mode."""

    pairs: dict[tuple[int, int, str], dict[str, dict[str, Any]]] = {}
    for episode in episodes:
        reasoning = str(episode["reasoning"])
        if reasoning not in {"off", "on"}:
            continue
        key = episode_key(episode)
        if reasoning in pairs.setdefault(key, {}):
            raise ValueError(f"Duplicate grouped episode for {key} reasoning={reasoning}")
        pairs[key][reasoning] = episode
    return pairs


def select_episode_pairs(
    episodes: list[dict[str, Any]], cue_counts: list[int]
) -> list[tuple[tuple[int, int, str], dict[str, dict[str, Any]]]]:
    """Select one informative, stable reasoning pair for each cue count."""

    complete_pairs = [
        (key, modes)
        for key, modes in pair_episodes(episodes).items()
        if set(modes) == {"off", "on"}
    ]
    complete_pairs.sort(key=lambda item: item[0])

    selected: list[tuple[tuple[int, int, str], dict[str, dict[str, Any]]]] = []
    used_probe_ids: set[str] = set()
    for cue_count in cue_counts:
        candidates = [item for item in complete_pairs if item[0][0] == cue_count]
        if not candidates:
            raise ValueError(f"No complete reasoning pair found for cue_count={cue_count}")

        # Prefer examples where reasoning changes shortcut-following behavior.
        informative = [
            item
            for item in candidates
            if bool(probe_turn(item[1]["off"]).get("took_shortcut"))
            and not bool(probe_turn(item[1]["on"]).get("took_shortcut"))
        ]
        pool = informative or candidates
        unique = [item for item in pool if item[0][2] not in used_probe_ids]
        chosen = (unique or pool)[0]
        selected.append(chosen)
        used_probe_ids.add(chosen[0][2])

    return selected


def validate_episode(episode: dict[str, Any]) -> None:
    """Validate the three-scripted-turn plus one-probe structure."""

    turns = episode.get("turns", [])
    expected_types = ["teaching"] * TEACHING_TURNS + ["probe"]
    actual_types = [turn.get("turn_type") for turn in turns]
    if actual_types != expected_types:
        raise ValueError(
            f"Unexpected turn structure for {episode_key(episode)} "
            f"reasoning={episode['reasoning']}: {actual_types}"
        )

    for expected_turn, turn in enumerate(turns[:TEACHING_TURNS], start=1):
        if int(turn.get("turn", 0)) != expected_turn:
            raise ValueError(f"Teaching turn number mismatch in {episode_key(episode)}")
        if turn.get("sent_to_model") is not False:
            raise ValueError(f"Teaching turn was marked as sent in {episode_key(episode)}")
        if turn.get("response_source") != "scripted":
            raise ValueError(f"Teaching response is not scripted in {episode_key(episode)}")

    request_messages = episode.get("probe_request_messages", [])
    expected_roles = [
        "system",
        "user",
        "assistant",
        "user",
        "assistant",
        "user",
        "assistant",
        "user",
    ]
    actual_roles = [message.get("role") for message in request_messages]
    if actual_roles != expected_roles:
        raise ValueError(
            f"Unexpected probe request roles for {episode_key(episode)}: {actual_roles}"
        )


def build_mode_example(episode: dict[str, Any]) -> dict[str, Any]:
    """Build one reasoning mode without treating scripted turns as model calls."""

    validate_episode(episode)
    turns: list[dict[str, Any]] = []
    optional_fields = (
        "parsed_answer",
        "correct_answer",
        "shortcut_answer",
        "label",
        "took_shortcut",
        "is_correct",
        "finish_reason",
        "was_truncated",
    )
    for source_turn in episode["turns"]:
        turn = {
            "turn": int(source_turn["turn"]),
            "turn_type": source_turn["turn_type"],
            "turn_index": int(source_turn["turn_index"]),
            "example_id": source_turn["example_id"],
            "sent_to_model": bool(source_turn["sent_to_model"]),
            "response_source": source_turn["response_source"],
            "user_message": source_turn["user_message"],
            "assistant_response": source_turn["assistant_response"],
        }
        for field in optional_fields:
            if field in source_turn:
                turn[field] = source_turn[field]
        turns.append(turn)

    probe = turns[-1]
    return {
        "reasoning": episode["reasoning"],
        "provider": episode["provider"],
        "model": episode["model"],
        "dataset": episode["dataset"],
        "cue_count": int(episode["cue_count"]),
        "cue_strategy": episode["cue_strategy"],
        "episode_index": int(episode["episode_index"]),
        "episode_number": int(episode["episode_number"]),
        "total_episodes": int(episode["total_episodes"]),
        "probe_id": episode["probe_id"],
        "summary": {
            "scripted_teaching_count": TEACHING_TURNS,
            "probe_label": probe.get("label"),
            "probe_answer": probe.get("parsed_answer"),
            "probe_correct_answer": probe.get("correct_answer"),
            "probe_shortcut_answer": probe.get("shortcut_answer"),
            "probe_took_shortcut": bool(probe.get("took_shortcut")),
            "probe_is_correct": bool(probe.get("is_correct")),
        },
        "turns": turns,
        "probe_request_messages": episode["probe_request_messages"],
    }


def build_examples(
    episodes: list[dict[str, Any]], cue_counts: list[int]
) -> list[dict[str, Any]]:
    """Build paired reasoning examples for the requested cue counts."""

    examples: list[dict[str, Any]] = []
    for key, modes in select_episode_pairs(episodes, cue_counts):
        cue_count, episode_index, probe_id = key
        examples.append(
            {
                "id": f"cue_{cue_count}_episode_{episode_index}_{probe_id}",
                "cue_count": cue_count,
                "episode_index": episode_index,
                "probe_id": probe_id,
                "reasoning_modes": {
                    reasoning: build_mode_example(modes[reasoning])
                    for reasoning in ("off", "on")
                },
            }
        )
    return examples


def validate_model_inputs(examples: list[dict[str, Any]]) -> None:
    """Fail if an exact probe request contains old model-facing scaffold text."""

    matches: list[str] = []
    for example in examples:
        for reasoning, mode in example["reasoning_modes"].items():
            for message in mode["probe_request_messages"]:
                content = str(message.get("content", "")).lower()
                for phrase in BANNED_MODEL_PROMPT_SCAFFOLD:
                    if phrase.lower() in content:
                        matches.append(
                            f"{example['id']} reasoning={reasoning} phrase={phrase!r}"
                        )
                        break

    if matches:
        sample = "\n".join(f"- {match}" for match in matches[:5])
        raise ValueError(
            "The selected probe requests contain old scaffold labels. Rerun "
            f"Experiment 2 with cleaned prompts.\n{sample}"
        )


def fence_text(text: str) -> str:
    """Wrap text in a Markdown code fence."""

    return f"```text\n{text}\n```"


def relative_display(path: Path) -> str:
    """Return a repository-relative path when possible."""

    try:
        return str(path.resolve().relative_to(ROOT.resolve()))
    except ValueError:
        return str(path.resolve())


def write_json_files(
    examples: list[dict[str, Any]], output_dir: Path, prompt_log: Path
) -> tuple[Path, Path]:
    """Write JSON and JSONL demo artifacts."""

    data_out = output_dir / DATA_FILENAME
    jsonl_out = output_dir / JSONL_FILENAME
    payload = {
        "schema_version": "2.0",
        "description": (
            "Experiment 2 examples with three predetermined assistant responses "
            "followed by one model-generated probe response."
        ),
        "source": {"grouped_prompt_log": relative_display(prompt_log)},
        "examples": examples,
    }
    data_out.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    with jsonl_out.open("w", encoding="utf-8") as jsonl_file:
        for example in examples:
            jsonl_file.write(json.dumps(example, ensure_ascii=False) + "\n")
    return data_out, jsonl_out


def write_markdown(examples: list[dict[str, Any]], output_dir: Path) -> Path:
    """Write a readable walkthrough that distinguishes scripted and model turns."""

    doc_out = output_dir / DOC_FILENAME
    lines = [
        "# Demo Conversation Examples",
        "",
        "Each conversation contains three teaching turns and one probe. The teaching "
        "assistant responses were predetermined and inserted into the history locally; "
        "they were not generated by the model. Only the final probe requested a model response.",
        "",
        "Machine-readable files:",
        "",
        f"- `{DATA_FILENAME}`",
        f"- `{JSONL_FILENAME}`",
        "",
    ]

    for example in examples:
        first_mode = next(iter(example["reasoning_modes"].values()))
        lines.extend(
            [
                f"## {example['id']}",
                "",
                f"- Cue count: {example['cue_count']}",
                f"- Cue strategy: `{first_mode['cue_strategy']}`",
                f"- Episode index: `{example['episode_index']}`",
                f"- Probe ID: `{example['probe_id']}`",
                "",
                "| Reasoning | Probe label | Probe answer | Correct answer | Shortcut answer | Took shortcut |",
                "| --- | --- | ---: | ---: | ---: | --- |",
            ]
        )
        for reasoning, mode in example["reasoning_modes"].items():
            summary = mode["summary"]
            took_shortcut = "yes" if summary["probe_took_shortcut"] else "no"
            lines.append(
                f"| {reasoning} | {summary['probe_label']} | {summary['probe_answer']} | "
                f"{summary['probe_correct_answer']} | {summary['probe_shortcut_answer']} | "
                f"{took_shortcut} |"
            )
        lines.append("")

        for reasoning, mode in example["reasoning_modes"].items():
            probe = mode["turns"][-1]
            lines.extend(
                [
                    f"### Reasoning {reasoning.title()}",
                    "",
                    f"- Provider/model: `{mode['provider']}` / `{mode['model']}`",
                    f"- Scripted teaching turns: {TEACHING_TURNS}",
                    f"- Probe sent to model: {'yes' if probe['sent_to_model'] else 'no'}",
                    "",
                ]
            )
            for turn in mode["turns"][:TEACHING_TURNS]:
                lines.extend(
                    [
                        f"<details><summary>Turn {turn['turn']} - scripted teaching - "
                        f"{turn.get('label')}</summary>",
                        "",
                        "User message:",
                        "",
                        fence_text(turn["user_message"]),
                        "",
                        "Predetermined assistant response (inserted locally; no model call):",
                        "",
                        fence_text(turn["assistant_response"]),
                        "",
                        "</details>",
                        "",
                    ]
                )

            lines.extend(
                [
                    f"<details open><summary>Turn {probe['turn']} - model-generated probe - "
                    f"{probe.get('label')}</summary>",
                    "",
                    "Exact request messages sent to the model:",
                    "",
                    fence_text(
                        json.dumps(
                            mode["probe_request_messages"], indent=2, ensure_ascii=False
                        )
                    ),
                    "",
                    "Model-generated assistant response:",
                    "",
                    fence_text(probe["assistant_response"]),
                    "",
                    "</details>",
                    "",
                ]
            )

    doc_out.write_text("\n".join(lines), encoding="utf-8")
    return doc_out


def main() -> None:
    """Create all demo files."""

    args = parse_args()
    output_dir = args.output_dir.resolve()
    prompt_log = output_dir / GROUPED_PROMPT_LOG
    episodes = load_grouped_episodes(prompt_log)
    examples = build_examples(episodes, args.cue_counts)
    validate_model_inputs(examples)
    data_out, jsonl_out = write_json_files(examples, output_dir, prompt_log)
    doc_out = write_markdown(examples, output_dir)
    for path in (data_out, jsonl_out, doc_out):
        print(f"Wrote {relative_display(path)}")


if __name__ == "__main__":
    main()
