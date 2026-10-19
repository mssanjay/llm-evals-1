"""Coverage for Experiment 1 plot inputs and story-length diagnostics."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import cue_eval.output_writer as output_writer
from cue_eval.output_writer import sample_size_label, story_token_counts_by_cue_count


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

    assert story_token_counts_by_cue_count(rows) == {2: [5, 4], 3: [7]}


def test_sample_size_label_keeps_total_episode_count_visible() -> None:
    """Distinguish the full condition size from valid parsed responses."""
    assert sample_size_label({"n": 45, "total_n": 45}) == "N=45"
    assert sample_size_label({"n": 42, "total_n": 45}) == "N=45\nvalid=42"


def test_combined_outputs_group_models_and_write_one_graph_set(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Keep model series separate in the combined report."""
    rows = [
        {
            "dataset": "math500",
            "model": model,
            "condition": "assistant_wrong",
            "reasoning": "off",
            "cue_count": 1,
            "probe_label": label,
            "rule_held_count": 3,
        }
        for model, label in (("qwen", "correct"), ("deepseek", "followed_bad_clue"))
    ]
    graph_names: list[str] = []

    def record_graph(path, *args, **kwargs) -> None:
        graph_names.append(path.name)

    monkeypatch.setattr(output_writer, "_write_cue_count_plot", record_graph)
    monkeypatch.setattr(output_writer, "_write_response_category_plot", record_graph)
    monkeypatch.setattr(output_writer, "_write_story_token_count_plot", record_graph)

    summary = output_writer.write_combined_experiment_outputs(tmp_path, rows)

    assert {row["model"] for row in summary} == {"qwen", "deepseek"}
    assert (tmp_path / "combined_experiment_summary.csv").exists()
    assert set(graph_names) == {
        "combined_shortcut_count_by_cue_count.png",
        "combined_shortcut_rate.png",
        "combined_response_categories_stacked.png",
        "combined_story_token_count_by_cue_count.png",
    }
