# HYPOTHESES.md
# Evaluator Hypotheses — Phase 2

> **Note (2026-06-01):** Signal/term names updated to the current computational vocabulary
> (e.g. stagnation_signal for the former "boredom" signal). Hypotheses themselves are unchanged.

These hypotheses guide the design of the delayed-reward evaluator.
Each will be tested once the system has run for ≥200 cycles with the WAL active.

---

## H1 — Useful functions get retrieved more

**Claim:** Cognitive functions whose outputs are retrieved by the memory daemon within
50 cycles will show higher bandit weights over time compared to functions whose outputs
are rarely retrieved.

**Signal:** Signal A (retrieval-within-N-cycles). An output tagged with `decision_id` that
appears in `context["retrieved_memories"]` within N=50 cycles earns `reward = 0.5 + 0.5*decay`.

**Falsification:** If bandit weights do not diverge between high-retrieval and low-retrieval
functions after 500 cycles, Signal A is not adding meaningful gradient.

---

## H2 — Goal-relevant functions close goals faster

**Claim:** Functions selected while a goal is active, if the goal closes within 200 cycles,
contributed to goal closure. Rewarding these decisions will increase their future selection
frequency when similar goals are active.

**Signal:** Signal B (goal closure rate). If `committed_goal_id` at decision time matches
a completed goal within M=200 cycles, `reward += 0.25`.

**Falsification:** If goal closure rate does not increase as bandit weights adapt over
500 cycles, Signal B correlation is spurious.

---

## H3 — Immediate rewards (0.5) are noise without delayed rewards

**Claim:** Replacing `reward = 1.0` (completion signal) with `reward = 0.5` (neutral prior)
reduces false positive learning on functions that completed but left no useful memory trace.

**Rationale:** A function that completes without error is not necessarily useful — the prior
0.5 reflects "ran without crashing," not "moved Orrin forward."

**Test:** Compare `reward_trace.json` distribution before and after Phase 2. The post-phase
distribution should show more spread (values at 0.0, 0.5–0.75, 1.0) rather than a spike at 1.0.

---

## H4 — Stagnation_signal and novelty interact with fitness signal

**Claim:** Functions selected under high stagnation_signal (`stagnation_signal ≥ 0.6`) receive lower delayed
rewards on average because novelty-driven choices are less goal-directed.

**Test:** After 500 cycles, bucket WAL entries by `context.stagnation_signal` at decision time and
compare mean delayed reward per bucket. High-stagnation_signal decisions should average ≤0.4.

---

## H5 — Emotional delta is a leading indicator of retrieval

**Claim:** Function executions that increase `exploration_drive` or `confidence` (positive emotional
delta) are more likely to be retrieved within N cycles than emotionally neutral executions.

**Rationale:** Emotionally salient events are stronger retrieval candidates in the memory
daemon's salience-weighted scoring.

**Test:** Cross-reference `_emo_r` values in `reward_trace.json` against Signal A resolution
in `evaluator_wal.jsonl`. Expect Pearson r > 0.2 between `_emo_r` and retrieval-based reward.

---

## Verification gate (Phase 2)

Boot for 30 minutes (≈180 cycles at 10s/cycle). After that:

- `brain/data/evaluator_wal.jsonl` must contain entries (any pending)
- `brain/data/reward_trace.json` must have >100 entries with ≥3 distinct reward values
- `brain/data/bandit_state.json` must show at least 2 functions with diverged weight magnitudes
  (i.e., `sum(|w_i|)` differs by >0.1 between the top and bottom functions)
