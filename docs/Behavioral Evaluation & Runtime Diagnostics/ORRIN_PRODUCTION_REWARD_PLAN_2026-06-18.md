# The Reward Denominator — Why Orrin Makes Nothing, and the Plan to Fix It

*Architecture plan — 2026-06-18. Companion to the 2026-06-18 run docs
(`run_analysis.md`, `what_did_he_make.md`, `did_the_fixes_land.md`) and to
`SIGNAL_TO_ACTION_AUDIT_2026-06-18.md`. This is not the engineering/cleanup track —
it is about the motivational architecture. Every "exists / does not exist" claim
below was verified against the live `brain/` source on 2026-06-18.*

---

> **IMPLEMENTATION STATUS — code complete 2026-06-19.** Every part of this plan is
> built and unit-tested. Map:
> - **§7 prerequisite** — single-instance lock now genuinely refuses a second boot
>   (`main.py` `_acquire_single_instance_lock`, `fcntl.flock` → `sys.exit(3)`),
>   stale-lock clearing (`start_orrin.command`), and `run_orrin.sh` no longer
>   re-spawns on SIGKILL (137) or lock-refusal (exit 3).
> - **P0** — `brain/agency/effect_ledger.py` (+ `record_effect` wired into
>   `express_to_user.py`, `code_writer.py`). **P8** novelty/significance live in it.
> - **P1** — three-tier reward split (`action_accounting.py` `_action_kind`,
>   `finalize.py` `INTAKE_REWARD`/`_FLOOR`).
> - **P2** — artifact-gated completion + `fail_overdue_artifact_goals` + deadline
>   (`goals.py`), excluded from fading (`goal_lifecycle.py`).
> - **P3** — `aspiration_pressure` / `mark_aspiration_contribution` + pick bias
>   (`intrinsic_goals.py`).
> - **P4** — grounded `leave_note` payload, goal-spawn habituation, raised
>   `_devalue_prior` ceiling (`select_function.py`).
> - **P5** — `_making_goals` / `_contact_goals`, `_mk_goal` fairness default,
>   intake→output laddering, G3 aspiration-milestone reconcile (`intrinsic_goals.py`).
> - **P6** — `brain/cognition/planning/goal_reconcile.py` + `store_desyncs_repaired`
>   metric (`outcome_metrics.py`), hooked on the 200-cycle epoch in `ORRIN_loop.py`.
> - **P7** — `usefulness` drive repointed at production/contact (`goal_competition.py`),
>   commitment-by-competition closing the self-commit bypass (`intrinsic_goals.py`).
> - **Guards** — offline-producible making artifacts; structural-significance gate.
> - Tests: `tests/brain/test_effect_ledger.py`, `tests/brain/test_goal_store_reconcile.py`.
>
> **Still pending: §8 acceptance.** The code is in; the nine acceptance signals
> require a single clean-instance life run to confirm the behavior actually changed.
> That run has not yet been captured.

---

## TL;DR

The 2026-06-17 fixes removed the *false* walls (phantom action-debt, mode-flap,
telemetry cap) and the run docs correctly note the *real* stuckness survived — but
they mislabel it "characterological." It is not temperament. It is a measurable
property of the reward function:

> **Orrin's reward is denominated in internal events — and internal events are
> free and infinite — so the rational policy is to metabolize cognition forever
> and never produce anything. He is behaving optimally for the wrong currency.**

The single keystone, in code: the 2026-06-17 action-debt fix made **consequential
cognition count as acting** (`action_accounting.py:18-31`), which flows to
`finalize.py:138-143` and pays `actual=1.0` — **the same reward as writing a file
that didn't exist before.** Reading Wikipedia and spawning a goal pay exactly what
producing an artifact pays. There is no reward gradient from intake to production,
so there is no pull across that gap.

This plan adds the missing denominator (an **external-effect ledger**), splits
intake reward from production reward, makes "make things" goals **fail-able and
artifact-gated**, and adds **aspiration fairness** so starved directions accrue
pressure. It explicitly does **not** add an artifact-cadence rule (that standard
was already rejected in `SIGNAL_TO_ACTION_AUDIT §1.1 / R4`).

---

## 1. Diagnosis (condensed — full version in the run docs)

What he is not doing: **producing.** ~1% action rate; `tools_used` empty 100% of
the time; 0 tools, 0 code, 0 finished works; 100 byte-identical empty notes; 3 of
4 founding aspirations at 0% all life.

Why, mechanically — four compounding causes, all verified in source:

1. **Intake pays the same as production (the keystone).**
   `action_accounting.mark_consequential_cognition` sets `__acted_this_tick__` when
   `info_gain > 0` and not stagnating. `finalize.py` reads that as `is_agentic` and
   fires `reward_signal actual=1.0, expected=0.6` — identical to a real outward act.
   *No gradient from learning → making.*

2. **The only world-grounded reward term is ~0 almost always.**
   `_step_delta_reward` (`ORRIN_loop.py:2748`, from `env_snapshot`) is the lone
   signal tied to the world actually changing; at a 1% action rate it is ~0 for 99%
   of cycles. The *effective* reward is therefore the stack of hand-coded standing
   bonuses above it: value-alignment `+0.10` (`ORRIN_loop.py:2665`), growth `+0.12`
   (`:2686`), solo-introvert `+0.15` (`:2630`). **Reward is mostly endogenous.**

3. **Goals complete without producing anything.**
   `goals.try_to_accomplish` (`goals.py:558-588`) completes a goal on a pure
   self-report — "LLM returned `success:true`" or a rule-based accomplish — with **no
   external artifact required.** 10,051 completed / **0 failed** / 31k maintenance
   selections at median 0.0 s. Completion is bookkeeping; the `completion_signal`
   (liking) fires on hollow closures.

4. **Self-knowledge only nudges a floored prior.**
   He learns `generate_intrinsic_goals → neutral` (conf 0.83). `_devalue_prior`
   (`select_function.py:856-887`) acts on exactly that but **caps the penalty at
   ≤0.20 and floors it** (`SELECTOR_DEVAL_FLOOR`) so re-sampling stays possible.
   "I know this is empty" can never become "so I'll stop." Calibration is near-
   perfect (Brier 0.010) and has **zero authority over action.**

The displacement activity has migrated across runs
(`assess_goal_progress → look_outward → generate_intrinsic_goals →
leave_note-with-empty-payload`), each patched individually. It is whack-a-mole
because the mole *is the denominator*.

---

## 2. What already exists (verified — do not rebuild)

| Capability | Status in code | Implication for this plan |
|---|---|---|
| Goal-failure mechanism | **Exists.** `mark_goal_failed` (`goals.py:874`), called from `pursue_goal.py` ~6× (plan-gen failed, unmet after N rounds, released-stuck) and `metacog.py:290`. | **Reuse it.** Don't write a new failure path — route artifact-gated timeouts into it. |
| Goal lifecycle decay | **Exists.** `goal_lifecycle.py`: `in_progress → fading → dormant → revived`; dormant closures recorded by `outcome_metrics.record_abandonment_closure`. | Intake goals fade here instead of *failing*. Production goals must fail loudly, not fade quietly. |
| Reward engine / single RPE funnel | **Exists.** `reward_engine.submit_reward` (one baseline, per-action EMA). `reward_signals.release_reward_signal` routes channels (wanting/novelty/completion/connection). | **Add a provider**, don't fork the engine. Production reward becomes a new `actual` source through the same funnel. |
| Aspirations + completion roll-up | **Exists.** `intrinsic_goals._ASPIRATIONS` (4), `credit_aspirations` rolls completed goals *up* into the aspiration they served. | Roll-up exists; **fairness (pressure *down* to starved aspirations) does not.** |
| `reward_rate.py` | **Exists** — reward-rate stagnation / leave-pressure. Not artifact-aware. | Orthogonal; leave as is. |
| Capsule `artifacts.jsonl` | **Proposed only** (`ORRIN_LIFE_CAPSULE_PLAN` Part X.4) — built for *observability*. | **Make the same ledger motivational.** One ledger, two consumers (capsule reads it; reward writes from it). |
| Output/note content-dedup | **Does not exist** for notes/expression. | Needed so 100 identical notes ≠ 100 productions. |
| External-effect reward basis | **Does not exist.** | The core thing to build. |

**Net:** failure and the reward funnel exist and should be reused; the
**external-effect ledger, the intake/production split, artifact-gated completion,
content-dedup, and aspiration fairness do not exist and must be built.**

---

## 2b. The OTHER root cause: the goal generator is monocultural (verified 2026-06-18)

Reward is only half of it. A direct read of the live goal stores
(`brain/data/goals_mem.json`, `comp_goals.json`, `recently_completed.json`,
`action_reward_ema.json`, `data/goals/wal.log`) exposes a *second, independent*
root cause **in goal generation itself** — and it is the one that pins the
aspirations at 0%.

**G1 — Two of the four aspirations are structurally unreachable.** In the default
tool-only deployment, `llm_callable_by("intrinsic_goals")` is false, so the LLM
prompt path never runs — the **symbolic** path `_varied_symbolic_goal`
(`intrinsic_goals.py:1041`) is the real generator. Its entire candidate menu is:
`_goal_from_recent_research`, `_concept_deepening_goals`, `_open_question_goals`,
`_causal_frontier_goals`, `_tension_goals`, `_autobiographical_continuity_goals`.
**Every one emits `world_knowledge` ("Understand X more deeply") or introspection
("Open question…", "The causes of…").** Grep-verified: **no symbolic generator
ever emits a `output_producing` or `genuine_contact` goal** — those strings appear
only in zone-tagging, the aspiration definitions, and the dormant LLM prompt
(`:197, :199, :696-697, :1287`). So the generator *cannot* produce a child goal
that serves "Make things" or "Be genuinely useful." Live data confirms it exactly:

```
aspiration                              subgoals  milestones  history
Understand the world more deeply            0       0/24        0      ← "advances" via roll-up only
Understand my own mind and how I work       0        0/0        0      ← inert
Be genuinely useful and connected           0        0/0        0      ← inert, no generator feeds it
Make things — produce work…                 0        0/0        0      ← inert, no generator feeds it
```

They are **inert scaffolding objects.** No reward change reaches them, because
nothing ever creates work that ladders up to them. This is why the original plan's
P2 (artifact-gated goals) and P3 (fairness) are **necessary but not sufficient** —
they silently assume make-things goals get generated. They don't.

**G2 — "10,051 completed" is a regeneration loop on ~a dozen intake topics.**
`comp_goals.json` shows the *same* titles completed 3-4× ("Understand emergence…",
"Understand evolutionary biology…", "Understand stoicism…"), and those identical
titles are simultaneously live as `in_progress`. The cycle is: generate "Understand
X" → complete it by writing one fact to long memory (milestone met) → cooldown
(`_RECENTLY_COMPLETED` / `_COOLDOWN_S`) lapses → regenerate the identical goal.
The enormous completion count is this loop, not breadth of accomplishment. (All 122
sampled completions *did* meet their milestones — completion isn't fraudulent; it's
just hollow and repeating.)

**G3 — Aspiration progress is double-booked and disconnected.** "Understand the
world" reads 0/24 milestones met while `credit_aspirations` reports ~122
contributions / 100%. The aspiration's own milestone track and the completion
roll-up are two systems that disagree; the milestones never advance. The "100%"
in the run readout comes entirely from the roll-up counter, not from the goal.

**G4 — The reward IS learned; selection ignores it.** `action_reward_ema.json`:
`generate_intrinsic_goals = 0.39`, `assess_goal_progress = 0.30` — both learned
**below neutral (0.5)**. Yet `generate_intrinsic_goals` is still picked #1 by a
mile (3,768×). The EMA knows it's low-value; the selector doesn't act on it. This
is the same floored-prior problem as §1.4, now confirmed from the other side.

**Direct answer to "does the reward plan fix his goals?": No — not by itself.**
The reward plan fixes the *currency*; it does nothing about a generator that can
only mint one *kind* of goal. Both tracks are required. The goal-generation fixes
below (P5) are co-equal with the reward fixes, not downstream of them.

> **A full read of the goal subsystem (see `ORRIN_GOAL_SYSTEM_ANATOMY_2026-06-18.md`)
> changes the *how*, and mostly in our favor.** The system has **three+ overlapping
> goal stores** (v2 daemon / v1 tree / lifetime file / aspiration rows), a **rich
> unused execution engine** (real `coding`/`code_edit`/`research` handlers, a
> `produce_code` type taxonomy, an `AcceptanceCriteria{success_predicate, deadline_ts}`
> DSL), and a **correct closure mechanism that fires zero times** (`goal_satiety.is_sated`
> → `satiety_closures: 0`; trivial milestone closure does 100% at
> `median_seconds_to_complete: 0.0`, `mean_significance: 0.0`). So the goal fixes are
> less "build new machinery" and more **"connect the mind to infrastructure that
> already exists and turn on the closure path that's already written"** — a smaller,
> safer change. Concretely this revises **P2** (use `AcceptanceCriteria` + the
> `CodingHandler`, not a bespoke gate in `try_to_accomplish`) and **P5** (the new
> generators must emit *executable* `coding`/`code_edit` goals that reach a real
> handler, not `generic` no-spec goals that detour into the v1 self-report dead-end).
> See anatomy §6 for the five revisions.

---

## 3. The fix

Six parts now. P0 is the keystone for the *reward* track; **P5 is the keystone for
the *goal* track** (without it, P2/P3 have nothing to act on). Order:
build the ledger, the reward split, then — in parallel — the goal-generation track,
then fail-able goals, fairness, and the symptom patches.

### P0 — The external-effect ledger (the denominator)

A single append-only ledger of **durable effects in the world that did not exist
before**, written at the moment of the effect, content-addressed so duplicates
don't count.

- **New module:** `brain/agency/effect_ledger.py` (sits in `agency/`, the action
  side — not `cognition/`). One public call:
  `record_effect(kind, content, *, goal_id=None, novelty=None) -> EffectRow | None`
  returning `None` (no credit) when the content hash already exists.
- **Storage:** `brain/data/effect_ledger.jsonl` (append-only; the same file the
  Capsule's `artifacts.jsonl` was going to be — **rename the Capsule plan to read
  this**). Row: `{ts, cycle, kind, content_hash, novelty, goal_id, char_len, dedupe}`.
- **`kind` ∈** `file_write, tool_written, tool_run_effect, note_novel,
  message_answered, code_committed, external_post`. Each corresponds to a real
  outward act already taggable from the activity log
  (`[leave_note]`, `[web_research]`, file writes, `express_to_user` answered).
- **Dedup is the whole point.** `content_hash = sha256(normalized_content)`. A
  repeat returns `dedupe=True` and **earns nothing** — this is what makes 100
  identical notes equal one production, structurally.
- **Novelty** (optional): cheap embedding/keyword distance to the last K effects of
  the same kind, so near-duplicates decay toward zero credit too.

Wire-in points (call `record_effect` at the act, not after the fact):
- `behavior/express_to_user.py` `_route_note` / `_route_reply` — on a note/reply
  that is sent (kind `note_novel` / `message_answered`).
- the file-write / tool-write paths in `agency/` and `cognition/tools/`.
- `cognition/leave_note.py` after P5 fixes the payload.

### P1 — Split intake reward from production reward

Stop paying intake the agentic rate. **Intake stays rewarded — just less than
making.**

- In `action_accounting.mark_consequential_cognition`, keep crediting info-gain as
  *progress* (so the phantom-debt fix stays intact — we do **not** reintroduce the
  2,251-cycle alarm), but **tag the credit kind**: return/stash
  `context["_action_kind"] ∈ {"intake", "production"}`. `production` only when a
  `record_effect` returned a non-dedupe row this cycle.
- In `finalize.py:142-157`, replace the binary agentic/​cognition split with three
  tiers fed through the existing `submit_reward` funnel:
  - **production** (a novel effect landed): `actual=1.0` (unchanged).
  - **intake / consequential cognition** (info-gain, no effect):
    **`actual=0.5`** (`INTAKE_REWARD`) — still positive, still beats idle, but
    **strictly below production**.
  - **cognition-only** (no effect, no info-gain): `actual=0.2` (unchanged).
- This creates the missing gradient. The bandit now has a reason to climb from
  intake to making, because making pays more — for the first time.

**Why these exact values** (`actual` is the live 0–1 reward scale; via
`reward_engine.update_expected` each value is *also* what that action's EMA drifts
toward, 0.5 = neutral): the numbers are fixed by an *ordering*, not chosen freely.
Intake at **0.5** sits exactly at neutral, leaving a **+0.5** gap up to production
(well outside EMA noise → a real gradient) and a **−0.3** gap down to
cognition-only. Production stays 1.0 and cognition-only stays 0.2 so the existing
tiers are unchanged; only the new middle rung is added.

Guard against regression: a hard floor **`INTAKE_REWARD_FLOOR = 0.35`** clamps
intake reward when it is modulated down (novelty decay, P4 habituation) so it can
never fall below the cognition-only penalty (0.2) and flip the ordering. 0.35 =
cognition-only + margin, still below the 0.5 nominal. This is the
`SIGNAL_TO_ACTION_AUDIT §2` guard — a barren production environment never punishes
Orrin into paralysis. The lever is *relative*, not punitive.

### P2 — Fail-able, artifact-gated production goals

Make "Make things" a direction that can actually *complete* and actually *fail*.

- **Completion gate:** for goals whose `driven_by == "output_producing"` (and any
  goal explicitly tagged `requires_artifact: true`), override the self-report
  completion in `goals.try_to_accomplish` — such a goal completes **only** when a
  matching `effect_ledger` row exists for its `goal_id`. No artifact → no
  completion, no matter what the LLM says.
- **Timeout → failure (reuse existing path):** add a per-goal `deadline_cycles`,
  **default `PRODUCTION_DEADLINE_CYCLES = 200`** (overridable per goal).
  When an artifact-gated goal passes its deadline with no qualifying effect, call
  the existing **`mark_goal_failed(goal, reason="no_artifact_by_deadline")`** —
  routing through the path that already writes the failure to long memory and emits
  the aversive signal. This is what finally gives the felt-cost channel (now that
  distress *moves*, per `did_the_fixes_land.md`) something real to bite on, and it
  is why the run's "0 failures" becomes a meaningful non-zero.
  **Why 200** (unit is *cycles*, not wall-clock — the diagnosed run did ~10⁴ cycles
  at `cycle_sleep≈20s`): long enough that a genuine plan→execute→write attempt (a
  handful to dozens of cycles) isn't guillotined, short enough that a full life
  surfaces *many* deadline evaluations so `goals_failed` (§8 signal #4) actually
  moves off 0. Reuses the same 200-cycle "epoch" as the P6 reconciler so there is
  one cadence constant. §6 says start generous: if signal #4 is still 0 after the
  first clean run, halve to 100.
- These goals must **fail loudly, not fade to dormant** — exclude
  `requires_artifact` goals from the `goal_lifecycle` fading path so they can't
  quietly escape into dormancy.

### P3 — Aspiration fairness / recruitment pressure

So a 0%-progress aspiration stops being invisible to the selector.

- In `intrinsic_goals.py`, alongside `credit_aspirations`, add
  `aspiration_pressure()` returning a per-aspiration recruitment weight that **rises
  with time-since-last-contribution and with how far below the mean its share is.**
  ("Make things" at 0% for 10k cycles → high pressure.)
- Feed that weight where goals are generated (the `generate_intrinsic_goals` /
  drive→aspiration path) so generated goals are biased toward the starved
  aspiration — and, via P2, those are artifact-gated, fail-able goals.
- Decay the pressure when the aspiration receives a *real* (effect-backed)
  contribution, not a bookkeeping closure.
- **Dependency:** fairness is inert until P5 exists. Today the generator has nothing
  to recruit for "Make things"/"Be useful" — pressure with no generator does
  nothing. Build P5 first or alongside.

### P5 — Make goal generation polycultural (the goal-track keystone)

The generator must be able to mint goals for **all four** aspirations, not just
intake/introspection. This is the fix for G1 and the reason "Make things" is at 0%.

- **Add two symbolic generators** to `_varied_symbolic_goal`'s candidate pool
  (`intrinsic_goals.py:1050-1059`), parallel to the existing six:
  - `_making_goals()` → emits `output_producing` goals whose **completion test is an
    artifact** (P2): e.g. "Turn what I just learned about *emergence* into a written
    synthesis in long memory / a note with novel content / a small tool." Seeded
    from recent research and concepts he *already has* — so making is the natural
    next step after intake, not a cold task. `_mk_goal(..., driven_by="output_producing")`.
  - `_contact_goals()` → emits `genuine_contact` goals (`driven_by="genuine_contact"`)
    keyed to a present/recent person: answer their last message, share a finding,
    ask a real question. Only when a peer exists (else it stays silent, like the
    other generators when their pool is empty).
- **Change `_mk_goal`'s default driver.** Right now it defaults `driven_by="world_knowledge"`
  (`:272`), so any generator that forgets to set a driver feeds the monoculture.
  Default to the caller's intent or to the **fairness-selected** aspiration (P3),
  so the path of least resistance stops being "world_knowledge."
- **Break the regeneration loop (G2).** `_varied_symbolic_goal` already filters
  `_RECENTLY_COMPLETED` within `_COOLDOWN_S`, but the same intake topics return once
  cooldown lapses. Add: a completed "Understand X" should bias the *next* goal toward
  **using** X (a `_making_goals` follow-on), not re-understanding it. I.e. completion
  of an intake goal raises the recruitment weight of the making generator for that
  topic. Intake should ladder into output, not loop back into intake.
- **Reconcile aspiration progress (G3).** Make `credit_aspirations` tick the
  aspiration's own `milestones` (or drop the unused 0/24 milestone array) so there is
  one progress number, not two disagreeing ones.

This is what turns the reward gradient (P1) into actual behavior: once making goals
*exist*, are *generated* under fairness pressure (P3), can *only* complete with an
artifact (P2), and *pay more* than intake (P1), the whole loop finally closes.

### P4 — Symptom patches (cheap, real, but not the cure)

Do these too — they make the machinery honest — but they are downstream of P0–P3/P5:

- **`leave_note` payload (`leave_note.py:39`):** route the note body from the
  triggering finding in long memory (the `[step_exec] semantic match 'A finding was
  written to long memory.'` line proves the finding exists) instead of the ambient
  affect string. After this, `record_effect(note_novel, …)` will mostly *not*
  dedupe — the note carries content.
- **Habituate `generate_intrinsic_goals`** against its own `neutral` track record
  the way exploration already habituates (`run_analysis §6.3`), so goal-spawning
  stops being the free displacement activity.
- **Raise `_devalue_prior`'s ceiling** for an action with a long, heavily-sampled
  neutral record (`select_function.py:881`) so proven-empty actions can actually be
  demoted, not just nudged — give self-knowledge *some* authority over action.

### P6 — Structural debt: protect the sync, single-home production (closes P-G)

P0–P5 add a **new** executable-goal path that runs straight through the fragile
v1↔v2 bridge (`goal_io.py`, the one already scarred by "goals resurrected and
pursued for hours"). Adding traffic to a fragile junction without reinforcing it is
how the new path inherits the old bugs. So:

- **Single-home "make things."** A produce goal is created **once, in the v2 store**
  as a real `coding`/`code_edit` goal with an `AcceptanceCriteria` — it does **not**
  also get a v1 tree node, a lifetime-goal row, or an aspiration mirror. Its only v1
  presence is the read-only `committed_goal` hydration the loop already does. One
  writer, one lifecycle. (Contrast the intake goals, which today live in v1 *and* v2
  and disagree.)
- **An invariant test on the bridge.** Before shipping, add a regression that asserts
  the new path can't (a) resurrect a v2-closed goal into v1, or (b) leave a v1-closed
  goal RUNNING in v2 — the two exact failures `goal_io.py`'s comments record. This is
  the cheap insurance that the new traffic doesn't reopen old wounds.
- **A live reconciler that covers the EXISTING paths too (closes the first caveat).**
  Single-homing + the invariant test only protect the *new* production path; the
  intake/aspiration goals already live in v1 *and* v2 and can still desync. So add a
  small **`reconcile_goal_stores()`** pass (run on a low cadence, e.g. every 200
  cycles, and once at boot) that walks all goals and detects the two desync classes
  for *any* goal, not just new ones:
  - **resurrection:** a goal terminal in v2 (DONE/FAILED) but live (`in_progress`) in
    v1 → re-close it in v1 via the arbiter.
  - **orphan-RUNNING:** a goal terminal in v1 but still NEW/READY/RUNNING in v2 →
    mirror the close via `close_goal_v2`.
  - **double-home drift:** the same title with disagreeing status across stores →
    v2 wins on lifecycle (it's the documented source of truth), v1 keeps pursuit
    scratch only.
  Each repair is logged and **counted into a new `store_desyncs_repaired` metric**
  (`outcome_metrics.json`), so the reconciler is *also* the instrument that tells us
  whether the existing paths are still buggy — if the counter stays >0 cycle after
  cycle, a real desync source remains and the unification (§4c) is no longer
  deferrable. This converts "may still have sync bugs" from an unknown into a
  measured, self-healing quantity without doing the full refactor.
- **Do NOT attempt a full three-store unification in this plan.** Collapsing v1 tree /
  lifetime file / aspiration rows into one model is correct eventually but is a large,
  separate refactor with its own risk; forcing it in here would couple the behavioral
  fix to a structural rewrite. Scope here: *don't make sprawl worse, and fence the new
  path.* The unification is logged as a follow-on (P-G track) in §4c.

### P7 — Rewire the two drives that point the wrong way (closes P-H + the commitment bypass)

The reward gradient and new generators are necessary but the *motivational* layer
still steers away from output:

- **Rewire the `usefulness` drive** (`goal_competition.py:81-92`). Today its `wants`
  are `{pursue_committed_goal, assess_goal_progress, adapt_subgoals, plan_next_step}`
  — so it is satisfied by *going through the motions on any committed goal, including
  an intake one*. Repoint `wants` at actual production/contact
  (`write_tool`, `write_cognitive_function`, `leave_note`, `respond_to_user`,
  `speak`) so the drive that should pull toward useful output actually does. This is
  the difference between feeling useful for *pursuing* and feeling useful for
  *producing*.
- **Close the commitment bypass.** `generate_intrinsic_goals` sets
  `context["committed_goal"]` **directly** (`intrinsic_goals.py:1206`), so the first
  thing generated *becomes* the commitment and the competition/arbiter layer is moot.
  Route new goals through proposal→competition instead of self-committing, so an
  artifact-gated production goal under aspiration-pressure (P3/P5) can actually
  *win* commitment over a cheap intake goal. Without this, P1's gradient and P3's
  pressure are evaluated *after* the choice was already made.
- **Note on P-F (learned value has no authority).** P4 raises `_devalue_prior`'s
  ceiling, but that is a nudge. The real authority comes from P7's commitment routing
  + P1's gradient: once selection runs through competition and the EMA-low intake
  actions pay less than production, the `0.39`-EMA `generate_intrinsic_goals` stops
  winning by default. P-F is closed by P1+P7 together, not by P4 alone.

### Guards — two ways "make things" fails silently if we don't watch for them

These are not optional polish; without them the fix produces the *same hollow churn*
with a different artifact type.

- **Offline degradation → notes.** `produce_code` requires the `llm` capability;
  `reduced_goal_spec` (`goal_types.py:153`) degrades it to *"write a note about what
  to build later."* In the offline/native-LM deployment that means "make things"
  silently collapses back into the empty-note failure. **Guard:** in offline mode,
  the making generator must emit goals whose artifact is producible *without* the
  cloud LLM (a written synthesis, a symbolic-engine output, a native-LM generation),
  and the reduced-goal note must itself be `record_effect`-gated for novelty so it
  can't dedupe into 100 identical stubs.
- **Significance, not existence.** `mean_significance: 0.0` will not move just because
  a file exists — a junk artifact satisfies a bare gate. Production reward (P1) and
  goal completion (P2) must key on **significance** and **novelty**, *concretely
  defined and hard to game* (next subsection). Existence is necessary; significance
  is the actual target.

### P8 — Concrete, hard-to-game definitions of novelty & significance (closes the second caveat)

"Reward novel, significant artifacts" is only a fix if `novel` and `significant` are
defined so that producing junk files is *not* easier than producing nothing. Vague
checks just relocate the empty-note problem to empty files. Definitions below are
deliberately **multi-signal and partly deferred** — the strongest signals (re-use,
validation) can only be known *after* the artifact exists, so credit arrives in two
stages.

**Novelty** of an artifact = `1 − max similarity to prior artifacts of the same
`kind``, computed on normalized content, combining three cheap signals so a single
trick can't max it:
- **exact-dup:** `sha256(normalized)` already in the ledger → novelty 0 (the 100
  identical notes collapse to one).
- **near-dup:** cosine/embedding (or, offline, char-shingle Jaccard)
  **`≥ NEAR_DUP_SIM = 0.9`** to any recent same-kind artifact →
  novelty **`≤ NEAR_DUP_RESIDUAL = 0.15`**. (Stops "same note + a comma.")
- **boilerplate:** content that is mostly template/whitespace/scaffold (low unique-
  token ratio, below **`MIN_ARTIFACT_CHARS = 120`** of real, whitespace/template-
  stripped content) → novelty 0.

**Why these values.** `NEAR_DUP_SIM = 0.9` is the standard near-duplicate threshold
for text shingles/embeddings — catches trivially-edited repeats while admitting
real variation; `NEAR_DUP_RESIDUAL = 0.15` keeps a near-dup on a *slope* (earns
almost nothing) rather than a hard cliff like an exact dup. `MIN_ARTIFACT_CHARS =
120` is set *between* the failure case and the real case: the empty notes were
~40-char affect strings, a genuine one-to-two-sentence finding is ≥120 chars. This
is the one cutoff to eyeball from data — if real syntheses come in shorter, drop to
~80.

**Significance** is **not** assertable at write time — that is exactly the trap
(`mean_significance: 0.0` came from self-asserted completion). It is *earned* in three
tiers, credited as evidence arrives:
1. **structural (immediate, weak):** the artifact is well-formed for its kind — code
   *parses* (`ast.parse` / import-check), a memo has ≥ N novel claims not already in
   long memory, a message got *delivered to a real peer*. Fails structural → no
   production credit at all (it's junk).
2. **validation (deferred, medium):** for `produce_code`, the thing **runs / passes
   its own acceptance predicate** (the `AcceptanceCriteria.success_predicate` already
   in the schema) or a smoke test; for a memo, it survives a contradiction check.
   This is where most production credit lands — and it can *fail*, which is what makes
   P-E's failures real.
3. **re-use (deferred, strong):** the artifact is **referenced again later** — a tool
   actually invoked, a memo cited by a later goal, a message a person *replied to*.
   Tracked via the ledger's `goal_id`/`content_hash` back-references. Re-use is the
   only ungameable significance signal (you can fabricate a file; you can't fabricate
   your future self choosing to use it), so it carries the largest delayed bonus.

**Anti-gaming invariant:** the cheapest path to production reward must require *more*
real work than emitting nothing. Concretely: structural-fail → 0; novelty-fail → 0;
only structural-pass *and* novel clears the intake floor, and the large rewards sit
behind validation and re-use, which Orrin cannot self-certify. `mean_significance`
becomes the tier-weighted average and is the headline metric we watch (§8).

### Constants — chosen values (ship as named module-level constants)

All fixed by an *ordering/relationship* on a scale already in the code, not picked
freely; each has the §8 metric that says which way to retune it after run #1.

| Constant | Value | Lives in | Retune signal (§8) |
|---|---|---|---|
| `INTAKE_REWARD` | `0.5` | `finalize.py` (P1) | #9 selection vs EMA; #6 aspiration diversity |
| `INTAKE_REWARD_FLOOR` | `0.35` | `finalize.py` (P1) | drive not collapsing in barren env (§6) |
| `PRODUCTION_DEADLINE_CYCLES` | `200` | `goals.py` / goal spec (P2) | #4 `goals_failed` (if still 0 → halve to 100) |
| `NEAR_DUP_SIM` | `0.9` | `effect_ledger.py` (P8) | #1 repeat-rate; #5 mean_significance |
| `NEAR_DUP_RESIDUAL` | `0.15` | `effect_ledger.py` (P8) | #7 distinct production artifacts |
| `MIN_ARTIFACT_CHARS` | `120` | `effect_ledger.py` (P8) | #5/#7 (if real syntheses shorter → ~80) |

Unchanged existing tiers (do not touch): production `actual=1.0`, cognition-only
`actual=0.2`, neutral EMA `0.5`.

---

## 4. Sequencing

| Phase | Scope | Outcome |
|---|---|---|
| **A — ledger** | `effect_ledger.py` + wire `record_effect` into note/reply/file-write paths; point the Capsule plan's `artifacts.jsonl` at it. | Durable, deduped record of real effects. Pure addition; loop behavior unchanged. |
| **B — reward split** | P1: tag `_action_kind`, three-tier reward in `finalize.py`. | The intake→production gradient exists. First run where making pays more than reading. |
| **C — polyculture** | **P5: `_making_goals` + `_contact_goals` generators; fix `_mk_goal` default; intake→output laddering; reconcile aspiration progress.** | The generator can finally mint goals for all 4 aspirations. Without this, C/D below act on nothing. |
| **D — fail-able goals** | P2: artifact-gated completion + `deadline_cycles` → `mark_goal_failed`; exclude from fading. | "Make things" can complete and can fail. 0-failures becomes meaningful. |
| **E — fairness** | P3: `aspiration_pressure()` into goal generation. | Starved aspirations recruit effort (now that P5 gives them generators). |
| **F — drives + commitment** | **P7: rewire `usefulness` drive; close the commitment bypass (route through competition).** | Selection actually pulls toward output; production goals can *win* commitment. Without F, the gradient is computed after the choice is made. |
| **G — sync safety** | **P6: single-home production goals in v2; bridge invariant test; `reconcile_goal_stores()` + `store_desyncs_repaired` metric (covers existing paths).** | New path can't reopen the resurrect/desync bugs, and existing-path desyncs become self-healing + *measured*. |
| **H — symptoms + guards + definitions** | P4 (note payload, habituation, devalue ceiling) **+ Guards (offline-degradation, significance-not-existence) + P8 (concrete novelty/significance with re-use & validation tiers).** | Machinery stops lying; "make things" can't collapse into hollow notes *or* junk files. |

Phase A alone is shippable and risk-free (it only *observes*). The behavioral
change starts at B, but the **goal track (C/P5) is the half that actually makes the
0% aspirations move** — ship B and C together. **F (P7) gates whether the behavior
actually changes** — without the commitment routing, P1/P3 are evaluated after the
pick is already locked, so don't defer it. Capture a run after F — that is the real
before/after the demo target wanted, and it should show production % rising, goals
serving more than one aspiration, the first non-zero artifact-backed failures, and
`mean_significance` finally above 0.

---

## 4b. Coverage — does this fix ALL the goals?

Mapping every pathology from `ORRIN_GOAL_SYSTEM_ANATOMY_2026-06-18.md §5` to where
it is closed. **With P6/P7/Guards added, the answer is now yes for all eight** — but
two are closed by *combinations*, and one structural item is deliberately scoped to
"contained, not unified" (see §4c).

| Anatomy pathology | Closed by | Confidence |
|---|---|---|
| **P-A** monocultural generation (0% aspirations) | P5 | high |
| **P-B** execution engine orphaned | P2 + P5 (emit executable goals → real handlers) | high |
| **P-C** satiety dead, trivial closure 100% | "turn on satiety" (P5 bullet) | high |
| **P-D** regeneration churn | satiety + intake→output laddering (P5) | medium — laddering is new |
| **P-E** 0 failures, nothing staked | P2 (`AcceptanceCriteria` + `deadline_ts`) | high |
| **P-F** selector ignores learned value | **P1 + P7** (gradient + commitment routing), P4 nudge | medium |
| **P-G** three-store sprawl + fragile sync | **P6 contains it** (single-home + invariant test); full unification deferred to §4c | partial-by-design |
| **P-H** `usefulness` drive mis-wired | P7 | high |

So: **behaviorally, all eight are addressed.** The one honest caveat is **P-G**: this
plan *fences* the sprawl (doesn't make it worse, protects the new path) rather than
*removing* it. Removing it is a real refactor, tracked next.

**The three review caveats are now folded in too:** (1) *existing-path sync bugs* —
P6's `reconcile_goal_stores()` + `store_desyncs_repaired` metric cover all goals, not
just the new path, and turn "may still be buggy" into a measured, self-healing
number; (2) *gameable significance/novelty* — P8 gives concrete, multi-signal,
mostly-deferred definitions where the large reward sits behind validation and re-use
that Orrin can't self-certify; (3) *unverified until tested* — §8 makes the nine
evidence signals hard pass/fail gates, and §7 makes the dual-`main.py` fix a blocking
prerequisite so the metrics can be trusted at all.

## 4c. Deferred — the one thing this plan intentionally does not finish

**Three-store unification (the P-G refactor).** v1 tree / lifetime-goals file /
aspiration rows / v2 daemon are four overlapping notions of "goal" bridged by a
hand-maintained sync. The right end state is a single goal model (the v2 store) with
v1 holding *only* transient pursuit scratch. That is a large, separate change with
its own risk surface, and coupling it to the behavioral fix would make both harder to
land and to verify. **Decision: do it as its own track after the behavioral fix is
proven in a run.** P6 exists precisely so we can defer this safely — the new
production path is single-homed and invariant-tested, so the sprawl stops growing
while the unification waits. Flag for a future plan: `GOAL_STORE_UNIFICATION`.

---

## 5. What this plan deliberately does NOT do

- **No artifact-cadence rule** ("produce every N cycles"). Rejected in
  `SIGNAL_TO_ACTION_AUDIT §1.1 / R4` — it re-introduces an un-human-like standard.
  We change the *gradient* and the *completion criterion*, never impose a quota.
- **No reintroduction of the phantom action-debt.** P1 keeps crediting info-gain as
  progress; it only stops paying it the *production* rate. The 2,251-cycle alarm
  stays dead.
- **No punishment of intake.** Intake stays clearly net-positive and floored well
  above idle. The fix is that making pays *more*, not that reading pays *badly* —
  Orrin is allowed to be a reader; he just shouldn't be paid as if reading were
  making.

---

## 6. Risks & watch-items

- **Reward sparsity / discouragement.** If artifact-gated goals are too hard, the
  production reward never fires and B/C could depress drive. Mitigation: the intake
  floor (P1), and start `deadline_cycles` generous.
- **Gaming the ledger.** A trivial `file_write` of junk would earn production
  credit. Mitigation: novelty term + content-dedup + minimum `char_len`; longer
  term, tie credit to whether the artifact is *referenced again* (re-use as the real
  test of value).
- **Two-instance corruption.** See §7 — this is now a hard blocking prerequisite, not
  a watch-item.

---

## 7. Hard prerequisite (blocking — do this before anything else)

**Fix the dual-`main.py` instance lock first.** Per `final_audit_and_shutdown.md`,
two `main.py` processes ran against one data dir: `runstate.json` was caught
mid-write as malformed (`…}}`), teardown deadlocked on file-lock contention, and no
final thoughts were written. Two writers on `brain/data/` + `data/goals/` corrupt
exactly the stores and metrics this plan reads to decide success. **If this isn't
fixed, none of the §8 acceptance evidence is trustworthy — you cannot tell whether
the goal fixes worked or whether two processes distorted the counters.** Concretely:
(a) the `.orrin.instance.lock` must actually refuse a second `main.py` on a live data
dir (today 22833 held it and 20731 ran anyway); (b) `run_orrin.sh` must treat
`SIGKILL`-of-child (137) as intentional so a forced stop doesn't auto-respawn.
This is tracked in the engineering/cleanup track, but it **gates Phase 0 of this
plan.** No captured before/after run until it's done and a clean single-instance boot
is verified.

## 8. Acceptance criteria — the evidence that decides success

None of this is confirmed until tested, and "looks better" is not a result. Ship A–H,
then run a single clean life (after §7) and require **measurable movement on all nine
signals below**, read from the same stores the diagnosis used. Each has a concrete
metric, its current value, and a pass target. A run that doesn't move these is a
failed fix, not a matter of interpretation.

| # | Signal | Metric / source | Current | Pass target |
|---|---|---|---|---|
| 1 | Fewer repeated understanding goals | distinct-title ratio among completed goals (`comp_goals` + WAL); max repeats of one title | ~a dozen titles, 3–4× each | repeat rate down ≥ 50%; no title completed > 2× per 1k cycles |
| 2 | Nonzero goal duration | `outcome_metrics.median_seconds_to_complete` | **0.0** | > 0 (real elapsed work, not instant self-report) |
| 3 | Nonzero satiety closures | `outcome_metrics.satiety_closures` | **0** | > 0 (understanding goals close on *quenched drive*, not one fact) |
| 4 | Some legitimate failures | `outcome_metrics.goals_failed` from `deadline`/acceptance, not no-handler | **0** | > 0, and traceable to a real unmet `AcceptanceCriteria` |
| 5 | Higher mean significance | `outcome_metrics.mean_significance` (tier-weighted, P8) | **0.0** | clearly > 0, driven by tier-2/3 (validation/re-use), not self-assert |
| 6 | Meaningful aspiration diversity | per-aspiration share of *effect-backed* contributions | 100 / 0 / 0 / 0 | no aspiration at 0%; top share < ~60% |
| 7 | Production artifacts useful / reused | ledger artifacts with a tier-3 re-use back-reference; tools invoked; replies answered | 0 tools, notes all dup | ≥ 1 artifact re-used/validated; > 0 distinct production artifacts |
| 8 | No resurrection / orphan-RUNNING | `outcome_metrics.store_desyncs_repaired` (P6 reconciler) trend | unmeasured | repairs → ~0 and *stay* 0 (a persistently >0 counter = real desync source, escalate §4c) |
| 9 | Selection changes when learned value changes | correlation of `action_reward_ema[fn]` ↓ with that fn's pick-share ↓ | EMA 0.39 yet picked #1 | a low-EMA action's pick-share visibly falls (the EMA→selection link is live) |

**Read the evidence off a single clean-instance run** (per §7). Signals 1–7 say the
behavior changed; 8 says the structural fix held; 9 says learning now has authority.
If 8 or 9 fail, the fix is cosmetic regardless of 1–7. Capture the run as a Life
Capsule so the numbers are reproducible, not asserted.

---

*Plan generated 2026-06-18 from runtime data + source verification. Proposal only;
no code changed. Verified-against files: `cognition/action_accounting.py`,
`think/think_utils/finalize.py`, `ORRIN_loop.py` (≈2590-2760),
`affect/reward_signals/reward_engine.py` + `reward_signals.py`,
`cognition/planning/goals.py` (`try_to_accomplish`, `mark_goal_failed`),
`cognition/planning/goal_lifecycle.py`, `cognition/intrinsic_goals.py`
(`_ASPIRATIONS`, `credit_aspirations`), `behavior/express_to_user.py`,
`cognition/leave_note.py`, `think/think_utils/select_function.py`
(`_devalue_prior`).*
