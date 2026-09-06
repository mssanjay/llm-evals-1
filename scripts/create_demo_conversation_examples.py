"""Create upload-ready full conversation examples for the demo.

The source prompt log stores each request exactly as sent to the model.
Teaching responses are recovered from the following request's history.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "outputs" / "experiment_2_bedrock"
PROMPT_LOG = SOURCE_DIR / "model_prompts.jsonl"
RESULTS_CSV = SOURCE_DIR / "all_experiment2_results.csv"
DATA_OUT = ROOT / "data" / "demo_conversation_examples.json"
JSONL_OUT = ROOT / "data" / "demo_conversation_examples.jsonl"
DOC_OUT = ROOT / "docs" / "demo_conversation_examples.md"
BANNED_MODEL_PROMPT_SCAFFOLD = (
    "Teaching story turn",
    "Practice problem:",
    "Final probe story.",
    "Probe problem:",
    "Use what you learned from the earlier turns if it seems helpful.",
)

# Three paired episodes with complete recorded outputs in both reasoning modes.
SELECTED_EPISODES = [
    {"slug": "cue_3_math500_0057", "cue_count": 3, "probe_id": "math500_0057"},
    {"slug": "cue_5_math500_0058", "cue_count": 5, "probe_id": "math500_0058"},
    {"slug": "cue_10_math500_0057", "cue_count": 10, "probe_id": "math500_0057"},
]


def load_results() -> list[dict[str, str]]:
    """Read row-level experiment results."""

    with RESULTS_CSV.open(newline="", encoding="utf-8") as csv_file:
        return list(csv.DictReader(csv_file))


def load_prompt_log() -> list[dict[str, Any]]:
    """Read exact model request payloads from JSONL."""

    entries: list[dict[str, Any]] = []
    with PROMPT_LOG.open(encoding="utf-8") as log_file:
        for line in log_file:
            entries.append(json.loads(line))
    return entries


def find_result_row(
    rows: list[dict[str, str]], *, cue_count: int, probe_id: str, reasoning: str
) -> dict[str, str]:
    """Find the result row for one reasoning mode of one episode."""

    matches = [
        row
        for row in rows
        if row["reasoning"] == reasoning
        and int(row["cue_count"]) == cue_count
        and row["probe_id"] == probe_id
    ]
    if len(matches) != 1:
        raise ValueError(
            f"Expected one row for cue_count={cue_count}, probe_id={probe_id}, "
            f"reasoning={reasoning}; found {len(matches)}"
        )
    return matches[0]


def find_prompt_entry(
    entries: list[dict[str, Any]],
    *,
    reasoning: str,
    cue_count: int,
    episode_index: int,
    turn_type: str,
    turn_index: int,
) -> dict[str, Any]:
    """Find one exact request payload from the prompt log."""

    matches = [
        entry
        for entry in entries
        if entry["reasoning"] == reasoning
        and int(entry["cue_count"]) == cue_count
        and int(entry["episode_index"]) == episode_index
        and entry["turn_type"] == turn_type
        and int(entry["turn_index"]) == turn_index
    ]
    if len(matches) != 1:
        raise ValueError(
            f"Expected one prompt for {reasoning=} {cue_count=} "
            f"{episode_index=} {turn_type=} {turn_index=}; found {len(matches)}"
        )
    return matches[0]


def response_from_next_request(
    current_entry: dict[str, Any], next_entry: dict[str, Any]
) -> str:
    """Recover a teaching response from the next request's chat history."""

    current_len = len(current_entry["messages"])
    next_messages = next_entry["messages"]
    if len(next_messages) <= current_len or next_messages[current_len]["role"] != "assistant":
        raise ValueError("Next request does not contain the expected assistant reply.")
    return next_messages[current_len]["content"]


def build_mode_example(
    row: dict[str, str], prompt_entries: list[dict[str, Any]]
) -> dict[str, Any]:
    """Build all five requests and responses for one reasoning mode."""

    reasoning = row["reasoning"]
    cue_count = int(row["cue_count"])
    episode_index = int(row["episode_index"])

    entries = [
        find_prompt_entry(
            prompt_entries,
            reasoning=reasoning,
            cue_count=cue_count,
            episode_index=episode_index,
            turn_type="teaching",
            turn_index=index,
        )
        for index in range(1, 5)
    ]
    entries.append(
        find_prompt_entry(
            prompt_entries,
            reasoning=reasoning,
            cue_count=cue_count,
            episode_index=episode_index,
            turn_type="probe",
            turn_index=0,
        )
    )

    teaching_labels = [row[f"teaching_label_{index}"] for index in range(1, 5)]
    teaching_answers = [row[f"teaching_answer_{index}"] for index in range(1, 5)]

    turns: list[dict[str, Any]] = []
    for index in range(4):
        turns.append(
            {
                "turn": index + 1,
                "turn_type": "teaching",
                "example_id": entries[index]["example_id"],
                "model_input": {"messages": entries[index]["messages"]},
                "model_output": {
                    "content": response_from_next_request(entries[index], entries[index + 1]),
                    "parsed_answer": teaching_answers[index],
                    "label": teaching_labels[index],
                },
            }
        )

    turns.append(
        {
            "turn": 5,
            "turn_type": "probe",
            "example_id": entries[-1]["example_id"],
            "model_input": {"messages": entries[-1]["messages"]},
            "model_output": {
                "content": row["probe_response"],
                "parsed_answer": row["probe_answer"],
                "label": row["probe_label"],
                "took_shortcut": row["probe_took_shortcut"] == "True",
                "is_correct": row["probe_is_correct"] == "True",
            },
        }
    )

    return {
        "reasoning": reasoning,
        "provider": entries[0]["provider"],
        "model": entries[0]["model"],
        "dataset": row["dataset"],
        "cue_count": cue_count,
        "episode_index": episode_index,
        "probe_id": row["probe_id"],
        "summary": {
            "rule_held_count": int(row["rule_held_count"]),
            "probe_label": row["probe_label"],
            "probe_answer": row["probe_answer"],
            "probe_correct_answer": row["probe_correct_answer"],
            "probe_shortcut_answer": row["probe_shortcut_answer"],
            "probe_took_shortcut": row["probe_took_shortcut"] == "True",
            "probe_is_correct": row["probe_is_correct"] == "True",
        },
        "turns": turns,
    }


def build_examples() -> list[dict[str, Any]]:
    """Build the three paired reasoning-on/off examples."""

    rows = load_results()
    prompt_entries = load_prompt_log()
    examples: list[dict[str, Any]] = []

    for selected in SELECTED_EPISODES:
        modes = {}
        for reasoning in ("off", "on"):
            row = find_result_row(
                rows,
                cue_count=selected["cue_count"],
                probe_id=selected["probe_id"],
                reasoning=reasoning,
            )
            modes[reasoning] = build_mode_example(row, prompt_entries)

        examples.append(
            {
                "id": selected["slug"],
                "cue_count": selected["cue_count"],
                "probe_id": selected["probe_id"],
                "reasoning_modes": modes,
            }
        )

    return examples


def validate_model_inputs(examples: list[dict[str, Any]]) -> None:
    """Fail fast if source logs still contain model-facing scaffold labels."""

    matches: list[str] = []
    banned_lower = [phrase.lower() for phrase in BANNED_MODEL_PROMPT_SCAFFOLD]
    for example in examples:
        for reasoning, mode in example["reasoning_modes"].items():
            for turn in mode["turns"]:
                for message in turn["model_input"]["messages"]:
                    content = message.get("content", "")
                    content_lower = content.lower()
                    for phrase, phrase_lower in zip(BANNED_MODEL_PROMPT_SCAFFOLD, banned_lower):
                        if phrase_lower in content_lower:
                            matches.append(
                                f"{example['id']} reasoning={reasoning} "
                                f"turn={turn['turn']} phrase={phrase!r}"
                            )
                            break

    if matches:
        sample = "\n".join(f"- {match}" for match in matches[:5])
        raise ValueError(
            "The selected source logs still contain model-facing scaffold labels. "
            "Rerun Experiment 2 with the cleaned prompt code before generating "
            f"upload examples.\n{sample}"
        )


def fence_text(text: str) -> str:
    """Wrap text for Markdown without breaking on backticks in content."""

    return f"```text\n{text}\n```"


def write_json_files(examples: list[dict[str, Any]]) -> None:
    """Write machine-readable upload artifacts."""

    payload = {
        "schema_version": "1.0",
        "description": (
            "Three full Experiment 2 conversation examples. Each reasoning mode "
            "contains every request the model saw and the matching model output."
        ),
        "source": {
            "prompt_log": str(PROMPT_LOG.relative_to(ROOT)),
            "results_csv": str(RESULTS_CSV.relative_to(ROOT)),
        },
        "examples": examples,
    }
    DATA_OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    with JSONL_OUT.open("w", encoding="utf-8") as jsonl_file:
        for example in examples:
            jsonl_file.write(json.dumps(example, ensure_ascii=False) + "\n")


def write_markdown(examples: list[dict[str, Any]]) -> None:
    """Write a GitHub-friendly walkthrough of the same payload."""

    lines = [
        "# Demo Conversation Examples",
        "",
        "These are three full Experiment 2 conversations from the Bedrock run.",
        "Each example includes both reasoning settings and all five model requests.",
        "",
        "Machine-readable files:",
        "",
        "- `data/demo_conversation_examples.json`",
        "- `data/demo_conversation_examples.jsonl`",
        "",
        "Each turn shows:",
        "",
        "- `model_input.messages`: every chat message sent to the model for that call",
        "- `model_output.content`: the model response recorded for that call",
        "- labels and parsed answers used by the scorer",
        "",
    ]

    for example in examples:
        lines.extend(
            [
                f"## {example['id']}",
                "",
                f"- Cue count: {example['cue_count']}",
                f"- Probe ID: `{example['probe_id']}`",
                "",
                "| Reasoning | Probe Label | Probe Answer | Correct Answer | Shortcut Answer | Took Shortcut |",
                "| --- | --- | ---: | ---: | ---: | --- |",
            ]
        )
        for reasoning, mode in example["reasoning_modes"].items():
            summary = mode["summary"]
            shortcut = "yes" if summary["probe_took_shortcut"] else "no"
            lines.append(
                f"| {reasoning} | {summary['probe_label']} | {summary['probe_answer']} | "
                f"{summary['probe_correct_answer']} | {summary['probe_shortcut_answer']} | {shortcut} |"
            )
        lines.append("")

        for reasoning, mode in example["reasoning_modes"].items():
            lines.extend(
                [
                    f"### Reasoning {reasoning.title()}",
                    "",
                    f"- Provider/model: `{mode['provider']}` / `{mode['model']}`",
                    f"- Episode index: `{mode['episode_index']}`",
                    f"- Teaching rule held count: {mode['summary']['rule_held_count']} of 4",
                    "",
                ]
            )
            for turn in mode["turns"]:
                output = turn["model_output"]
                label = output["label"]
                parsed = output["parsed_answer"]
                lines.extend(
                    [
                        f"<details><summary>Turn {turn['turn']} - {turn['turn_type']} - {label} - parsed {parsed}</summary>",
                        "",
                        "Model input messages:",
                        "",
                        fence_text(json.dumps(turn["model_input"]["messages"], indent=2, ensure_ascii=False)),
                        "",
                        "Model output:",
                        "",
                        fence_text(output["content"]),
                        "",
                        "</details>",
                        "",
                    ]
                )

    DOC_OUT.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    """Create all demo files."""

    examples = build_examples()
    validate_model_inputs(examples)
    write_json_files(examples)
    write_markdown(examples)
    print(f"Wrote {DATA_OUT.relative_to(ROOT)}")
    print(f"Wrote {JSONL_OUT.relative_to(ROOT)}")
    print(f"Wrote {DOC_OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
