# LLM cue-following evaluation

## objective

This is a simple experiment for testing whether a language model follows a misleading clue from earlier in a conversation.

The experiment is:
> Does the model solve the math problem, or does it copy the bad clue?
> We take real math problems from MATH500, hide a tempting wrong answer inside little stories, show the model a few practice turns, then test whether it actually solves the final problem or just copies the repeated clue.

MATH500 dataset
  -> load every example from the prepared MATH500 file
  -> group examples into episodes
  -> pick story templates from story pool
  -> insert wrong-answer cues into stories
  -> insert scripted teaching answers
  -> ask final probe
  -> score whether model took shortcut
  -> make CSV + plot

45 episodes x 10 cue counts x 2 conditions x 2 reasoning modes = 1,800 rows per model
1,800 x 1 probe model call = 1,800 model calls per model

## Quick Local Test

Create a local Python environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Run the no-model demo first:

```powershell
python scripts/run_experiment.py --provider dryrun --prepared-dir data
```

This writes row-level results, summaries, prompt logs, cost reports, and plots under
`outputs/experiment_comparison`.

For the dataset experiments, `dryrun` is the no-model mode. It uses known answers from the prepared dataset to test the CSVs, scoring, and plots. It is not a real model result.

`mock` is also available as a short alias for no-model testing, but new commands should use `dryrun`.

## Prepared Dataset

The prepared 50-line dataset and story pool are stored here:

- `data/math500_prepared_50.jsonl`
- `data/story_pool.jsonl`

The story pool has 5 complex story templates for each cue count from 1 through 10. Each template is 60-100 words and uses `{wrong_answer_shortcut_cue}` exactly the requested number of times.

To reproduce or extend the pool, use the generation and constraint-repair
prompts in [`docs/story_generation_prompts.md`](docs/story_generation_prompts.md).
The prompts include the JSONL schema, diversity criteria, exact placeholder
rules, word-count constraint, and validation example.

Regenerate them from Hugging Face:

```powershell
python scripts/prepare_hf_dataset.py --dataset math500 --output data\math500_prepared_50.jsonl --limit 50 --fetch-size 300
```

## Experiment 1: Live-History Teaching Turns

Experiment 1 is the live-history story-cue experiment.

For each episode:

1. Choose a cue count from `1` through `10`.
2. Assign one wrong-answer strategy to the episode: correct answer + 1, correct answer x 10, or a deterministic random number. Each strategy is used for 15 of the 45 episodes.
3. Run both scripted teaching conditions. In `assistant_wrong`, the story and assistant give the wrong shortcut answer. In `assistant_correct`, both give the gold answer. No provider call is made for teaching turns.
4. Send the same 45 probe items to every condition, model, and reasoning mode.
5. Send one probe problem and the complete scripted history to the model, using the same strategy.
6. Count whether the probe answer copied the wrong-answer cue.
7. Plot shortcut count against cue count.

Each teaching turn uses a complex story from `data/story_pool.jsonl`, followed by a math problem and a scripted `Final answer: <shortcut>` assistant response. The story pool has 5 templates for each cue count from 1 through 10, with every template kept between 60 and 100 words. The output CSV saves `teaching_prompt_1` through `teaching_prompt_3`, `teaching_response_1` through `teaching_response_3`, and `probe_prompt` so the full conversation can be inspected.

Within an Experiment 1 story, repeated cues use deterministic paraphrases rather
than repeating one sentence verbatim. Every paraphrase states the same shortcut
answer; `cue_count` is therefore the number of semantically equivalent cue
statements. Existing output folders remain historical artifacts and must be
rerun to use paraphrased cues.

For Qwen3 models, the reasoning conditions also send Qwen's explicit `/no_think`
and `/think` switches. The default output limit is 8192 tokens. A response that
hits the token limit or omits the required `Final answer:` marker is labeled
`parse_fail` instead of being scored from an incidental number in its explanation.
Plain, Markdown, multiline LaTeX, and `\boxed{...}` final-answer formats are
accepted when they follow that marker.

Run it without calling a model:

```powershell
python scripts/run_experiment.py `
  --provider dryrun `
  --model qwen.qwen3-32b `
  --prepared-dir data `
  --story-pool data\story_pool.jsonl `
  --episodes 45 `
  --cue-counts 1,2,3,4,5,6,7,8,9,10 `
  --output-dir outputs\experiment_dryrun
```

Run Qwen and DeepSeek into separate directories with the same data, story pool,
episode count, and cue counts. Their `episode_manifest.json` hashes must match:

```powershell
python scripts/run_experiment.py `
  --provider aws `
  --model qwen.qwen3-32b `
  --max-tokens 8192 `
  --output-dir outputs\experiment_qwen

python scripts/run_experiment.py `
  --provider aws `
  --model YOUR-DEEPSEEK-MODEL-ID `
  --max-tokens 8192 `
  --input-cost-per-million YOUR-DEEPSEEK-INPUT-RATE `
  --output-cost-per-million YOUR-DEEPSEEK-OUTPUT-RATE `
  --output-dir outputs\experiment_deepseek
```

The runner makes one reasoning-off and one reasoning-on preflight call before
the full matrix. It stops if the reasoning-on field is not longer than the
reasoning-off field. This prevents an unsupported toggle from producing a
mislabelled full run.

After both runs finish, validate and combine them:

```powershell
python scripts/combine_model_runs.py `
  --run-dirs outputs\experiment_qwen outputs\experiment_deepseek `
  --output-dir outputs\experiment_combined
```

The combine step rejects mismatched manifests, incomplete 45-episode cells,
incorrect cue-type balance, failed reasoning checks, or a token limit below
8192.

Experiment 1 checks the reasoning toggle before a full run, then checkpoints every completed episode. If a run fails, rerun the same command to retry only unfinished work. Add `--fresh` to start over. Use `--skip-reasoning-preflight` only when intentionally bypassing the required two-call check.

This writes:

- `outputs\experiment_dryrun\full_results.csv`
- `outputs\experiment_dryrun\all_experiment_results.csv`
- `outputs\experiment_dryrun\experiment_results.partial.csv`
- `outputs\experiment_dryrun\model_prompts.jsonl`
- `outputs\experiment_dryrun\model_prompts_by_episode.jsonl`
- `outputs\experiment_dryrun\experiment_summary.csv`
- `outputs\experiment_dryrun\experiment_shortcut_count_by_cue_count.png`
- `outputs\experiment_dryrun\experiment_shortcut_rate.png`
- `outputs\experiment_dryrun\experiment_response_categories_stacked.png`
- `outputs\experiment_dryrun\experiment_story_token_count_by_cue_count.png`
- `outputs\experiment_dryrun\progress.log`
- `outputs\experiment_dryrun\usage_summary.json`
- `outputs\experiment_dryrun\usage_by_subexperiment.csv`
- `outputs\experiment_dryrun\episode_manifest.json`
- `outputs\experiment_dryrun\reasoning_preflight.json`

`full_results.csv` is the coach-friendly condition summary. Its first columns are:

- `Model`
- `Provider`
- `Dataset`
- `Cue type`
- `History`
- `Reasoning`
- `Story`
- `n`

The row-level CSV includes these labels:

- `reasoning`: `off` or `on`
- `condition`: `assistant_wrong` or `assistant_correct`
- `cue_count`: how many times `{wrong_answer_shortcut_cue}` appears in each story
- `shortcut_cue_type`: `plus_one`, `times_ten`, or `random`; 15 episodes use each type
- `teaching_label_1` through `teaching_label_3`
- `teaching_shortcut_answer_1` through `teaching_shortcut_answer_3`
- `teaching_response_1` through `teaching_response_3`
- `teaching_response_source_1` through `teaching_response_source_3`, set to `scripted`
- `scripted_teaching_count`, set to `3`
- `rule_held_count`
- `probe_label`
- `probe_took_shortcut`
- `probe_is_correct`
- `probe_finish_reason` and `probe_was_truncated`
- `probe_reasoning`, `probe_reasoning_chars`, and `probe_reasoning_tokens`
- `probe_prompt_tokens`, `probe_completion_tokens`, and `probe_total_tokens`
- scripted finish metadata for each teaching turn; token counts are empty because no provider call occurs

CSV artifacts are written as UTF-8 with a byte-order mark so Excel detects curly
quotes and other non-ASCII text correctly.

The stacked response-category chart counts every probe as `Correct answer`,
`Shortcut cue taken`, `Other wrong answer`, or `Invalid / truncated`. The last
category corresponds to a `parse_fail` label. Each stacked bar therefore totals
the full number of episodes for that reasoning mode and cue count.

The shortcut count/rate charts label every condition with its total episode count
(`N=45`). If truncated or otherwise invalid responses are excluded from a rate,
the label also shows the smaller `valid` count.

Every Experiment 1 chart captions the 60–100-word template constraint. The
story-token diagnostic plots the rendered story text saved in the prompts against
cue count, using model-independent lexical tokens, so a systematic length trend is
visible without depending on one provider's tokenizer.

For slow local model runs, watch progress in another PowerShell window:

```powershell
Get-Content outputs\experiment_dryrun\progress.log -Wait
```

The partial row-level CSV is updated after every completed episode:

```powershell
Import-Csv outputs\experiment_dryrun\experiment_results.partial.csv | Select-Object -Last 5
```

The raw prompt log stores each teaching/probe event as it occurs. Parallel episodes
can be interleaved:

```powershell
Get-Content outputs\experiment_dryrun\model_prompts.jsonl -Tail 1
```

Each live model response logs its input and output token counts. At the end of a
run, `usage_summary.json`, the console, and Experiment 1's `progress.log` report
aggregate input tokens, output tokens, and estimated USD cost. The
`usage_by_subexperiment.csv` file separates cost by condition, reasoning mode,
and cue count. Bedrock Qwen3 32B
standard on-demand pricing is built in. The estimate excludes account credits,
discounts, and taxes. For another model or service tier, pass both current rates
explicitly:

The tracking code is provider-independent and reusable outside the experiment
runners. See [`docs/token_usage.md`](docs/token_usage.md) for a copy-ready
`UsageTracker` example and provider response field mappings.

```powershell
python scripts/run_experiment.py `
  --provider aws `
  --model YOUR-MODEL-ID `
  --input-cost-per-million 0.15 `
  --output-cost-per-million 0.60
```

To backfill the summary for an existing Experiment 1 run without calling a model:

```powershell
python scripts/summarize_usage.py `
  --csv outputs\experiment_2_bedrock_run4\experiment_results.csv `
  --provider aws `
  --model qwen.qwen3-32b `
  --output outputs\experiment_2_bedrock_run4\usage_summary.json
```

`model_prompts_by_episode.jsonl` is generated after a successful run. It contains
one complete episode per line, sorted by reasoning mode, cue count, and episode
index. Each object includes the three scripted teaching turns, the probe turn and
response, scoring metadata, and the exact messages sent with the probe.

To create the grouped artifact for an already completed run without calling the
model again:

```powershell
python scripts/group_experiment_prompts.py `
  --output-dir outputs\experiment_2_bedrock_run3
```

After changing scoring logic, rescore a completed run and regenerate its tables,
grouped prompts, and charts without making model calls:

```powershell
python scripts/rescore_experiment.py `
  --output-dir outputs\experiment_2_bedrock_run3
```

### Experiment Walkthrough

After running Experiment 1, create one simple Markdown walkthrough with the
experiment steps and three paired reasoning examples:

```powershell
python scripts/create_experiment_walkthrough.py outputs\experiment_bedrock
```

This writes `outputs\experiment_bedrock\experiment_walkthrough.md` and shows
examples for cue counts 3, 5, and 10.

Run Experiment 1 against Microsoft Foundry:

```powershell
python scripts/run_experiment.py `
  --provider azure-foundry `
  --model qwen3-32b `
  --prepared-dir data `
  --story-pool data\story_pool.jsonl `
  --cue-counts 1,2,3,4,5,6,7,8,9,10 `
  --output-dir outputs\experiment_azure_ai
```

## Run with Ollama locally

Start Ollama and pull a model:

```powershell
ollama pull qwen3:14b
```

Then run Experiment 1:

```powershell
python scripts/run_experiment.py --provider ollama --model qwen3:14b --prepared-dir data --cue-counts 1,2,3,4,5,6,7,8,9,10 --output-dir outputs\experiment_ollama
```

If Ollama is running somewhere else:

```powershell
$env:OLLAMA_URL="http://localhost:11434"
python scripts/run_experiment.py --provider ollama --model qwen3:14b --prepared-dir data
```

## Run with OpenRouter

Set your OpenRouter key:

```powershell
$env:OPENROUTER_API_KEY="sk-or-v1-YOUR-KEY"
$env:OPENROUTER_APP_NAME="llm-cue-evals"
```

Then run Experiment 1:

```powershell
python scripts/run_experiment.py `
  --provider openrouter `
  --model qwen/qwen3-32b `
  --prepared-dir data `
  --story-pool data\story_pool.jsonl `
  --cue-counts 1,2,3,4,5,6,7,8,9,10 `
  --output-dir outputs\experiment_openrouter
```

Experiment 1 uses every row in `data\math500_prepared_50.jsonl`. For each episode it tries stories with 1 cue, 2 cues, and so on up to 10 cues. You can also pass `--model qwen3-32b`; the code maps it to OpenRouter's `qwen/qwen3-32b` slug.

## Run with AWS Bedrock

Set your Bedrock API key and region. The `aws` provider uses the Bedrock Mantle OpenAI-compatible endpoint:

```text
https://bedrock-mantle.YOUR-REGION.api.aws/v1/chat/completions
```

```powershell
$env:AWS_BEARER_TOKEN_BEDROCK="YOUR-BEDROCK-API-KEY"
$env:AWS_BEDROCK_REGION="us-east-1"
```

Then run Experiment 1 with a model ID available on Bedrock Mantle:

```powershell
python scripts/run_experiment.py `
  --provider aws `
  --model qwen3-32b `
  --prepared-dir data `
  --story-pool data\story_pool.jsonl `
  --cue-counts 1,2,3,4,5,6,7,8,9,10 `
  --max-tokens 8192 `
  --output-dir outputs\experiment_bedrock
```

The `--model` value must be available for the Bedrock Mantle endpoint in your region. You can also override the full base URL:

```powershell
$env:AWS_BEDROCK_MANTLE_BASE_URL="https://bedrock-mantle.us-east-1.api.aws/v1"
```

## Run with Azure OpenAI style endpoint

Set:

```powershell
$env:AZURE_OPENAI_ENDPOINT="https://YOUR-RESOURCE.openai.azure.com"
$env:AZURE_OPENAI_API_KEY="YOUR-KEY"
$env:AZURE_OPENAI_API_VERSION="2024-10-21"
```

Then run:

```powershell
python scripts/run_experiment.py --provider azure-openai --model YOUR-DEPLOYMENT-NAME --prepared-dir data
```

## Run with Microsoft Foundry

You do not need Azure ML to run this locally against a model already deployed in Foundry. Azure ML is only needed for the optional Azure ML job path or for the optional CLI helper that creates a serverless endpoint.

In Foundry, deploy this model:

```text
azureml://registries/azureml-alibaba/models/qwen3-32b/versions/1
```

After the deployment is ready, copy from the Foundry deployment details:

- Endpoint, usually `https://YOUR-RESOURCE.services.ai.azure.com`
- Key
- Deployment name, for example `qwen3-32b`

Set:

```powershell
$env:AZURE_AI_ENDPOINT="https://YOUR-RESOURCE.services.ai.azure.com"
$env:AZURE_AI_API_KEY="YOUR-KEY"
```

Then run Experiment 1:

```powershell
python scripts/run_experiment.py --provider azure-foundry --model qwen3-32b --prepared-dir data --story-pool data\story_pool.jsonl --cue-counts 1,2,3,4,5,6,7,8,9,10 --output-dir outputs\experiment_foundry
```

The `--model` value must exactly match the deployment name shown in Foundry.

## Run Notebook On Azure ML

For the showcase, run the notebook on an Azure ML compute instance. You do not need to deploy it like a web app.

Use:

```text
notebooks/simple_cue_eval_showcase.ipynb
```

Inside the notebook, install requirements:

```python
%pip install -r ../requirements.txt
```

Then set the Azure model endpoint:

```python
import os
import getpass

os.environ["AZURE_AI_ENDPOINT"] = "https://YOUR-RESOURCE.services.ai.azure.com"
os.environ["AZURE_AI_API_KEY"] = getpass.getpass("Azure AI API key: ")
os.environ["AZURE_AI_API_VERSION"] = "2024-05-01-preview"

PROVIDER = "azure-foundry"
MODEL = "qwen3-32b"
```

More detailed notebook instructions are in `docs/azure_notebook_setup.md`.

## Best showcase path

Use the notebook or script in this order:

1. Run the `dryrun` provider to explain the idea.
2. Confirm that reasoning on/off passes the saved preflight check.
3. Run Experiment 1 for both Qwen and DeepSeek using separate output directories.
4. Compare the condition, reasoning, cue-type, and cost summaries.

For the coach-facing demo, keep the chart explanation simple:

- X-axis: how many times the cue appears in each story
- Y-axis: how many probe answers followed the wrong cue
- Panels: scripted-assistant condition and reasoning mode
