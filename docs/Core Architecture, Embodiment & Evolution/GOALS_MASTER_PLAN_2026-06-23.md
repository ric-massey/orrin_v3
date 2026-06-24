# Orrin Goals — Master Plan (all goal fixes)

**Created:** 2026-06-23 (renamed from `SURVIVAL_GOAL_LAYER_PLAN`, expanded to hold
every goal-architecture fix)
**Status:** Part I **COMPLETE** (Phases 1–4, 2026-06-23, 25 tests). Part II
**COMPLETE** (D1–D4, 2026-06-24). D2 lifecycle inversion is all-in (no flag): the
committed goal is chosen from the v1 cognitive tree (single source of truth); v2 is
the execution projection only. D3 binds that goal through the global workspace — the
conscious goal-moment carries the authoritative goal's id, so awareness and pursuit
are provably one object (`bound_goal` / `goal_in_focus` accessors; binding facets
carry `goal_id`). 17 Part-II tests + clean ORRIN_ONCE. **The whole GOALS_MASTER_PLAN
is now implemented.** Only open item: a real multi-cycle run (Ric) to validate D2
live and fix forward (top suspect: v1-originated goals not writing their v2 id back).
**Scope:** the single home for Orrin's goal-architecture work — both *how goals
behave* (the layered behavioral model) and *how the goal is represented/stored*
(the v1/v2 question). Two parts:

- **Part I — Survival / Homeostatic Goal Layer** (behavior): wire the
  autonomic→cortical bridge so survival can preempt/recruit goals.
- **Part II — v1/v2 Goal Representation** (storage): collapse the two-store /
  sync model toward one authoritative goal with derived projections (Option D),
  because that is the architecture closest to human cognition.

The two parts are independent and can land in either order; Part I is the
higher-fidelity-per-effort win, Part II removes a class of drift bugs and is the
human-closest *representation*.

---

# Part I — Survival / Homeostatic Goal Layer

## 1. Why this exists

Humans hold goals in **distinct layers with different origins and different
rules**, not one uniform pile:

- **Survival / homeostatic** — given, not chosen (breathe, eat, rest). These are
  mostly *autonomic*: you don't form "a goal to breathe." But when a vital signal
  crosses a threshold it **preempts** whatever you were doing (you stop reading and
  eat), and a *persistent* deficit **recruits** a deliberate goal ("I should sort
  out my sleep"). You can't Wrosch-disengage from them, and they **return** on a
  cycle (hunger comes back).
- **Intrinsic / growth** — emergent from drives (curiosity, mastery). Exploratory,
  they **habituate**, and they're cheap to drop.
- **Deliberate / core** — chosen by reasoning ("run a marathon because it's good
  for me"), but still *caused* — they trace back to a drive/aspiration and one's
  past. They need commitment, can be revised/disengaged, and can be traded off.

A 2026-06-23 read of `brain/cognition/planning/` found Orrin's **intrinsic** and
**deliberate** layers are genuinely well-modeled. The **survival layer is the
gap** — and in a precise, fixable way.

### The deciding fidelity failure

In humans, a survival signal crossing threshold can **seize the goal slot**.
Orrin currently *cannot do this*: it can get absorbed in a growth goal while a
vital signal goes critical, because the machinery that would interrupt it is
**built but unwired**. That is the single most un-human thing about its goal
behavior, and it is small to fix.

---

## 2. Diagnosis (grounded in the code, not asserted)

Orrin already models survival correctly *as an autonomic substrate*:

- `brain/affect/setpoints.py` + `brain/affect/homeostasis.py` — homeostatic
  setpoints with restoring forces (Cannon 1932). Correct: kept *below* the goal
  system, like a brainstem.
- `brain/embodiment/setpoint_regulation.py` — a daemon that watches vital signals
  (e.g. `resource_deficit`) and emits **alerts** `{id, severity: warning|critical,
  description, tags, suggested_fn}`.
- `brain/loop/reflect.py::tier1_health_check` — reads those alerts each cycle and
  folds them into the context: critical → escalating `raw_signals` + direct
  emotional cost after ≥3 ignored cycles (McEwen 1998 allostatic load; Selye 1956
  GAS; Baumeister 1994 ego depletion). It sets `context["health_score"]` and
  `context["_tier1_critical"]`.

**What's missing is the bridge from that autonomic substrate up into the goal
system.** Three concrete defects:

### Defect A — the acute preempt is a consumer wired to the wrong key

`brain/cognition/planning/goal_closure.py::_survival_critical(context)` decides
whether a vital state must preempt goal pursuit. It reads:

```python
if context.get("_setpoint_critical") or context.get("health_critical"):  # NEVER SET
    return True, "setpoint_critical"
if float(context.get("health_score", 1.0)) < 0.35:                       # set by tier1 — LIVE
    return True, "health<0.35"
if float(af.get("resource_deficit", 0.0)) > 0.85:                        # maybe set
    return True, "resource_deficit>0.85"
```

- `_setpoint_critical` / `health_critical` are referenced **only** here — nothing
  in the tree ever writes them. The producer (`tier1_health_check`) writes a
  *different* key, `_tier1_critical`. **Producer and consumer pass in the night.**
- The `health_score < 0.35` path *is* live (tier1 sets `health_score`), so the
  preempt is closer to working than "dead" — but:
- The whole preempt is gated `ORRIN_SURVIVAL_PREEMPT=False`
  (`goal_closure.py::_survival_preempt_enabled`), so it never runs by default.

The call site already exists and is correct:
`brain/cognition/planning/goal_execution.py:102` checks `_survival_preempt_enabled()`
→ `_survival_critical(context)` → yields the cycle with
`reason="survival_preempt"` (transient, resumable — not a failure). **So the acute
path is one key-reconciliation + one flag-flip from functioning.**

### Defect B — no persistent deficit recruits a goal (the chronic case)

`tier1_health_check` escalates a neglected critical alert by raising its
*signal strength* and adding *emotional cost* — but it never turns a chronic
deficit into a **goal**. A warning nudges function *selection* via `raw_signals`;
it never becomes a committed intention. So the human pattern — "this depletion
isn't acute, but it keeps coming back, so I'll make addressing it a goal" — has no
mechanism. The autonomic→cortical *recruitment* path is absent.

Note the alerts already carry `suggested_fn` (e.g. the `resource_deficit_critical`
alert suggests rest/recovery) — i.e. the *target action* for a recruited goal is
already named by the producer.

### Defect C — survival "satiety" doesn't return

`brain/cognition/planning/goal_satiety.py` exists but its proxies are for
*exploration/understanding* goals (novelty exhaustion, topic-uncertainty closed),
and satiety **closes** a goal permanently. There is no "hunger returns" cycle: a
homeostatic goal, once satisfied, should *deactivate* and **re-fire when the
deficit recurs**, not complete-and-vanish.

---

## 3. Design principles

1. **Keep the autonomic part autonomic.** Setpoints/restoring forces and the
   vital-floor reflex stay below the goal system. We do **not** create "a goal to
   breathe." We only build the *escalation* path: threshold-crossing → goal-level
   action.
2. **The layer determines the rule.** A survival goal is preemptive,
   non-disengageable, and satiety-cycling. A deliberate goal is committable,
   disengageable, tradeable. Same machinery must branch on layer, not treat all
   goals alike.
3. **Two escalation modes, matched to physiology:**
   - **Acute / crisis → preempt** (interrupt the committed goal *now*, for the
     cycle). Maps to a vital signal crossing a hard threshold.
   - **Chronic / persistent → recruit** (escalate to a deliberate restoration
     goal). Maps to a sub-acute deficit that keeps recurring.
4. **Hysteresis, not thrashing.** Survival must be able to seize the slot, but a
   signal hovering at threshold must not flip the committed goal every cycle.
   Enter/exit thresholds differ; recruited goals have a refractory period.
5. **Behavior-preserving by default until proven.** Each phase lands behind its
   existing flag, verified on a real run before the flag flips on.

---

## 4. The plan

### Phase 1 — Wire the acute preempt (small, high-value) — **CODE-COMPLETE 2026-06-23**

**Goal:** a critical vital signal interrupts the committed goal for the cycle.

1. ✅ **Reconcile the key.** `tier1_health_check` (`brain/loop/reflect.py`) now sets
   `context["_setpoint_critical"] = True` next to `context["_tier1_critical"] = True`
   when a `critical` alert is seen, and stashes the alert id/desc in
   `context["_setpoint_critical_reason"]`. The key is reset to `False` at the top of
   each read (context persists across cycles, so a cleared critical must un-latch it).
   Fixed the producer, not the consumer, so intent stays explicit.
2. ✅ **Characterization test** — `tests/brain/test_survival_preempt_wire.py`
   (5 tests, green): the wire (key set / cleared), the hysteresis state machine, and
   the integration assertion (fake critical alert → `pursue_committed_goal` yields
   `reason="survival_preempt"`, `detail` = alert id, committed goal byte-identical).
3. ✅ **Flag flipped on** — `goal_closure._survival_preempt_enabled` now defaults
   `True` (set `ORRIN_SURVIVAL_PREEMPT=0` to disable). Verified by a headless
   `ORRIN_ONCE=1 ORRIN_SURVIVAL_PREEMPT=1` run: boots with the preempt armed, runs a
   normal cycle, exit 0, no traceback. Note: sustained-critical thrash can't be
   exercised in a one-cycle run with no critical vital signal present; the Phase-1
   hysteresis (step 4) is the guard for that case.
4. ✅ **Hysteresis** in `goal_closure.py`: `_survival_critical` is now a wrapper over
   a new `_raw_survival_critical`; it requires the raw condition for ≥2 consecutive
   cycles before preempting and resets the streak after 1 clean cycle (streak lives
   in `context["_survival_crit_streak"]`; sole writer, called once/cycle).

**Why first:** it closes the worst fidelity gap (survival can't currently
override), it's nearly free, and it de-risks Phase 2 (recruitment leans on the
same producer keys).

### Phase 2 — Deficit → goal recruiter (the autonomic→cortical bridge) — **DONE 2026-06-23**

**Goal:** a *persistent* sub-acute deficit becomes a deliberate restoration goal.

1. ✅ **Wired in `tier1_health_check`** (`brain/loop/reflect.py`): the per-alert
   neglect counter (`_h1_ignored[aid]`) now also increments for `warning`s (not just
   `critical`s — the chronic case *is* a recurring sub-acute deficit). When neglect
   crosses `RECRUIT_AFTER_CYCLES` (5), the new `_h1_maybe_recruit` helper calls the
   recruiter instead of only escalating signal strength.
2. ✅ **Recruiter** — `brain/cognition/planning/survival_goals.py`:
   `build_survival_goal(alert)` → `tier="survival"`, `driven_by` = the alert's
   homeostatic signal (tag, else id with severity suffix stripped), first plan step =
   the alert's `suggested_fn` (fallback `rest`), title from `description`,
   `recruit_aid` stamped. `recruit_survival_goal(alert, ctx)` submits via
   `context["proposed_goals"]` (the exact intrinsic-goal path → `goal_io.sync_proposed_goals`),
   with **refractory dedup**: skip if an open goal with that `recruit_aid` exists in
   this cycle's proposals OR as a non-terminal goal in the store.
3. ✅ **Survival-tier priority floor** — `executive._TIER_TURNS` gains
   `"survival": 4` (above `core`/`existential` at 3), and the goal carries the top
   intrinsic priority (5). So it outranks growth/core in step allocation + proposal
   adoption with no special case in the selector.
4. **Tests** — `tests/brain/test_survival_recruit.py` (10, green): goal shape,
   signal derivation, suggested_fn fallback, proposed_goals submission, refractory
   dedup (within-cycle, open-store-goal, re-recruit once terminal), tier1
   threshold gating (not before N, exactly one at N, no pile-on after), warning-
   severity recruitment, and the executive priority floor.

**Why:** this is the genuinely new behavior — chronic depletion escalating into an
intention. It reuses the alert's own `suggested_fn` as the action, so it doesn't
invent capability Orrin lacks.

> **Bounded by Part II:** the recruited goal *competes* via the existing proposal/
> commitment path with the survival floor giving it precedence. Proving it always
> *wins* commitment end-to-end is entangled with the v1/v2 seam (a `generic` goal
> round-trips through GoalsAPI), which is exactly what Part II collapses. Phase 2's
> exit criterion — recruit a deduped survival goal whose first step is the alert's
> `suggested_fn` — is met and unit-verified.

### Phase 3 — Survival-goal behavior rules (make the layer matter) — **DONE 2026-06-23**

**Goal:** survival goals behave by survival rules, not deliberate-goal rules.

1. ✅ **Non-disengageable.** `goal_closure._degrade_or_disengage` now exempts
   `tier=="survival"` from the Wrosch abandon branch: a survival goal may still
   *degrade* to a simpler restoration above, but the final disengage returns `None`
   (holds the slot, retries) instead of `mark_goal_failed` + clearing the slot. A
   non-survival goal in the same spot still disengages (test).
2. ✅ **Satiety with return (Defect C).** `goal_closure._finalize_goal_completion`
   intercepts `tier=="survival"`: status → `dormant` (not `completed`), stamped with
   `_satisfied_ts`, slot released, **no achievement reward** (survival pays
   restoration, not the production reward — guards the cheap-reward risk). The
   recruiter (`survival_goals._in_refractory`) treats a dormant deficit as
   re-recruitable but only after `MIN_REFIRE_INTERVAL_S` (30 min) — the hunger-
   returns cycle, respecting a minimum re-fire interval.
3. ✅ **Emotional coupling** — unchanged (tier1 still adds risk/impasse cost on
   neglect); it now has a behavioral outlet (preempt/recruit/hold) instead of only
   nagging.

**Tests** — `tests/brain/test_survival_rules.py` (6, green): survival not
disengaged vs. non-survival still disengaged; satisfied survival → dormant +
`_satisfied_ts` vs. non-survival unaffected; dormant deficit blocked within the
re-fire interval, re-recruited after it.

### Phase 4 — enable core-goal satiety closure — **DONE 2026-06-23**

Deliberate/core goals used to close on *plan completion*, not on the underlying
need being *sated*, because `ORRIN_TIER_CLOSURE` was default-off. ✅ Flipped on
(`goal_closure._tier_closure_enabled` defaults `True`; `ORRIN_TIER_CLOSURE=0`
restores the legacy gate) — the "stop because you're full, not because the plate is
empty" rule for layer 2. Safe to default-on: the satiety path has a cycle-1 guard
and `mark_goal_completed` still refuses hollow closure (no faked success).

Verified: `tests/brain/test_tier_closure.py` (4, green — flag default, disablable,
sated-closes, unsated-holds), a 107-test goal/closure/satiety/pursue sweep with the
flag on, and a clean headless `ORRIN_ONCE` run.

---

## 5. Reasoning & citations

The substrate is already theory-grounded; this plan connects it to action:

- **Cannon (1932) homeostasis** — setpoints + restoring forces (`setpoints.py`).
- **McEwen (1998) allostatic load / Selye (1956) GAS / Baumeister (1994) ego
  depletion** — ignored homeostatic stress compounds; already cited in
  `tier1_health_check`. The fix gives that mounting cost a *behavioral resolution*
  (preempt/recruit) rather than only emotional accrual.
- **Autonomic → cortical escalation** — the core human pattern this implements:
  homeostatic regulation is subcortical *until* a deficit crosses threshold, when
  it recruits cortical (goal-directed) action. The two modes (acute preempt vs.
  chronic recruit) mirror reflexive vs. motivated regulation.
- **Wrosch et al. goal disengagement** — adaptive for *chosen* goals; Phase 3
  correctly **exempts** survival from it (you disengage from a marathon, not from
  rest).
- **Gollwitzer Rubicon / commitment** — recruited survival goals still pass through
  commitment competition, so they're *intentions*, not interrupts bolted on
  outside the goal system.

---

## 6. Risks & guardrails

- **Slot thrashing.** A vital signal at threshold could flip the committed goal
  every cycle. Mitigation: Phase-1 hysteresis (enter/exit thresholds + consecutive-
  cycle requirement); Phase-2 refractory dedup.
- **Survival starves growth.** A permanent low-grade deficit could let survival
  goals monopolize the slot. Mitigation: recruit only on *threshold-crossing*
  (not steady-state); satiety→dormant so a satisfied need yields the slot back.
- **Reward-denominator interaction.** Survival goals must not become a cheap,
  always-available reward source that crowds out production (see the production-
  reward work). Mitigation: survival completion pays *restoration*, not the
  production reward; recruited goals are gated by real deficit, not by reward.
- **Flag discipline.** Every phase lands behind its flag and a green ORRIN_ONCE
  run before the default flips — same rule the rest of the planning code follows.

---

## 7. Exit criteria

- A critical vital alert **preempts** the committed goal for the cycle (test +
  real run), with hysteresis preventing per-cycle flip-flop.
- A persistent deficit **recruits** a survival-tier goal whose first step is the
  alert's `suggested_fn`, deduped against re-recruitment.
- Survival goals **never Wrosch-disengage**; they degrade-to-simpler at most.
- A satisfied survival goal goes **dormant and re-fires** when the deficit recurs
  (hunger returns), respecting a minimum interval.
- `ORRIN_SURVIVAL_PREEMPT` (and, if chosen, `ORRIN_TIER_CLOSURE`) default on, with
  the gate green.

## 8. Explicitly out of scope (for Part I)

- v1/v2 goal **storage** consolidation — now **Part II** of this same document.
- Any change to the autonomic setpoint/vital-floor math itself — we only add the
  escalation bridge above it.

---

# Part II — v1/v2 Goal Representation (storage)

## 9. Why this exists

Orrin currently keeps a goal in **two stores that synchronize**:

- **v1** (`goals_mem.json`, `brain.cognition.planning.*`) — the *cognitive* goal:
  plans, subgoals, pursuit state, tier/aspiration/origin, emotional links. The
  rich representation; **all the layering Part I depends on lives here.**
- **v2** (`data/goals/`, `GoalsAPI`/daemon/WAL/handlers) — the *executable
  work-order*: durable, handler-run, event-bus, for goals that act in the world
  (coding/research/housekeeping). Its `Goal` model is **flat** — `id/title/kind/
  spec/priority/status/tags/steps`, no tier/aspiration/origin.

`goal_io.py` bridges them (sync v1→v2 for executable kinds; events v2→v1). **The
seam is where drift bugs live** (e.g. the 2026-06-12 plan-progress loss).

## 10. Why this belongs in the *goals* plan (the human argument)

A human goal is **one thing**, distributed across brain systems (PFC holds the
intention, basal ganglia run the procedure, memory holds it dormant, affect
colors it) but **bound into a single experienced intention**. The systems don't
each keep a private copy and reconcile — drift between them is a *dissociation*
(goal neglect, anarchic-hand), which is pathological, not normal. Orrin's
two-store sync is exactly that un-human reconciliation, and its drift bugs are
the symptom.

So this is not merely plumbing — **the representation IS part of goal cognition.**
The human-closest design is one authoritative goal that the planning, execution,
memory, and affect systems all *bind to and project from*, never two originals
that negotiate.

## 11. The options considered (and why D)

- **A — keep both stores syncing.** *Furthest from human*: the sync is the
  dissociation; two minds about one goal. (It's now *fenced* by the Phase-7
  ownership table + `ADAPTER_FILES` ratchet, so it's survivable — but it's the
  status quo, not a fix.)
- **B — collapse onto v2.** Human **only if** v2's flat schema is first extended
  to carry the full cognitive richness (tier/aspiration/origin/plans). Naive B
  (flatten the goal into the work-order row) **destroys** the very layering Part I
  needs — so plain B is wrong-direction.
- **C — retire v2.** Throws away real capability (executable handlers, WAL,
  durability). A regression. Off the table.
- **D — one authoritative goal + derived projections.** *Closest to human.* One
  goal exists once (the rich, layered cognitive representation is authoritative);
  the execution view, memory view, and UI view are **projections** rebuilt from
  it, not independent copies. Nothing to drift because there's no second original.

**Decision: D, with the authoritative representation = the rich cognitive goal**
(it carries tier/aspiration/origin, which v2 cannot), and **v2 demoted to a
durable executor/projection** for the subset of goals that act in the world.

## 12. The plan

The principle: make the cognitive goal the single source of truth, and make the
v2 store a **rebuildable projection** of it (durable execution substrate), so the
bidirectional *sync* becomes a one-directional *render*.

- **D1 — Declare the source of truth.** ✅ **DONE 2026-06-24.** `goal_io._V1_AUTHORITATIVE_FIELDS`
  codifies the contract: the v1 cognitive goal owns `tier / driven_by / source /
  recruit_aid / zone / orientation / serves` (the layering v2's flat model can't
  hold); v2 owns lifecycle (status/priority/execution). Documented inline as the
  ownership table for the goal seam.
- **D2 — Replace dual-write with project-then-execute.** ◑ **Field-ownership slice
  DONE 2026-06-24; lifecycle inversion remaining (staging-gated).**
  - ✅ The projection now carries the authoritative cognitive fields in the v2
    **spec** (`sync_proposed_goals`), and the read restores them (`_goal_to_v1`:
    `tier = spec.get("tier") or kind`, + the rest), with the live v1 node winning
    over the stale spec in `committed_goals_v1` (order: **v1 node → spec → kind**).
    This makes the v2 record a regenerable *projection* for those fields instead of
    a flatter copy that silently dropped `tier`/origin — the canonical seam-drift
    bug, and the Part I Phase-2 caveat, are fixed.
  - ✅ **Lifecycle inversion LIVE (all-in, no flag) 2026-06-24.** `sense.py` calls
    `committed_goals_v1(api, context)`, now reimplemented as the v1-authoritative
    read: the committed goal is chosen from the **v1 cognitive tree**
    (`_committable_from_v1_tree`, tier-then-priority ordered, reusing the executive's
    tier floor; bucket / directional / terminal goals excluded). Each cycle
    `_reconcile_open_v2_into_v1` first absorbs any open v2-only goals into v1 (so
    nothing is stranded) and mirror-closes v2 for goals v1 has finished
    (anti-resurrection). v2 still executes the projected work-orders and reports
    events; it no longer decides what's committed. The old v2-driven pull, the
    `ORRIN_GOALS_V1_AUTHORITATIVE` flag, and the now-dead `_PURSUIT_FIELDS` hydration
    were deleted — **one path**. Tests: `tests/brain/test_v1_authoritative_goals.py` (4).
    **Watch on the first real run:** backfilled v1 nodes carry the v2 id (events
    reconcile), but a goal that *originates* in v1 and is projected to v2 doesn't yet
    write the v2 id back onto its v1 node — verify failed/completed events still map
    for those, and fix forward if not.
- **D3 — Bind through the workspace.** ✅ **DONE 2026-06-24.** The committed goal is
  now a workspace-bound object, not a text echo: its candidate and the resulting
  conscious moment carry `goal_id` bound to the authoritative goal object
  (`global_workspace.update_workspace`), and `binding.py` stamps `goal_id` onto a
  bound situation's goal facet — so "the goal I'm aware of" and "the goal I'm
  pursuing" are provably the same object (one goal, many views), not two copies that
  drift. New accessors `global_workspace.bound_goal(context)` (the single
  authoritative goal every subsystem should read) and `goal_in_focus(context)` (is
  that goal currently conscious?). Tests:
  `tests/brain/test_goal_workspace_binding.py` (6). *Follow-up (incremental, not
  blocking): migrate subsystems that reach into `context["committed_goal"]` directly
  onto `bound_goal()` so the single-accessor contract is enforced everywhere.*
- **D4 — Collapse the seam's drift tests into invariants.** ✅ **DONE 2026-06-24.**
  `tests/brain/test_goal_projection_invariants.py` (5): a survival goal's tier
  survives a v2 round-trip; the projection is reconstructible (project→read); legacy
  goals fall back to kind without crashing; the live v1 node overrides a stale spec.
  (The pre-existing `test_goal_store_reconcile.py` already locks the resurrection /
  left-RUNNING drift bugs.)

Each step is incremental and reversible; D2 can be done per goal-kind. Memory has
a *separate, larger* version of this same question (~50 readers of the v1 JSON) —
**out of scope here; goals first** because the blast radius is smaller and
execution clearly wants one owner.

## 13. Risks & guardrails (Part II)

- **Execution latency.** The cognitive loop reads v1 in-process cheaply; v2 is a
  daemon. Keep the authoritative read in-process (cognitive goal); only the
  *projection/execution* crosses to the daemon. Don't put the hot per-cycle read
  behind the daemon.
- **Capability loss.** Demoting v2 must preserve its real features (handlers, WAL,
  event bus) — they move *under* the projection, they don't disappear.
- **Big-bang risk.** Do it per goal-kind behind a flag; keep A's `ADAPTER_FILES`
  fence in place until each kind is migrated, shrinking the allowlist as you go
  (the ratchet only narrows).

## 14. Exit criteria (Part II)

- One declared source of truth for the goal's intention/plan/tier/origin; v2 holds
  only derived execution state.
- `goal_io.py` no longer bidirectionally reconciles — it projects then consumes
  events; a v2 record is reconstructible from the cognitive goal.
- The historical seam-drift bugs are encoded as invariants/tests that fail on
  divergence.
- (Stretch) the committed goal is a workspace-bound object the subsystems share.

## 15. Out of scope (Part II)

- v1/v2 **memory** consolidation (the ~50-reader version of this) — a separate,
  larger effort; not part of the goals plan.

