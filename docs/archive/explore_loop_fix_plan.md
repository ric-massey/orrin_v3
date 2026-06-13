# Fix Plan — The "Explore" Goal Loop, Its Cascade, and the Brain-Accurate Goal Model

**Status:** Proposed (design only). Root causes and the existing goal architecture both
verified against the working tree on branch `convergence-layer`; every claim cites
`file:line`.

**Rev 4** — the immediate-bug analysis (Rev 1–3) is preserved as §1–§2 and §5. Rev 4 adds
the part those revisions were missing: a survey of the **goal system that actually exists**
(§3) and the **brain-accurate target model** the fixes should move toward (§4) — two closure
pathways, *tier-scaled* closure (so a tiny goal and a never-ending one are treated
differently), and strict survival precedence. The closure-semantics question from review is
resolved here: process-milestones are correct for *trivial* goals and wrong for *large*
ones — the bar must scale with the goal, not be uniform. See §9 (Changelog).

---

## 0. TL;DR

> **A goal whose objective is already met can never *close*, because closure is gated on
> the *plan* finishing — and the plan contains steps that can never execute. Nothing detects
> the resulting no-real-progress loop, so the system re-runs the same search forever, fails
> the same predictions forever, and narrates its own stuck-ness without the tools to stop.**

The live goal *"Explore the computer I live on — what's here?"* (`brain/data/goals_mem.json`)
has **both milestones `met: true`** yet `status: in_progress`, steps 2–3 stuck `pending`.

Two layers of answer:
- **Immediate (§5):** fix the closure gate (Fix 1) and the live bleed stops; add the one
  *hard* escape actuator the system has never had (Fix 2), because every recurrence guard it
  owns is a soft advisory offer that has already failed (E8).
- **Structural (§3–§4):** the deeper issue is that the goal model treats every goal
  identically — same tier, same boolean process-milestones, same single-focus pursuit —
  when a brain runs **many goals at many scales with scale-dependent closure** and an
  **absolute survival override**. The scaffolding for all of this already exists in the
  code but is unused. The fixes should populate it, not invent it.

---

## 1. Evidence — the verified mechanics

**E1 — Completion is gated on plan-steps-done, not objective-met.**
`pursue_goal.py:811` — the completion block only runs `if remaining == 0`. The milestone
check (`pursue_goal.py:817`) is nested *inside* that gate, so it's never reached while any
step is pending. There's a guard against **hollow** completion (steps done, objective unmet
→ re-plan/fail, `pursue_goal.py:818`) but **no path for the inverse**: objective met, plan
unfinished — which should be a *success*.

**E2 — The blocking steps can never execute.**
The pending steps are *"Generate a self-question from what I found"* and *"Reflect on
whether the question connects to any current goal."* `recognise_step_action`
(`step_execution.py:97`) maps a step to a tool by substring; neither phrase matches any
keyword (`step_execution.py:45–62`), so both return `None` — a thought, not an act. Thought
steps are never marked `completed`, so `remaining` never hits 0, so E1's gate never opens.

**E3 — Exploration has no cross-call novelty memory.**
`search_own_files` dedups *within one call* but keeps **no memory across calls**, so every
invocation returns the same ~20 matches. The action "succeeds" while surfacing zero new
information.

**E4 — The stall watchdog is blind to this loop.**
`_plan_progress_sig = (completed_steps, met_milestones, plan_len)` (`metacog.py:138`). When
the plan regenerates and the search step re-completes, `completed_steps` 0→1, the signature
changes, `advanced = True`, `stall` resets (`metacog.py:186`). So the I12 watchdog
(`_WATCHDOG_CYCLES = 12`, `metacog.py:75`) never fires — the goal *looks* like it advances
every cycle while making no real progress.

**E5 — Prediction failure has no corrective feedback.**
`assess_goal_progress` is predicted to drop `uncertainty` and raise `positive_valence`. The
searches yield nothing, so predictions fail (`mismatch` 0.75–1.0), firing surprise
(`prediction.py:425–428`) — but **nothing feeds sustained per-action prediction failure
back into the goal/action policy.** Mismatch becomes affective noise, not a reason to stop.

**E6 — Rut detection can't reach the goal layer.**
`metacog_analyze` detects the rut and suppresses the offending fn for 15 cycles
(`metacog.py:361`). But suppression targets the **bandit's** pick; the loop is driven by the
committed-goal **pursuit/executive** path, which bypasses bandit suppression. Muting
`search_own_files` doesn't stop the goal from re-running it.

**E7 — Homeostatic strain is purely downstream.**
The `affect_arbiter` stability-budget scaling is the *symptom* of E5 surprise + E6
stagnation + rumination emitting affect every cycle. It resolves once the loop is broken.

**E8 — There is no *hard* escape actuator; every recurrence guard is a soft offer.**
*This finding re-scopes the whole back half of the plan.* End-to-end:
1. The I12 watchdog does **not** act — it only **emits an offer** (`metacog.py:219–222`,
   `wants="re-plan"`); the `release` escalation at 2× is also just an offer
   (`metacog.py:226–229`). Metacog mutates no goal state by design (`metacog.py:151`).
2. That offer must **win a single-winner salience competition** to reach consciousness
   (`global_workspace.py:171`); only the winner's `wants` is carried (`:182`).
3. Even then it applies a **soft +0.40 additive bias** toward `abandon_goal`
   (`select_function.py:805`), *"BIASES, never forces (I7) … competing with everything
   else"* (`:793`) — and only on the **deliberate** lane, while the runaway is on the
   **procedural/Executive** lane (E6).

Three soft gates in series, no hard backstop. The live goal *already* fires structural
offers (`objective_unmet` `:205`, `stuck_step` `:214`) and is still stuck. So any fix that
merely emits *more/earlier* offers feeds a funnel that has already failed. The system needs
a **hard** lever (Fix 2); Fix 1 is currently the only one.

---

## 2. The cascade

```
E1 closure gated on plan, not objective ─┐
E2 plan steps can't execute ─────────────┼──► goal never closes
E3 no novelty memory ───► same search ───┘        │
                                                  ▼
                         re-pursue every cycle  ──► E5 predictions fail (mismatch ↑)
                                                  ├──► E4 stall sig churns → watchdog never fires
                                                  ├──► E6 rut detected, can't act → stagnation floods
                                                  └──► E7 affect budget exceeded → deltas numbed
                                                              │
   E8 even when E4/E6 DO fire, the offer is advisory ─────────┘ (no hard actuator → loop persists)
```

---

## 3. The goal system as it actually exists (verified)

The fixes must build on this, not reinvent it. All four pieces the redesign needs already
have scaffolding in the tree — three are under-used, one is unpopulated.

**3.1 — A goal *hierarchy* already exists: aspirations → concrete goals.**
`_ASPIRATIONS` (`intrinsic_goals.py:593`) are four enduring directional goals — *"Understand
my own mind,"* *"Understand the world more deeply,"* *"Be genuinely useful…,"* *"Make
things…"* — created with `kind="aspiration"`, `tier="long_term"`, and *"never auto-completed,
never pursued/committed directly"* (`:590–591`). They **accrue** progress as concrete goals
that `serve` them complete (`credit_aspirations`, `:651`; reverts any wrongly-completed
aspiration, `:695`). **These are exactly the user's "ambiguous goals that never end," and the
mechanism is already correct.** The live tree confirms it: every short-term goal carries a
`serves` link to one of these (`goals_mem.json`).

**3.2 — A goal *scale/tier* system exists but is unpopulated.**
`achievement_significance` (`goals.py:543`) weights felt achievement by tier:
`_TIER_W = {existential 1.25, core 1.12, identity 1.12, growth 1.0, exploratory 0.92, minor
0.8, trivial 0.7}`, further scaled by milestone count, plan length, and struggle. **This is
the machinery for "tiny (a funny note) → large (understand physics)."** But generation
hardcodes `tier="short_term"` and `kind="generic"` on every goal (`intrinsic_goals.py:875,
1064`), so **all 15 live goals are the same tier** — the scale axis is defined and never
used. The reward magnitude already *wants* to scale with ambition; nothing tells it the
ambition.

**3.3 — Multiple concurrent goals already run; one focus is conscious.**
The Executive pulls `committed_goals` (plural, ≤ `_DEFAULT_QUEUE_K = 3`) priority-ordered
from the GoalsAPI (`executive.py:44,69,75`), runs a **round-robin advancing one goal's step
per cycle** (`:134–137`), and swaps each target into the `committed_goal` slot only for its
pursuit call, **restoring the single deliberate focus afterward** (`:148–162`). So "multiple
goals at a time" is *already* implemented at the procedural layer, with one attentional
spotlight — which is itself brain-accurate (you pursue many goals, attend to one). The queue
is populated live, not dead code: `ORRIN_loop.py:1264` sets
`context["committed_goals"] = goal_io.committed_goals_v1(api, limit=3)` each cycle and seeds
`committed_goal` from its head (`:1268`). What's missing is only **priority/drive weighting**
of the rotation — it advances goals in flat round-robin order (`executive.py:135`), giving a
`trivial` goal the same share as a `core` one (addressed in 6.3).

**3.4 — Survival is already tiered, but only *gates* and *biases* — it can't *preempt*.**
Three existing survival mechanisms:
- `setpoint_regulation.py` — *"Tier 1 survival daemon, unconditional background monitoring,"*
  detection-only; on `critical` (e.g. `resource_deficit > 0.92`, data corruption) the main
  loop *"may override the bandit's choice entirely."*
- `_under_load` (`intrinsic_goals.py:37`) — blocks adoption of **new** goals under
  strain/low health/resource-deficit (stops thrash).
- `threat_detector` (`motivation/drive.py`) — can hard-override function selection to a
  safety function.

**Gap:** all three act at *function selection* or *new-goal adoption*. None **suspends an
already-committed goal**. So a poorly-bounded long-running concrete goal (the realistic
danger — aspirations are never committed, §3.1) can still monopolize the Executive while
survival pressure climbs. The user's constraint *"never-ending goals can't get in the way of
survival"* is **not** currently enforced at the pursuit layer.

---

## 4. The brain-accurate target model

This reframes "when does a goal close?" — the question review surfaced — and folds in the
user's four requirements (many goals, many scales, never-ending goals, survival first).

**4.1 — Plan-completion ≠ goal-satisfaction (so Fix 1's *direction* is correct).**
In the brain, plans are flexible *means* (PFC); the drive behind a goal is *motivational*
(limbic/dopaminergic). Satisfy the drive and the plan is dropped mid-execution — the brain
never refuses to feel "done" because a sub-step didn't fire. E1 (closure gated on
plan-steps) is the least brain-like thing in the system; decoupling closure from plan
completion is unambiguously correct.

**4.2 — Two distinct closure pathways, neither a milestone checkbox.**
- **Satiety closure (success)** — an exploration/understanding drive is quenched by
  *habituation of novelty / information gain*: the dopaminergic novelty response decays as
  repeated sampling stops reducing uncertainty. The brain-true signal is *"the rate of new
  information has fallen,"* not *"one action was logged."* **Two satiety proxies by goal
  type** (this distinction is load-bearing — see Fix 1/Fix 4):
  - *Bounded-corpus exploration* (filesystem: `search_own_files`, `grep_files`,
    `survey_environment` — the live Explore goal): satiety = **Fix 4's novel-observation
    counter flattening** (repeated calls stop surfacing new locations → `exhausted`). Works
    because the corpus is finite.
  - *Open-ended understanding/research* (web: `research_topic`, `wikipedia_search`,
    `fetch_and_read` — the bulk of `"Understand X more deeply"` goals): the web is
    effectively *unbounded-novelty*, so Fix 4's counter never flattens. Satiety here =
    **`uncertainty(topic)` dropping** below threshold — the information-gap signal that
    *already exists* (`intrinsic_motivation.py:56`, `0=covered…1=unknown`) and is already
    used to *pick* deepening topics (`intrinsic_goals.py:534`). A topic is "understood
    enough" when its info-gap closes, not when search results stop differing.
- **Disengagement closure (giving up)** — distinct substrate: dorsal ACC computes a "quit"
  signal when effort yields no reward, avoiding learned helplessness. This is Fix 2 (hard
  actuator) + Fix 6 (sustained-failure feedback).

A goal closes when **either** pathway fires. The current code has *neither* — it has a plan
gate.

**4.3 — The closure *bar scales with tier* (this resolves the milestone-quality debate).**
Process-milestones are not wrong *per se* — they're wrong *uniformly applied*:
- **`trivial`/`minor` goal** (*"write something funny in a doc to remember"*): the act *is*
  the satisfaction. "A note was written" is a correct, brain-accurate closing condition.
  One-and-done is right here. **Keep process-milestones.**
- **`growth`/`core` goal** (*"understand how physics works"*): one search cannot satisfy
  this; closing on "a fact was written" is the bug. It must close on **satiety** (4.2 novelty
  derivative flattening) **or** be explicitly open-ended and ladder upward like an aspiration.
- **`aspiration`** (never-ending): never closes; accrues (§3.1, already correct).

So the redesign is **not** "add an outcome bar to every goal." It is: **generation assigns a
tier, and closure semantics are selected by tier.** A trivial goal keeps the cheap gate; a
large goal gets the satiety gate; an aspiration never closes. This is why the live Explore
goal feels wrong — it's a `growth`-scale question (*"what's here?"*) wearing `trivial`-scale
process-milestones.

**4.4 — Many goals, one attention (already mostly built — §3.3).**
Keep the Executive's concurrent-queue + single-deliberate-focus design (brain-accurate).
Add **priority/drive weighting** to the rotation so a higher-tier or survival-relevant goal
gets more of the round-robin than a trivial one, instead of flat rotation.

**4.5 — Survival is strict precedence, and must *preempt*, not just gate.**
A homeostatic/survival drive crossing threshold must be able to **suspend the in-flight
committed goal** (pause, don't fail — it resumes when the drive clears), not merely block new
adoption (§3.4 gap). This is the mechanism that enforces *"never-ending goals can't get in
the way of survival."* It generalizes the existing `setpoint` critical-override from
*function selection* up to *goal pursuit*. Pause-not-fail matters: survival interrupts are
transient, and a never-ending/large goal should be **resumable**, not destroyed, by a
survival blip.

---

## 5. Fixes (ordered by leverage)

### Fix 1 — Tier-aware objective closure *(keystone — the hard close)*
**Where:** `pursue_goal.py` — a guard **before** the `remaining == 0` gate at `:811`, reusing
the existing completion machinery below it.
**Change:** Decouple closure from plan completion (§4.1), and select the closing condition by
tier (§4.3):
- **`trivial`/`minor`:** if its (process) milestones are all met → complete now, regardless
  of pending plan steps. The act is the satisfaction.
- **`growth`/`core`/`exploratory`:** do **not** close on process-milestones alone; close on
  the **satiety signal** — Fix 4's novelty-counter flattening for *filesystem* exploration,
  or **`uncertainty(topic)` dropping** for *web research/understanding* goals (§4.2; the
  novelty counter never flattens on unbounded web results, so research goals need the
  info-gap proxy) — or via the disengagement pathway (Fix 2). Until satiety, keep pursuing
  (bounded by Fix 2 so it can't spin forever).
- **`aspiration`:** never closes here (already enforced, §3.1).

**Required sub-behaviours (correctness, not polish):**
- **(a)** Guard the trivial short-circuit on `_ms and all(m.get("met") for m in _ms)` —
  `all([])` is vacuously true; milestone-less goals route to Fix 5, never auto-close.
- **(b)** Run `apply_milestone_updates(context)` first (`:813–814`) so a just-met milestone
  is seen.
- **(c)** Route the write through `goal_arbiter.apply(...)` like the existing completed path
  (`:840,849`) — atomic load→merge→save, never an in-place mutation, or it won't persist.
- **(d)** Idempotency guard on `goal.get("status") not in {completed,abandoned,failed}` in
  **both** completion paths, so the completion reward fires **exactly once**.
- **(e)** Keep `mark_goal_completed`'s hollow-completion guard intact — it refuses to
  complete (and refuses to reward) when milestones are unmet (`goals.py:566`, guard at
  `:575`: *"No objective met → no completion, no reward"*). Fix 1 only removes the *additional*
  plan-completion requirement, never this. (Note `mark_goal_completed` has **no**
  already-`completed` re-entry guard of its own — it would re-fire the reward if called twice
  — which is exactly why Fix 1(d)'s idempotency check is required, not optional.)

**Hard prerequisite — §6.1 (generation assigns tier) ships *with* Fix 1.** This is a settled
decision, not an option (rationale below). Until generation populates `tier` (it currently
hardcodes `short_term`/`generic`, §3.2), the tier branch is inert. `growth` is the
**unknown-tier fallback only** — applied to genuinely unclassifiable goals — **not** a
universal default. Known-`trivial` goals must get the cheap one-act close; only ambiguous
goals fall back to satiety-gating.

> **Decision (settled): per-tier closure, `growth` as the unknown-fallback — *not* a blanket
> `growth` default.** A uniform satiety gate is both less stable and less brain-accurate:
> (1) satiety is only well-defined for *exploratory* goals — a `trivial` goal has no novelty
> stream, so a blanket satiety gate never cleanly fires and re-introduces the stall we're
> removing; (2) such goals could then only close via Fix 2's *disengagement* path, replacing
> "accomplished" affect with "gave up" affect on every small goal — a persistent negative
> affective drift over time; (3) it puts the least-proven mechanism (Fix 4's novelty
> derivative) in the load path of *every* goal instead of scoping it to `growth+`. Humans
> close trivial goals by *doing the act* and large goals by *satiety/waning interest* — these
> are distinct, and the model must reflect that. Classification is near-free because
> generation is already templated (`leave a note` → `trivial`, `understand X` → `growth`), so
> the blanket default buys little simplicity while taking on real risk. A blanket `growth`
> default is acceptable **only** as a <24h stopgap if §6.1 slips — never as the shipped model.
**Why:** directly closes the live goal *correctly* (the Explore goal is `growth`-scale → it
closes when novelty is exhausted, not on the first search) and fixes the inverse-gate bug.
**Verify:** a `trivial` goal with met process-milestones closes in one cycle; the live
Explore goal closes when Fix 4's novelty counter flattens (not on cycle 1); the completion
reward fires once; no milestone-less goal auto-closes.

### Fix 2 — A hard escalation actuator + survival preemption *(the missing lever)*
**Where:** `metacog.py` watchdog/escalation (`:219–229`) + a per-goal counter on the
monitor's `gs` record (`:183`) + a preemption hook in `executive.py`/`pursue_goal.py`.
**Why its own fix:** E8 shows the watchdog already escalates — by emitting louder *offers*
that die in three soft gates. Hardening the *signal* (Fix 3) without a hard *sink* just adds
advisories.
**Change — two hard levers:**
- **Disengagement (§4.2):** add a per-goal `un_honored` counter (the §20.1 honored/dismissed
  verdict is per offer-*kind*, not per-goal — consume its signal but accumulate per-goal).
  When it crosses a hard threshold after the soft offers have had their chance, **call the
  guarded `mark_goal_failed`/`abandon_goal` directly** from metacog's escalation path (the
  only option that *deterministically* acts; both are already guarded and feed self-repair).
  A narrow, logged exception to "metacog mutates no goal state." `_force_action_next` is a
  *soft* fallback only — it forces *an* action, not necessarily the release.
- **Survival preemption (§4.5):** when a survival/homeostatic drive crosses threshold (read
  the signals `setpoint_regulation`/`_under_load`/DriveEngine already produce), **suspend the
  committed goal** (`status="paused"`, resumable — the Executive already skips `paused`,
  `executive.py:87`) rather than letting pursuit continue. Resume when the drive clears.
**Why:** converts "the system is aware it's stuck / under threat" into "the system stops /
yields" — which E8 shows nothing currently does, and §3.4 shows survival can't currently do
to an in-flight goal.
**Verify:** a goal emitting un-honored structural offers is hard-released within a bounded
number of cycles, no human input; a spiking survival drive pauses (not fails) the committed
goal mid-pursuit and it resumes after.

### Fix 3 — A real-progress (satiety) stall signature *(depends on Fix 4)*
**Where:** `metacog.py:138` `_plan_progress_sig` + advance check `:185–186`.
**Depends on Fix 4** — `_plan_progress_sig(goal)` receives only `goal`; the novelty counter
it needs doesn't exist on the goal today and must be persisted there by Fix 4.
**Change:** add the **novel-observation count** to the signature; `advanced =` *that*
changed, not merely `completed_steps`. "Same fingerprint for N cycles despite step
re-completions" = **stall** → fires the watchdog → hits **Fix 2's hard sink** (not another
advisory). This same flattening signal is the **satiety** read Fix 1 uses to close large
goals (§4.2) — one signal, two consumers.
**Verify:** a synthetic goal re-completing the same step with identical Fix-4 results accrues
`stall` and trips the watchdog by `_WATCHDOG_CYCLES`.

### Fix 4 — Novelty memory for exploration actions *(supplies the satiety signal)*
**Where:** `search_own_files.py` + the other `_PROCEDURAL_FNS` explorers
(`step_execution.py:84–89`).
**Change:** persist a **per-(action, goal)** "already-surfaced" set (result hashes / visited
locations) across calls. When a call yields no new results, return
`{"status":"ok","novel":false,"exhausted":true,…}`; expose a monotonic **novel-observation
counter** (Fix 3 reads it; Fix 1 reads its derivative for satiety).
**Scope note — Fix 4 supplies satiety only for bounded-corpus exploration.** This counter
flattens for filesystem search (finite corpus) but **not** for web research (unbounded
novelty), so it is *not* the satiety signal for `"Understand X"` goals — those use
`uncertainty(topic)` (§4.2). Fix 4 covers the live Explore goal and other filesystem
explorers; it does not, by itself, let research goals close.
**Scope & decay (correctness):** scope **per-(action, goal)**, not global (a global flag
would starve a *future* explore goal's first search); **age/decay** the set, don't only cap
it (the agent writes files, so the corpus genuinely grows — "exhausted" is never permanent).
**Verify:** a second identical call in one goal returns `novel:false`; a *different* goal's
first call still returns results; after the corpus changes, a previously-exhausted query can
re-surface novelty.

### Fix 5 — Don't let unexecutable "thought" steps block closure *(milestone-less goals)*
**Where:** `pursue_goal.py` step path + `recognise_step_action` (`step_execution.py:97`).
**Change:** when a step maps to `None` (a thought), either hand it to the deliberate mind and
mark it `completed` once processed, or exclude `None`-mapped steps from the `remaining` gate
so they can't deadlock it.
**Verify:** a milestone-less goal whose plan contains a thought-step still reaches `completed`.

### Fix 6 — Prediction failure → policy feedback *(the disengagement arc)*
**Where:** `prediction.py:check_predictions` (`:365`) + the goal/action policy.
**Change:** track a per-(action, goal) **mismatch EMA**; when sustained high (> 0.6 over K),
lower that action's expected payoff for that goal and feed the signal into **Fix 2's
escalation counter** (one path to the hard sink, not a competing soft offer). Sustained
failure, never a single miss.
**Verified store caveat:** `decision_stats.json` is keyed **per-function**, not
per-(action, goal) (`interoception.py:139` "Per-function avg_reward"; written
`reflection.py:247`). Lowering payoff there penalizes the action for **every** goal (global
over-suppression, same class as Fix 4's global risk). A per-(action, goal) penalty needs
**new scoped state**, or the global down-weight must be a conscious choice.
**Verify:** after K failed predictions on a goal, its payoff drops and the escalation counter
advances; **at most one** offer per stuck goal per cycle.

### Fix 7 — Rut detection that reaches the goal layer
**Where:** `metacog_analyze` rut branch (`metacog.py:349–361`).
**Change:** when the rut fn is goal-driven, feed it into **Fix 2's un-honored counter** so a
persistent goal-driven rut escalates to the *hard* actuator, not just a bandit mute. With
Fix 2 present, Fix 7 is a *signal source* for the hard escalator, not a standalone soft offer.
**Verify:** a goal-driven rut advances the escalation counter and ultimately triggers Fix 2's
hard release.

### Fix 8 — Habituate repeated identical alerts *(downstream hygiene)*
**Where:** the "Affective stagnation" note (`metacog.py:405+`) + rumination emit.
**Change:** collapse/decay repeated identical stagnation alerts (one alert + a rising
counter). **Verify:** stagnation produces a single decaying alert; `affect_arbiter` stops
logging budget-exceeded once Fixes 1–7 land.

---

## 6. Structural follow-on — populate the model (enables tier-aware closure)

These aren't loop-bug fixes; they make §4's model real. Fix 1's tier branch is inert until
generation supplies a tier, so **6.1 is a prerequisite for Fix 1's correctness, not optional.**

- **6.1 — Generation assigns tier + scale. [HARD PREREQUISITE for Fix 1 — ships together.]**
  `intrinsic_goals.py` must classify each goal it mints (`_mk_goal`, the LLM path, the
  templates) into the existing `_TIER_W` bands (`trivial…existential`) instead of hardcoding
  `short_term`/`generic` (`:875,1064`). Cheapest start: derive tier from `driven_by` + a size
  heuristic (a "leave a note" template → `trivial`; an "understand X" deepening goal →
  `growth`); the LLM prompt (`:932`) can be asked for a tier directly. `growth` is the
  **unknown-tier fallback**, not a default for all goals (see Fix 1 decision box). Without
  this, Fix 1's tier branch is inert and the system either regresses to "every goal closes on
  one action" or — under a blanket `growth` default — fails to close trivial goals at all.
- **6.2 — Tier-appropriate milestones.** A `growth` goal's milestones should be **outcome**
  bars (e.g. *N distinct* novel observations, sourced from Fix 4's counter), not the process
  bars the templates emit today. Trivial goals keep process bars.
- **6.3 — Priority/drive-weighted Executive rotation (§4.4).** Replace the flat round-robin
  (`executive.py:134`) with a weighting by tier/priority/drive so larger or
  survival-relevant goals get more cycles. Small change, brain-accurate.
- **6.4 — Continuity-spawn cooldown (anti-thrash for Fix 1).** The completion continuity hook
  auto-commits the next goal inside `mark_goal_completed` (`goals.py:641`). If Fix 1 closes a
  trivial goal each cycle and the hook respawns a near-identical one, the old spin becomes a
  spawn→complete→reward churn. Ship a cooldown: don't re-commit a same-template goal completed
  in the last N cycles (a `_RECENTLY_COMPLETED` cooldown already exists in generation,
  `intrinsic_goals.py:74` — extend it to the continuity hook).

---

## 7. Sequencing

1. **Fix 1 + 6.1 + 6.4** — keystone closure, *with* tier-assignment (6.1 is a hard
   prerequisite, not optional — see Fix 1 decision box) and the spawn cooldown, so closure is
   correct (not "everything closes on one action," not "trivial goals never close") and
   doesn't thrash. Ship + verify first. `growth` is the **unknown-tier fallback only**, never
   a blanket default.
2. **Fix 2** — the hard actuator (disengagement) + survival preemption. Lands before any
   soft-offer fix so offers have a hard sink (E8) and survival can preempt (§3.4 gap).
3. **Fix 4 → Fix 3** — novelty store first, then the satiety/stall signature that consumes
   its counter (Fix 3 depends on Fix 4).
4. **Fix 5** — deadlock removal for milestone-less goals.
5. **Fix 6 + Fix 7** — feedback arcs, wired into Fix 2's escalator, deduped (E8 anti-flood).
6. **6.2, 6.3, Fix 8** — outcome-milestones, weighted rotation, alert hygiene.

Each ships behind a flag where it touches the live affect/goal loop, verified by a watched
restart before the next lands. **Reversibility caveat:** a flag gates *code*, but once Fix 1
or Fix 2 fire a completion reward or a hard release/pause they have shifted persistent
affect/reward/goal state — a watched restart is not a clean rollback. Fixes 1, 2, 6 leave
residue; Fixes 3, 4, 8 are code-reversible.

---

## 8. Risks & guards

| Risk | Guard |
|---|---|
| Fix 1 closes *every* goal on one action (the original bug, inverted) | Tier-gated closure (§4.3): only `trivial`/`minor` close on process-milestones; `growth`+ close on satiety/disengagement. Unknown-tier fallback = `growth`, not trivial. |
| Blanket `growth` default leaves trivial goals never closing | Rejected as the shipped model (Fix 1 decision box): per-tier closure with `growth` only as unknown-fallback; known-`trivial` goals close on the act. Blanket default allowed only as a <24h stopgap if 6.1 slips. |
| 6.1 mis-classifies a goal's tier | Fix 2's disengagement pathway backstops a too-high tier (it still releases); a too-low tier is caught by the all-milestones-met assertion still gating completion. Heuristic is near-deterministic because generation is templated. |
| Fix 1 weakens anti-hollow protection | It doesn't — `mark_goal_completed`'s guard still refuses completion + reward when milestones are unmet (`goals.py:566`, guard `:575`); Fix 1 only removes the extra plan-completion requirement. |
| Fix 1 closes/​rewards twice | Idempotency guard on `status` in both paths (1d). |
| Fix 1 short-circuits milestone-less goals | `_ms and all(...)` guard (1a); they route to Fix 5. |
| Fix 1 completion doesn't persist | Route through `goal_arbiter.apply(...)` (1c). |
| Fix 1 trades spin for spawn-thrash | Continuity-spawn cooldown (6.4); does **not** block Fix 1. |
| Fix 2 over-abandons real-but-slow goals | Hard release only after N un-honored offers *post* soft-path; routes to *guarded* `abandon_goal`/`mark_goal_failed`, feeding self-repair. |
| Fix 2 breaks "metacog mutates no goal state" | Deliberate, narrow, logged exception, reachable only on proven N-cycle soft-path failure. |
| Fix 2 survival preemption destroys a long/never-ending goal | **Pause, not fail** (`status="paused"`, resumable, `executive.py:87`); resume on drive clear (§4.5). |
| Fix 3 breaks "advance resets stall" | Novelty term *adds*; real progress still resets `stall`. |
| Fix 4 over-suppresses a future goal's first search | Per-(action, goal) scope + decay, never global+permanent. |
| `growth` *research* goals never reach satiety (Fix 4 counter never flattens on unbounded web results) → only ever close via Fix 2 disengagement | Use `uncertainty(topic)` (`intrinsic_motivation.py:56`) as the satiety proxy for web/understanding goals; reserve Fix 4's counter for bounded-corpus (filesystem) exploration (§4.2, Fix 1). |
| Fixes 2/6/7 flood the workspace | One offer per stuck goal per cycle; 6/7 route into Fix 2's counter, not independent offers. |
| Fix 6 penalizes an action globally (wrong granularity) | `decision_stats` is per-function; per-(action, goal) penalty needs new scoped state, or accept the global down-weight knowingly. |

---

## 9. Acceptance criteria

- **A1.** The live *"Explore the computer"* goal (`growth`-tier, *filesystem* exploration)
  reaches `completed` **when Fix 4's novelty counter flattens** — not on cycle 1 — the search
  loop stops, and the completion reward fires **exactly once**.
- **A1b.** A `growth`-tier *research* goal (`"Understand X more deeply"`) reaches `completed`
  when **`uncertainty(X)` drops below threshold**, not via Fix 4's counter (which never
  flattens on web results) and not via Fix 2 disengagement — confirming research goals have a
  real *satiety* (success) close, not only a give-up close (§4.2).
- **A2.** A `trivial`-tier goal with met process-milestones closes in **one** cycle (via the
  *act/satiety* path, registering as accomplished — **not** via Fix 2 disengagement), while a
  `growth`-tier goal does **not** close in one cycle. Confirms per-tier closure, not a blanket
  `growth` default.
- **A3.** A synthetic **unmet-objective** same-step-same-result goal trips the watchdog by
  `_WATCHDOG_CYCLES` (Fix 3) **and is hard-released by Fix 2** within a bounded number of
  further cycles, no human input.
- **A4.** A repeated `search_own_files` in one goal reports `novel:false`; a *different*
  goal's first call still returns results (Fix 4).
- **A5.** Sustained prediction failure lowers the action's payoff and advances Fix 2's
  escalation counter; **at most one** offer per stuck goal per cycle (Fix 6/7/2).
- **A6.** A spiking survival/homeostatic drive **pauses** the committed goal mid-pursuit
  (`status="paused"`) and it **resumes** after the drive clears — it is not failed (§4.5).
- **A7.** Multiple goals advance across cycles via the Executive queue while a single
  deliberate focus is maintained; higher-tier goals get more rotation than trivial ones (6.3).
- **A8.** No spawn-thrash: after A1/A2, the continuity-spawned goal does not itself
  close-and-reward within one cycle (6.4 cooldown).
- **A9.** `affect_arbiter` stops logging "stability budget exceeded" in steady state, and the
  stagnation alert no longer floods (Fix 8).
- **A10.** No regression: goals needing their plan to finish still gate correctly; aspirations
  still never auto-complete and still accrue (§3.1).

---

## 11. Implementation status (Rev 5 — built)

All fixes implemented on branch `convergence-layer`, flag-gated, 181 existing tests pass,
no regressions. End-to-end: the live Explore goal now closes on the cycle its novelty is
exhausted (~cycle 4), not cycle 1 and not never.

**New modules**
- `brain/cognition/novelty_memory.py` — Fix 4 per-(goal, action) novelty store
  (observe / novel_count / is_exhausted), aged + capped.
- `brain/cognition/planning/goal_satiety.py` — Fix 1 satiety helper (two proxies by goal
  type: novelty-exhaustion for filesystem, `uncertainty(topic)` for research; work-gate
  blocks cycle-1 closure).

**Edited**
- `pursue_goal.py` — Fix 1 tier-aware closure (`_maybe_close_on_tier`), idempotent
  `_finalize_goal_completion`, Fix 5 thought-step exclusion (milestone-less goals), Fix 2
  survival preemption (`_survival_critical`, yield-not-fail).
- `metacog.py` — Fix 3 novelty term in `_plan_progress_sig` + real-progress stall reset,
  Fix 2 hard-disengage actuator (3× watchdog → guarded `mark_goal_failed`), Fix 7
  goal-driven rut → stall bump, Fix 8 stagnation re-arm.
- `intrinsic_goals.py` — 6.1 `_classify_tier` applied at every mint point.
- `goals.py` — 6.4 spawn cooldown recorded before the continuity hook.
- `search_own_files.py` — Fix 4 wiring (records observations, reports "nothing new").
- `executive.py` — 6.3 tier-weighted round-robin.
- `prediction.py` — Fix 6 goal-scoped sustained-mismatch EMA → Fix 2 escalation.

**Flags** (house pattern; all default OFF ⇒ legacy behavior)
- `ORRIN_TIER_CLOSURE` — Fix 1 tier/satiety closure + Fix 5 thought-step exclusion.
- `ORRIN_HARD_DISENGAGE` — Fix 2 hard actuator + Fix 6 + Fix 7 (the escalation arc).
- `ORRIN_SURVIVAL_PREEMPT` — Fix 2 survival preemption.
- 6.1 / 6.3 / 6.4 / Fix 8 are unflagged (additive, safe: tier metadata, weighted rotation,
  cooldown, single-shot alert).

**Deferred / subsumed (documented, not skipped silently)**
- **Fix 6 per-action payoff-lowering** — the prediction schema carries no `(action, goal)`
  key (`prediction.py:212`), so per-action payoff can't be lowered without new linkage; the
  *goal-scoped* corrective arc (sustained mismatch → Fix 2) is implemented, which is the part
  that stops the loop.
- **6.2 outcome-milestones** — subsumed by Fix 1 satiety: growth goals now close on the
  satiety signal (the real outcome bar), so swapping process-milestones for
  N-distinct-observation bars would be redundant and risks re-introducing stalls on small
  corpora. Not added rather than add risky/dead code.

**Still requires watched-restart verification** (the house pattern — can't be unit-tested):
A1/A1b/A6/A7 behaviours under the live loop, and tuning of `_UNCERTAINTY_SATED` (0.25),
`_BARREN_EXHAUSTED` (3), and the `3×` hard-disengage threshold.

### 11.1 Found and fixed by *running* it (not in the original plan)

A live run (flags on) reproduced the loop and exposed three issues the unit tests could not.
All three are fixed and verified; the third is the most important and was a blind spot in the
plan's entire layer of analysis.

1. **Novelty granularity defeated by Orrin's own growing files.** Hashing matches by
   `file:line` counted the *same* content at *new* line numbers as novel — because the search
   matches `activity_log.txt`/`private_thoughts.txt`, which grow every cycle (the log even
   records the goal title each cycle). `count=52, barren=0` → satiety never fired. Fix: hash by
   **file path** (the right unit for "what areas exist") + a **diminishing-returns / habituation**
   clause (`novelty_memory.py` `_LOW_NOVELTY_RATIO`/`_LOW_NOVELTY_LIMIT`) so satiety is "new-rate
   fell," not "zero new." (`search_own_files.py`, `novelty_memory.py`.)

2. **Double-reward across stale goal-dict copies.** The same goal exists as several dicts at
   once (`committed_goal`, the `committed_goals` queue, a store pull), all still `in_progress`,
   so the per-dict idempotency check passed for each and the completion fired twice (~141s
   apart). Fix: a per-goal-id finalize guard (`_FINALIZED_IDS`, 1-hour window) in `pursue_goal.py`.

3. **Closure didn't *persist* — the keystone blind spot.** The satiety close correctly marked
   the goal `completed`, but it kept reverting to `in_progress` and being re-pursued
   (observed `barren×25`); the goal_auditor independently reported *"15 goals, only 4 ever
   completed."* Root cause: `save_goals` (`goals.py`) is hit by *dozens of uncoordinated
   load→mutate→save call sites* (the GoalArbiter's own header admits this), so a writer holding
   a **stale `in_progress` copy overwrites the `completed` status** — a classic lost-update.
   **The entire fix plan was written against the v1 `pursue_goal` closure layer and never
   analyzed the goal-*persistence* layer.** Fix: **terminal-status stickiness** at the single
   save chokepoint (`save_goals`, `_TERMINAL_STATUSES`) — a goal already
   `completed/failed/abandoned` on disk can never be downgraded to a non-terminal status by a
   stale copy. This is also the structural cause behind `CRITICAL_REVIEW.md` #3 ("goal
   completion is not first-class") and the low completion rate.

**Live-verified before the persistence fix:** satiety closure fires (`closed
(satiety:novelty_exhausted…)`), survival preemption fires (`survival preemption
(resource_deficit>0.85) — yielding … resumable`), continuity spawns *varied* goals (no
same-title thrash). **Still to verify live (post-fix):** that the Explore goal now closes
**once and stays closed** (no resurrection) — a watched restart with the flags.

---

## 10. Changelog

**Rev 4.1 → Rev 4.2** (verification pass — re-checked every load-bearing citation against the
tree; two real errors found):
- **Wrong citation corrected:** `goals.py:543` is `achievement_significance`/`_TIER_W`, **not**
  the hollow-completion guard. The real guard is `mark_goal_completed` (`:566`, refusal at
  `:575`). Fixed in Fix 1(e) and the risk table. Also noted `mark_goal_completed` has no
  already-completed re-entry guard, which is *why* Fix 1(d) idempotency is mandatory.
- **Conceptual hole closed:** Fix 1/Fix 4 claimed `growth` goals close on "Fix 4's novelty
  derivative," but that counter only flattens for *bounded-corpus* (filesystem) exploration —
  **web research goals (the bulk of `"Understand X"`) would never reach satiety** and could
  only ever close by giving up. Added the second satiety proxy, `uncertainty(topic)`
  (`intrinsic_motivation.py:56`, already used at `intrinsic_goals.py:534`), to §4.2/Fix 1/Fix 4,
  a risk row, and acceptance A1b.
- **Tightened §3.3:** the multi-goal queue is confirmed *live* (`ORRIN_loop.py:1264–1268`
  populates `committed_goals`), not dead code; removed the vague "queue can't grow past
  bootstrap" claim — the only real gap is flat-rotation weighting (6.3).
- Re-verified and left unchanged: E1 (`pursue_goal.py:811/817/818`), E3
  (`search_own_files.py:98` within-call dedup), E4 (`metacog.py:138/186`, `_WATCHDOG_CYCLES`
  `:75`), E6 (`_try_suppress(top_fn, 15…)` `metacog.py:361`), Fix 6 store granularity
  (`interoception.py:139`, `reflection.py:247`), Fix 7 rut branch (`metacog.py:349–361`),
  Fix 8 stagnation (`metacog.py:405`), 6.4 continuity hook (`goals.py:641`).

**Rev 4 → Rev 4.1** (settled the closure-default decision):
- **Per-tier closure with `growth` as the unknown-fallback** is now a recorded decision
  (Fix 1 decision box), chosen over a blanket `growth` default on long-term-stability and
  brain-fidelity grounds: a uniform satiety gate doesn't fire on non-exploratory goals
  (re-stall), forces trivial goals to close via "gave-up" disengagement (affective drift),
  and over-extends the unproven novelty signal to every goal. **§6.1 (tier assignment) is
  promoted to a hard prerequisite that ships with Fix 1.** Sequencing, risks, and A2 updated
  accordingly.

**Rev 3 → Rev 4** (deep architecture pass, per request — "get as close to how the human
brain works"; survey what exists first):
- **New §3** — documented the *existing* goal architecture: the aspiration hierarchy
  (`intrinsic_goals.py:593`, the user's never-ending goals — already correct), the unpopulated
  tier system (`goals.py` `_TIER_W` — the tiny↔large scale, defined but unused), the
  already-built multi-goal Executive round-robin (`executive.py:44–162`), and the tiered
  survival layer that *gates but can't preempt* (`setpoint_regulation`, `_under_load`,
  `threat_detector`).
- **New §4** — the brain-accurate target: plan ≠ satisfaction (4.1); **two closure pathways**
  — satiety-via-habituation and effort-disengagement (4.2); **tier-scaled closure** resolving
  the milestone debate — process-milestones are correct for *trivial* goals, wrong for *large*
  ones (4.3); many-goals/one-attention (4.4); **survival as strict preemption, pause-not-fail**
  (4.5).
- **Fix 1** reworked from "milestones = objective" to **tier-aware closure** with a
  conservative `growth` default; A1 now expects the Explore goal to close on *satiety*, not
  cycle 1.
- **Fix 2** extended with **survival preemption** (pause the in-flight goal), closing the §3.4
  gap.
- **New §6** — structural follow-ons (tier assignment 6.1, outcome-milestones 6.2, weighted
  rotation 6.3, spawn cooldown 6.4); 6.1 promoted to a Fix 1 prerequisite.
- Acceptance expanded (A2 trivial one-shot, A6 survival pause/resume, A7 multi-goal+focus).

**Rev 2 → Rev 3:** Fix 2 added its own per-goal counter (the §20.1 verdict is per-kind);
direct guarded `mark_goal_failed` as the only hard actuator; Fix 6 per-function-store caveat;
§ milestone-quality reframed as spawn-cooldown not a Fix 1 blocker; typo + risk rows.

**Rev 1 → Rev 2:** added E8 (no hard actuator — the soft-offer funnel); promoted the hard
escalation actuator to its own fix; Fix 3 depends on Fix 4; Fix 4 scope per-(action, goal) +
decay; Fix 1 hardened (arbiter persistence, idempotency, empty-milestone exclusion,
spawn-thrash); Fixes 6/7 deduped; reversibility caveat.
