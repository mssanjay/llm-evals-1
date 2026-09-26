# Experiment 2 Flow Walkthrough

This document turns the detailed CSV into a coach-friendly story.
It explains how a multi-turn episode works and links to five example episodes.

## Big Idea

Each episode is a small conversation. Three predetermined shortcut answers are inserted into its teaching history. Then the model receives the full history and a final probe problem. We check whether it solves the problem or copies the planted cue.

## What The Files Mean

- Source CSV: `outputs\experiment_2_bedrock_run4\all_experiment2_results.csv`
- Flow doc: `FLOW.md`
- Episode docs: one markdown file per selected paired episode

## Episode Flow

1. Pick a MATH500 problem.
2. Assign one wrong-answer strategy to the whole episode.
3. Pick a story template with the requested number of wrong-answer shortcut cues.
4. Add teaching turn 1 and its scripted shortcut answer to the history.
5. Save that predetermined answer in the result record.
6. Repeat for three teaching turns.
7. Send the probe problem using the full history and the same strategy.
8. Label the probe answer as correct, shortcut, or other wrong answer.

## Selected Episodes

| Episode Doc | Cue Count | Probe ID | Reasoning Off Result | Reasoning On Result |
| --- | ---: | --- | --- | --- |
| [episode_01_cue_1_math500_0009.md](episode_01_cue_1_math500_0009.md) | 1 | math500_0009 | followed_bad_clue (shortcut) | other_wrong_answer (no shortcut) |
| [episode_02_cue_2_math500_0012.md](episode_02_cue_2_math500_0012.md) | 2 | math500_0012 | followed_bad_clue (shortcut) | other_wrong_answer (no shortcut) |
| [episode_03_cue_3_math500_0016.md](episode_03_cue_3_math500_0016.md) | 3 | math500_0016 | followed_bad_clue (shortcut) | correct (no shortcut) |
| [episode_04_cue_4_math500_0013.md](episode_04_cue_4_math500_0013.md) | 4 | math500_0013 | followed_bad_clue (shortcut) | correct (no shortcut) |
| [episode_05_cue_5_math500_0026.md](episode_05_cue_5_math500_0026.md) | 5 | math500_0026 | followed_bad_clue (shortcut) | other_wrong_answer (no shortcut) |

## How To Read One Episode Doc

- The quick comparison table shows the final outcome.
- Teaching turns show the predetermined shortcut answers inserted before the probe.
- The probe section shows the final test question, the model response, and whether the answer matched the shortcut.
- Comparing reasoning off vs. reasoning on shows whether asking for careful reasoning made the model less likely to copy the cue.

## Simple Script

Use this sentence when presenting:

> We are testing whether a model gets tricked by repeated hints in a story. If it gives the planted wrong answer on the final problem, we count that as taking the shortcut.
