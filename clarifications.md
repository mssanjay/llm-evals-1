# clarifications

## usage tracker and pricing code

- See `cue_eval/usage.py`
- how to use it ...

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

## model response parser code

- The parser is in [response_parser.py (line 27)](cue_eval/response_parser.py:27).
      - extract_final_number() parses Final answer: <number>.
      - It supports Markdown/LaTeX formatting.
      - It rejects truncated responses.

- Experiment2 calls it for probes at [experiment2.py (line 715)](cue_eval/experiment2.py:715).

## rolling window sampling for episode creation

- The rolling-window sampling code is _make_episodes() in [experiment2.py (line 782)](cue_eval/experiment2.py:782).
        ```
        for start in range(len(examples) - TEACHING_TURNS):
            episodes.append(examples[start : start + TEACHING_TURNS + 1])
        ```
With TEACHING_TURNS = 3, each four-example window contains:
Window 1: examples 0, 1, 2 → teaching; example 3 → probe
Window 2: examples 1, 2, 3 → teaching; example 4 → probe
Window 3: examples 2, 3, 4 → teaching; example 5 → probe
