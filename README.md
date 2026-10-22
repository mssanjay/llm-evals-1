# LLM Cue-Following Experiment

This project tests a simple question:

> Will a language model solve a math problem, or will it copy a misleading clue
> repeated earlier in the conversation?

The experiment uses problems from MATH-500. It places a tempting answer inside
short stories, builds a three-turn teaching history, and then asks the model one
final math question called the **probe**.

This guide supports two providers:

- AWS Bedrock
- Azure AI Foundry

## What the experiment does

For each episode, the program:

1. Chooses three teaching problems and one final probe problem.
2. Adds a repeated answer clue to each story.
3. Inserts three scripted teaching answers. These do not call the model.
4. Sends the full teaching history and final probe to the model.
5. Runs the probe with reasoning off and reasoning on.
6. Checks whether the model gave the correct answer or copied the clue.
7. Saves CSV files and graphs.

A complete run creates:

```text
45 episodes × 10 cue counts × 2 teaching conditions × 2 reasoning modes
= 1,800 probe calls
```

The program also makes two short reasoning-check calls before starting. A full
run can therefore take time and cost money. Start with the small test described
below.

## 1. Set up Python

Open PowerShell in this project's main folder. The folder should contain
`README.md`, `requirements.txt`, and the `scripts` directory.

Create and activate a Python environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

The required experiment data is already included:

- `data\math500_prepared_50.jsonl`
- `data\story_pool.jsonl`

You do not need to download another dataset before running the experiment.

## 2. Choose a provider

Use either AWS Bedrock or Azure AI Foundry. You need access to a deployed model
and its API credentials.

Never paste a real API key into the source code or commit it to Git. The commands
below keep the key in your current PowerShell session.

### Option A: AWS Bedrock

Set your Bedrock bearer token and AWS region:

```powershell
$env:AWS_BEARER_TOKEN_BEDROCK="YOUR-BEDROCK-API-KEY"
$env:AWS_BEDROCK_REGION="us-east-1"
```

The default model is `qwen.qwen3-32b`. It must be available through Bedrock in
your region.

Run a small test first. This uses one episode and one cue count:

```powershell
python scripts\run_experiment.py `
  --episodes 1 `
  --cue-counts 1 `
  --output-dir outputs\aws_test
```

If the test succeeds, run the full experiment with the project defaults:

```powershell
python scripts\run_experiment.py
```

The full AWS results are written to `outputs\experiment_bedrock`.

To use another Bedrock model or output folder:

```powershell
python scripts\run_experiment.py `
  --provider aws `
  --model YOUR-MODEL-ID `
  --output-dir outputs\my_aws_run
```

### Option B: Azure AI Foundry

Deploy a chat model in Azure AI Foundry. Copy these values from its deployment
page:

- Endpoint, such as `https://YOUR-RESOURCE.services.ai.azure.com`
- API key
- Deployment name

Set the endpoint and key:

```powershell
$env:AZURE_AI_ENDPOINT="https://YOUR-RESOURCE.services.ai.azure.com"
$env:AZURE_AI_API_KEY="YOUR-AZURE-API-KEY"
```

Run a small test. Replace `YOUR-DEPLOYMENT-NAME` with the exact deployment name
shown in Foundry:

```powershell
python scripts\run_experiment.py `
  --provider azure-foundry `
  --model YOUR-DEPLOYMENT-NAME `
  --episodes 1 `
  --cue-counts 1 `
  --output-dir outputs\azure_test
```

If the test succeeds, run the full experiment:

```powershell
python scripts\run_experiment.py `
  --provider azure-foundry `
  --model YOUR-DEPLOYMENT-NAME `
  --output-dir outputs\experiment_azure
```

## 3. Watch a run

Open a second PowerShell window and watch the progress log:

```powershell
Get-Content outputs\experiment_bedrock\progress.log -Wait
```

For Azure, replace `experiment_bedrock` with `experiment_azure`.

The program saves a checkpoint after every completed episode. If the run is
stopped, run the same command again. It will continue with unfinished episodes.

Use `--fresh` only when you intentionally want to discard that run's checkpoint
and start over:

```powershell
python scripts\run_experiment.py --fresh
```

## 4. Read the results

Start with these files inside the output folder:

- `experiment_results_simplified.csv` — easiest file for manual review
- `experiment_summary.csv` — totals grouped by condition and cue count
- `experiment_shortcut_rate.png` — percentage of valid answers that copied the clue
- `experiment_response_categories_stacked.png` — all answer categories
- `experiment_shortcut_count_by_cue_count.png` — shortcut counts
- `usage_summary.json` — token usage and estimated cost when pricing is known

The simplified CSV keeps the most useful columns:

- `model` — model or deployment that was tested
- `condition` — whether the scripted teaching answers were wrong or correct
- `reasoning` — `off` or `on`
- `cue_count` — how many equivalent clue statements appeared in each story
- `cue_strategy` — how the tempting answer was created
- `probe_id` — ID of the final math problem
- `actual_probe` — three teaching exchanges followed by the final probe
- `probe_response` — the model's full response
- `probe_answer` — the number parsed from the response
- `probe_correct_answer` — the real answer
- `probe_shortcut_answer` — the tempting clue answer
- `probe_label` — how the response was scored
- `probe_was_truncated` — whether the response hit the token limit

The most important `probe_label` values are:

- `correct` — the model solved the problem correctly
- `followed_bad_clue` — the model copied the misleading answer
- `other_wrong_answer` — the model was wrong for another reason
- `parse_fail` — no usable final answer was found

The detailed `experiment_results.csv` is also kept for debugging and deeper
analysis.

## 5. Create a readable walkthrough

After a full run, create a Markdown document explaining the experiment and
showing three examples:

```powershell
python scripts\create_experiment_walkthrough.py outputs\experiment_bedrock
```

This creates:

```text
outputs\experiment_bedrock\experiment_walkthrough.md
```

Use `outputs\experiment_azure` instead for an Azure run.

## Convert older results to the simplified CSV

If an older output folder has `experiment_results.csv` but not the simplified
file, run:

```powershell
python scripts\create_simplified_results.py outputs\YOUR-EXPERIMENT-FOLDER
```

The script creates `experiment_results_simplified.csv` without calling a model.

## Compare two completed model runs

Run each model into a different output folder. Both runs must use the same data,
45 episodes, cue counts, and experiment settings. Then run:

```powershell
python scripts\combine_model_runs.py `
  --run-dirs outputs\model_one outputs\model_two `
  --output-dir outputs\experiment_combined
```

This validates the runs and creates one combined set of graphs.

## Common problems

### PowerShell will not activate the environment

Run this once in the current PowerShell window, and then activate it again:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

### An API environment variable is missing

Set the AWS or Azure variables again in the same PowerShell window where you run
the experiment. Environment variables set this way disappear when the window is
closed.

### Azure says the deployment was not found

Make sure `--model` exactly matches the deployment name in Azure AI Foundry. It
is not always the same as the model's catalog name.

### The reasoning preflight fails

The program checks that reasoning on behaves differently from reasoning off. A
failure usually means the model does not support the requested reasoning control
or the deployment hides that information. Check the model and deployment before
starting the full run. Do not skip this check unless you understand how that
changes the experiment.

### A run stopped halfway through

Run the exact same command again. The checkpoint lets the experiment continue
without repeating completed episodes.

## Experiment details

- The prepared dataset contains 50 MATH-500 examples.
- An episode has three scripted teaching turns and one model-generated probe.
- The full experiment uses 45 rolling episodes.
- Cue counts range from 1 through 10.
- Cue strategies are `plus_one`, `times_ten`, and deterministic `random`.
- Each cue strategy is used in 15 of the 45 episodes.
- The two teaching conditions are `assistant_wrong` and `assistant_correct`.
- The two reasoning modes are `off` and `on`.
- The default maximum response length is 8,192 tokens.
- CSV files use UTF-8 encoding so they open correctly in Excel.

Story-generation details are documented in
[`docs/story_generation_prompts.md`](docs/story_generation_prompts.md). Token
tracking details are documented in [`docs/token_usage.md`](docs/token_usage.md).
