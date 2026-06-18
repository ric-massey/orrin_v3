# Demo Run Fixes — Deep Implementation Plan (2026-06-17)

**Diagnosis source:** `DEMO_RUN_FIXES_2026-06-17.md` (Parts I–IV), in this same folder — not re-argued here.
**Branch:** `finish-desktop-polish`.
**Every code anchor below was re-opened and confirmed against live source on 2026-06-17.**

This plan turns the diagnosis into **exact change sites, the current code at each, the
precise edit, the invariant it enforces, the edge cases it must not break, and a runnable
acceptance check** — so an engineer (or a future session) can execute each item without
re-deriving anything. The 15 work items (W1–W15), their canonical IDs/aliases, the dependency
graph, and the PR slicing are organized into the 7 phases below.

## Implementation status — 2026-06-17

- Implemented: shared action accounting, reward-rate baselines, structured reach outcomes,
  raw distress telemetry, allostatic exploration load, adaptive drift detection, stale-goal
  reconciliation, consequential-cognition credit, keyless reach recognition, reward-rate
  impasse/ejection, neutral-outcome devaluation, grounded drive satisfaction, intrinsic-goal
  stall suppression, idle-monitor floor, active auditors, novelty-memory dedup, and the single
  reach-consummation path.
- Integrated downstream: direct research now grows the knowledge graph; drive tags distinguish
  world/social/internal orientation; self and world mastery receive separate credit; rest
  satisfaction is narrowed; outbound social acts receive partial credit; contact sensing and
  conscious-stream persistence use reconciled/atomic paths.
- Verified: Python compilation, direct behavioral assertions, telemetry/stale-goal assertions,
  and the production frontend build pass. The focused pytest file reports `7 passed`; its
  session teardown fails only because an Orrin process inherited from the previous session is
  actively mutating the live `brain/data` tree guarded by `tests/conftest.py`.
- Still requires a stopped/restarted runtime: the Phase 1 and Phase 3 LLM-up validation runs,
  before/after trace evidence, and long-horizon allostatic/sleep tuning.
- Remaining larger-scope research tracks: W13 reflection-content/autobiography cadence and
  explicit long-memory forgetting policy; W15's separate external sandbox surface. Existing
  domain-action credits already feed the symbolic self-model, but need run evidence.

---

## How to use this plan (read this first)

You don't need to understand the whole brain to do this work. Each item is self-contained:
it names the file and line, shows the code that's there now, gives the exact edit, and ends
with an **acceptance check** you can run to prove it works. Trust the anchors — they were
verified on 2026-06-17 — but **always re-open the file and confirm the line still matches
before editing**, because earlier PRs in the sequence shift line numbers.

**Before you touch code:** skim the matching section of the diagnosis doc (`DEMO_RUN_FIXES_2026-06-17.md`)
for the *why*. This plan deliberately doesn't re-argue it. If a change ever seems to contradict
the diagnosis, stop and ask — don't guess.

**The working loop for every item:**
1. Branch off `finish-desktop-polish` (don't commit straight to it). One PR per the slicing
   table at the bottom — that table is the source of truth for what ships together.
2. Make the edit exactly as written. If reality differs from the "current code" shown here,
   **stop and flag it** rather than improvising — a drifted anchor usually means an earlier PR
   already moved things.
3. Write the unit/regression test named in the item's acceptance block *first* or alongside —
   they live in `tests/`. Run `pytest tests/` and get it green.
4. For items whose acceptance says "(run)", you'll need a live Orrin run to confirm behaviour.
   See `project_restart_procedure` notes / `run_orrin.sh`; ask before kicking off a long run.
5. Respect the **forced order** at the bottom. §0 scaffolding lands first; nothing downstream
   works without it.

**Conventions used throughout:**
- `W1`–`W15` = the 15 work items. `B*`/`C*` = the original finding IDs from the diagnosis doc
  (e.g. "B12", "C5"); they're cross-referenced so you can trace any change back to its evidence.
- `file.py:NNN` = file and 1-based line number, e.g. `ORRIN_loop.py:2862`. Clickable in most editors.
- **`context`** is the per-cycle dict threaded through the whole cognitive loop — most state
  reads/writes go through it. Keys prefixed `_` (e.g. `_leave_pressure`) are internal scratch.
- **Priority legend:** **P0** = root-cause blocker, do first; **P1** = core behavioural fix;
  **P2** = important but not load-bearing; **P3** = larger scope / can trail. Priorities are
  on each item header (e.g. `· P1 ·`).

**A note on the "no magic numbers" theme.** Much of this plan replaces hardcoded thresholds
(`debt >= 8`, "after 10 cycles", etc.) with comparisons of two *learned, running averages*. If
that feels abstract, read §0.3 once — it's the engine the rest of the plan plugs into, and the
"Fidelity review" at the very end explains in plain terms what changed and why. The remaining
constants you'll see (`0.35`, `8.0`, `0.5`, …) are **shape parameters of smooth curves, not
on/off switches** — don't "tidy them up" into thresholds.

**Glossary** (terms that recur; you don't need prior neuroscience):
- **Reward rate / EMA** — an exponential moving average of reward. "Local" rate = recent
  return on the *current* goal; "global" rate = life-long background return. The whole rut
  machinery is "is local below global?".
- **MVT (Marginal Value Theorem)** — the foraging rule "leave the current patch when its
  payoff rate drops below the environment's average." Here: leave a goal when its local reward
  rate falls below the global background. Replaces "give up after N cycles."
- **patch_deficit / leave-pressure** — how far below background the current goal is (0 = fine,
  →1 = leave), and the accumulated drive to switch goals built from it.
- **stagnating** — the state where local rate is materially below background *and* there's
  open `action_debt`. Gates how strict the system gets about what counts as real action.
- **action_debt** — a per-cycle counter that climbs when a committed goal produced no
  consequential action. The phantom inflation of this counter is the P0 root bug (W1).
- **consummation** — the "payoff" reward at the *end* of a satisfying action (e.g. a useful
  web reach), as opposed to the drive that motivated it. W10 collapses ~6 scattered ones into one.
- **allostatic load** — slow-accumulating cost of a drive being chronically off its setpoint;
  lets the system notice a *sustained* problem without over-reacting to a brief spike (W2).
- **LC-NE / tonic gain** — the brain's explore-vs-exploit switch; cited as the rationale for
  making "leave the goal" a smoothly rising probability rather than a hard cutoff.

---

## 0. Shared scaffolding — build these once, three items consume them

Two pieces of machinery are referenced by W1/W3/W7/W8/W9 and by W4/W5/W6/W10. Building
them ad-hoc inside each item is exactly the "patch one lane" anti-pattern that caused the
bug. Build them first, as named modules, and have every consumer import them.

### 0.1 `brain/cognition/action_accounting.py` — the single action-truth authority

**Why:** today "did this cycle act?" is answered in ≥4 disagreeing places
(`ORRIN_loop.py:2132` take_action, `:2849` fallback exec, `:2852` `__acted_this_tick__`
drain, `:2881` watchdog) and the cognition lane (`:2219–2820`) answers it *nowhere*. The
debt accumulator at `:2862` only sees `acted_this_cycle`. One authority function removes
the disagreement.

**Exact contents** (artifact-grounded, no function-name allowlist — an allowlist goes
stale the moment a new research tool is added):

```python
# brain/cognition/action_accounting.py
"""Single source of truth for 'did this cycle produce goal-relevant, consequential
action?'. Every consumer (action_debt, impasse escalation, goal-avoidance metacog,
finalize is_agentic, drive credit) reads THIS, so they can never disagree again.

Grounded in artifacts, not names: a cycle acted iff an external/progressive effect was
measured (a milestone ticked, or env_snapshot moved past the neutral 0.5), or one of the
real action lanes already stamped the discharge flag."""
from __future__ import annotations
from typing import Any, Dict

# env_delta neutral value: delta_reward returns 0.5 for "nothing changed".
_ENV_NEUTRAL = 0.5

def mark_consequential_cognition(context: Dict[str, Any], *, env_r: float | None,
                                 ticked_n: int | None, is_failure: bool,
                                 info_gain: float | None = None) -> bool:
    """Called from the cognition lane once env_r/ticked_n/is_failure are known.
    Records whether this cognition step was a real act, and (if so) stamps the same
    discharge flag the action gate uses. Returns the verdict.

    STATE-DEPENDENT STRICTNESS (the anti-over-externalisation rule). A brain does not
    only reward world-change — internal progress (insight, a resolved prediction) is
    intrinsically consequential (the dopaminergic 'aha'). So when the system is NOT
    stagnating, genuine internal `info_gain` counts as a real act. Only once
    `is_stagnating` (the current goal's local reward rate has fallen below the global
    background — MVT, §0.3) does the bar rise to an EXTERNAL effect, so a *rut* can be
    discharged only by acting on the world, not by more thinking. The gate is therefore
    contextual gain-modulation, not a permanent externalist rule."""
    from cognition.reward_rate import is_stagnating
    external = (not is_failure) and (
        (int(ticked_n or 0) > 0)
        or (env_r is not None and float(env_r) > _ENV_NEUTRAL)
    )
    internal = (not is_failure) and (info_gain is not None and float(info_gain) > 0.0)
    produced = external or (internal and not is_stagnating(context))
    if produced and context.get("committed_goal"):
        context["_consequential_cognition_this_cycle"] = True
        context["__acted_this_tick__"] = True   # drained into acted_this_cycle at loop :2852
    return bool(produced)

def cycle_produced_goal_action(context: Dict[str, Any]) -> bool:
    """The authority every downstream consumer reads. Pure (no mutation)."""
    if not context.get("committed_goal"):
        return False
    if context.get("__acted_this_tick__"):                       # gate / pursue / take_action
        return True
    if int(context.get("_milestones_ticked_this_cycle", 0) or 0) > 0:
        return True
    return bool(context.get("_consequential_cognition_this_cycle"))

def reset_cycle_action_flags(context: Dict[str, Any]) -> None:
    """Clear per-cycle scratch at cycle start so flags never leak across cycles."""
    context["_milestones_ticked_this_cycle"] = 0
    context.pop("_consequential_cognition_this_cycle", None)
```

**Edge cases the regression test must cover:** `mark_consequential_cognition` must return
`False` (and stamp nothing) when `is_failure` is True OR `env_r == 0.5` with `ticked_n == 0`
**and** `info_gain` is 0/None — otherwise W1 becomes a blanket discharge and the *real* stall
detector goes blind. It must also cover the state-dependent split: with `info_gain > 0` and
no external delta it returns **True when healthy** (`is_stagnating` False) but **False once
stagnating** — proving internal progress is rewarded normally yet a rut still demands an
outward act to clear.

### 0.2 `ReachOutcome` — the structured curiosity result (W4, used by W5/W6/W10)

**Why:** `seek_novelty`/`look_outward` return bare prose, so every downstream consumer
re-derives intent by sniffing substrings (`"Searching:" in result` at `seek_novelty.py:201`
is the live bug). A typed result kills the string-sniffing at the source.

Put it in `brain/cognition/exploration_value.py` (already the home of `record_reach_outcome`
and `_info_gain`, so the dataclass and its scorer live together):

```python
from dataclasses import dataclass, field

@dataclass
class ReachOutcome:
    mode: str                       # "memory" | "dormant_goal" | "question" | "world" | "home"
    acted: bool                     # did a real sub-action run (not a self-question fallback)?
    is_external: bool               # did it touch the world (wiki/research/web) vs internal?
    info_gain: float = 0.0          # 0..1, from _info_gain(); the consummation driver
    created_memory: bool = False
    satisfied_curiosity: bool = False
    inner_fn: str = ""              # realized sub-action, e.g. "wikipedia_search" (for W6/C6)
    text: str = ""                  # human-readable summary (logging only; never parsed)
```

`seek_novelty`/`look_outward` keep returning their `str` for callers that log it (the
`text` field), but **also** stash the `ReachOutcome` on `context["_last_reach_outcome"]`
so the loop's accounting reads fields, not prose. This keeps the change backward-compatible
with every existing string caller while giving the new consumers structured truth.

### 0.3 `brain/cognition/reward_rate.py` — adaptive baselines (replaces every fixed threshold)

**Why:** the diagnosis is full of hardcoded constants — `debt >= 8`, the last-`recent[-8:]`
variety window, a 10-cycle mode timer, `_DELIBERATION_LOCKOUT_DEBT = 5`,
`_FORCE_ACTION_MAX_CYCLES = 4`. Every one is a magic integer that is (a) brittle, (b)
cycle-speed-dependent (the C12 two-timebase bug), and (c) **biologically wrong**: brains do
not "give up after N cycles", they leave a depleting patch when its **local reward rate falls
below the global background rate** (Marginal Value Theorem, Charnov 1976; the dACC / locus-
coeruleus foraging computation). This module supplies that relative baseline so the rut
machinery scales *continuously* instead of switching at a constant. **Every downstream item
(W1 state-gate, W3 escalation/eject, W7 satiation) reads these — there is one definition of
"stagnating" and it is always a comparison of two live, learned rates.**

```python
# brain/cognition/reward_rate.py
"""Adaptive, reward-rate-relative baselines. 'When to leave the current goal' is decided by
comparing the LOCAL reward rate (this committed goal) to the GLOBAL background rate (the
long-run average across life) — never a hardcoded cycle count. Implements the Marginal Value
Theorem patch-leaving rule and the tonic-LC explore/exploit switch as continuous functions."""
from __future__ import annotations
import math, random
from typing import Any, Dict

# Smoothing factors, not cycle counts, so baselines are invariant to loop speed (pairs with
# the C12 single-timebase fix). Global is ~25x slower than local: life-scale vs recent-window.
_GLOBAL_ALPHA = 0.002   # life-scale background rate
_LOCAL_ALPHA  = 0.05    # current-goal recent rate

def update_reward_rate(context: Dict[str, Any], *, reward: float,
                       committed_goal_id: str | None) -> None:
    """Once per cycle, after the reward blend. Maintains a persistent global EMA and a
    per-goal local EMA. On a goal switch the local rate is RE-SEEDED at the global baseline
    (neutral prior) — never zeroed — so a fresh goal isn't instantly judged a failure (a new
    patch gets the benefit of the doubt)."""
    g = float(context.get("_global_reward_ema", reward))
    g += _GLOBAL_ALPHA * (reward - g)
    context["_global_reward_ema"] = g
    if committed_goal_id != context.get("_local_rate_goal_id"):
        context["_local_reward_ema"] = g
        context["_local_rate_goal_id"] = committed_goal_id
    l = float(context.get("_local_reward_ema", g))
    context["_local_reward_ema"] = l + _LOCAL_ALPHA * (reward - l)

def patch_deficit(context: Dict[str, Any]) -> float:
    """MVT leave-signal in [0,1]: how far the current goal's local rate has fallen BELOW the
    global background, normalised by the background. 0.0 = at/above background (stay);
    ->1.0 = local return has collapsed relative to what life usually yields (leave). This
    continuous value replaces every `debt >= N`."""
    g = float(context.get("_global_reward_ema", 0.0))
    l = float(context.get("_local_reward_ema", g))
    if g <= 1e-6:
        return 0.0
    return max(0.0, min(1.0, (g - l) / g))

def accrue_leave_pressure(context: Dict[str, Any]) -> float:
    """Integrate the deficit into a 'leave pressure' that CHARGES proportional to how far
    below background we are and BLEEDS as the local rate recovers — then damp it by a
    refractory factor after a recent switch (so it can't oscillate, the creative<->adaptive
    limit cycle in the run). Returns the current pressure. No step function anywhere."""
    deficit = patch_deficit(context)
    p = float(context.get("_leave_pressure", 0.0))
    p = p + deficit * (1.0 - p) - (1.0 - deficit) * 0.10 * p
    p *= _refractory_factor(context)
    context["_leave_pressure"] = max(0.0, min(1.0, p))
    return context["_leave_pressure"]

def should_force_switch(context: Dict[str, Any]) -> bool:
    """Stochastic patch-leave: the per-cycle hazard rises SMOOTHLY with accrued leave pressure
    (a survival function, no fixed cutoff). Gain-modulated like tonic LC-NE — the longer the
    local rate stays below background, the higher the probability of disengaging. Records a
    switch so the refractory damping engages."""
    p = float(context.get("_leave_pressure", 0.0))
    hazard = 1.0 - math.exp(-p / 0.35)        # 0.35 shapes the curve; it is not a trigger point
    if random.random() < hazard:
        context["_last_switch_cycle"] = int(context.get("_cycle_index", 0) or 0)
        context["_leave_pressure"] = 0.0
        return True
    return False

def _refractory_factor(context: Dict[str, Any]) -> float:
    """1.0 long after a switch, ->0 right after one; recovery lengthens if switches are coming
    fast (anti-oscillation)."""
    last = context.get("_last_switch_cycle")
    if last is None:
        return 1.0
    age = int(context.get("_cycle_index", 0) or 0) - int(last)
    return max(0.0, min(1.0, age / (age + 8.0)))

def is_stagnating(context: Dict[str, Any]) -> bool:
    """The state that gates how strict action-credit / drive-satisfaction should be (W1, W7).
    True when the local rate is materially below background — a RELATIVE condition re-evaluated
    every cycle against a learned baseline, never a constant count."""
    return patch_deficit(context) >= 0.5 and int(context.get("action_debt", 0) or 0) > 0
```

The constants here (`0.10`, `0.35`, `8.0`, the `>= 0.5` in `is_stagnating`) are **shape
parameters of continuous functions, expressed relative to a learned quantity** — not trigger
points where behaviour switches on. The *decision* is always a comparison of two live EMAs
(local vs global reward rate), so the whole rut machinery self-tunes to whatever return
Orrin's environment actually yields, at any loop speed. No fixed cycle-count threshold
survives anywhere downstream.

---

## Phase 0 — independent, ship-first (W2, W11, W12)

### W2 — Stop the dashboard hiding distress  ·  P1  ·  `brain/ORRIN_loop.py:194–243`

Three separate compressions, all in `_emit_affect`. Confirmed current code:

- `:230` `valence=_clamp01(0.5 + 0.5 * _f(a.get("valence")))` — raw 0.178 → shown 0.589.
- `:224` `distress = _clamp01(negative_load(a) / 2.5)` — impasse 0.65 → distress 0.26.
- `:211–217` `homeostasis = _clamp01(1.0 - (mean(devs)) * 1.6)` over **every** core signal's
  deviation from `setpoint(k)`. `exploration_drive` rests ~0.85 ≫ its setpoint, dragging
  homeostasis to ~0.78 with nothing wrong.

**Changes:**
1. **Add raw channels** (don't remove the remapped ones — the Face needs the centred value;
   the Brain charts need the truth). In the `tb.affect(...)` call add:
   ```python
   valence_raw=_f(a.get("valence")),                       # −1..1, uncompressed
   impasse_raw=_clamp01(_f(cs.get("impasse_signal"))),     # the real 0.65, charted directly
   ```
   Then add `valence_raw` and `impasse_raw` as series in the Brain affect chart component
   (frontend) — a follow-the-data task once the fields exist in telemetry.
2. **Chart impasse directly** rather than only through the `/2.5` distress divisor. Keep
   `distress` for the Face, but the Brain panel should plot `impasse_raw`.
3. **Don't normalise the pathology — down-weight, then track it as allostatic load.**
   Raising `exploration_drive`'s setpoint to its observed resting value (~0.8) would make
   homeostasis *tautological*: it could no longer register that a chronically pinned
   exploration drive is **itself** the disease (the whole of B12). That cures the sensor by
   blinding it. Instead, in `affect/setpoints.py` keep exploration's evolutionarily-meaningful
   setpoint but **down-weight its contribution** to the homeostasis deviation mean (so a brief
   curiosity spike no longer reads as "something off"), AND in `affect/homeostasis.py` add a
   slow `allostatic_load` accumulator that integrates *sustained* deviation of
   `exploration_drive` above setpoint over a long horizon:
   ```python
   # Brief deviation is free; a drive parked above setpoint for hours accrues load.
   dev = max(0.0, float(core.get("exploration_drive", 0.0)) - setpoint("exploration_drive"))
   load = float(state.get("allostatic_load", 0.0))
   state["allostatic_load"] = max(0.0, min(1.0, load + 0.01 * dev - 0.01 * (1 - dev)))
   ```
   That load is the genuine signal B12/W7 consume to pull the drive down — not the moment-to-
   moment homeostasis reading. (Allostasis = stability through change; setpoints may move, but
   chronic *unmet* deviation must still cost something — McEwen's allostatic load. The `0.01`
   rates are horizon shape, not a trigger.)

**Acceptance (run):** during the next rut, the Brain panel's `valence_raw` trends toward 0
and `impasse_raw` sits ~0.65 (visibly red); a *transient* `exploration_drive` spike no longer
drags homeostasis, but a multi-hour pinned drive shows `allostatic_load` rising toward 1.
**Unit:** feed `_emit_affect` a state with `valence=0.178, impasse_signal=0.65` and assert the
bridge received `valence_raw≈0.178`, `impasse_raw≈0.65`; feed a sustained high
`exploration_drive` and assert `allostatic_load` climbs while homeostasis stays near 1 for a
single-cycle spike.

### W11 — Kill the `adaptive→adaptive` no-op  ·  P2  ·  `brain/affect/affect_drift.py`

Confirmed: `"adaptive"` is in the gentle-reflection set (`:95`), and after any intervention
`:132` calls `set_current_mode("adaptive")` **unconditionally**, and `:133` logs the reset.
When already `adaptive`, the 10-cycle persistence counter re-flags it forever (3,415 resets
last run, 178 literal no-ops), each firing a gentle-reflection LLM call + novelty reward.

**Changes (do both):**
1. **Remove `"adaptive"` from the gentle set** at `:95` — it is the resting/recovery target,
   not a drift to escape. New set: `{"exploratory", "focused", "curious", "quiet"}`.
2. **Guard the reset** at `:131–133`:
   ```python
   if current_mode != "adaptive":
       set_current_mode("adaptive")
       log_private(f"Orrin reset mode from {current_mode} to adaptive due to emotional drift.")
   else:
       drift_tracker[current_mode] = 0   # already home; damp the counter, no reward, no LLM
   ```
   Note `:80`/`:117` already zero `drift_tracker[current_mode]` inside each branch, so with
   `"adaptive"` removed from `:95` the gentle branch no longer fires for it at all; the guard
   at `:132` is belt-and-suspenders for any future path that lands here in `adaptive`.
3. **Replace the fixed 10-cycle persistence trigger with an affect-deviation gate (variable).**
   Today the watchdog fires on bare mode *persistence* (held N=10 cycles), which is exactly why
   it thrashes a contented mode. A mode should only be "escaped" when affect is actually
   drifting, and how long it may persist should scale with how *settled* affect is — not a
   constant. Gate the intervention on a running drift magnitude `mean(|signal − setpoint|)` over
   the core affect channels, measured **relative to its own recent variability** (an EMA-
   normalised deviation / z-score), and fire only when normalised drift exceeds its recent band:
   ```python
   drift = _mean_abs_dev(core)                      # mean |signal - setpoint|
   mu = ema(context, "_drift_mu", drift); sd = ema_abs(context, "_drift_sd", drift - mu)
   if (drift - mu) > 2.0 * (sd + 1e-6):             # drifting vs his OWN recent band, not a count
       intervene()
   ```
   A mode the system is calm in persists indefinitely; a mode it's straining in is escaped
   quickly. No fixed 10.

**Acceptance:** grep the next run's log for `reset mode from adaptive to adaptive` → 0 hits;
gentle-reflection LLM-call rate drops materially; mode changes correlate with affect change
(an intervention only fires when normalised drift breaks its recent band, never on persistence
alone).

### W12 — Stale-copy goal re-open loop  ·  P2  ·  producer hunt is over

The guard is `goals.py:save_goals` (`:212–250`) — it correctly restores a terminal goal that
an incoming tree tries to re-open, and logs `blocked re-open of terminal goal … by a stale
copy` (`:245`). That log line dominated ~30 min of the run, so **a writer re-presents a
completed-goal copy every cycle.** The producers are the **~20 uncoordinated
`merge_updated_goal_into_tree(...)` calls in `pursue_goal.py`** (`:458,482,575,685,768,942,
1190,1218,1250,1358,…`) plus `ORRIN_loop.py:2349`. Each merges an **in-memory `goal` dict
the lane has been holding** back into the tree; if that goal was completed on disk after the
lane captured it, the merge re-opens it and the guard slaps it back — every cycle.

**Change (fix at source, not just block):** the in-memory copy must be reconciled to terminal
state *before* it is merged, so it never presents a stale `in_progress`. Add a tiny helper in
`goals.py` and call it at the top of `merge_updated_goal_into_tree`:
```python
def _reconcile_to_disk_terminal(goal: dict) -> dict:
    """If this goal is already terminal on disk, adopt that status before merging —
    so a lane holding a pre-completion copy can't re-open it (the guard then never trips)."""
    if not isinstance(goal, dict):
        return goal
    gid = goal.get("id") or goal.get("title") or goal.get("name")
    for n in _flatten(load_json(GOALS_FILE, default_type=list) or []):
        if (n.get("id") or n.get("title") or n.get("name")) == gid \
           and str(n.get("status", "")).lower() in _TERMINAL_STATUSES:
            goal["status"] = n["status"]
            return goal
    return goal
```
This moves the reconciliation one step earlier than the `save_goals` guard, so the churn
(load→mutate→merge→guard-restore→save) collapses: the merge no longer carries a re-open.

**Acceptance:** the `blocked re-open` line stops recurring every cycle (occasional is fine —
genuine races still get caught by the `save_goals` guard); wasted cycles measurably drop.

---

## Phase 1 — W1: phantom `action_debt` (P0 root cause)

This is the root. Builds on §0.1. Implements Part IV Fix A+B as one change.

### Current state (verified, do not re-derive)
- Cognition lane `:2219–2820` never assigns `acted_this_cycle`. The only writers are
  `:2132, :2849, :2852, :2881`.
- `:2862` `context["action_debt"] = 0 if acted_this_cycle else +1`, gated on `committed_goal`.
- `_env_r` is computed at `:2369`, `_ticked_n` at `:2324`, `_is_failure` at `:2393` — all
  **before** the reward blend at `:2437`. This is the insertion window.
- `research_topic`/`wikipedia_search` have **0** occurrences of `__acted_this_tick__` (they
  never self-stamp), confirming the cognition-pick research call can't discharge debt today.

### Step 1.1 — cycle-start cleanup (`:1901`, next to `acted_this_cycle = False`)
```python
from cognition.action_accounting import reset_cycle_action_flags
reset_cycle_action_flags(context)
```

### Step 1.2 — record the milestone count where it's already computed (`:2324`)
Right after `_ticked_n = _tick_ms(context)`:
```python
context["_milestones_ticked_this_cycle"] = int(_ticked_n or 0)
```

### Step 1.3 — credit consequential cognition (insert after `:2398`, before the blend at `:2437`)
```python
from cognition.action_accounting import mark_consequential_cognition
_ro = context.get("_last_reach_outcome")
mark_consequential_cognition(context, env_r=_env_r, ticked_n=_ticked_n, is_failure=_is_failure,
                             info_gain=(getattr(_ro, "info_gain", None) if _ro else None))
```
That single call stamps `__acted_this_tick__`, which the existing drain at `:2852`
(`acted_this_cycle = acted_this_cycle or bool(context.pop("__acted_this_tick__", False))`)
turns into `acted_this_cycle`, which the existing `:2862` turns into `action_debt = 0`. **No
new plumbing into the debt line** — the existing drain does it. Passing `info_gain` is what
lets internal progress discharge debt *when healthy* while a *rut* still demands an outward
act (the state-dependent rule in §0.1) — so the fix breaks the rumination loop without
encoding a permanent "only world-change counts" value system.

### Step 1.5 — feed the adaptive baseline (after the reward blend at `:2437`)
The MVT baselines (§0.3) need the *blended* reward, so update them once it exists:
```python
from cognition.reward_rate import update_reward_rate
update_reward_rate(context, reward=float(_blended_reward),
                   committed_goal_id=(context.get("committed_goal") or {}).get("id"))
```
This is the single per-cycle write that makes `is_stagnating` / `patch_deficit` truthful for
every consumer in W1/W3/W7. It must run every cycle (acted or not) so the local rate reflects
real return, not just active cycles.

### Step 1.4 — route the authority fn into the *other* consumers (the part V1 hand-waved)
The debt line is fixed by 1.3, but four other places independently decide "did he act?" and
will still disagree unless they read the authority:
- **`finalize.py:132–137`** `is_agentic` — today `is_agentic_action(next_function)` is always
  False for a cognition pick, then re-checked via `__acted_this_tick__ + AGENTIC_TYPES`.
  Replace the re-check with `or cycle_produced_goal_action(context)` so consequential
  cognition earns the agentic reward (this is the "starves the correct action of reward" half
  of A1).
- **goal-avoidance metacog** (the detector that emits *"Goal avoidance: N cycles without
  taking action on '…'"*, consumed by `behavioral_adaptation._classify` at `:93`) — must count
  a cycle as action when `cycle_produced_goal_action(context)` is True, or it re-fires the
  false alarm that filled `behavior_changes.json` 247/250.
- **`goal_progress`** (`_last_progress_cycle`) — already keys off `_ticked_n` (`:2338`), so it
  is consistent; no change, but assert it in the test.
- **W3's impasse escalation** (Phase 3) reads `action_debt`, now truthful — no extra wiring.

### Acceptance (Part IV.4 verification plan, made concrete)
1. **Unit (`tests/test_action_accounting.py`):** `mark_consequential_cognition(ctx,
   env_r=0.7, ticked_n=0, is_failure=False)` with a committed goal → returns True, sets both
   flags; `cycle_produced_goal_action(ctx)` → True.
2. **Regression (same file):** `env_r=0.5, ticked_n=0, is_failure=False` → returns False,
   stamps nothing, `cycle_produced_goal_action` → False (debt must still climb on a
   no-artifact step). And `is_failure=True` with `env_r=0.9` → False (a failed step never
   discharges).
3. **Run:** the *"Goal avoidance: N cycles without taking action on 'Understand mathematics'"*
   alarm stops firing while research executes `status=ok`; `emit_trace`'s `debt` field
   (`:2913`) tracks genuine inaction only.

---

## Phase 2 — W4 + W5: structured outcomes & the discarded reach

### W4 — `ReachOutcome` in `seek_novelty`/`look_outward`  ·  builds §0.2  ·  P2 (unblocks P1 items)
- `seek_novelty.seek_novelty` (`:75–98`): each `mode` branch already knows its mode and what
  it did. Construct a `ReachOutcome` per branch and stash it:
  - `memory` → `ReachOutcome("memory", acted=False, is_external=False, created_memory=bool(reflection))`
  - `dormant_goal` → `ReachOutcome("dormant_goal", acted=False, is_external=False, created_memory=...)`
  - `question` → `ReachOutcome("question", acted=False, is_external=False, created_memory=...)`
  - `explore` (`_trigger_exploration_goal`) → see W5 below; `is_external=True, acted=True`
    when the reach succeeded.
  Stash on `context["_last_reach_outcome"]` and still `return result` (the `text`).
- `look_outward.look_outward`: on both the keyless path (`:65 return _result`) and the SERPER
  path (`:103 return f"Searching: {query}"`), build the outcome with `inner_fn` set to the
  realized sub-action (`wikipedia_search`/`research_topic`/`web_search`) and `info_gain` from
  the value it already passes to `record_reach_outcome` (`:62`).

**Acceptance:** callers branch on `context["_last_reach_outcome"]` fields; no new substring
tests are introduced.

### W5 — World-reach no longer silently discarded  ·  P1, cheapest single win  ·  `seek_novelty.py:196–207`
Confirmed bug: `_trigger_exploration_goal` accepts the reach **only if `"Searching:" in
result`** (`:201`). `look_outward` emits `"Searching:"` **only on the SERPER path** (`:103`);
the default keyless demo path returns the actual Wikipedia/research text (`:65`), which has no
`"Searching:"`. So a *working* reach falls through to a redundant `_generate_question()`
(`:207`). The reach's habituation still fires (`look_outward.py:62` calls
`record_reach_outcome` before returning) — what's lost is the **recognition**: the
`log_activity` exploration-credit is dropped and a self-question is piled on top.

**Change:** replace the `"Searching:"` test with an error-sentinel test, and once W4 lands,
branch on the structured field:
```python
result = look_outward(context)
ro = context.get("_last_reach_outcome")
reached = bool(ro and ro.acted) if ro else bool(
    result and not str(result).lstrip().startswith(("❌", "⚠️"))
    and "Couldn't form" not in str(result)
)
if reached:
    log_activity(f"[stagnation_signal] Exploration via look_outward: {str(result)[:80]}")
    return result
# else fall through to _generate_question(context)
```

**Acceptance:** with no `SERPER_API_KEY`, a successful Wikipedia/research reach is recognized
as an outward action, earns the `log_activity` credit, and is **not** followed by a fallback
self-question.

---

## Phase 3 — reconnect the correctives (depends on W1)

### W3 — Re-key impasse + behavioral eject (variable, reward-rate-relative)  ·  P1
**Affective half — `brain/cognition/cognitive_cost.py:142–172`.** Confirmed: impasse keys on
`cycles_active` of the *current* goal, resets on `_tension_goal_id` change (`:150–153`),
caps at `+0.15` (`:162`), and the file has **no reference to `action_debt`**. So impasse
restarts near zero on every goal rotation and never compounds across the rut.

Add a **deficit-driven term that survives goal switches and scales continuously** — *no*
`debt >= 8` step. It reads the MVT patch-deficit (§0.3), so it escalates exactly in proportion
to how far the current goal's local reward rate has fallen below Orrin's global background
rate, and it is **coupled to an available escape** (the no-dead-end invariant — see below):
```python
from cognition.reward_rate import patch_deficit, accrue_leave_pressure
deficit = patch_deficit(context)            # 0..1, local rate vs global background (both learned)
accrue_leave_pressure(context)              # integrate for the behavioural half
# Continuous escalation: scales with the deficit, saturates toward 1, never a fixed cutoff,
# and cannot restart on goal rotation (the deficit is measured against the PERSISTENT global EMA).
if context.get("_escape_available", True):
    cur = float(core.get("impasse_signal", 0.0))
    core["impasse_signal"] = min(1.0, cur + 0.25 * deficit * (1.0 - cur))
    if deficit > 0:
        context["_impasse_reason"] = f"local reward rate ~{deficit:.0%} below background (stall)"
else:
    # No behavioural exit available this cycle → CONVERT, don't accumulate into a corner.
    context["_force_disengage_goal"] = True
```
This is the locus-coeruleus adaptive-gain story in software: tonic "leave" drive rises smoothly
as local return stays below background. The escalation is monotone in a *relative, learned*
quantity, not a counter — so it neither restarts on rotation nor caps at a magic 0.15.

**The no-dead-end invariant (the one that keeps this from being a depression generator):**
impasse may rise **only while a behavioural escape is actually available**. Escalating,
unresolvable distress with no exit is the learned-helplessness setup (Maier–Seligman). The
behavioural half must therefore set `_escape_available = False` whenever the suppression below
would leave *zero* selectable candidates, and in that case impasse holds and the goal is
disengaged rather than ramped further.

**Behavioral half — `brain/cognition/behavioral_adaptation.py:184–215`.** Confirmed: the
`goal_avoidance` branch sets `_force_action_next`, a fixed `_FORCE_ACTION_MAX_CYCLES (4)`
budget, and `_suppress_goal_deliberation` at a fixed `debt >= 5`. **Replace both fixed counts
with the stochastic patch-leave (§0.3) and make the suppression state-based (it lifts on
recovery), not a countdown:**
```python
from cognition.reward_rate import should_force_switch, patch_deficit, is_stagnating
if is_stagnating(context) and should_force_switch(context):   # hazard rises smoothly with pressure
    context["_force_action_next"] = True
    context["_suppress_goal_deliberation"] = True
    context["_suppress_intrinsic_goals"] = True               # NEW — exclude the intrinsic class
# Suppression is cleared by RECOVERY, not a clock: when the local rate climbs back to background
# (patch_deficit ~0) drop the flags. The lockout therefore lasts exactly as long as the stall —
# no _FORCE_ACTION_MAX_CYCLES, no _DELIBERATION_LOCKOUT_DEBT constant survives.
if patch_deficit(context) < 0.1:
    for k in ("_suppress_goal_deliberation", "_suppress_intrinsic_goals", "_force_action_next"):
        context.pop(k, None)
```
The **gap V1 identified is real**: none of the old flags excluded the *intrinsic goal class*,
so "forced action" was satisfied by selecting yet another `intrinsic-*` goal. In
`select_function`/`goal_arbiter` candidate assembly, when `_suppress_intrinsic_goals` is set,
drop goals where `source == "intrinsic"` or `str(id).startswith("intrinsic-")` or `"intrinsic"
in tags` from the selectable set (class markers confirmed at
`intrinsic_goals.py:1200–1206,1406–1412`). **Before** committing that suppression, assert at
least one non-intrinsic candidate remains; if none does, set `_escape_available = False` so the
affective half disengages the goal instead of escalating into a corner.

**Acceptance:** impasse rises monotonically across goal-rotations during a real stall and in
*proportion to the reward-rate deficit* (not a step at a magic debt count); a high-impasse rut
terminates in an *external* action attempt (or a non-intrinsic goal) once the stochastic
leave-hazard fires, and the suppression lifts the moment the local reward rate recovers — with
**no fixed-cycle budget anywhere**. Assert impasse never climbs while `_escape_available` is
False, and that the switch never oscillates (refractory damping holds after a recent switch).

### W7 — Learning/curiosity lever  ·  P1
- **B1 devaluation:** extend the existing outcome-devaluation (`project_learning_diagnosis_fix`)
  so a high-n, high-confidence `neutral` outcome applies a mild boredom penalty that decays
  the action's selection share. `seek_novelty` was learned `neutral` at conf 0.91 over 803
  obs and kept its pull — that's the target.
- **C5 info-gain gate — `drive_engine.py:248–250`:** confirmed: exploration is satisfied
  (`satisfy("exploration", 0.20)`) whenever `fn not in recent[-8:]` — pure function-variety.
  Gate it on realized info-gain instead: only satisfy when `context["_last_reach_outcome"]`
  reports `info_gain > 0` (or a non-zero `env_snapshot`/KG delta). Internal function-switching
  alone must stop discharging exploration.
- **B12 satiation:** let the devaluation/info-gain gate actually *lower* `exploration_drive`
  so it can fall below ~0.85 and stop re-pumping empty `seek_novelty`/`look_outward`. The
  satiety store (`exploration_value.record_reach_outcome`) already rises on empty reaches;
  wire that satiety into the drive so the loop closes.

**Acceptance:** an action learned `neutral` at high n/conf loses selection share; internal
function-switching alone stops discharging exploration; `exploration_drive` falls after
sustained neutral novelty instead of parking at ~0.85.

### W8 — Hollow-success gate (B2 + B11 + C8, ship together)  ·  P1
- **B11 — `finalize` + goal-completion path:** 99% of cycles were `thrash=True`
  (`delta_reward=0.000`) yet thousands of completions were reported. Gate goal-step success /
  completion reward on a **non-zero `env_snapshot` delta** (the same `_env_r > 0.5` signal W1
  trusts) or an explicit verified artifact. The milestone-completion path at
  `ORRIN_loop.py:2340–2353` already re-checks milestones via `mark_goal_completed` (hollow
  guard) — extend that discipline to the *reward*, not just the status flip.
- **B2 — spawn throttle:** rate-limit / penalize `generate_intrinsic_goals` when the committed
  goal carries open `action_debt`. Move reward from goal-closure *count* to
  completion-with-external-delta. (Pairs with W3's `_suppress_intrinsic_goals`.)
- **C8 — `drive_engine.py:256–257`:** confirmed `if committed_goal and reward > 0.4:
  satisfy("meaning", 0.18)`. Gate `meaning` satisfaction on measured goal progress (env-delta
  / milestone tick / verified artifact), not on a merely-pleasant `reward > 0.4`.

**Acceptance:** goal-completion and agentic-reward counts track `env_snapshot` deltas, not
intent; spawn/maintenance selection rate drops when a committed goal is stalled; `meaning`
pressure drops only when a goal actually advances.

### W9 — Un-silence the correctives  ·  P1
- **Idle-monitor:** authority decayed `0.90 → 0.48` and was dismissed. Floor its authority
  while `action_debt` persists (don't let the one alarm that's right decay to irrelevance).
- **Auditor peers:** `goal_auditor` / `reward_auditor` exist (`brain/peers/goal_auditor.py`,
  `reward_auditor.py`, registered in `peer_registry.py`) but ran with empty
  `interaction_history`. Actively invoke them on persistent stall (e.g. when
  `_impasse_reason` is set by W3) and record the interaction.

**Acceptance:** during a real stall, monitor authority holds and the auditor peers fire with
non-empty histories.

---

## Phase 4 — curiosity engine & drive credit (depends on W4)

### W6 — `seek_novelty` self-fuel loop + dedup  ·  P1/P2  ·  `seek_novelty.py:101–158`
Confirmed self-fuel loop: `_pick_mode` (`:101–112`) returns `"memory"` whenever any
long-memory item has `recall_count == 0`, excluding only `dream_insight`/`refusal` (`:109`).
`_explore_old_memory` (`:150–156`) then **writes a new** `stagnation_signal_reflection`
entry — which is **not** in the exclusion set — manufacturing the next `recall_count==0`
item. That is the mechanism behind 1,103/2,001 (55%) `stagnation_signal_reflection` memories.

**Changes:**
1. **Break the loop:** add `seek_novelty`'s own output event types to the exclusion filter at
   both `:109` and `:136`:
   ```python
   _SELF_TYPES = ("dream_insight", "refusal", "stagnation_signal_reflection",
                  "stagnation_signal_question", "stagnation_signal_goal_review")
   # :109 and :136 → e.get("event_type", "") not in _SELF_TYPES
   ```
2. **Dedup (B4):** before `update_long_memory(reflection, …)` in `_explore_old_memory`
   (`:153`), rate-limit and near-duplicate-dedup the write (skip if an identical/near
   `stagnation_signal_reflection` was written in the last K entries).

**Acceptance:** `stagnation_signal_*` share of long memory stops growing monotonically;
`seek_novelty` stops resolving to `"memory"` on consecutive calls with no new real memory.

### W10 — Drive credit & the one consummation circuit  ·  P1
- **C6 hidden sub-actions — `drive_engine.evaluate_cycle(fn_name, …)`** sees only the
  top-level name, so a `seek_novelty`→`look_outward` reach is credited as `"seek_novelty"`
  (not in `_mastery_fns` at `:270–273`). Read `context["_last_reach_outcome"].inner_fn`
  (W4) and credit drives off the realized sub-action.
- **C7 mastery split — `drive_engine.py:270–278`:** confirmed `_mastery_fns` blends
  world-learning (`research_topic`, `wikipedia_search`, `fetch_and_read`, `read_rss`) with
  self-inspection (`search_own_files`, `look_around`, `grep_files`, `search_files`,
  `list_directory`, `reflect_on_internal_agents`) at the same `0.35`. Split into a
  `self_understanding` drive vs a `world_mastery` drive with separate setpoints; codebase-grep
  must not discharge world-mastery. (Note: a `mastery` drive already exists at `:199–205`;
  this splits its satisfaction sources, it doesn't add a whole new pressure from scratch.)
- **C13 one consummation circuit (the synthesis):** today `record_reach_outcome` is wired into
  only `look_outward.py:62,136` and `search_own_files.py:22` — the 4 web-research tools, when
  selected *directly* by the bandit, never call it. Route every outward function through
  `exploration_value.record_reach_outcome`, and emit **one** consummation reward from that
  single point (not the ≥6 scattered ones across `finalize.py`, `drive_engine.py`,
  `exploration_value.py`, `action_gate.py`, `reward_calibrator.py`). Have that one event
  lower `exploration_drive` **and** reset `action_debt` together.

**Acceptance:** a successful informative reach produces a single legible reward, lowers
`exploration_drive`, resets `action_debt`, and raises outward-learning selection share next
cycle; an uninformative reach does none of these.

---

## Phase 5 — thaw & integrate (P2, after the loop is truthful)

### W13 — narrative / knowledge / language / attention (B3 · B9 · B10 · B13)
- **B3:** detect reflection-content stagnation (cosine/Jaccard similarity of recent
  reflections); force novelty injection / autobiography-chapter advance on an age cadence;
  enable real memory decay (`forgetting_log` showed 0 pruned all life — find why the decay
  path never ran).
- **B9:** wire `research_topic`/`wikipedia_search`/`read_a_book` results through
  `knowledge_graph.add_entity/add_relation` + a consolidation pass. **Investigate why the
  existing writers didn't fire** (`experimentation.py`, `skill_synthesis.py`,
  `perception/environment.py`, `person_detector.py`) despite spaCy loading — note
  `look_outward.ingest_outward_result` *does* call `knowledge_graph.observe` (`:130–131`), so
  the keyless direct-research path may be the uncovered gap, mirroring C13.
- **B10:** feed vocabulary/language stores from *read content* (B9's text), not internal
  diagnostic strings; confirm the native-LM corpus isn't contaminated by stuckness-reports
  (`project_language_native_lm`).
- **B13:** reconcile committed-goal against recent attention/theme mix; if a committed goal's
  local reward rate has collapsed relative to background (`is_stagnating`/`patch_deficit` from
  §0.3 — **not** a fixed "no cognition for N cycles" count), deliberately re-engage or formally
  disengage — no debt-accruing phantom commitment. Replace the fixed `_GOAL_STALL_MAX=40`
  degrade path at `ORRIN_loop.py:2361–2367` with the same continuous deficit signal, so the
  disengage threshold scales with loop speed and actual return rather than a magic 40. (Overlaps
  W3's `_suppress_intrinsic` and its stochastic patch-leave.)

### W14 — drive-engine tuning (C2 · C9 · C10 · C11 · C12)
- **C2 — `seek_novelty._pick_mode` ladder (`:101–126`):** invert toward outward-first (world
  reach before internal memory review) or weight outward as first-class when `curiosity_gap`
  is high.
- **C9 — `drive_engine.py:260–263`:** narrow `rest` satisfaction to genuinely restorative fns
  (`dream`, `sit_with`, `rest`, `integration`); drop the broad `reflect`/`wonder`/`contemplate`
  substring match so rumination stops sedating the system.
- **C10 — `drive_engine.py:266–267`:** the only social satisfaction is `_user_spoke_this_cycle`.
  Add satisfaction for Orrin's own outbound social acts, scaled below a real user reply.
- **C11 — `drive_engine.py:140`:** `tags = self.tags + ["drive", "internal"]` tags even
  exploration/social as `internal`. Tag worldward drives worldward
  (exploration→`external/world`, social→`human/relation`) and verify the router consumes tags.
- **C12 — `drive_engine.py:249–253,281,297–307`:** two timebases (daemon `tick()` every 10s
  **and** per-cycle `tick()` in `evaluate_cycle`). Pick one: either drop the per-cycle ticks
  and let the daemon own buildup, or make the daemon decay-only. Buildup must be
  cycle-speed-invariant.

---

## Phase 6 — larger scope / downstream (P3, W15)
- **B6:** largely resolves once W1 (credit) + W8 (finishing out-rewards spawning) land —
  verify motivation peaks correlate with external-action attempts, not new goals.
- **B7 (design):** give `look_outward`/action a genuine external surface distinct from source
  (sandboxed workspace/notes/output dir or web). `world_root` = the repo today, so all 1,362
  `look_outward` calls only perceived his own codebase.
- **B8:** feed per-capability success/failure stats into the symbolic self-model so weak-area
  beliefs move with evidence (Brier 0.026 calibration is good; the self-model is just static).
- **Reliability:** find the writer producing malformed `conscious_stream` (corrupted twice/
  life, 13:52 & 21:08); reconcile the two contact paths — `temporal_state.py:136–137` resets
  `cycles_since_contact` only on non-empty `latest_user_input`, disagreeing with the
  person-detector that logged a "someone".

---

## Validation gate (run between phases — load-bearing)
The analysed run had **no LLM for its entire duration**, so part of the "stuckness" may be a
degraded-mode artifact. **Re-run with the LLM up after Phase 1 and again after Phase 3.** If
the rut persists with the LLM available, W3/W7/W8/W10 are confirmed architectural; if it
clears, their priority drops and W2 (never misread a degraded run again) becomes the main win.

---

## PR slicing & hard sequencing
| PR | Contents | Gate |
|----|----------|------|
| PR-0 | §0 scaffolding (`action_accounting.py`, `ReachOutcome`) | unit tests green; nothing wired yet |
| PR-1 | Phase 0 (W2, W11, W12) | unit + 1 short run; dashboard trends red in a rut; no `adaptive→adaptive` |
| PR-2 | Phase 1 (W1) | unit + regression + LLM-up validation run |
| PR-3 | Phase 2 (W4, W5) | no fallback self-question after a working keyless reach |
| PR-4 | Phase 3 (W3, W7, W8, W9) | LLM-up rut-eject run; correctives fire |
| PR-5 | Phase 4 (W6, W10) | stagnation-memory share flat; one consummation reward |
| PR-6 | Phase 5 (W13, W14) | KG grows; drives cycle-speed invariant |
| PR-7 | Phase 6 (W15) | scope-dependent; B7 may be its own track |

**Forced order:** §0 → W1 → {W3, W7, W8, W9}; §0 → W4 → {W5, W6, W10}; W8's B2+B11 halves
ship together. Everything else parallelizes within its phase.

---

## Fidelity review — does the variable rewrite hold up?

A self-audit of the threshold-removal pass, against two bars: (1) it must still *fix the
diagnosed pathology*, and (2) it must not introduce a new one. Honest assessment, including
where it's still soft.

### What the rewrite actually changed
Every fixed cycle-count or debt-count trigger in the rut machinery now routes through one
definition of "stagnating" in `reward_rate.py` (§0.3), which is **always** a comparison of two
live EMAs — the current goal's local reward rate vs the life-scale global background rate. The
constants that remain (`0.10`, `0.35`, `8.0`, `0.5`, the two `_ALPHA`s) are **shape parameters
of continuous functions**, not points where behaviour flips on. Concretely retired: `debt >= 8`
(W3 impasse), `_DELIBERATION_LOCKOUT_DEBT = 5`, `_FORCE_ACTION_MAX_CYCLES = 4`, the cap at
`+0.15`, the 10-cycle mode timer (W11), the `recent[-8:]` variety window (W7/C5), and
`_GOAL_STALL_MAX = 40` (W13/B13). The decision in each is now monotone in a *relative, learned*
quantity, so it self-tunes to whatever return the environment yields and is invariant to loop
speed — which also closes the C12 two-timebase bug at the source.

### Three invariants that keep this from becoming a depression generator
1. **No dead end (W3).** Impasse may rise *only while a behavioural escape is actually
   available*; with zero selectable candidates the goal is disengaged, not ramped. This is the
   Maier–Seligman learned-helplessness guard, made structural.
2. **Internal progress still counts (W1/§0.1).** Strictness is state-dependent: genuine
   `info_gain` discharges debt when healthy; the bar rises to an *external* effect only once
   `is_stagnating`. The fix breaks rumination without encoding a permanent "only world-change
   matters" value system.
3. **Sense the disease, don't normalise it (W2).** Exploration's setpoint is *down-weighted*,
   not relocated; a separate slow `allostatic_load` integrator carries the chronic-deviation
   signal. Homeostasis can still see that a pinned drive is itself the pathology.

### Residual risks — where this still needs the run to adjudicate
- **EMA warm-up.** `_GLOBAL_ALPHA = 0.002` means the background rate takes ~hundreds of cycles
  to become trustworthy. Until then `patch_deficit` is noisy and could mis-fire early in a life
  or right after a cold start. Mitigation already in code: local re-seeds *at* global on goal
  switch (neutral prior), and `is_stagnating` is AND-gated with `action_debt > 0` so it can't
  trip on a cold baseline alone. Still: **watch the first validation run for early thrash.**
- **Stochastic leave variance.** `should_force_switch` is a hazard draw, so two identical states
  can diverge. That's deliberate (it's what breaks the creative↔adaptive limit cycle), and the
  refractory factor damps oscillation — but it makes the regression test necessarily
  statistical (assert *distributional* leave-timing, not a fixed cycle). Flagged in the W3
  acceptance.
- **One free parameter moved, not eliminated.** The `>= 0.5` in `is_stagnating` and `/0.35` in
  the hazard are still chosen numbers. They are now *relative* (fraction-below-background) and
  *continuous*, which is the real win, but they are not *learned*. A later pass could make the
  hazard shape itself adapt to the variance of the reward stream. Out of scope here; noted so
  it isn't mistaken for fully self-tuning.

### Verdict
The rewrite is faithful to the diagnosis: every pathology the run surfaced (phantom
research-debt, impasse restarting on goal rotation, intrinsic-goal escape hatch, mode thrash,
empty-novelty re-pumping) is addressed by the *same* relative-rate mechanism rather than a new
constant. It is biologically defensible (MVT patch-leaving, tonic-LC adaptive gain, allostatic
load, learned-helplessness guard) rather than merely de-magic-numbered. The honest gap is that
two shape parameters remain hand-set and the global EMA needs warm-up — both are observable in
the Phase-1/Phase-3 validation runs, which is exactly where the plan already routes them.
