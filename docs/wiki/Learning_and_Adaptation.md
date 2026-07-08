# Learning & Adaptation

Learning in Orrin is not one algorithm — it's several mechanisms, each learning independently from
the reward signal, some immediately and some with delay. The UI's **Learning** room surfaces the
result as before→after→because diffs.

## Immediate learning

- **Function selector** — the main contextual bandit that picks the next cognitive function; updates
  from immediate reward each cycle.
- **`depth_bandit`** (UCB1) — learns how many draft→critique→revise rounds the inner loop should run.
- **`thinking_depth`** — chooses shallow vs. deep reasoning chains for goal pursuit.

## Delayed learning (credit that can't be scored at action time)

- **Evaluator** (`brain/eval/`) — rewards a past decision when a memory it tagged is retrieved
  within ~50 cycles, or its goal closes within ~200. This is how "storing the right memory" or
  "setting up a good goal" eventually pays.
- **Demand-expectations** — learns which actions actually relieve which demands and routes that
  prediction error back into the control signals.

```mermaid
flowchart LR
    A[Decision] --> O[Outcome later]
    O --> E[Evaluator: memory used? goal closed?]
    E --> CR[Credit back to the original decision]
    CR --> B[Bandit / signal update]
```

## Grounded reward

Reward is denominated in **durable outward effects**, not internal churn, via the
[effect ledger](Production_and_Effect_Ledger) — so learning pushes toward producing things, not just
thinking about them. Quality is gated by the [Quality Standard](Quality_Standard).

## Optional self-shaping (OpenAI-only)

`brain/cognition/finetuning/finetune_pipeline.py` filters traces with outcome ≥ 0.65, submits a
fine-tune job, and repoints `model_config.json` on completion so generation drifts toward what has
worked. Symbolic-only mode never touches it.

## Code pointers

- `brain/think/think_utils/select_function.py`, `brain/think/depth_bandit.py`
- `brain/eval/` — delayed-learning daemons
- See also [Action Selection and Bandit](Action_Selection_and_Bandit)
