# Run options

## Best first demo

Use the notebook:

```text
notebooks/simple_cue_eval_showcase.ipynb
```

Start with `PROVIDER = "dryrun"` so the student can explain the idea without waiting for a model.

For the MATH-500 experiment without calling a model:

```powershell
python scripts/experiment_1.py --provider dryrun --skip-prepare --prepared-dir data --limit 100
```

This is a dry run for checking the graph and scoring pipeline. It is not evidence about a model.

## Local model with Ollama

Use this when the computer has enough memory for the chosen model.

```powershell
ollama pull qwen3:14b
python scripts/run_experiment.py --provider ollama --model qwen3:14b
```

Smaller local fallback:

```powershell
ollama pull qwen3:8b
python scripts/run_experiment.py --provider ollama --model qwen3:8b
```

## Foundry endpoint from your computer

Use this when you want the model hosted by Foundry but still want to run the script locally.

```powershell
$env:AZURE_AI_ENDPOINT="https://YOUR-RESOURCE.services.ai.azure.com"
$env:AZURE_AI_API_KEY="YOUR-KEY"
python scripts/run_experiment.py --provider azure-foundry --model qwen3-32b
```

## OpenRouter from your computer

Use this when you want to avoid Azure setup and call a hosted model through OpenRouter.

```powershell
$env:OPENROUTER_API_KEY="sk-or-v1-YOUR-KEY"
python scripts/run_experiment2.py --provider openrouter --model qwen/qwen3-32b --prepared-dir data --story-pool data\story_pool.jsonl --limit 100 --output-dir outputs\experiment2_openrouter
```

## AWS Bedrock from your computer

Use this when you want the model hosted on AWS Bedrock through the Mantle OpenAI-compatible endpoint.

```powershell
$env:AWS_BEARER_TOKEN_BEDROCK="YOUR-BEDROCK-API-KEY"
$env:AWS_BEDROCK_REGION="us-east-1"
python scripts/run_experiment2.py --provider aws --model us.anthropic.claude-3-5-haiku-20241022-v1:0 --prepared-dir data --story-pool data\story_pool.jsonl --limit 100 --max-tokens 1024 --output-dir outputs\experiment2_bedrock
```

Use a Bedrock model ID that is available on Bedrock Mantle in your region.

## Totally in Azure

Use this after the notebook works.

1. Upload or clone this repo into an Azure ML workspace.
2. Open `notebooks/simple_cue_eval_showcase.ipynb` on an Azure ML compute instance for the easiest cloud demo.
3. Open `azureml/run_azure_ai_job.yml` when you want a full Azure ML job.
4. Replace `YOUR_COMPUTE_NAME`, `YOUR-RESOURCE`, and `YOUR-KEY`.
5. Do not commit a real API key; use a workspace secret for a real project.
6. Submit the job:

```powershell
az ml job create --file azureml/run_azure_ai_job.yml
```

For a no-model smoke test in Azure:

```powershell
az ml job create --file azureml/run_mock_job.yml
```

## Recommendation

Use this order:

1. `dryrun` in the notebook.
2. `ollama` locally if available.
3. OpenRouter, Foundry, or Bedrock endpoint from your computer.
4. Azure ML job only when you want the whole run in Azure.
