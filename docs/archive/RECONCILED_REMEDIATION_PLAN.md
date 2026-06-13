# Reconciled Remediation Plan — Closure, Retirement & Selection Balancing

**Status:** Implementation-ready. No further architecture review required.
**Authoritative source:** `docs/` reconciliation audit (supersedes the original
`CRITICAL_REVIEW.md` mechanism and the original response plan where they conflict).
**Date:** 2026-06-08
**Governing stance:** This is a **repair-and-balancing** effort, not a redesign. The
architecture is fundamentally sound. Do **not** add cognition, metacognition, memory, or
new subsystems. Prefer deterministic maintenance, correct retirement, and runtime balance.

---

## Executive Summary

### Current architecture state

Orrin's closure machinery — completion gating, satiety/satisficing, fade→dormant lifecycle,
goal retirement, completion archiving, aspiration roll-up — **exists and is largely correct
code.** The original review's claim that this code is *dead/unreachable* was **falsified** by
the reconciliation audit. The functions are auto-discovered by the cognition registry
(`registry/cognition_registry.py:136`, `iter_modules("cognition")`), bound to real callables,
and (for `fade_goals`) present in the live 281-entry selection candidate pool with a fully
intact dispatch path (`execute_action_via_registries` → `_call_cognition`).

The real defect is **selection starvation**: closure and maintenance functions are
systematically absent from runtime selection history. `decision_stats.json` holds **83**
functions with real decision history; **every** closure/lifecycle function
(`fade_goals`, `prune_goals`, `pause_goal`, `record_lifetime_progress`, `is_sated`) is
**absent**, while exploration functions (`research_topic`, `seek_novelty`) are present and
recur. The cause is structural, not accidental:

- Closure/maintenance functions have **no semantic prior** in `_SEMANTIC_PRIORS`
  (`think/think_utils/select_function.py:165`), so the emotion-cued bandit never surfaces them.
- Several (`prune_goals`, `pause_goal`, `is_sated`) are **non-dispatchable** (they require
  injected args), so they cannot enter the bandit pool at all.
- `fade_goals` *is* dispatchable but, lacking any prior, is out-competed every cycle and has
  **zero** recorded selections.

On top of this sit two concrete correctness bugs and two grounding gaps (below).

### Confirmed bottlenecks

1. **Goal retirement does not run.** Completed/failed/invalid goals accumulate in
   `goals_mem.json` (live: 9 `completed` + 1 `failed` + 1 `None` of 15).
2. **`comp_goals.json` deterministic schema collision.** Within a single `mark_goal_completed`
   call the list archive is written then overwritten by the cooldown dict.
3. **Satiety closure runs through one narrow path** (`pursue_goal.py:523`) — only the actively
   pursued committed goal is ever tested.
4. **Symbolic plans orphan as permanent empties** (live: 3/4 `status:"empty"`, 0 steps).
5. **No motivational weight on the causal graph** and **no practical resource→goal cancellation**.
6. **Selection layer favors exploration over closure** — the dominant, highest-priority issue.

### Expected outcomes after remediation

- `goals_mem.json` stops accumulating terminal/invalid goals (Phase B).
- The completion archive (`comp_goals.json`) becomes a reliable list; the cooldown works on
  its own file (Phase A).
- Sated exploration goals close population-wide, not just in the focus slot (Phase B).
- `symbolic_plans.json` stops filling with empty orphans (Phase A).
- Closure/maintenance actions execute on a **deterministic cadence**, decoupled from the
  emotion-cued bandit, while exploration remains bandit-driven and unchanged (Phase C).
- Resource pressure can pause/deprioritize committed goals via existing signals (Phase D).
- All of the above is observable through a thin metrics accumulator (Phase E).

---

## Root Causes (reconciled only)

### RC1 — Selection starvation of closure/maintenance (dominant)

**Description.** The function-selection layer routes on emotion-cued semantic priors plus a
contextual bandit. Exploration/reflection functions have priors and accumulate reward history;
closure/maintenance functions have neither a prior nor (in most cases) dispatchability, so they
never enter or never win selection.

**Evidence.** `_SEMANTIC_PRIORS` (`select_function.py:165`) maps `stagnation_signal`,
`exploration_drive`, etc. to `seek_novelty`/`search_own_files`/`generate_intrinsic_goals` —
no closure/maintenance function appears in any prior. `decision_stats.json` = 83 functions
with history; closure/lifecycle functions absent. `bandit_state.json` has arms for
`research_topic`/`seek_novelty`, none for `fade_goals`/`prune_goals`/`pause_goal`.

**Architectural impact.** Closure is not "missing" and not "dead" — it is **never scheduled**.
Any fix that relies on the bandit eventually picking these functions is unsound. Maintenance
must move to a deterministic tier.

### RC2 — `comp_goals.json` deterministic schema collision

**Description.** One file (`COMPLETED_GOALS_FILE`, `paths.py:80`) is used under two
incompatible schemas: a **dict** `{title: ts}` cooldown (`intrinsic_goals.py:76–93`) and a
**list** of completed-goal dicts (`goals.py` + 6 readers).

**Evidence.** Inside `mark_goal_completed`: `goals.py:647–649` writes the **list**, then
`goals.py:690–694` calls `_persist_recently_completed()` (`intrinsic_goals.py:91`) which
overwrites the **same file** with the **dict**. Deterministic clobber, every completion. The
list-readers (`evolution.py:209`, `autobiography.py:158`, `goal_auditor.py:49`,
`evaluator_daemon.py:175`, aspiration crediting `intrinsic_goals.py:703`) then receive a dict
and degrade to empty.

**Architectural impact.** The completion archive ("Signal B") is effectively never persisted;
every downstream consumer of completion history is starved.

### RC3 — Goal retirement is unwired

**Description.** `prune_goals` (`goals.py:364`) removes terminal goals from the tree but has
**no caller** and is **non-dispatchable** (positional `List[Dict]`). It also only filters
`{completed, abandoned}` — not `failed`, `cancelled`, or `None`.

**Evidence.** No caller in tree (only unrelated `prune_goals_wal`). `_is_dispatchable` →
False. Live `goals_mem.json`: 11 of 15 goals are terminal/invalid yet still active.

**Architectural impact.** The active goal tree grows monotonically; stale goals keep competing
for attention and inflate every "open thread" count.

### RC4 — Fade/lifecycle never invoked deterministically

**Description.** `fade_goals` (`goal_lifecycle.py:132`) is reachable and dispatchable but
selection-starved (RC1). It is documented to run "every ~60 cognitive cycles" but nothing
schedules it.

**Evidence.** Dispatchable=True, in candidate pool, **0** entries in `decision_stats.json` /
`bandit_state.json`; no execution logs.

**Architectural impact.** No abandonment gradient; the `form_commitment` "faded" clear path
never fires; lifetime-goal weights never decay.

### RC5 — Satiety evaluated too narrowly

**Description.** `is_sated` (`goal_satiety.py:82`) is correct but called from one site
(`pursue_goal.py:523`); only the focus goal is tested.

**Architectural impact.** Exploration goals that have genuinely quenched their drive remain
open unless they happen to be the active committed goal.

### RC6 — Symbolic plans persist as permanent empty orphans

**Description.** `_assemble_plan` (`temporal_planner.py:239`) emits `status:"empty"` when
`_build_plan` returns no steps (novel goals whose tokens aren't in the causal graph);
`_save_plan` (`:245`) persists them; `advance_plan` requires steps, so they never close.

**Evidence.** Live `symbolic_plans.json`: 3/4 empty, 0 steps, `completed_at:null`.

**Architectural impact.** Noise + a misleading "planning is happening" signal. The symbolic
layer is a secondary view; the real execution path is `goal["plan"]` via `pursue_goal`.

### RC7 — No motivational weight / no resource→goal cancellation (grounding, deferred)

**Description.** `causal_graph` edges carry no value/reward/salience weight; `_under_load`
(`intrinsic_goals.py:37`) throttles new-goal *intake* but nothing pauses/deprioritizes
*committed* goals under sustained load.

**Architectural impact.** Lowest leverage; addressed last and only by reusing existing systems.

---

## Phase A — Critical Bugs

### A1 — Completion Archive Collision

**Rationale.** A single file cannot be both a dict and a list. Separating the cooldown from the
archive is simpler and safer than teaching seven readers to accept both shapes, and it
eliminates the deterministic overwrite at the source.

**Requirements satisfied:** separate archive vs cooldown storage; eliminate deterministic
overwrite; preserve backward compatibility for the list archive.

**Implementation steps.**
1. **Add a new path** in `brain/paths.py` next to `COMPLETED_GOALS_FILE`:
   ```python
   RECENTLY_COMPLETED_FILE = DATA_DIR / "recently_completed.json"   # dict {title: ts} cooldown
   ```
2. **Repoint the cooldown** in `brain/cognition/intrinsic_goals.py`:
   - `_load_recently_completed` (`:76–82`) → read `RECENTLY_COMPLETED_FILE` (`default_type=dict`).
   - `_persist_recently_completed` (`:89–93`) → write `RECENTLY_COMPLETED_FILE`.
   - Leave `intrinsic_goals.py:703` (aspiration crediting) reading `COMPLETED_GOALS_FILE` as a
     **list** — it is already correct.
3. **Leave the list archive untouched** in `goals.py` (`:647–649`, `:1113–1116`, `:260–267`),
   `evolution.py:209`, `autobiography.py:158`, `goal_auditor.py:49`, `evaluator_daemon.py:175`.
   With the cooldown writer removed from `COMPLETED_GOALS_FILE`, the `goals.py:690–694`
   `_persist_recently_completed()` call now writes the *new* file, so the archive written at
   `:649` is no longer clobbered. **No code change is needed at `goals.py:690–694`** — only the
   target file moves. (Verify the same for `pursue_goal.py:478–480`.)

**Files affected:** `brain/paths.py`, `brain/cognition/intrinsic_goals.py`. (No change to the
seven list-readers.)

**Migration strategy (one-time, guarded — do not migrate silently).**
- On first load of `RECENTLY_COMPLETED_FILE` when it is absent: if `comp_goals.json` currently
  holds a **dict**, move that dict into `RECENTLY_COMPLETED_FILE` and reset `comp_goals.json`
  to `[]`.
- Normalize `comp_goals.json` to the list schema: if it holds a dict or contains non-completed
  entries (e.g. the 4 aspiration dicts currently present), drop entries whose `status` is not
  `"completed"`/`"failed"`/`"abandoned"` and coerce to a list. Log the normalization counts.
- Implement as a small idempotent `_migrate_comp_goals()` run once at `intrinsic_goals` import
  (guarded by the existence of the new file).

**Validation procedure.**
- Unit: write a completion via `mark_goal_completed`; assert `comp_goals.json` is a **list** and
  contains the new entry **after** the call returns (i.e., not clobbered).
- Unit: assert `recently_completed.json` is a **dict** and suppresses an immediate re-proposal
  of the just-completed title within `_COOLDOWN_S`.
- Property: assert `comp_goals.json` is always a list post-write (add a type assert in test).
- Manual: after one runtime day, `comp_goals.json` length grows with completions; downstream
  `goal_auditor`/`evaluator_daemon` see non-empty lists.

**Expected impact:** Completion archive becomes reliable; aspiration crediting / autobiography /
evaluator receive real completions; cooldown works independently.

**Risk level:** **Low.** The only behavioral change is the file target; migration is guarded
and idempotent.

---

### A2 — Symbolic Plan Orphans

**Rationale.** The symbolic plan layer is a secondary, causal-graph-derived view, not the
execution path (`goal["plan"]` via `pursue_goal` is). Persisting zero-step plans creates
permanent orphans and a false "planning happening" signal. Prefer **not creating** the orphan
over sweeping it later.

**Requirements satisfied:** prevent persistence of zero-step plans; define retirement for
malformed plans; prevent permanent empty accumulation.

**Implementation steps.**
1. **Do not persist zero-step plans.** In `temporal_planner.integrate_goal_plan` (`:49`), after
   `_assemble_plan`, skip `_save_plan(plan)` when `plan["step_count"] == 0`; return the plan
   dict (still useful to the caller) with `status:"unplannable"` but **unpersisted**. The caller
   `intrinsic_motivation.py:216` already falls back to the real `goal["plan"]` path via
   `pursue_goal`, so no behavior is lost.
2. **One-time sweep for existing orphans.** On `temporal_planner` import (guarded, idempotent),
   load `PLANS_FILE`, drop any plan with `status in {"empty","unplannable"}` and `step_count == 0`,
   and re-save. This retires the 3 live empties plus the malformed nested-title entry.
3. **Defensive read.** In `get_plan_stats` (`:251`) and `get_active_plans` (`:75`), filter out
   any residual `status in {"empty","unplannable"}` so stats never count orphans even if one
   slips through.

**Files affected:** `brain/symbolic/temporal_planner.py`.

**Validation procedure.**
- Unit: call `integrate_goal_plan` on a goal whose tokens aren't in the causal graph; assert no
  plan is written to `PLANS_FILE` and `pursue_goal` still produces a real `goal["plan"]`.
- Unit: seed `PLANS_FILE` with an empty plan; import the module; assert it is swept.
- Assert `get_plan_stats()["total"]` counts only step-bearing plans.

**Expected impact:** `symbolic_plans.json` reflects only real plans; planning signal becomes
trustworthy.

**Risk level:** **Low.** Fallback path already exists and is exercised today.

---

## Phase B — Closure Activation

> Closure systems already exist. **Do not build new ones.** Make the existing ones execute
> reliably via a deterministic maintenance tier, decoupled from the emotion-cued bandit.

**Shared infrastructure (used by B1–B3 and Phase C/D): a deterministic maintenance pass.**
Reuse the existing cadence pattern in `brain/ORRIN_loop.py` (~`:2745`, where `credit_aspirations`
already runs on `get_cycle_count() % 25 == 0`). Add a single guarded maintenance block in the
same idle region that calls retirement, fade, and population satiety on slow cadences. This is
the architecture's own established pattern for "upkeep that runs automatically every N cycles"
(cf. the `_ALWAYS_EXCLUDE` rationale in `select_function.py`).

### B1 — Goal Retirement (RC3)

**Rationale.** Retirement must be deterministic, not bandit-dependent. `prune_goals` already
encodes the tree-filter logic; it just needs a caller and a slightly wider terminal set.

**Requirements satisfied:** remove completed, failed, and invalid goals from active stores via a
deterministic path that does not depend on bandit selection.

**Implementation steps.**
1. **Widen the filter.** `prune_goals` (`goals.py:364`) currently keeps `failed`/`None`. Change
   its `is_active` predicate to retire any goal whose status is in `_TERMINAL_STATUSES`
   (`goals.py:208` = `{completed, failed, abandoned, cancelled}`) **and** treat `status in
   (None, "")` invalid goals as retire-eligible **only if** they also lack milestones/subgoals
   (avoid nuking a legitimately in-flight goal that merely lacks a status field — normalize via
   the existing `_norm`/`save_goals` path first).
2. **Wire a deterministic caller.** In the ORRIN_loop maintenance block, on a slow cadence
   (e.g. `% 50`), load goals, run `prune_goals`, and save via the central `save_goals`
   (`goals.py:~213`, which has terminal-status stickiness protection). **Order matters:** run
   retirement strictly **after** `mark_goal_completed` has archived the goal — since retirement
   runs in a separate cycle from completion, this ordering holds naturally, but the maintenance
   block must run *after* any in-cycle completion path, not before.
3. **Do not make `prune_goals` bandit-selectable.** It stays non-dispatchable; retirement is
   upkeep, not a deliberate choice.

**Files affected:** `brain/cognition/planning/goals.py`, `brain/ORRIN_loop.py`.

**Risk level:** **Low–Medium.** Mitigated by `save_goals` stickiness (prevents stale-copy
lost-update) and by archiving before retiring. Add an assert: no goal is dropped from
`goals_mem.json` without a corresponding `comp_goals.json` entry (terminal=completed) — for
`failed`/`cancelled`, archival is optional but log the retirement.

**Validation:** before/after counts of terminal goals in `goals_mem.json` (live 9 completed →
~0 after a maintenance cycle); unit test runs N cycles and asserts the active tree contains no
`_TERMINAL_STATUSES` goal.

**Expected impact:** Active goal tree stops growing; stale goals stop competing for attention.

### B2 — Goal Fading (RC4)

**Where deterministic invocation belongs.** In the same ORRIN_loop maintenance block, call
`fade_goals(context)` on the cadence it was designed for — every ~60 cycles
(`get_cycle_count() % 60 == 0`). `fade_goals` already loads its own state
(`load_lifetime_goals()` + `_fade_regular_goals`) and is self-contained.

**How to avoid double execution / coexist with the dispatchable version.** `fade_goals` is
currently *also* in the bandit candidate pool (dispatchable=True) but has never been selected.
Once we invoke it deterministically, leaving it bandit-eligible creates a latent double-execution
path. **Resolution:** add `fade_goals` (and the other lifecycle maintenance functions) to
`_ALWAYS_EXCLUDE` in `select_function.py:37`. This is exactly the precedent the file already
sets for `update_affect_state` and the `apply_*` pressures — *"Per-cycle UPKEEP that already
runs automatically every cycle … Excluding them from SELECTION loses no behaviour — they still
run automatically."* Deterministic invocation + selection exclusion = runs exactly once, never
double-fires, and stops masquerading as a deliberate choice that never wins.

**Exact reasoning.** `fade_goals` is **idempotent within a cadence window** (it only decays
weight past `_FADE_UNATTEND_SECONDS` and clamps at floors), so even an accidental extra call is
harmless — but excluding it from the bandit removes the ambiguity entirely and keeps the
selection pool honest (only genuine deliberate cognition competes).

**Files affected:** `brain/ORRIN_loop.py`, `brain/think/think_utils/select_function.py`.

**Risk level:** **Low.** Idempotent function; exclusion follows existing precedent. Pre-check:
verify `load_lifetime_goals()` is fail-safe when `LIFETIME_GOALS_FILE` is absent (return `[]`).

**Validation:** unit test asserts a regular goal unattended past threshold transitions to
`dormant` after a maintenance cycle; assert `fade_goals` no longer appears in the
`_load_actions()` candidate pool.

**Expected impact:** Abandonment gradient restored; lifetime weights decay; `form_commitment`
"faded" clear path begins firing.

### B3 — Satiety Expansion (RC5)

**Rationale.** `is_sated` is correct and truthful; it is simply not consulted for non-focus
goals. Broaden *coverage*, not *logic*.

**Design for efficiency / avoiding excessive processing.**
- In the maintenance block, on a **slow cadence** (e.g. `% 40`, never every cycle), iterate
  **only** active goals whose `driven_by`/kind is exploration/understanding (skip task/committed
  goals — they close via milestones). This bounds the population scanned.
- For each, call the existing `is_sated(goal, context)`; on `(True, reason)`, close via the
  existing `mark_goal_completed` (which preserves the hollow-completion guard).
- Cap work per pass (e.g. evaluate at most K goals/cycle, round-robin) so a large backlog never
  spikes latency.
- Keep cadence slow so a transient low-uncertainty reading cannot prematurely close a goal; the
  existing cycle-1 `_did_exploration_work` guard (`goal_satiety.py:69`) and the hollow-completion
  gate remain in force.

**Files affected:** `brain/ORRIN_loop.py` (maintenance block); no change to `goal_satiety.py`.

**Risk level:** **Low–Medium.** Mitigated by slow cadence, the cycle-1 guard, and the
hollow-completion gate. Watch `abandonment_rate`/`completion_rate` in Phase E for over-eager
closing.

**Validation:** seed an exploration goal, drive its topic uncertainty below threshold, run the
maintenance pass, assert it closes with `reason="uncertainty=…"`; assert a goal with unmet
milestones is **not** closed.

**Expected impact:** Sated exploration goals close population-wide, bounding perpetual
exploration.

---

## Phase C — Selection-Layer Corrections (highest architectural priority)

**Why exploration has history and closure does not.** Three compounding structural facts:
1. **Priming/priors.** `_SEMANTIC_PRIORS` (`select_function.py:165`) maps every distress and
   exploration emotion to exploration/reflection/regulation functions. Closure/maintenance
   functions appear in **no** prior, so the bandit is never cued toward them.
2. **Dispatchability.** `prune_goals`, `pause_goal`, `is_sated`, `record_lifetime_progress`
   require injected args → `_is_dispatchable` → False → excluded from the candidate pool
   entirely. They *cannot* be selected regardless of weight.
3. **Bandit incentives.** The one closure function that *is* dispatchable (`fade_goals`) has no
   prior and no accumulated reward, so under emotion-cued routing + reward-weighted bandit it is
   out-competed every cycle → zero history → never accrues reward → permanent starvation
   (a self-reinforcing cold-start trap).

**Principled solution (NOT "increase closure weights").** Reweighting closure functions into the
emotion-cued bandit would be wrong: closure/maintenance is **categorically not a deliberate,
emotion-cued choice** — it is housekeeping that must run on schedule irrespective of mood. The
correct architecture is the one the codebase **already uses** for `update_affect_state` and the
`apply_*` pressures: **a deterministic maintenance tier, explicitly excluded from selection.**

**Plan.**
1. **Establish the maintenance tier** (the ORRIN_loop block from Phase B) as the single home for
   retirement (B1), fade (B2), and population satiety (B3). These run on cadence, deterministically.
2. **Exclude them from selection.** Add the deterministic maintenance functions (`fade_goals`;
   keep the non-dispatchable ones as-is) to `_ALWAYS_EXCLUDE` (`select_function.py:37`), with a
   comment mirroring the existing upkeep rationale. This guarantees:
   - **Closure/maintenance actions receive execution opportunities** — every cadence window,
     unconditionally.
   - **Exploration remains functional and unchanged** — its priors and bandit arms are untouched.
   - **No double execution** — deterministic-tier functions never also compete in the bandit.
3. **Do not add closure priors to `_SEMANTIC_PRIORS`.** That would reintroduce the very
   masquerade we are removing. The emotion-cued pool stays exclusively deliberate cognition.

**Files affected:** `brain/think/think_utils/select_function.py`, `brain/ORRIN_loop.py`.

**Rationale (summary).** This makes the think/act selection pool *honest* (only genuinely
selectable deliberate cognition competes) and makes closure *reliable* (scheduled, not gambled
on a cold-start bandit). It is minimal-change, follows existing precedent, and does not touch
exploration.

**Risk level:** **Low.** No new mechanism; reuses two existing patterns (cadence maintenance +
`_ALWAYS_EXCLUDE`).

**Validation:** assert excluded functions disappear from `_load_actions()`; assert exploration
functions remain in the pool with unchanged priors; Phase E confirms closure-selection counts
(now "maintenance executions") become non-zero while exploration counts hold steady.

---

## Phase D — Resource Grounding (after closure work)

**Rationale.** `_under_load` (`intrinsic_goals.py:37`) already computes a truthful load signal
from existing systems (`energy_mode`, `body_sense`, `health_score`, `resource_deficit`). Reuse
it to influence committed goals — no new subsystem.

**Requirements satisfied:** resource pressure influences committed goals, planning, and
prioritization — by leveraging existing affect/motivation/goal systems.

**Implementation steps (measurement-gated — only after Phase E shows goals pile up under load).**
1. **Committed-goal pause.** In the maintenance block, when `_under_load(context)` returns
   `(True, reason)` **sustained** across a window (e.g. true on ≥3 consecutive maintenance
   passes), call the already-present `goal_lifecycle.pause_goal` on the lowest-priority committed
   goals. `pause_goal` exists and is correct; it is simply invoked deterministically here
   (it is non-dispatchable, so this is its only viable invocation path).
2. **Planning influence.** Gate `integrate_goal_plan` / new-plan generation behind the same
   sustained-load check (skip speculative planning under load) — a one-line guard at the
   `intrinsic_motivation.py:216` call site.
3. **Prioritization influence.** Feed `resource_deficit` as a small negative term into the
   existing goal-weight/attention path (reuse the existing weighting; do not add a new scorer).

**Files affected:** `brain/ORRIN_loop.py`, `brain/cognition/intrinsic_goals.py`,
`brain/symbolic/intrinsic_motivation.py`.

**Risk level:** **Medium** (behavioral). Strictly gated behind Phase E data; ship only if
metrics show committed goals accumulate under sustained load. Resume paused goals when load
clears (use the existing `resume_goal`).

**Note on RC7/causal-graph value weighting:** **Do not build** the
fact→consequence→value annotation yet. It is the lowest-leverage item and the felt-interoception
path already covers the most important resource case. Revisit only if Phase E shows behavior
genuinely fails to adapt to consequences.

---

## Phase E — Measurement and Validation

**Rationale.** Phases A–D change closure behavior; we must see that they worked and gate Phase D
on data. Add **one thin accumulator**, modeled on the existing `symbolic/progress_tracker.py` —
not a cognitive subsystem.

**Change.** New `brain/cognition/planning/outcome_metrics.py` → `data/outcome_metrics.json`
(rolling 90-day daily snapshots). Record at **existing chokepoints only**:

| Metric | Source chokepoint |
|---|---|
| `active_goals`, `average_goal_age` | maintenance pass over `goals_mem.json` |
| `goals_completed`, `mean_significance`, `median_seconds_to_complete` | `mark_goal_completed` (single completion site) |
| `goals_failed` | `mark_goal_failed` |
| `goals_retired` | `prune_goals` maintenance caller (B1) |
| `satiety_closures` | satiety maintenance pass (B3), `reason` startswith `uncertainty`/`novelty` |
| `abandonment_closures` | `fade_goals` dormant transition (B2) |
| `exploration_selections`, `closure_selections`, `maintenance_selections` | read from `decision_stats.json` + maintenance-tier invocation counters |
| Derived: `completion_rate`, `abandonment_rate`, `closure_frequency` | computed at snapshot |

Surface alongside the existing `progress_tracker.report()` output. Keep it to bookkeeping at
existing call sites — **no new instrumentation hooks**, no metrics framework.

**Files affected:** new `outcome_metrics.py`; one-line record calls at the chokepoints above.

**Risk level:** **Low.** Pure bookkeeping.

### Success Criteria (metrics that must improve)
- `active_goals` **stops growing** and `average_goal_age` for terminal goals → ~0 (retirement works).
- Terminal-status goals in `goals_mem.json` → **0** after a maintenance cycle.
- `closure_frequency` and `maintenance_selections` become **non-zero** and recur.
- `satiety_closures` and `abandonment_closures` register **> 0** over a runtime day.
- `comp_goals.json` grows monotonically as a **list**; no dict ever observed post-write.
- `symbolic_plans.json` contains **0** `status:"empty"` entries.
- `exploration_selections` remain in their pre-change band (exploration not regressed).

### Failure Criteria (indicates the fix failed)
- `abandonment_rate` or `satiety_closures` **spike** (fading/satiety too aggressive — goals
  closing that should stay open).
- `exploration_selections` **collapse** (selection-layer change starved exploration).
- `completion_rate` drops or `median_seconds_to_complete` balloons (retirement/fade interfering
  with legitimate in-flight goals).
- Any reappearance of dict-shaped `comp_goals.json` or empty symbolic plans.
- New error-log volume from the maintenance block.

### Rollback Criteria
- **Per-phase, independently revertable.** If a Failure Criterion trips and correlates with a
  specific phase:
  - A1/A2: revert the file/path change; data migration is idempotent and non-destructive
    (archive list preserved), so rollback is safe.
  - B1 (retirement): if legitimate goals are being dropped, disable the `prune_goals` maintenance
    caller (single cadence line) — logic change to `prune_goals` is inert without a caller.
  - B2 (fade): remove the cadence call and the `_ALWAYS_EXCLUDE` additions to restore prior
    (starved) behavior.
  - B3 (satiety): remove the population satiety pass.
  - C: remove `_ALWAYS_EXCLUDE` additions (restores bandit eligibility, which was a no-op anyway).
  - D: gated; disable the load→pause call.
- **Hard rollback trigger:** if `exploration_selections` fall > 30% from baseline OR
  `completion_rate` falls below baseline for 2 consecutive days, revert the most recent phase and
  re-baseline before re-attempting.

---

## Constraints honored

- **No** new cognition, metacognition, memory, self-model, affect, or planner subsystems.
- **No** architecture redesign. Phases A–C are wiring + one bug fix + one guard + one
  `_ALWAYS_EXCLUDE` edit; D and E reuse existing systems.
- **No** new closure *logic* — B1 reuses `prune_goals`, B2 reuses `fade_goals`, B3 reuses
  `is_sated`, D reuses `pause_goal`/`_under_load`.
- The architecture is treated as **fundamentally sound**: this is repair and balancing.

## Implementation order

```
A1 (archive collision)      ── highest confidence, real bug, mechanism-independent
A2 (empty-plan guard)       ── cheap, safe, confirmed
C  (selection tier + exclude) ── establishes the deterministic maintenance home
B1 (retirement)  ┐
B2 (fade)        ├─ land on the Phase-C maintenance tier
B3 (satiety)     ┘
E  (metrics)                ── validates A–B, baselines for D
D  (resource grounding)     ── measurement-gated; ship only if E justifies
```

Rationale for ordering C before B1–B3: the deterministic maintenance tier and the
`_ALWAYS_EXCLUDE` correction are the *home* the closure activations land in; establishing it
first prevents B1–B3 from being written against the (unsound) bandit-selection assumption.

## Definition of done

1. `comp_goals.json` is reliably a list; cooldown lives in `recently_completed.json` (A1).
2. No empty symbolic plans persist or accumulate (A2).
3. Closure/maintenance runs deterministically and is excluded from the selection pool (C).
4. `goals_mem.json` no longer accumulates terminal/invalid goals (B1); stale goals fade to
   dormant (B2); sated exploration goals close population-wide (B3).
5. `outcome_metrics.json` persists the Phase E metrics daily; success criteria are met and
   exploration is not regressed (E).
6. A documented, data-backed decision on whether Phase D resource grounding is warranted.

When 1–5 hold, the cognition-over-closure imbalance is resolved **mechanically** — not by making
Orrin think more, and not by reviving "dead" code (there was none), but by giving the closure he
already has a **deterministic place to run** and removing it from a bandit that never picked it.
