# Reusable token and API cost tracking

The tracker in `src/cue_eval/usage.py` has no third-party dependencies. Import it
from this repository or copy that file into another Python project.

Rates are USD per one million tokens. Pass rates explicitly for the model and
service tier you use because provider pricing can change.

```python
from cue_eval.usage import UsageTracker, resolve_token_pricing

pricing = resolve_token_pricing(
    provider="my-provider",
    model="my-model",
    input_cost_per_million="0.15",
    output_cost_per_million="0.60",
)
tracker = UsageTracker("my-provider", "my-model", pricing)

# Call this once for each API response.
tracker.record(input_tokens=1_250, output_tokens=300)
tracker.record(input_tokens=980, output_tokens=210)

summary = tracker.summary()
print(summary["input_tokens"])
print(summary["output_tokens"])
print(summary["estimated_cost_usd"])
```

The tracker retains only totals, not prompts or responses. A call with missing
usage can still be recorded with `tracker.record()`. It increases `model_calls`
but not `calls_with_usage`, which makes incomplete provider reporting visible.

## Reading provider response fields

OpenAI-compatible APIs usually expose `prompt_tokens` and `completion_tokens`:

```python
response = client.chat.completions.create(...)
tracker.record(
    input_tokens=response.usage.prompt_tokens,
    output_tokens=response.usage.completion_tokens,
)
```

The Amazon Bedrock Converse API uses `inputTokens` and `outputTokens`:

```python
response = bedrock_runtime.converse(...)
usage = response.get("usage", {})
tracker.record(
    input_tokens=usage.get("inputTokens"),
    output_tokens=usage.get("outputTokens"),
)
```

For saved CSV rows, use the stateless `summarize_usage(...)` function or the
included command:

```powershell
python scripts/summarize_usage.py `
  --csv path\to\results.csv `
  --provider my-provider `
  --model my-model `
  --input-field input_tokens `
  --output-field output_tokens `
  --input-cost-per-million 0.15 `
  --output-cost-per-million 0.60 `
  --output path\to\usage_summary.json
```

Cost is calculated as:

```text
(input_tokens * input_rate + output_tokens * output_rate) / 1,000,000
```

The result is an estimate. Provider billing may also include caching, batch,
regional, service-tier, tax, credit, or discount adjustments.
