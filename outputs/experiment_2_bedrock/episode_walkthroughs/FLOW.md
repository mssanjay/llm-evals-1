# Experiment 2 Flow Walkthrough

This document turns the detailed CSV into a coach-friendly story.
It explains how a multi-turn episode works and links to five example episodes.

## Big Idea

Each episode is a small conversation. The model gets four teaching turns that contain a planted wrong-answer cue inside a story. Then it gets a final probe problem. We check whether the model solves the math problem or copies the planted cue.

## What The Files Mean

- Source CSV: `outputs\experiment_2_bedrock\all_experiment2_results.csv`
- Flow doc: `FLOW.md`
- Episode docs: one markdown file per selected paired episode

## Episode Flow

1. Pick a MATH500 problem.
2. Pick a story template with the requested number of wrong-answer shortcut cues.
3. Send teaching turn 1 to the model.
4. Save the model answer and add it to the conversation history.
5. Repeat for four teaching turns.
6. Send the probe problem using the full conversation history.
7. Label the probe answer as correct, shortcut, or other wrong answer.

## Selected Episodes

| Episode Doc | Cue Count | Probe ID | Reasoning Off Result | Reasoning On Result |
| --- | ---: | --- | --- | --- |
| [episode_01_cue_1_math500_0012.md](episode_01_cue_1_math500_0012.md) | 1 | math500_0012 | followed_bad_clue (shortcut) | other_wrong_answer (no shortcut) |
| [episode_02_cue_3_math500_0018.md](episode_02_cue_3_math500_0018.md) | 3 | math500_0018 | followed_bad_clue (shortcut) | other_wrong_answer (no shortcut) |
| [episode_03_cue_5_math500_0019.md](episode_03_cue_5_math500_0019.md) | 5 | math500_0019 | followed_bad_clue (shortcut) | other_wrong_answer (no shortcut) |
| [episode_04_cue_7_math500_0022.md](episode_04_cue_7_math500_0022.md) | 7 | math500_0022 | followed_bad_clue (shortcut) | other_wrong_answer (no shortcut) |
| [episode_05_cue_10_math500_0024.md](episode_05_cue_10_math500_0024.md) | 10 | math500_0024 | followed_bad_clue (shortcut) | other_wrong_answer (no shortcut) |

## How To Read One Episode Doc

- The quick comparison table shows the final outcome.
- Teaching turns show how many times the model followed the planted cue before the probe.
- The probe section shows the final test question, the model response, and whether the answer matched the shortcut.
- Comparing reasoning off vs. reasoning on shows whether asking for careful reasoning made the model less likely to copy the cue.

## Simple Script

Use this sentence when presenting:

> We are testing whether a model gets tricked by repeated hints in a story. If it gives the planted wrong answer on the final problem, we count that as taking the shortcut.
