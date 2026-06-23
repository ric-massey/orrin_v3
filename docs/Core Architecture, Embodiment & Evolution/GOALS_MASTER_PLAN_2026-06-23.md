# Orrin Goals — Master Plan (all goal fixes)

**Created:** 2026-06-23 (renamed from `SURVIVAL_GOAL_LAYER_PLAN`, expanded to hold
every goal-architecture fix)
**Status:** proposed (diagnosis complete; no code changed yet)
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

### Phase 1 — Wire the acute preempt (small, high-value)

**Goal:** a critical vital signal interrupts the committed goal for the cycle.

1. **Reconcile the key.** In `tier1_health_check`, when a `critical` alert is seen,
   also set `context["_setpoint_critical"] = True` (and stash the alert id/reason).
   One line, next to the existing `context["_tier1_critical"] = True`. This is the
   missing wire; prefer fixing the producer over loosening the consumer so the
   intent ("a setpoint is critical") is explicit.
2. **Add a characterization test** (`tests/brain/`): inject a fake
   `setpoint_regulation.get_state` returning a critical alert → run the
   reflect→pursue path with `ORRIN_SURVIVAL_PREEMPT=1` → assert
   `pursue_committed_goal` yields with `reason="survival_preempt"` and the
   committed goal is **not** mutated (transient, resumable).
3. **Flip the flag on** (`ORRIN_SURVIVAL_PREEMPT` default → True) *only after* the
   test passes and a real ORRIN_ONCE run shows no thrash.
4. **Add hysteresis** to `_survival_critical`: require the critical condition for
   ≥2 consecutive cycles before preempting, and clear after 1 clean cycle — so a
   signal dithering at the threshold can't ping-pong the slot.

**Why first:** it closes the worst fidelity gap (survival can't currently
override), it's nearly free, and it de-risks Phase 2 (recruitment leans on the
same producer keys).

### Phase 2 — Deficit → goal recruiter (the autonomic→cortical bridge)

**Goal:** a *persistent* sub-acute deficit becomes a deliberate restoration goal.

1. In `tier1_health_check`, track the neglect counter that already exists
   (`_h1_ignored[aid]`). When a `warning`/`critical` alert's neglect crosses a
   recruit threshold (e.g. ≥ N cycles unaddressed), call a new
   **survival-goal recruiter** instead of only escalating signal strength.
2. New recruiter (sibling of `intrinsic_goals.generate_intrinsic_goals`, e.g.
   `brain/cognition/planning/survival_goals.py`): build a goal from the alert —
   `tier="survival"`, `driven_by` = the alert's homeostatic signal, first step =
   the alert's `suggested_fn`, title from `description`. Submit it through the same
   path intrinsic goals use, with a **refractory dedup** (don't recruit the same
   `aid` while one is already open).
3. The recruited goal competes in the normal commitment competition **but with a
   survival-tier priority floor**, so it can outrank growth goals without a
   special case in the selector.

**Why:** this is the genuinely new behavior — chronic depletion escalating into an
intention. It reuses the alert's own `suggested_fn` as the action, so it doesn't
invent capability Orrin lacks.

### Phase 3 — Survival-goal behavior rules (make the layer matter)

**Goal:** survival goals behave by survival rules, not deliberate-goal rules.

1. **Non-disengageable.** In `goal_closure._degrade_or_disengage`, exempt
   `tier=="survival"` from Wrosch disengagement — a survival goal may *degrade* to
   a simpler restoration (means-ends) but must **never abandon**. (Wrosch
   disengagement is adaptive for *chosen* goals; you don't "give up" on rest.)
2. **Satiety with return (Defect C).** When a survival goal's deficit clears,
   mark it `dormant` rather than `completed`, and let the Phase-2 recruiter
   **re-activate** it when the deficit recurs — the hunger-returns cycle. Store the
   last-satisfied timestamp; recruitment respects a minimum re-fire interval.
3. **Emotional coupling** is already present (tier1 adds risk/impasse cost on
   neglect) — leave as is; it now also has a behavioral outlet (preempt/recruit)
   instead of only nagging.

### Phase 4 — (related, optional) enable core-goal satiety closure

Out of strict scope but adjacent: deliberate/core goals currently close on *plan
completion*, not on the underlying need being *sated*, because
`ORRIN_TIER_CLOSURE` is default-off. If desired, enable it (behind the same
verify-then-flip discipline) so core goals can close on satiety — the "stop
because you're full, not because the plate is empty" rule for layer 2.

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

- **D1 — Declare the source of truth.** The committed/cognitive goal (v1
  representation) is authoritative for intention, plan, tier, aspiration, origin,
  status. v2 holds only execution/durability state, derived from it.
- **D2 — Replace dual-write with project-then-execute.** Where `goal_io.py` today
  *syncs* (v1→v2 create + v2→v1 event reconcile), change to: the cognitive goal
  **projects** a v2 work-order when (and only when) it needs world-execution; v2
  reports execution results back as *events the cognitive goal consumes*, not as a
  competing source of truth. The projection is regenerable from the cognitive
  goal, so a lost/rebuilt v2 record is recoverable, not a divergence.
- **D3 — Bind through the workspace.** Route the committed goal through the global
  workspace so planning/execution/memory/affect all read the *same bound object*
  (this lands on the known binding gap — see `project_binding_workspace`). Binding
  is what makes "one goal, many views" real rather than aspirational; goals are
  the highest-value thing to bind.
- **D4 — Collapse the seam's drift tests into invariants.** The seam bugs
  (plan-progress loss, etc.) become assertions: a projection must be reconstructible
  from the authoritative goal; a v2 event must never silently overwrite cognitive
  state it didn't originate.

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

