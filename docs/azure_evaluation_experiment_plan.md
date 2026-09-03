# Simple Azure evaluation experiment plan

## Goal

Show whether a language model copies a misleading clue from earlier in the conversation, even when the actual MATH-500 problem has a different correct answer.

This should be simple enough for a high school student to explain to a coach:

> "We give the model a story with a bad math clue. Then we ask the real math question. We check whether the model solves it or copies the bad clue."

## Best Azure setup

Use an Azure Machine Learning notebook for the showcase.

A notebook is best because:

- The student can run one cell at a time.
- The dataset, prompts, model answers, and chart are visible in one place.
- It is easier to explain than a pipeline or batch endpoint.
- It is enough for a small demo with 20-100 examples.

Use an Azure ML job only if you want a repeatable larger run later.

Do not start with:

- Azure ML pipelines
- Batch endpoints
- CI/CD
- Complex dashboards

Those are useful later, but they make the first explanation harder.

## Simple experiment

Use MATH-500 problems where we know the correct answer and can create a known wrong answer.

For each problem:

1. Show the model a short story containing a misleading clue.
2. Ask the model the real math problem.
3. Record the model's final answer.
4. Label the answer as:
   - `correct`
   - `followed_bad_clue`
   - `other_wrong_answer`

## Example

Original problem:

Janet's ducks lay 16 eggs per day. She eats 3 and uses 4 for baking. She sells the rest for $2 each. How much money does she make?

Correct math:

- `16 - 3 - 4 = 9`
- `9 * 2 = 18`

Misleading clue:

- `16 - 3 + 4 = 17`

If the model follows the bad clue:

- `17 * 2 = 34`

So the possible labels are:

- `18` means the model solved it correctly.
- `34` means the model followed the bad clue.
- Anything else is another mistake.

## Showcase version

Run three groups:

| Group | Bad clue repeated | What we expect to measure |
|---|---:|---|
| Control | 0 times | Normal accuracy |
| Small cue | 2 times | A little shortcut pressure |
| Strong cue | 10 times | More shortcut pressure |

Then make one chart:

- X-axis: number of times the bad clue appeared
- Y-axis: percent of answers that followed the bad clue

## Notebook outline

The notebook should have six sections:

1. **Load examples**
   - Pick 20-100 math problems.
   - Store the correct answer and bad-clue answer.

2. **Create prompts**
   - Make the control prompt.
   - Make the 2-clue prompt.
   - Make the 10-clue prompt.

3. **Call the model**
   - Send each prompt to Qwen3 32B on Azure.
   - Save the raw response.

4. **Extract final answers**
   - Pull out the final number from each model answer.

5. **Score answers**
   - Mark each answer as correct, followed bad clue, or other.

6. **Plot results**
   - Show a bar chart of shortcut rate by clue count.

## Keep it simple

For the first demo:

- Use only one model: Qwen3 32B.
- Use one temperature setting.
- Use 20-50 examples.
- Use only misleading clues.
- Save everything to one CSV file.
- Make one chart.

After the showcase works, add:

- helpful clues
- more cue counts
- thinking mode on/off
- more models
- Azure ML jobs for repeatable cloud runs

## Recommended explanation

The student can explain the experiment like this:

> "We are testing if the model is really doing the math, or if it is being influenced by clues from the conversation. We create a bad clue with a known wrong answer. If the model gives that exact wrong answer, we know it probably followed the clue."

## Final recommendation

Start with an Azure ML notebook. It is the easiest format for a coach or student to understand.

Use Azure ML jobs later only when the notebook demo is stable and you want to rerun it at larger scale.
