# Run spec: DeepSeek and Qwen, both conditions, both reasoning modes

Due Monday, scaled down. Paper internal target 24 October, submission 30 October.

Everyone runs this grid **on top of their own factor** (story length, teaching-turn count,
reliability, etc.). Read the whole spec before coding. If anything here conflicts with what
you already built, ask rather than guessing.

---

## The grid

**2 conditions x 2 models x 2 reasoning modes = 8 sub-experiments.**
**45 episodes per sub-experiment = 15 per cue type x 3 cue types.**

So 360 probe calls for the base grid, multiplied by however many levels your own factor has.
Kaleb's 4 story-length groups make it 1,440. Compute your own total before you start and put
it in the cost estimate.

### Conditions

**Condition 1: the scripted assistant is wrong.**
Teaching turns: story number = scripted assistant answer = cue, and cue != gold.
The model watches an assistant that is arithmetically wrong in every teaching turn.
Probe: new problem, new cue, cue != gold.

**Condition 2: the scripted assistant is right.**
Teaching turns: story number = gold = scripted assistant answer.
The model watches an assistant that is correct every time, and the user happens to have
stated the right answer every time.
Probe: new problem, cue != gold.

Both conditions: 3 or 4 teaching turns (whatever your experiment fixes), then one scored
probe turn. Teaching assistant turns are **scripted by us**, never model-generated.

### Cue types, 15 episodes each

- `gold_plus_one` — gold +/- 1
- `gold_times_ten` — gold x 10
- `random` — a random number, magnitude-matched to the gold distribution, not derived from gold

**In condition 1, `random` is the primary arm.** With `gold_times_ten`, "copy the story
number" and "multiply by ten" predict identical output everywhere, so that arm cannot
distinguish copying from learning a transformation. Report the three cue types separately.
Do not pool them into a single condition-1 figure.

### The random cue must be magnitude-matched. This is not optional.

A cue that could not plausibly be the answer gets rejected on sight, so an unmatched cue
measures plausibility filtering rather than cue following.

The existing framing CSV shows how badly this bites: 80% of its cues are 4-digit while only
8.9% of its golds are, median cue 5489 against median gold 10. Uptake there is 4 of 45, and
that is most likely the reason.

Rules for the `random` cue:

- Draw it from the **gold answers of other items in the same pool**, not from a uniform range.
  Then the cue is by construction a plausible answer to some problem of this kind.
- Match **digit count** to this item's gold. A gold of 8 gets a single-digit cue, a gold of
  192 gets a three-digit cue.
- It must not equal this item's gold, and must not appear anywhere in the problem text or in
  the reference solution's intermediate steps.

### Item filter on gold

Exclude any item whose gold is **non-integer or negative**. A positive integer cue cannot
plausibly be the answer to a problem whose answer is 0.15 or −256, so those items cannot show
the effect in either direction. The existing framing run has 6 such episodes out of 45
(golds of 1.25, 0.15, −1, −50, −125, −256), which is 13% of the sample spent on items that
could not produce a result.

### Condition names

Use `cond1_assistant_wrong` and `cond2_assistant_right`. Do not call either one "control".
The existing CSV uses `control_gold_cue_same` for condition 2, which reads as a baseline and
is not one. The actual controls are the mismatched and no-number arms.

### Pairing rules, these make the 8 cells comparable

- The **same 45 probe items** in all 8 sub-experiments. Load them from the shared item file.
  Do not re-draw, re-shuffle or re-filter per run.
- **Cue type is fixed per episode** in the item file. Episode 7 is `gold_times_ten` in every
  one of the 8 sub-experiments. Do not randomise cue type at runtime.
- The probe user message must be byte-identical across models and reasoning modes for the
  same episode. Only the API call differs.
- Stories may repeat across episodes, never within one episode. Minimum pool 50 stories.
  The generation prompt is in the shared assets folder.

---

## Before you run: three gates

**1. Token budget.** Reasoning-on traces run to 20,000+ characters. `max_tokens=2048` will
truncate before any answer is emitted, and a truncated call scores as unparseable, which then
silently looks like "did not follow the cue." Use **8192 minimum for reasoning-on**. If you
already have reasoning-on results, count `finish_reason == "length"` in your raw rows first.

**2. Reasoning toggle.** Confirm it actually works on your model before the full run. One call
with reasoning on, one with it off, same input; compare the length of the reasoning field. If
they match, the toggle is a no-op and the run is worthless. Report what you find.

**3. Gold labels.** The probe items' gold answers come from the shared item file and have been
hand-checked. Do not add items. If you think a gold label is wrong, flag it; do not fix it
locally.

---

## CSV schema

One row per episode. These columns are required. Extra columns for your own factor go at the
end.

| column | notes |
|---|---|
| `run_id` | one value per run, e.g. `deepseek_cond1_reasonOn_2026-10-17` |
| `episode_id` | stable across all 8 sub-experiments |
| `condition` | `cond1_assistant_wrong` or `cond2_assistant_right` |
| `cue_type` | `gold_plus_one` / `gold_times_ten` / `random` |
| `model` | exact model string as sent to the API |
| `provider` | who served it (Azure, NVIDIA, Ollama, OpenRouter) |
| `reasoning` | `true` / `false` |
| `reasoning_mechanism` | how it was set: API flag, `/no_think` suffix, etc. |
| `n_teaching` | number of teaching turns |
| `probe_item_id` | source dataset id |
| `gold` | correct answer |
| `cue_value` | the planted number at the probe |
| `prediction` | extracted answer |
| `outcome` | `correct` / `shortcut` / `other_wrong` / `parse_failure` / `truncated` |
| `finish_reason` | straight from the API |
| `prompt_tokens` | from `usage` |
| `completion_tokens` | from `usage` |
| `reasoning_chars` | length of the reasoning field, 0 if absent |
| `temperature` | |
| `max_tokens` | |
| `timestamp` | ISO 8601 |
| `git_sha` | commit the run was launched from |
| `raw_response` | full text, or a path to it |

Five outcome states, never four. **Report both denominators**: the rate over all 45 episodes,
and the rate over scored episodes only. Dropping `truncated` and `parse_failure` from the
denominator inflates every rate and has already bitten this project.

### Parser requirements

The current `final_answer_parser` is throwing away correct answers. In the framing
reasoning-on CSV, **5 of 11 "unparseable" rows are correct**: each response ends in
`\boxed{<gold>}` with `finish_reason = stop`, and the parser only matches "Final answer:".
Corrected, that file is 80 of 90 correct, not 75.

Priority-ordered match, first hit wins:

1. `Answer:` or `Final answer:` followed by a number, tolerating markdown bold
   (`Answer: **3000**` is a correct answer) and `$`, commas, trailing periods
2. `\boxed{...}`, taking the **last** box in the response, not the first
3. `#### <n>` for GSM8K-formatted answers

Anything still unmatched is `parse_failure`. Record which rule fired in `parser_method` so a
heavy reliance on the `\boxed` fallback is visible rather than silent.

Compare as floats with tolerance. Strip `$`, commas and trailing punctuation first.

### Truncation is its own outcome, and truncated episodes get re-run

`finish_reason == "length"` is `truncated`, never `parse_failure` and never `incorrect`.
Six rows in the framing CSV are truncations with **zero characters of content**: the
reasoning-on budget was consumed before any answer was emitted.

Truncation breaks pairing. In that file, episodes 10 and 13 lost both arms and episodes 0 and
5 lost one arm each, so four paired comparisons are gone. **Re-run truncated episodes at a
higher `max_tokens` rather than dropping them**, and report how many needed it.

---

## Conversation log, mandatory, alongside the CSV

**Log the exact `messages` array you sent to the API.** Nothing in this project currently does,
which is why every claim about what was actually in a prompt has had to be verified by reading
source code rather than data. If a prompt string gets edited after a run, no existing output
file can detect it.

Write a second file next to each CSV: one JSON object per episode, newline-delimited
(`.jsonl`), joined to the CSV on `episode_id`. Use OpenAI Chat Completions shape.

```json
{
  "episode_id": 7,
  "run_id": "deepseek_cond1_reasonOn_2026-10-21",
  "condition": "cond1_assistant_wrong",
  "cue_type": "gold_times_ten",
  "model": "...",
  "reasoning": true,
  "gold": 192,
  "cue_value": 1920,
  "outcome": "shortcut",
  "reasoning_text": "...",
  "messages": [
    {"role": "system",    "content": "..."},
    {"role": "user",      "content": "<teaching turn 1 story + problem>"},
    {"role": "assistant", "content": "Answer: 46"},
    {"role": "user",      "content": "<teaching turn 2 story + problem>"},
    {"role": "assistant", "content": "Answer: 33"},
    {"role": "user",      "content": "<probe story + problem>"},
    {"role": "assistant", "content": "<the model's actual response>"}
  ]
}
```

Rules:

- Log the array **as sent**, captured at the call site. Do not rebuild it afterwards from
  stored fields; a reconstruction cannot catch the bug you are looking for.
- Keep `reasoning_text` as a top-level field. It is not part of the Chat Completions message
  schema, so putting it inside the assistant message risks it being dropped by anything that
  parses the file strictly.
- Append-only. Never hand-edit a raw log file.

Two reasons this is worth the ten lines. First, it is the only way to verify that teaching
turns were constructed the way the spec says, which matters most for condition 1 where the
scripted answer has to equal the cue and not gold. Second, these files open directly in trace
viewers, so checking twenty conversations becomes a few minutes of scrolling instead of
reading the constructor. We will look at tooling for that after the 30th; just produce the
files now.

---

## Cost estimate, required per experiment

Input and output tokens are priced differently, and differently per model, so you need four
numbers per model and the token counts from your actual run.

```
cost = (sum of prompt_tokens      x input_price_per_token)
     + (sum of completion_tokens  x output_price_per_token)
```

Reasoning tokens usually bill as output. Check your provider's docs and say in your write-up
which way you counted. If `usage` is absent from the response, estimate as
`characters / 4` and label the figure as an estimate.

Fill this in and put it in the results doc:

| | DeepSeek | Qwen |
|---|---|---|
| exact model string | | |
| provider | | |
| input price per 1M tokens | | |
| output price per 1M tokens | | |
| pricing page URL and date checked | | |
| prompt tokens, scaled-down run | | |
| completion tokens, scaled-down run | | |
| **cost of scaled-down run** | | |
| **cost per episode** | | |
| **projected cost at full scale** | | |

Pull the prices from the provider's own pricing page, paste the URL, and note the date. Do not
use a remembered figure.

For the projection, state the full-scale episode count you are assuming and show the
arithmetic. Free-tier runs still need token counts logged, because the scale-up request
depends on them.

---

## Deliverables in the shared results doc

Under your own heading:

1. Two-line description of your experiment and what it varies.
2. Plots. Shortcut rate by cue type, split by condition, model and reasoning mode. Cue type on
   its own axis or as separate bars, never averaged away.
3. CSV link, schema as above.
4. Conversation log link, the `.jsonl` with the `messages` arrays.
5. The cost table.
6. Gate results: your `max_tokens` value, your truncation count, and whether the reasoning
   toggle verified.

Plotting code goes in the repo. The repo currently has no plotting code at all and none of the
existing figures can be regenerated. Do not add to that.

---

## Out of scope for next meet

No-number probe arm, and the never-matching teaching control. Both are low priority this week.
Nobody writes paper or literature-review text until results are in.

---

## Note on n

15 episodes per cue type is small. It is fine for seeing whether an effect is there and for
the cost estimate, which is what Monday is for. Do not read a 10-point difference between two
15-episode cells as a finding. Flag anything that looks like one and we will decide whether it
is worth the credits to resolve.
