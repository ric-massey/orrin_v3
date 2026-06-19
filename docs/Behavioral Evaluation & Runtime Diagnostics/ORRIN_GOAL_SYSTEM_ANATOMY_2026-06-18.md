# The Orrin Goal System — Complete Anatomy

*Deep architecture map — 2026-06-18. Written after a full read of the goal
subsystem (~10k lines across `brain/cognition/planning/`, `brain/cognition/
intrinsic_goals.py`, `brain/goal_io.py`, the `goals/` daemon package and its
handlers) cross-checked against the live run data (`brain/data/goals_mem.json`,
`comp_goals.json`, `outcome_metrics.json`, `data/goals/{wal.log,state.jsonl}`,
`action_reward_ema.json`). Companion to `ORRIN_PRODUCTION_REWARD_PLAN_2026-06-18.md`
— that plan is the *fix*; this is the *understanding* it has to be correct about.*

---

## 0. The one-paragraph truth

Orrin's goal system is **three overlapping goal representations, two parallel
lifecycles, a rich unused execution engine, and a correct closure mechanism that
never fires** — held together by a fragile sync. The cognitive mind generates only
intake/introspection goals into a v1 store where they "complete" by self-report in
0.0 s with 0.0 significance; the real executor daemon (which *can* write code, run
research, edit files) is fed only janitorial goals; and the schema can express
fail-able, deadline-bound, artifact-gated "make things" goals that nothing ever
creates. The system's *own* metrics say it: **10,051 completed, 0 failed,
mean_significance 0.0, median_seconds_to_complete 0.0, satiety_closures 0,
maintenance_selections 31,498.**

---

## 1. The three goal representations (this is the root of the sprawl)

| # | Store | File(s) | Owns | Lifecycle vocabulary |
|---|---|---|---|---|
| **v2** | The **daemon** (`goals/` package + GoalsAPI) | `data/goals/wal.log`, `state.jsonl`, snapshots | Authoritative **lifecycle + priority**, and **execution** via registered handlers | `NEW → READY → RUNNING → DONE/FAILED/BLOCKED` (`goals/model.py Status`) |
| **v1** | The **cognitive tree** | `brain/data/goals_mem.json`, `comp_goals.json` | **Pursuit state**: plan, milestones, step attempts, replan count | `proposed → in_progress → completed/failed/abandoned/dormant` |
| **lifetime** | **Standing goals** | `LIFETIME_GOALS_FILE` (`goal_lifecycle.py`) | `never_complete` directional goals + `motivational_weight` decay | `in_progress → fading → dormant → revived / paused → resumed` |

Plus the **aspirations** (`intrinsic_goals._ASPIRATIONS`, 4 of them) which live as
`kind:"aspiration"` rows *inside the v1 tree* — a fourth, semi-overlapping notion of
"long-term goal" that is **distinct from** the `lifetime` store. So "a long-term
goal" can mean an aspiration row (v1), a lifetime goal (separate file), or a v2
long-kind goal. They are not unified.

**The bridge** (`brain/goal_io.py`) keeps v1 and v2 in sync and is visibly
scar-tissued: `_PURSUIT_FIELDS` carry-over exists because "the per-cycle
committed_goal rebuild discarded all plan progress and the milestone gate
regenerated the same plan forever (FINDINGS 2026-06-12 §1)"; `committed_goals_v1`
returns `[]` deliberately because a stale focus file "resurrected a closed goal and
pursued it for hours (§6)." The sync is correct *now* but it is the kind of
two-source-of-truth design that keeps generating those bugs.

---

## 2. The lifecycle, end to end (what actually happens to a goal)

```
GENERATE (v1, cognition)
  intrinsic_goals.generate_intrinsic_goals()
    └─ default deployment is TOOL-ONLY → LLM path off →
       _varied_symbolic_goal() draws from 6 generators, ALL intake/introspection:
         _goal_from_recent_research · _concept_deepening_goals · _open_question_goals
         _causal_frontier_goals · _tension_goals · _autobiographical_continuity_goals
       → emits kind:"generic", driven_by:"world_knowledge" (the _mk_goal default)
       → sets context["committed_goal"] DIRECTLY (bypasses competition) AND
         appends to context["proposed_goals"]

SYNC (v1 → v2)
  goal_io.sync_proposed_goals()
    └─ kind "generic" ∈ _EXECUTABLE_KINDS → api.create_goal() into the daemon
       BUT the proposed dict has no "spec" → spec={} in v2

PLAN/PARK (v2 daemon)
  GenericHandler.plan(): spec empty → Step(status=WAITING, name="external_pursuit")
    └─ "the cognitive loop pursues this goal, not the daemon" — the daemon becomes a
       lifecycle bookkeeper for intrinsic goals; it executes NOTHING for them.
  (Confirmed in data: the 99 intrinsic goals in the v2 snapshot sit at NEW/READY,
   never reaching DONE through the daemon.)

PURSUE (v1)
  pursue_goal.py works the plan + milestones (e.g. "research a new angle",
  "write a fact to long memory"). Survival/threat can preempt (the §2 closed-loop).

CLOSE (v1) — four doors, by far the busiest is the trivial one:
  • milestone met → mark_goal_completed()  ← ~all closures; instant, significance 0
  • satiety (drive quenched: uncertainty≤0.25 or novelty exhausted) → 0 closures EVER
  • fade → dormant (6 h unattended, weight decays) → abandonment_closures: 47
  • mark_goal_failed() (only inside deliberate pursuit) → 0 failures

MIRROR (v1 → v2)
  goal_io.close_goal_v2() pushes the v1 close into the daemon so it isn't resurrected.

CREDIT (v1)
  credit_aspirations() rolls completed goals UP into the aspiration their driven_by
  serves — a counter SEPARATE from the aspiration's own milestones (which stay 0/N).
```

---

## 3. The execution engine that exists and is barely used

The v2 daemon has **real, working handlers** (`goals/handlers/`):

| Handler | kind | What it does |
|---|---|---|
| `CodingHandler` | `coding` | plans + writes code (310 lines) |
| `CodeEditHandler` / `code_editor` | `code_edit` | edits files, runs the edit |
| `ResearchHandler` | `research` | multi-step research → writes a synthesized memo (`synth_kind`) |
| `HousekeepingHandler` | `housekeeping` | snapshots, dependency upgrades |
| `GenericHandler` | `generic` | reflect / investigate / process_todos — **or "unknown spec → mark done"** |

And the **schema is rich enough for real "make things" goals** (`goals_schema.py`,
`goal_types.py`):
- `AcceptanceCriteria{success_predicate, deadline_ts, retry_limit}` + a working
  `eval_predicate` DSL and `has_expired()`.
- A goal-**type** taxonomy: `produce_code` (verb+artifact), `acquire_knowledge`,
  `social`, `self_understand`, … with `EXCLUSIVE_DOING` actions, `REQUIRED_CAPABILITY`
  (`produce_code→llm`, `acquire_knowledge→web`), and `reduced_goal_spec()` for
  degrade-when-capability-down.

**So the machinery to build, to fail on a deadline, to gate completion on an
acceptance predicate, and to route a `produce_code` goal to `write_tool` —
all exists.** In the live run it is exercised **only** by autonomously-triggered
janitorial goals ("Upgrade safe dependency patches", daily housekeeping snapshots).
Nothing Orrin *wants* ever becomes a `coding`/`code_edit`/`research`-kind v2 goal
with an `AcceptanceCriteria`. The cognitive generator emits `generic` goals with no
executable spec, so they detour into v1 self-report and never touch a real handler.

---

## 4. Selection, drives, and commitment (how a goal wins attention)

- **`goal_competition.py`** computes six drives — exploration, mastery, autonomy,
  stability, **usefulness**, identity_consistency — from affect, finds conflicting
  pairs (incl. *"wondering vs. doing"* = exploration↔usefulness, the exact 19:05
  conflict the run docs saw), bumps uncertainty, and returns per-function pull
  scores. **But it steers *function* selection, not *goal generation*.** And
  "usefulness" `wants` {pursue_committed_goal, assess_goal_progress, …} — i.e. it is
  satisfied by *working whatever goal is committed*, even an intake goal. So the
  usefulness drive never demands useful *output*; it's quenched by goal-pursuit
  motions on an "Understand X" goal.
- **`goal_arbiter.py`** is the lock-guarded write chokepoint (mirrors the
  AffectArbiter) — sound; prevents the split-brain races the affect layer had.
- **Commitment** is partly bypassed: `generate_intrinsic_goals` sets
  `context["committed_goal"]` directly on a cold start, so the "competition" is often
  moot — whatever was generated is what's pursued.

---

## 5. The pathologies, ranked, each tied to data + code

**P-A — Monocultural generation (the cause of the 0% aspirations).** The real
(symbolic) generator has no producing/contact generator; `_mk_goal` defaults
`driven_by="world_knowledge"`. Result in data: "Make things" and "Be useful"
aspirations have **0 subgoals / 0 milestones / 0 history**. Structurally unreachable.

**P-B — The execution engine is orphaned from the mind.** Real handlers
(coding/research/code_edit) + the whole `produce_code`/`AcceptanceCriteria`/
`deadline` schema exist but are wired only to janitorial triggers. The "make things"
capability is *already built* and simply never invoked by a wanted goal.

**P-C — The correct closure path is dead; the trivial one does everything.**
`satiety_closures: 0` — the drive-quenched closure (`goal_satiety.is_sated`, built by
`explore_loop_fix_plan.md` precisely to replace trivial-milestone closure) **never
fires**. Meanwhile milestone self-report closes goals at `median_seconds_to_complete:
0.0` with `mean_significance: 0.0`. The good mechanism is inert; the bad one it was
meant to retire is at 100%.

**P-D — Regeneration churn.** Same titles ("Understand emergence/stoicism/
evolutionary biology…") appear completed 3-4× in `comp_goals.json` *and* live as
`in_progress`. `goals_completed: 10,051` is ~a dozen intake topics recycled past the
`_RECENTLY_COMPLETED` cooldown. Intake never ladders into output — it loops back into
intake.

**P-E — 0 failures because nothing is staked.** `mark_goal_failed` fires only inside
deliberate pursuit; intake goals self-certify or fade (`abandonment_closures: 47`,
never `failed`). No goal carries a real `deadline_ts`/`AcceptanceCriteria`, so none
can fail. The felt-cost channel (which now moves) has nothing to bite.

**P-F — Learned value has no authority.** `action_reward_ema`:
`generate_intrinsic_goals: 0.39`, `assess_goal_progress: 0.30` (both below neutral)
— yet `generate_intrinsic_goals` is picked #1 (3,768×). The reward IS learned; the
selector ignores it (capped/floored `_devalue_prior`, §1.4 of the reward plan).

**P-G — Representation sprawl.** Three+ stores (v2 daemon / v1 tree / lifetime file /
aspiration rows) with overlapping meaning and a scar-tissued sync. Not the headline
behavioral bug, but it is *why* fixes are fragile and why "long-term goal" is
ambiguous in the code.

**P-H — `usefulness` drive mis-wired.** Satisfied by pursuing any committed goal, so
it exerts no pull toward actual output or contact.

---

## 6. What this means for the fix plan (revisions)

The reward plan's instinct (gate completion on an artifact, make goals fail-able,
make generation polycultural) is right — but the anatomy changes *how* to build it,
mostly by **reusing infrastructure that already exists instead of adding new**:

1. **Don't invent a new completion gate — use `AcceptanceCriteria` + `goal_types`.**
   A "make things" goal should be a real **`produce_code`/`coding`-kind v2 goal** with
   an `AcceptanceCriteria{success_predicate, deadline_ts}` and routed to the existing
   `CodingHandler`/`CodeEditHandler`. That gives artifact-gated completion, the
   deadline→FAILED path, and `REQUIRED_CAPABILITY` degradation *for free*. (Reward
   plan P2 should target this, not a bespoke gate in `try_to_accomplish`.)

2. **P5's new generators must emit *executable* goals, not `generic` no-spec ones.**
   `_making_goals()` should emit `kind:"coding"`/`"code_edit"` with a spec the
   handler understands (so it reaches a real executor), and `_contact_goals()` a
   `social`/`research`-memo goal that produces a shareable artifact. Otherwise they
   detour into the same v1 self-report dead-end (P-B) and change nothing.

3. **Turn on satiety, or stop pretending intake goals "complete."** `is_sated` is
   built and returns 0. Either wire it as the closure path for `acquire_knowledge`
   goals (so they close on *quenched uncertainty*, not on "wrote one fact"), or make
   their milestone require real info-gain. Today's instant/zero-significance closure
   is the engine of P-D churn.

4. **The effect-ledger (reward plan P0) overlaps the v2 artifact concept.** The
   daemon already writes `data/goals/artifacts/…` for executed goals. The ledger
   should *subsume* that — one artifact record whether the effect came from a v2
   handler or a v1 note — so production credit is uniform.

5. **Consolidate representations (P-G) — at least make "make things" single-homed.**
   New producing goals should live in ONE place (the v2 executable store), not be
   forked across v1/lifetime/aspiration. This is the lowest-risk way to stop the sync
   scar tissue from spreading to the new path.

**Bottom line for the plan:** the reward denominator (currency) and the generator
monoculture (what he can want) are still the two headline fixes — but the goal track
is less "build new machinery" and more **"connect the mind to the execution engine
and acceptance/deadline schema that already exist, and turn on the closure mechanism
that's already written."** That is a smaller, safer change than the original plan
implied, and it is the accurate one.

---

*Generated 2026-06-18 from a full source read + live run data. Analysis only; no
code changed. Source map: `goals/{model,api,store,goals_daemon,registry}.py`,
`goals/handlers/{generic,coding,research,code_edit,housekeeping}.py`,
`brain/goal_io.py`, `brain/cognition/planning/{goals,goals_schema,goal_types,
goal_satiety,goal_arbiter,goal_lifecycle,pursue_goal}.py`,
`brain/cognition/{intrinsic_goals,goal_competition}.py`. Data: `outcome_metrics.json`
(10,051/0/0.0/0.0/0), `goals_mem.json`, `comp_goals.json`, `data/goals/state.jsonl`.*
