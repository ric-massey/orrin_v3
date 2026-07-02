# Implementation Plan: Audit Remediation — Make the Making Real

**Date:** 2026-07-01
**Derives from:** `CODEBASE_AUDIT_2026-07-01.md` (13 parts, 22 findings, 6 passes).
**Status:** Proposed — the build plan for the audit's findings.

> **The bet, in one sentence.** Orrin already *makes things* LLM-free — symbolic
> rules, skills, experiments, causal knowledge, and (via the v2 daemon) research
> memos and housekeeping artifacts — but **none of it records an effect**, so the
> goal/production/reward system is blind to all of it. Wire every durable artifact to
> the effect ledger, make understand-goals reach a real synthesizer, let making pay
> per attempt, and the "produces nothing" invariant that has held across seven lives
> finally breaks.

Each phase lists **Goal · Files · Changes · Acceptance · Tests · Risks**, ordered by
leverage. AR1 is the keystone; AR2–AR4 make it behavioural; AR5–AR9 are the
downstream hygiene fixes; the architectural forks (Part 8 of the audit) are decisions,
listed last as gated work.

**Whole-plan gate:** this plan is only *proven* by `NEXT_RUN_TESTS.md` §8 — Run 1
(06-30) **failed the gate** ("shipped, not proven; production end fed garbage").
Re-test gate: signals **5, 6, 7, 9 must move**. Do a stamped staging run after AR1–AR4
land and read it against that gate before calling any of this done.

---

## AR1 — Every durable artifact records an effect *(the keystone — D7)*

**Goal.** Make the production ledger see the two subsystems that actually produce and
currently record nothing: the **symbolic engine** and the **v2 executor handlers**.
This is the single highest-leverage change in the audit.

**Files.**
- `brain/agency/effect_ledger.py` — add a `symbolic_artifact` kind (or reuse
  `tool_run_effect`) + its structural-significance branch.
- `brain/symbolic/rule_synthesis.py`, `crystallization.py`, `autonomous_experiment.py`,
  `causal_graph.py` — record an effect when a rule is synthesized / skill crystallized
  / experiment resolved / causal edge added.
- `goals/handlers/research.py`, `housekeeping.py`, `code_edit.py`, `coding.py` — record
  an effect when a handler writes a real artifact.
- `goals/runner.py` (`_execute_step`) — the single chokepoint alternative: record an
  effect on any handler step that reaches `DONE` with a written artifact path.

**Changes.**
1. Add `EFFECT_KINDS ∋ "symbolic_artifact"` with structural significance ≈ 0.5–0.6
   (a synthesized rule/skill is verified structure, like `tool_run_effect`). Novelty
   dedup already prevents re-crediting the same rule.
2. At each symbolic production point, call `record_effect("symbolic_artifact", <the
   rule/skill/experiment text>, goal_id=<active goal>, metadata={"kind": "rule"|"skill"
   |"experiment"|"causal_edge"})`. Bind to the active goal via `bound_goal` when one is
   committed; otherwise record ungoaled (still counts for metrics).
3. In the v2 handlers (or once in `runner._execute_step`), on a `DONE` step that wrote
   an artifact file, `record_effect("file_write"|"tracked_work", <artifact text>,
   goal_id=goal.id, metadata={"path": ...})`. `file_write` is a valid `EFFECT_KINDS`
   with no emitter today — this makes it real.

**Acceptance.** In a run, the effect ledger shows **more than one kind** (not 100%
`note_novel`): `symbolic_artifact` and `file_write`/`tracked_work` rows appear.
`mean_significance` reflects rules/skills/memos, not just notes. An understand-goal
that produces a rule can satisfy P1's `has_qualifying_effect`.

**Tests.** `tests/brain/test_symbolic_effects.py`: synthesizing a rule / crystallizing
a skill records a credited effect bound to the active goal; a duplicate rule dedupes
(no double credit). `tests/goals/test_handler_effects.py`: a housekeeping/research
handler `DONE` records a `file_write` effect for its artifact.

**Risks.** Over-crediting trivial symbolic churn (every tiny rule tweak paying) — gate
on the ledger's existing `MIN_ARTIFACT_CHARS` + novelty dedup, and consider a
per-cycle cap so a rule-synthesis storm can't farm reward. Keep symbolic effects
*significance-scaled* so a one-line rule ≠ a real skill.

---

## AR2 — Route understand-goals to a real synthesizer *(D5)*

**Goal.** Understand-goals currently detour into v1 self-report + a hollow note. Route
them to the v2 `ResearchHandler`, whose offline extractive synthesizer
(`_offline_fallback_memo`) already works LLM-free — and (per AR1) now records an effect.

**Files.** `brain/cognition/intrinsic_helpers.py` (`_mk_goal`), `brain/goal_io.py`
(`sync_proposed_goals`), `goals/handlers/research.py`.

**Changes.**
1. Cognitive "understand/research X" generators emit `kind:"research"` with a spec the
   handler understands (`{queries|title, synth_kind:"memo"}`), not `kind:"generic"`.
2. Confirm `sync_proposed_goals` routes `research` kind to `api.create_goal` (it's in
   `_EXECUTABLE_KINDS`) so it reaches the handler, not the `GenericHandler` park.
3. `ResearchHandler` records the memo effect (AR1) so the goal closes on P1's gate.

**Acceptance.** An "understand X" goal produces a **sourced extractive memo artifact**
(not "something present but hard to name"), records an effect, and closes on the
effect — LLM-free.

**Tests.** `tests/goals/test_research_route.py`: an understand-goal → `kind:research` →
`ResearchHandler` → memo artifact + credited effect → P1 close.

**Risks.** Depends on AR1 (handler effect). Don't route *introspective* goals ("trace
my own code") here — those are `search_own_files`, not web research (keep the
classifier honest).

---

## AR3 — Native LM into composition, not string templates *(D6)*

**Goal.** The LLM-free fallbacks in `compose_section` and `leave_note` emit hardcoded
boilerplate that games the gate. Use his own trained language organ instead.

**Files.** `brain/agency/compose_section.py` (`_draft` fallback), `brain/cognition/
leave_note.py` (the finding path), `brain/cognition/language/voice.py` /
`conditional_render.py` (the native-LM entry the mouth already uses).

**Changes.** In the `not llm_callable_by(...)` branch of `_draft` and the note-body
fallback, call `native_lm.generate(prompt=<goal finding/frontier>, …)` (the same organ
`voice.lm_draft` uses) instead of the string template. Keep a structural floor so a
degenerate generation still passes/needs `MIN_ARTIFACT_CHARS` honestly.

**Acceptance.** LLM-off section/note artifacts are in his own (crude, improving) voice,
not the fixed template; note-body distinct-count rises (was 1 across 100 notes).

**Tests.** `tests/brain/test_native_composition.py`: with LLM off + a trained stub LM,
`compose_section`/`leave_note` produce native-LM text (not the known template string).

**Risks.** Early-life LM output is noise — keep it gated on the P2a maturity check
`voice.lm_draft` already uses; fall back to the template only if the LM isn't ready.

---

## AR4 — Making pays per attempt *(R1 — makes the fix "take")*

**Goal.** The per-cycle reward gradient favors intake (any signal-moving cycle pays;
production pays only a rare lump). Give making a competitive per-attempt reward so a
reward-maximizing selector doesn't drift back to reading.

**Files.** `brain/cognition/produce_and_check.py` (already records reach outcome),
`brain/loop/cognition_reward.py` (`shape_cognition_reward`), `brain/cognition/
exploration_value.py`.

**Changes.**
1. A `produce_and_check` **attempt** (pass OR fail) pays a small reward comparable to
   an intake action — trying to make is never locally worse than reading. A *pass* pays
   more (it already records `tool_run_effect`); a *fail* still pays the "you attempted
   a checkable thing" credit + writes the gap.
2. A `symbolic_artifact` effect (AR1) pays production reward the moment it's recorded,
   not only at goal close — so LLM-free cognition pays like production per artifact.

**Acceptance.** Across a run, `action_reward_ema` for making actions (produce_and_check,
compose_section, symbolic synthesis) is ≥ the EMA for pure-intake reads; the selector
picks making at least as often as reading when a goal admits it.

**Tests.** `tests/brain/test_making_reward.py`: a produce-and-check attempt and a
symbolic-artifact record each yield a per-event reward ≥ an intake action's typical
reward.

**Risks.** Over-rewarding attempts → reward farming by spamming checks. Cap per-cycle;
use `exploration_value` habituation so repeated identical attempts decay.

---

## AR5 — Goal birth-rate quota *(G2 / AD4)*

**Goal.** ~95% of generated goals are "understand X." Even with a making path, make/
connect goals must be *born* to compete for slots.

**Files.** `brain/cognition/intrinsic_goals.py` (`generate_intrinsic_goals`,
`_varied_symbolic_goal`), `brain/cognition/intrinsic_generators.py`.

**Changes.** Enforce a minimum share of make/connect goals per generation batch (and a
cap on intake generation), keyed to the aspiration scoreboard so the starved
aspirations get born, not just boosted at pick-time.

**Acceptance.** In a run, generated-goal mix reflects all four aspirations; be-useful/
make each draw > 0% of production (was 0.0% every run).

**Tests.** `tests/brain/test_goal_birthrate.py`: over N generation batches, make/connect
share ≥ the configured floor.

**Risks.** Forcing make-goals that can't yet succeed → failure spam. Land after AR1–AR3
so make-goals have a reachable success path first.

---

## AR6 — Memory hygiene + persistence *(M1, M3)*

**Goal.** Stop long-memory self-pollution (real findings evicted by duplicate
telemetry) and wire the built-but-unused vector-memory persistence.

**Files.** `brain/cog_memory/long_memory.py` (dedup window + write policy),
`brain/cognition/prediction_helpers.py` (the prediction-error writer), `main.py` (boot
WAL replay), `memory/wal.py` (existing `replay_events`).

**Changes.**
1. Do **not** write per-cycle `[prediction error]` / `[metacog/pattern]` entries to
   *long* memory (route to a metrics log); extend `_dedup_window_for` to content-key
   the known-periodic event types so they can't slip the 10-entry window.
2. At boot, replay the memory WAL into the store before `daemon.start()`
   (`main.py:215` — a few lines using `WAL.replay_events`), or ship a persistent store
   impl.

**Acceptance.** Long-memory duplicate-content share drops sharply (was prediction-errors
34–39× each); semantic recall is non-empty on the first cycle after a restart.

**Tests.** `tests/memory/test_wal_replay_boot.py`: after a simulated restart, the store
holds the pre-restart events. `tests/brain/test_longmem_dedup.py`: a periodic
prediction-error is stored once, not per recurrence.

**Risks.** WAL replay cost at boot on a large log — cap replay to the last N / rotate.

---

## AR7 — Honest goal closure: milestones, notes, error-strings *(G3, G4, G5)*

**Goal.** Stop honest work failing the gate, hollow notes passing it, and internal
error strings becoming goals.

**Files.** `brain/cognition/planning/env_snapshot.py` (`_milestone_met`),
`brain/cognition/leave_note.py`, `brain/cognition/intrinsic_helpers.py` (subject
filter).

**Changes.**
1. **G3:** mark a research/finding milestone met by a real ledger effect
   (`has_qualifying_effect`) for the goal, not by keyword-matching the milestone prose.
2. **G4:** route `leave_note` body from the goal's actual finding/effect; fall back to
   the felt-state seed only when there is genuinely no finding (and don't credit it).
3. **G5:** filter goal/problem subjects so internal diagnostic strings (`*.gate.*`,
   dotted module paths, `record_failure` categories) can't become goal titles.

**Acceptance.** An introspective goal that did the work + left a real effect closes
(doesn't fail on the milestone gate); no goal titled after an internal error string.

**Tests.** extend `tests/brain/test_satiety_close.py` + a new
`test_milestone_effect_grounding.py`.

**Risks.** Low.

---

## AR8 — Let energy breathe *(R2)*

**Goal.** `resource_deficit ≈ 0.037` constant → fatigue carries no behavioral signal
and `_allostatic_load` never arms. Make embodiment breathe.

**Files.** `brain/control_signals/update_signal_state.py` (resource_deficit block —
accumulation +0.002/cyc vs 0.025 recovery; exhaustion arms only > 0.60).

**Changes.** Rebalance accumulation vs recovery so fatigue climbs over a working
session and the exhaustion/allostatic dynamics become reachable — **move deliberately**
(~20 consumers read `resource_deficit`: action gate, speech, selection, binding, WM,
consolidation).

**Acceptance.** Over a multi-hour run, `resource_deficit` shows a rise-and-recover
curve (not flat ~0.037); `_allostatic_load` becomes non-zero under sustained load.

**Tests.** `tests/brain/test_energy_breathes.py`: over simulated idle+work cycles,
resource_deficit rises under sustained work and recovers at rest.

**Risks.** Too much fatigue → he stops doing things. Tune against the survival floor;
this is the one B3-diagnosis item still open.

---

## AR9 — Operational safety *(O1, O2)*

**Goal.** Kill the silent `uchg`-lock class of failure and fix the stale reset script.

**Files.** `main.py` / `run_orrin.sh` (boot writability check), `reset_orrin.py`.

**Changes.**
1. At boot, verify `brain/data` is writable; **fail loudly** (not into `record_failure`)
   if not — the `uchg` immutable-flag lock silently turned exemplar/artifact writes into
   failed goals.
2. `reset_orrin.py`: target `identity_state.json` (not the renamed `self_model.json`)
   and clear `effect_artifacts/`.

**Acceptance.** A locked data dir stops the boot with a clear message; reset leaves no
stale identity/effect state.

**Tests.** `tests/test_boot_writability.py` (skip on CI if perms can't be simulated).

**Risks.** None.

---

## Architectural forks — decisions before code *(audit Part 8 + D8)*

These are **not** scheduled here; they are decisions to make first. Each blocks a
class of work.

- **AD1 — What "making" means LLM-free.** Recommended spine: symbolic artifacts (AR1)
  + verified computation (produce_and_check). Decide whether code authorship (D8,
  currently LLM-only) is a droid capability or an LLM-only luxury.
- **AD2 — Understand-goals: v2-routed (AR2) or v1 synthesis port.** Pick one; single-home.
- **AD3 — Canonical "long-term goal."** Unify the five overlapping notions (aspiration
  rows / lifetime file / v2 long-kind / P4 `directional` / `never_complete`).
- **AD4 — Goal population policy** (AR5 encodes whatever you decide here).
- **AD5 — Memory retention policy** (what long-memory is *for* vs. telemetry — AR6).
- **revised-G1 / GOAL_STORE_UNIFICATION** — already your named, deliberately-deferred
  architecture task. Do the planned unification (bidirectional idempotent reconcile +
  single archive writer); bring the 114-desync / 25k-failure numbers to it. **Do not
  band-aid** — the store core guards resurrection/orphan bugs.
- **D8 — LLM-free creativity/skills.** The `innovation/` subpackage + `skill_synthesis`
  go dark LLM-off. Decide whether to give them symbolic fallbacks or accept that
  deliberate creativity is LLM-only (background symbolic growth via crystallization
  continues either way — and AR1 makes it visible).

---

## Build order

```
AR1 (effects for symbolic + handlers) ─── keystone, do first
   ├─► AR2 (route understand-goals → ResearchHandler, needs AR1's handler effect)
   ├─► AR3 (native LM into composition)
   └─► AR4 (making pays per attempt, needs AR1's symbolic effects)
AR5 (birth-rate quota) — after AR1–AR3 give make-goals a success path
AR6 (memory hygiene + WAL replay) — parallel, independent
AR7 (honest closure) — parallel, small
AR8 (energy breathes) — parallel, tune carefully
AR9 (op safety) — parallel, cheap, do early
── then: stamped STAGING RUN, read against NEXT_RUN_TESTS §8 (signals 5,6,7,9 must move)
── architectural forks (AD1–AD5, GOAL_STORE_UNIFICATION, D8): decide, then schedule
── LAST: update living docs — ARCHITECTURE.md (AR1 adds symbolic/handler effects to the
   loop map), CONFIGURATION.md (any new flag), and run the doc-clearance plan
   (`DOC_ARCHIVE_CHECKLIST_2026-07-01.md`) so this plan + the audit archive together
   once the staging run passes.
```

**Definition of done (whole plan):** AR1–AR9 landed + `make verify` green + a stamped
staging run passing `NEXT_RUN_TESTS §8` (signals 5,6,7,9 move) + living docs updated.
Only then do this plan and `CODEBASE_AUDIT_2026-07-01.md` move to `archive/`.

**If you do exactly one thing: AR1.** It is the keystone the audit's six passes
converged on — make the work Orrin already does LLM-free finally count.

*Authored 2026-07-01 from `CODEBASE_AUDIT_2026-07-01.md`. Proposed — no code changed by
this write.*
