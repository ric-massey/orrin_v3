# Findings — why goals never finish, curiosity spike/decay, and errors found
**Date:** 2026-06-12 · **Run inspected:** fresh-start run begun 2026-06-12 00:16, ~10.7 h of logs (15,668 activity-log lines). Orrin was stopped at the time of this analysis.

---

## 1. Why he can't finish goals

### Root cause: the committed goal's plan is thrown away every cycle (split-brain between the two goal stores)

There are two goal representations, and pursuit progress is written to one while the
committed goal is re-read from the other:

- **Every cycle**, `ORRIN_loop.py:1403-1407` rebuilds `context["committed_goal"]`
  from the **v2 GoalsAPI store** (`data/goals/state.jsonl`) via
  `goal_io.committed_goals_v1()` → `_goal_to_v1()` (`brain/goal_io.py:36-50`).
- `_goal_to_v1()` returns a **fresh dict with no `plan`, no `milestones`, no
  `_step_attempts`, and `status` hard-coded to `"in_progress"`**. Whatever plan
  progress the previous cycle made is not in this dict.
- Meanwhile `pursue_committed_goal()` (`brain/cognition/planning/pursue_goal.py:929-952`)
  faithfully advances the plan and persists it — but into the **v1 tree**
  (`brain/data/goals_mem.json`) via `goal_arbiter.apply(merge_updated_goal_into_tree…)`.
  Nothing ever reads the plan back out of the v1 tree into the context goal.

Net effect per cycle: `get_goal_plan(goal)` is empty → the milestone gate
regenerates the same symbolic 3-step plan → step 1 ("Gather context…") executes →
progress is persisted where nobody looks → next cycle starts from zero. The log
shows **77 occurrences of "Milestone gate: generated plan"** for the *same*
housekeeping goal in ~10.7 h, each time executing only step 1.

Goals therefore only ever close through escape hatches, never through plan
completion:

```
[pursue_goal] Goal 'Housekeeping: daily snapshot (2026-06-12)' closed
              (satiety:novelty_exhausted:search_own_files barren×845)
```

— i.e. it took **845 barren repetitions** of the same search before the satiety
valve fired.

**Fix direction:** either carry `plan`/`milestones`/`_step_attempts` through
`_goal_to_v1()` (hydrate from the v1 tree by goal id when building the context
goal), or stop reloading `committed_goal` from the v2 store when the in-context
goal with the same id already has a plan in flight.

### Aggravating factor A: LLM is disabled, so plans are always the generic template

`brain/data/model_config.json` has `"llm_enabled": false`, so `llm_available()`
(`brain/utils/llm_gate.py:42`) returns False for everything. Every plan is the
symbolic fallback ("Gather context → Reflect on what was found → Write a concrete
next action"). Steps 2–3 are thought-steps that map to no tool, and router
self-assessment stays symbolic too (`Self-assess: weak domain 'PLANNING'
(conf=0.23) — continuing symbolic (LLM tool-only mode)` repeats all run). Even
with the plan-persistence bug fixed, symbolic-only plans rarely satisfy milestone
objectives ("A new fact about X was written to long memory").

### Aggravating factor B: duplicate goal records

`brain/data/comp_goals.json` contains the same goal id (`g_3a933aec31`) **multiple
times** (8 list entries, several being copies of the same goal at different
hours, each independently "completed"). The merge path
(`merge_updated_goal_into_tree`, `goals.py:326`) appends when its (name,
timestamp) match fails, so re-created goals accumulate instead of replacing.

### Observable symptom loop

Orrin himself notices the stagnation: knowledge formation created the rule
**"Sustained reflection without goal-directed action predicts continued
stagnation"** and then formed/applied it **349 times** in 10.7 h (no dedup —
see Errors §3.4). `review_failures_internal` is executed near-continuously,
confirming the selector is spinning on internal review instead of advancing work.

---

## 2. Why curiosity rises extremely fast then drops slowly

"Curiosity" in the UI is the affect signal `exploration_drive`
(mapped at `brain/ORRIN_loop.py:238`). The asymmetry is structural: **pumps are
big and fire every cycle; decay is a small fraction of the gap per call.**

### The fast rise
Every reward event pumps `exploration_drive`
(`brain/affect/reward_signals/reward_signals.py`):

| source | gain per event |
|---|---|
| `reward_signal` | `0.025 × strength × wellbeing × risk` (×1.7 in phasic mode) |
| `novelty` | `0.03 × strength × (1 + 0.5·stagnation)` |
| `connection` | `0.05 × strength` |

Several reward events fire per cognitive cycle (cycles run every ~10–30 s), so
from the 0.30 baseline the drive can hit the ceiling within a handful of cycles —
which on the UI looks like an instant spike.

### The slow drop
Two decay mechanisms exist and both are weak relative to the pumps:

1. The hours-based law (`homeostasis.apply_restoring_forces`,
   `brain/affect/homeostasis.py:70-76`) uses `decay_rate=0.01/hour` with
   `hours_passed ≈ 0.005` per cycle → it removes ~0.005 % of the gap per cycle,
   i.e. effectively nothing (the code comments acknowledge this).
2. The real restoring force is the per-call pull in
   `brain/affect/update_affect_state.py:618`: **2 % of the gap toward the 0.30
   setpoint per `update_affect_state` call**. From 0.9 that's −0.012 on the first
   call and exponentially less as it falls — hundreds of calls to get back near
   baseline. And `update_affect_state` only runs when the selector picks it (or
   when setpoint-regulation force-overrides to it, which happened 62 times this run).

3. On top of that, the information-gain gate that is supposed to stop
   self-reinforcing curiosity **floors at 0.4**
   (`reward_signals.py: _expl_gate = 0.4 + 0.6 × novelty`) — so even
   zero-novelty repetition (the 845 barren searches) keeps refuelling the drive
   at 40 % strength while it is trying to decay.

So: pump ≈ +0.04–0.08 per cycle while active, decay ≈ −2 % of remaining gap per
update call, with a 40 % refuel leak. Fast saturation, long droop — exactly the
shape observed. If a sharper return is wanted, raise the per-call rate at
`update_affect_state.py:618` (e.g. 0.02 → 0.05 for positive drives), lower the
`_expl_gate` floor (0.4 → ~0.1), or make the pump gains decay with repetition.

---

## 3. Errors and problems found

1. **LLM disabled all run** — `model_config.json: llm_enabled=false` while
   `.env` does contain `OPENAI_API_KEY`. If unintentional, flip the config; if
   intentional (tool-only mode), the planning/curiosity issues above are what
   pure-symbolic operation currently produces.
2. **Provenance tag leaked into a goal title** — committed goal:
   `Understand [EXTERNAL/UNTRUSTED source=https more deeply`. A
   `[EXTERNAL/UNTRUSTED source=https://…]` wrapper from working memory was
   ingested as a knowledge-graph *concept name* and passed
   `_acceptable_goal_subject()` (`brain/cognition/intrinsic_goals.py:600-642`).
   The filter needs to reject names containing `[`/`source=`/URL fragments. The
   garbage goal is still pending in `goals_mem.json`.
3. **Duplicate goal records** in `comp_goals.json` (same id stored repeatedly) —
   see §1.
4. **Knowledge-formation dedup missing** — the same `goal_avoidance` rule was
   "formed" 349 times (`conf=0.60, prior_hits=0` every time) and rule
   `1bc68d9a16` re-applied continuously. Formation should match against existing
   rules before creating.
5. **Affect churn under load** — 62 `setpoint_regulation critical override`
   events forcing `update_affect_state`, and 16 `affect_arbiter stability budget
   exceeded` trims in 10.7 h. Symptom of the reward-pump asymmetry in §2.
6. **`think_audit` warnings** — 21 modules bypass the scratchpad wrapper and
   call `generate_response` directly (incl. `planning/goals.py`,
   `planning/pursue_goal.py`, `intrinsic_goals.py`). Audit-only today, but those
   are exactly the allowlist-sensitive call sites.
7. **Stale temp file** — `brain/data/trace.jsonl.hekpxd7t.tmp` (25 MB) left
   behind by an interrupted atomic write; safe to delete.
8. **Minor**: `memory/embedder.py:93` FutureWarning
   (`get_sentence_embedding_dimension` → `get_embedding_dimension`); a leaked
   multiprocessing semaphore warning at shutdown; `run_orrin.sh` auto-restarts
   on any exit (the `exit 143` in the log was the deliberate stop today, not a
   crash).

No Python tracebacks were recorded this run — `error_log.txt`, `failures.jsonl`
and `model_failures.txt` are all empty since the 00:16 fresh start. The damage
is all behavioral (the loops above), not exceptions.
