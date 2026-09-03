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
  -> ask model teaching turns
  -> ask final probe
  -> score whether model took shortcut
  -> make CSV + plot

46 episodes x 10 cue counts x 2 reasoning modes = 920 result rows
920 x 5 model calls = 4,600 model calls

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
python scripts/run_experiment1.py --provider dryrun --prepared-dir data
```

This writes `outputs/results.csv`, `outputs/summary.csv`, and `outputs/shortcut_rate.png` if `matplotlib` is installed.

For the dataset experiments, `dryrun` is the no-model mode. It uses known answers from the prepared dataset to test the CSVs, scoring, and plots. It is not a real model result.

`mock` is also available as a short alias for no-model testing, but new commands should use `dryrun`.

## Prepared Dataset

The prepared 50-line dataset and story pool are stored here:

- `data/math500_prepared_50.jsonl`
- `data/story_pool.jsonl`

The story pool has 5 complex story templates for each cue count from 1 through 10. Each story uses `{wrong_answer_shortcut_cue}` exactly the requested number of times.

Regenerate them from Hugging Face:

```powershell
python scripts/prepare_hf_dataset.py --dataset math500 --output data\math500_prepared_50.jsonl --limit 50 --fetch-size 300
```

## Experiment 1: Multi-Turn Story Cues

Experiment 1 is the simpler showcase experiment.

Question:

> If the bad clue appears more times inside one story, does the model follow it more often?

The x-axis is wrong-answer cue count inside the story, from `0` through `10`.
The default run now uses all cue counts from `0` through `10`.

Run it without calling a model:

```powershell
python scripts/run_experiment1.py `
  --provider dryrun `
  --prepared-dir data `
  --cue-counts 0,1,2,3,4,5,6,7,8,9,10 `
  --output-dir outputs\experiment1_demo
```

This writes:

- `outputs\experiment1_demo\full_results.csv`
- `outputs\experiment1_demo\math500_summary.csv`
- `outputs\experiment1_demo\math500_shortcut_rate.png`

Run Experiment 1 against Microsoft Foundry:

```powershell
python scripts/run_experiment1.py `
  --provider azure-foundry `
  --model qwen3-32b `
  --prepared-dir data `
  --output-dir outputs\experiment1_azure_ai
```

### Math500 Reasoning Plot

Use this when you want two panels for reasoning on/off.

```powershell
python scripts/run_math500_reasoning_cue_plot.py `
  --provider dryrun `
  --data data\math500_prepared_50.jsonl `
  --story-pool data\story_pool.jsonl `
  --output-dir outputs\math500_reasoning_cue_plot
```

This MATH-500 plot uses:

- X-axis: no. of times `{wrong_answer_shortcut_cue}` appears in the story
- Y-axis: no. of times the model took the shortcut

Run the same plot against Microsoft Foundry:

```powershell
python scripts/run_math500_reasoning_cue_plot.py `
  --provider azure-foundry `
  --model qwen3-32b `
  --data data\math500_prepared_50.jsonl `
  --story-pool data\story_pool.jsonl `
  --output-dir outputs\math500_reasoning_cue_plot_azure_ai
```

## Experiment 2: Live-History Teaching Turns

Experiment 2 is the live-history version of the story-cue experiment.

For each episode:

1. Choose a cue count from `1` through `10`.
2. Run 4 teaching turns in the same conversation history, using stories with that many cue mentions.
3. Score each teaching answer as `correct`, `followed_bad_clue`, or `other_wrong_answer`.
4. Ask one probe problem in that same conversation, also using a story with that many cue mentions.
5. Count whether the probe answer copied the wrong-answer cue.
6. Plot shortcut count against cue count.

Each teaching turn uses a complex story from `data/story_pool.jsonl`, followed by a math problem. The story pool has 5 templates for each cue count from 1 through 10. The output CSV saves `teaching_prompt_1` through `teaching_prompt_4` and `probe_prompt` so the full conversation can be inspected.

Run it without calling a model:

```powershell
python scripts/run_experiment2.py `
  --provider dryrun `
  --model qwen.qwen3-32b `
  --prepared-dir data `
  --story-pool data\story_pool.jsonl `
  --cue-counts 1,2,3,4,5,6,7,8,9,10 `
  --output-dir outputs\experiment2_dryrun
```

This writes:

- `outputs\experiment2_dryrun\full_results.csv`
- `outputs\experiment2_dryrun\all_experiment2_results.csv`
- `outputs\experiment2_dryrun\experiment2_results.partial.csv`
- `outputs\experiment2_dryrun\model_prompts.jsonl`
- `outputs\experiment2_dryrun\experiment2_summary.csv`
- `outputs\experiment2_dryrun\experiment2_shortcut_count_by_cue_count.png`
- `outputs\experiment2_dryrun\experiment2_shortcut_rate.png`
- `outputs\experiment2_dryrun\progress.log`

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
- `cue_count`: how many times `{wrong_answer_shortcut_cue}` appears in each story
- `teaching_label_1` through `teaching_label_4`
- `rule_held_count`
- `probe_label`
- `probe_took_shortcut`
- `probe_is_correct`

For slow local model runs, watch progress in another PowerShell window:

```powershell
Get-Content outputs\experiment2_dryrun\progress.log -Wait
```

The partial row-level CSV is updated after every completed episode:

```powershell
Import-Csv outputs\experiment2_dryrun\experiment2_results.partial.csv | Select-Object -Last 5
```

The prompt log stores the full chat messages for each teaching/probe model request:

```powershell
Get-Content outputs\experiment2_dryrun\model_prompts.jsonl -Tail 1
```

Run Experiment 2 against Microsoft Foundry:

```powershell
python scripts/run_experiment2.py `
  --provider azure-foundry `
  --model qwen3-32b `
  --prepared-dir data `
  --story-pool data\story_pool.jsonl `
  --cue-counts 1,2,3,4,5,6,7,8,9,10 `
  --output-dir outputs\experiment2_azure_ai
```

## Run with Ollama locally

Start Ollama and pull a model:

```powershell
ollama pull qwen3:14b
```

Then run:

```powershell
python scripts/run_experiment1.py --provider ollama --model qwen3:14b --prepared-dir data
```

For Experiment 1:

```powershell
python scripts/run_experiment1.py --provider ollama --model qwen3:14b --prepared-dir data --output-dir outputs\experiment1_ollama
```

For Experiment 2:

```powershell
python scripts/run_experiment2.py --provider ollama --model qwen3:14b --prepared-dir data --cue-counts 1,2,3,4,5,6,7,8,9,10 --output-dir outputs\experiment2_ollama
```

If Ollama is running somewhere else:

```powershell
$env:OLLAMA_URL="http://localhost:11434"
python scripts/run_experiment1.py --provider ollama --model qwen3:14b --prepared-dir data
```

## Run with OpenRouter

Set your OpenRouter key:

```powershell
$env:OPENROUTER_API_KEY="sk-or-v1-YOUR-KEY"
$env:OPENROUTER_APP_NAME="llm-cue-evals"
```

Then run Experiment 2:

```powershell
python scripts/run_experiment2.py `
  --provider openrouter `
  --model qwen/qwen3-32b `
  --prepared-dir data `
  --story-pool data\story_pool.jsonl `
  --cue-counts 1,2,3,4,5,6,7,8,9,10 `
  --output-dir outputs\experiment2_openrouter
```

Experiment 2 uses every row in `data\math500_prepared_50.jsonl`. For each episode it tries stories with 1 cue, 2 cues, and so on up to 10 cues. You can also pass `--model qwen3-32b`; the code maps it to OpenRouter's `qwen/qwen3-32b` slug.

## Run with AWS Bedrock

Set your Bedrock API key and region. The `aws` provider uses the Bedrock Mantle OpenAI-compatible endpoint:

```text
https://bedrock-mantle.YOUR-REGION.api.aws/v1/chat/completions
```

```powershell
$env:BEDROCK_API_KEY="YOUR-BEDROCK-API-KEY"
$env:AWS_BEDROCK_REGION="us-east-1"
```

Then run Experiment 2 with a model ID available on Bedrock Mantle:

```powershell
python scripts/run_experiment2.py `
  --provider aws `
  --model us.anthropic.claude-3-5-haiku-20241022-v1:0 `
  --prepared-dir data `
  --story-pool data\story_pool.jsonl `
  --cue-counts 1,2,3,4,5,6,7,8,9,10 `
  --max-tokens 1024 `
  --output-dir outputs\experiment2_bedrock
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
python scripts/run_experiment1.py --provider azure-openai --model YOUR-DEPLOYMENT-NAME --prepared-dir data
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

Then run:

```powershell
python scripts/run_experiment1.py --provider azure-foundry --model qwen3-32b --prepared-dir data
```

For Experiment 1:

```powershell
python scripts/run_experiment1.py --provider azure-foundry --model qwen3-32b --prepared-dir data --output-dir outputs\experiment1_foundry
```

For Experiment 2:

```powershell
python scripts/run_experiment2.py --provider azure-foundry --model qwen3-32b --prepared-dir data --story-pool data\story_pool.jsonl --cue-counts 1,2,3,4,5,6,7,8,9,10 --output-dir outputs\experiment2_foundry
```

The `--model` value must exactly match the deployment name shown in Foundry.

### Optional: create the endpoint by CLI

```powershell
.\scripts\create_azure_serverless_qwen32b.ps1 `
  -ResourceGroup "YOUR-RESOURCE-GROUP" `
  -WorkspaceName "YOUR-AZUREML-WORKSPACE" `
  -EndpointName "qwen3-32b"
```

This CLI helper uses Azure ML commands because that is how Azure exposes serverless endpoint creation through the command line. You can skip it when using the Foundry portal.

## Deploy to Azure ML

Install Azure CLI, sign in, and select the subscription:

```powershell
az login
az account set --subscription "YOUR-SUBSCRIPTION-ID"
az extension add --name ml --upgrade
```

Run Experiment 1 as an Azure ML job without a model call:

```powershell
.\scripts\deploy_azureml.ps1 `
  -ResourceGroup "YOUR-RESOURCE-GROUP" `
  -WorkspaceName "YOUR-AZUREML-WORKSPACE" `
  -ComputeName "YOUR-COMPUTE-NAME" `
  -Experiment 1 `
  -Provider dryrun
```

Run Experiment 2 as an Azure ML job against Foundry:

```powershell
$env:AZURE_AI_ENDPOINT="https://YOUR-RESOURCE.services.ai.azure.com"
$env:AZURE_AI_API_KEY="YOUR-KEY"
$env:AZURE_AI_API_VERSION="2024-05-01-preview"

.\scripts\deploy_azureml.ps1 `
  -ResourceGroup "YOUR-RESOURCE-GROUP" `
  -WorkspaceName "YOUR-AZUREML-WORKSPACE" `
  -ComputeName "YOUR-COMPUTE-NAME" `
  -Experiment 2 `
  -Provider azure-foundry `
  -Model qwen3-32b
```

Run Experiment 2 as an Azure ML job against OpenRouter:

```powershell
$env:OPENROUTER_API_KEY="sk-or-v1-YOUR-KEY"

.\scripts\deploy_azureml.ps1 `
  -ResourceGroup "YOUR-RESOURCE-GROUP" `
  -WorkspaceName "YOUR-AZUREML-WORKSPACE" `
  -ComputeName "YOUR-COMPUTE-NAME" `
  -Experiment 2 `
  -Provider openrouter `
  -Model qwen/qwen3-32b
```

Run Experiment 2 as an Azure ML job against AWS Bedrock:

```powershell
$env:AWS_BEDROCK_REGION="us-east-1"
$env:BEDROCK_API_KEY="YOUR-BEDROCK-API-KEY"

.\scripts\deploy_azureml.ps1 `
  -ResourceGroup "YOUR-RESOURCE-GROUP" `
  -WorkspaceName "YOUR-AZUREML-WORKSPACE" `
  -ComputeName "YOUR-COMPUTE-NAME" `
  -Experiment 2 `
  -Provider aws `
  -Model us.anthropic.claude-3-5-haiku-20241022-v1:0
```

For a real shared project, prefer a secret store instead of hard-coding Bedrock API keys.

To generate the Azure ML job YAML without submitting:

```powershell
.\scripts\deploy_azureml.ps1 `
  -ResourceGroup "YOUR-RESOURCE-GROUP" `
  -WorkspaceName "YOUR-AZUREML-WORKSPACE" `
  -ComputeName "YOUR-COMPUTE-NAME" `
  -Experiment 2 `
  -Provider dryrun `
  -NoSubmit
```

The generated job file is written under `outputs\azureml_jobs\`.

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
2. Run Experiment 1 to show the simple bad-clue repetition effect.
3. Run Experiment 2 to show the live-history teaching-turn methodology.
4. Run Azure if you want the result to use the same hosted model every time.

For the coach-facing demo, keep the chart explanation simple:

- Experiment 1 x-axis: wrong-answer cue count inside the story
- Experiment 2 x-axis: how many times the wrong-answer cue appears in each story
- Experiment 2 y-axis: how many probe answers followed the bad clue
