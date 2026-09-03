# Run the notebook with a Foundry model

You do not need to deploy the notebook like an app. You can run it locally or inside Azure, then call the model from Microsoft Foundry.

## What you need

- Microsoft Foundry model deployment
- Endpoint key for that model

## Recommended flow

1. Open the notebook locally or in Azure.
2. Deploy Qwen3 32B in Foundry.
3. Copy the Foundry endpoint, key, and deployment name.
4. Open `notebooks/simple_cue_eval_showcase.ipynb`.
5. Install requirements in a notebook cell:

```python
%pip install -r ../requirements.txt
```

If the notebook is opened from the repo root instead of the `notebooks` folder, use:

```python
%pip install -r requirements.txt
```

## Set Azure model variables

In a notebook cell, set:

```python
import os
import getpass

os.environ["AZURE_AI_ENDPOINT"] = "https://YOUR-RESOURCE.services.ai.azure.com"
os.environ["AZURE_AI_API_KEY"] = getpass.getpass("Azure AI API key: ")
os.environ["AZURE_AI_API_VERSION"] = "2024-05-01-preview"
```

Then set:

```python
PROVIDER = "azure-foundry"
MODEL = "qwen3-32b"
```

Now run the experiment cells.

## Run Experiment 1 in the notebook

Experiment 1 tests whether repeating a bad clue more often makes the model follow it more.

```python
from cue_eval.experiment import run_experiment

rows, summary = run_experiment(
    data_path=ROOT / "data" / "math500_prepared_50.jsonl",
    output_dir=ROOT / "outputs" / "notebook_experiment1_azure",
    provider="azure-foundry",
    model="qwen3-32b",
    cue_counts=[0, 2, 10],
    temperature=0.2,
    max_tokens=256,
)

summary
```

## Run Experiment 2 in the notebook

Experiment 2 uses the live-history teaching-turn methodology.

```python
from cue_eval.experiment2 import run_experiment2_experiment, write_experiment2_outputs

all_rows = run_experiment2_experiment(
    data_path=ROOT / "data" / "math500_prepared_50.jsonl",
    dataset_name="math500",
    output_dir=ROOT / "outputs" / "notebook_experiment2_azure" / "math500",
    provider="azure-foundry",
    model="qwen3-32b",
    temperature=0.2,
    max_tokens=256,
    reasoning_modes=["off", "on"],
    cue_counts=[1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
    max_workers=8,
    story_pool_path=ROOT / "data" / "story_pool.jsonl",
)

summary = write_experiment2_outputs(ROOT / "outputs" / "notebook_experiment2_azure", all_rows)
summary
```

## Start small

Experiment 2 now uses every row in the prepared MATH500 file. Use `dryrun` first when you want a quick check without waiting for model calls.

## Key idea

- Notebook = best for showing and explaining the experiment.
- Azure ML job = optional for a final repeatable batch run.
