"""Coverage for compact, manually readable experiment results."""

from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cue_eval import output_writer


def _result_row() -> dict[str, object]:
    """Build one complete result row for compact-output tests."""
    row: dict[str, object] = {
        "dataset": "math500",
        "model": "qwen.qwen3-32b",
        "condition": "assistant_wrong",
        "reasoning": "off",
        "cue_count": 3,
        "cue_strategy": "plus_one",
        "probe_id": "probe-1",
        "probe_prompt": "Probe question",
        "probe_response": "Final answer: 11",
        "probe_answer": 11,
        "probe_correct_answer": 10,
        "probe_shortcut_answer": 11,
        "probe_label": "followed_bad_clue",
        "probe_was_truncated": False,
        "rule_held_count": 3,
    }
    for index in range(1, 4):
        row[f"teaching_prompt_{index}"] = f"Teaching question {index}"
        row[f"teaching_response_{index}"] = f"Final answer: {index}"
    return row


def test_simplified_rows_combine_the_probe_conversation() -> None:
    """Put all teaching exchanges and the final probe in one ordered cell."""
    simplified = output_writer.simplify_experiment_rows([_result_row()])[0]
    actual_probe = str(simplified["actual_probe"])

    assert list(simplified) == [
        "model",
        "condition",
        "reasoning",
        "cue_count",
        "cue_strategy",
        "probe_id",
        "actual_probe",
        "probe_response",
        "probe_answer",
        "probe_correct_answer",
        "probe_shortcut_answer",
        "probe_label",
        "probe_was_truncated",
    ]
    assert actual_probe.count("TEACHING TURN") == 6
    assert actual_probe.index("Teaching question 1") < actual_probe.index(
        "Teaching question 3"
    )
    assert actual_probe.endswith("FINAL PROBE - USER:\nProbe question")


def test_output_writer_includes_simplified_csv(tmp_path, monkeypatch) -> None:
    """Write the compact file whenever the normal output set is created."""
    monkeypatch.setattr(
        output_writer, "_write_cue_count_plot", lambda *args, **kwargs: None
    )
    monkeypatch.setattr(
        output_writer, "_write_response_category_plot", lambda *args: None
    )
    monkeypatch.setattr(
        output_writer, "_write_story_token_count_plot", lambda *args: None
    )

    output_writer.write_experiment_outputs(tmp_path, [_result_row()])

    path = tmp_path / output_writer.SIMPLIFIED_RESULTS_FILENAME
    with path.open(newline="", encoding="utf-8-sig") as file:
        rows = list(csv.DictReader(file))
    assert len(rows) == 1
    assert rows[0]["actual_probe"].endswith("FINAL PROBE - USER:\nProbe question")
    assert rows[0]["probe_label"] == "followed_bad_clue"
