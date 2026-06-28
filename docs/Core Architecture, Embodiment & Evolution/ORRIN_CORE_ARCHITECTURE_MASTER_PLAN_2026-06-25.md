# Orrin — Core Architecture Master Plan

**Date:** 2026-06-25
**Status:** Active — the single execution plan for Core Architecture work.

**What this is.** An *actionable* task list, not a proposal. The analysis, evidence,
and design rationale that produced these tasks have been archived; this file is only
**what to build, in what order, and how we know each piece is done.** Every task links
back to its source for the full reasoning.

**Sources (in `archive/`, read for evidence/rationale, do not re-derive):**
- `ORRIN ROOT CAUSE AND FIX PROPOSAL 2026-06-25.md` — the open-loop thesis, WS-1…WS-6.
- `ORRIN ASPIRATION COVERAGE PROPOSAL 2026-06-25.md` — WS-7.
- `ORRIN MORTALITY CEILINGS WILL PROPOSAL 2026-06-25.md` — WS-8.
- `GOALS_MASTER_PLAN_2026-06-23.md` — Track-1 §A open items (rest built/complete).
- `PRODUCTION_LOOP_CLOSURE_PROPOSAL_2026-06-20.md` — Track-1 §B open items (rest code-complete).
- `orrin_embodiment_architecture.md` + `EMBODIMENT_BUILD_PLAN.md` — Track 2 design spec.

**Run that drove this plan:** life of 2026-06-23 23:37 → 2026-06-25 00:41 EDT (17,352
cycles, clean stop). Before assigning effort to any `[prior pass]` item, re-confirm it
against raw data — most claims are traced in the source proposals.

> **As-built baseline (re-verified against source 2026-06-25).** The proposals were
> written as if nothing was built; some of it is. This revision scopes each task to its
> **remaining delta** and marks built work as as-built/validation. Confirmed already
> implemented: **all of Track 2** (`reaper/host_resources.py`, `brain/cognition/
> host_interoception.py`, `body_band.py`, `body_budget.py` — wired in `watchdogs.py:267`
> + `brain/loop/sense.py:363`); the artifact-completion gate (`goals/model.py:107
> artifact_satisfied`); committed-slot eviction (`intrinsic_goals.py:182
> _evict_spent_committed_goal`); the WS-8b ceiling enforcement half (`EMO_CEILINGS` +
> `pump_signal`); and the WS-2 learned-stats/EVC/associability consumption. These are
> *pending validation*, not untreated.

---

## The one rule

> **Unit of work = one complete loop, not one component.** Pick a loop, wire every edge,
> prove it closes on real evidence, then move. Add nothing new until the current loop's
> acceptance test is green. Sequence bottom-up by dependency, not by what's fun to build.
> The capstone test stays red until the whole thing works: *a goal born from a felt need
> closes because it satisfied that need, with evidence, and the spawning drive then drops.*

The meta-risk: this plan's most likely failure mode is Orrin's own pathology — sense
richly, close nothing, keep polishing solid substrate. Apply the rule to ourselves.

---

## TRACK 1 — Cognitive loop closure

Two tracks total. Track 1 (below) is where this run failed and where the leverage is.
Track 2 (embodiment) is independent and deferrable. Do Track 1 first.

### Execution order

```
Phase 0 (now, all parallel):  T0.1  T0.2  T0.3  T0.4  T0.5(quality predicate)
Phase 1 (the blocker):        T1.1  T1.2  [T1.3]  → T1.P (fast) → T1.G CLOSURE RUN (gate)
Phase 2 (after Phase 1):      T2.1  T2.2  T2.3  T2.4
Phase 3 (after closure green):T3.1
```

**Hard rule:** do **not** start production-output polish or aspiration-*completion*
balance (Phase 3) before T1.1 + T1.2 are green. They sit downstream; polishing first
repeats the open-loop pattern this plan exists to break.

**The gate is T1.1 + T1.2 only.** `[T1.3]` is bracketed because it is *not* a gate
dependency — mortality urgency never firing did **not** cause this run's failure (closure
did). T1.3 runs in the Phase-1 window because it's load-bearing for "finishes things," but
if its clock-source decision stalls, **do not let it block the closure validation run.**

---

### PHASE 0 — Make the instruments honest + clear cheap faults
*All low-risk, independent, parallelizable. Trustworthy runs gate every later phase.*

#### ☑ T0.1 — Unify allostatic load + decide vitality's fate  *(WS-5)*  — DONE 2026-06-26
- [x] Retired `homeostasis.update_allostatic_load` (the mistuned raw-`exploration_drive`
      integrator). `telemetry.py` + the affect API now read the behaviourally-active
      `_allostatic_load`; `life_capsule_ingest` reads the telemetry archive downstream so it
      auto-corrects. Test repointed to `interoception.allostatic_setpoint`.
- [x] Vitality **deleted** (write-only, no reader). A new "rest when vitality low" consumer
      would duplicate the existing resource_deficit/allostatic rest machinery — the
      anti-pattern this plan fights — so removed it from health_monitor's uplift/drain.
- **Files:** `homeostasis.py` (`:107–117` integrator, `:74`/`:98` `_EXPLORATION_DEV_WEIGHT`),
  `interoception.py` (`:245–247,300` `_allostatic_load`), `telemetry.py:197`,
  `life_capsule_ingest.py:330`, `health_monitor.py` (vitality, 6 occurrences).
- **Done when:** telemetry `allostatic_load` tracks the behaviorally-active recovery
  variable and falls when the body recovers; vitality is either wired with a reader or gone.

#### ☑ T0.2 — Collapse the dual affect-ceiling tables  *(WS-8b)*  — DONE 2026-06-26
> Deleted `_dup_soft_ceil`; the dup-key sync clamp now derives from `EMO_CEILINGS`
> (one source of truth). Routed the two main positive-boost bypass writers
> (`update_affect_state.py` success-trigger, `affect_patterns.py` appraisal boost) through
> `pump_signal` so a spike can't pump a drive over its ceiling. End-of-cycle "no signal
> over ceiling" is re-confirmed in the T1.G run.
**Built:** `EMO_CEILINGS` + `pump_signal()` enforcement exist. **Remaining delta:** the
duplicate table still lives at `update_affect_state.py:428` (`_dup_soft_ceil` —
motivation/confidence 0.80, exploration_drive 0.85) and **disagrees** with `EMO_CEILINGS`.
- [ ] Delete `_dup_soft_ceil`; derive the dup-key sync clamp from `EMO_CEILINGS` so there's
      one source of truth.
- [ ] Re-confirm the over-cap leak (motivation 0.900, confidence 0.893, positive_valence
      0.902 from the run) is gone once the single table is enforced; if any signal still
      exceeds its `EMO_CEILINGS` value at end-of-cycle, find the bypassing write and route
      it through `pump_signal()`.
- **Files:** `brain/affect/homeostasis.py` (`EMO_CEILINGS`), `update_affect_state.py:428`.
- **Done when:** exactly one ceiling table exists; no core signal exceeds its `EMO_CEILINGS`
  value at end of any cycle.

#### ☑ T0.3 — Aspiration quick wins: scoreboard + seed + orphaned-`will`  *(WS-7 Changes 5, 1, 3-core)*  — DONE 2026-06-26
> Built `aspiration_scoreboard.py` (generated/attempted/progressed/completed per rolling
> window; generated+progressed+completed wired; fed into `aspiration_pressure`) and
> `production_funnel.py` (candidate→…→credited drop-edge instrument; `candidate` wired,
> deeper stages wired in T1.P). Seed-at-birth: `_seed_drive_priors()` seeds every
> drive→aspiration prior at boot. Orphaned `will` (+`self_exploration`, `simulate_selves`,
> `curiosity`, `problem_solving`) now carry explicit priors via `_AUX_DRIVE_ALIASES`, so
> none defaults to world-knowledge. Tests: `tests/brain/test_objective_quick_wins.py`.
The three WS-7 changes that are independent-now, cheap, and either correctness or
observability. (Coverage floor + credit-blending = T2.3; partial credit = T3.1.)
**Built:** aspiration pressure + drive-weighted generation already exist. **Remaining:**
- [ ] **Scoreboard (Change 5):** per-aspiration generated / attempted / progressed /
      completed, per rolling window — today you only see end-state 20/0/0/0 and can't see
      *where* each aspiration died. Feed the numbers into `aspiration_pressure`.
- [ ] **Production funnel (so "0 output" is never again a mystery).** Same idea, applied to
      the making path: candidate generated → committed → reached compose handoff → producer
      ran → artifact written → credited. This is the instrument T1.G's throughput
      kill-criterion reads to name the exact edge that drops. (Counts only; iterate the path
      stages, no per-stage special-casing.)
- [ ] **Seed at birth (Change 1):** build the full drive→aspiration prior table at boot so
      every aspiration starts with a standing weight (`_PRIOR_SEED_WEIGHT` 0.50), not lazily
      on first completion. *Where:* `intrinsic_aspirations.py` `_ensure_aspirations()`/boot.
- [ ] **Fix the orphaned `will` (Change 3, correctness core):** `will.py:243` tags goals
      `driven_by="will"` but `will` isn't in `_DRIVE_TO_ASPIRATION`, so credit always
      defaults to "Understand the world" — confirmed live in
      `brain/data/drive_aspiration_credit.json` (`will → "Understand the world..." 0.35` is
      the *only* ledger entry). Audit every emitted `driven_by` value (`will`,
      `simulate_selves`, `self_exploration`, `value`, `thread`, `exploration_drive`, …);
      ensure none lacks a mapping.
- [ ] All count-agnostic — iterate `_ASPIRATIONS`, no fixed "four."
- **Files:** `intrinsic_aspirations.py`, `intrinsic_goals.py`, `cognition/will.py`;
  `drive_aspiration_credit.json` (data).
- **Done when:** the scoreboard exists; the ledger has a seeded prior for all aspirations
  from cycle 0; no `driven_by` value defaults to world-knowledge for lack of a mapping.

#### ☑ T0.4 — Isolated component faults  *(WS-6)*  — DONE 2026-06-26
Ordinary defects, not open edges. Each is independent.
- [x] **Narrative interval > lifetime:** `autobiography._sample_interval` now scales to
      `mortality.felt_lifespan_seconds()` (new accessor) targeting ~40 chapters/life,
      clamped to [2 h, 8 h] so the next chapter is reachable inside a run; the on-disk read
      is clamped to the band so a stale 26.4 h value can't out-gate it.
- [x] **`final_thoughts_written: false` on graceful stop** — `shutdown_loop` now calls
      `terminal.final_reflection(context, reason="operator_stop")`, writing the boot handoff
      WITHOUT setting the death flag (added a `reason` param).
- [x] **`proposed_goals.json` 0 bytes** — `behavior_generation` seeds valid `[]` instead of
      a 0-byte `touch()`; readers already guard via `load_json`.
- [x] **`chat_log.json` FileNotFound** — telemetry `/chat` router returns empty on a missing
      file WITHOUT recording a failure (a fresh run legitimately has no chat yet).
- [x] **Unbounded per-cycle JSONL** — `telemetry_archive` capped in `hub._archive_points`;
      goals state.jsonl + WAL compacted via new `FileGoalsStore.checkpoint()` called every
      5 min from the daemon loop (lock-guarded against worker upserts). `production_loop` +
      `memory_graph` were already bounded. Tests: `tests/goals_test/test_store_checkpoint.py`.

#### ◧ T0.5 — The shared real-content / quality predicate  *(anchors every "is this real work?" check)*  — SCAFFOLDING DONE 2026-06-26
> **Built `brain/cognition/quality_predicate.py`** — the single `assess_quality` /
> `is_real_work` / `assess_artifact_file` check. Layered: negative gates (stub /
> machine-log, template-skeleton, near-duplicate) then positive grounding (tokens
> traceable to real evidence, absent from the template) + answers-its-own-question.
> Anti-Goodhart: a FLOOR only (boolean); the `score` is non-credit. Golden set under
> `tests/fixtures/quality_golden/` (anti-exemplars = the run's real slop shapes;
> `exemplars/` has one **starter** — *Ric authors the real standard here*). Verified:
> the predicate rejects all **9 real on-disk `s_*_ok.txt` stubs** + the template note,
> passes the exemplar (`tests/brain/test_quality_predicate.py`). **Wired into T1.1's
> `artifact_satisfied`** (`goals/model.py` — file-existence loophole closed; stubs/
> template notes no longer satisfy; tests in `test_artifact_completion_gate.py`).
> **Remaining:** Ric to author the positive exemplars; T1.P / T1.G / T2.4 import the
> same module when they're built (their call sites don't exist yet).

**The single most important thing to get right.** Every production guarantee rests on it —
T1.1 closure gate, T1.P, T1.G throughput, T2.4 note bodies — and a weak version just
relocates the bet from *"does he produce"* to *"is the check honest,"* which is worse
because it fails silently. A high bar, made **testable and adversarial** (buildable now —
the anti-exemplars are already on disk from this run):
- [ ] **Define quality as a calibrated set, not a heuristic.** Build a golden set:
      exemplars of work that meet the standard (**Ric authors these — they *are* the
      standard**), and anti-exemplars pulled from *this run's actual artifacts*: the ×56
      `grounded_parts`-template note, the 9 `s_*_ok.txt` stubs, the dedupe-rejected
      duplicates. The predicate must **pass every exemplar and reject every anti-exemplar** —
      that regression test is the operational definition of "high quality."
- [ ] **Layer the checks — cheap negative gates, then positive grounding:**
  - reject template skeletons (high n-gram overlap with the `grounded_parts` prompt),
    stubs (trivial length / boilerplate), and near-duplicates of prior output;
  - require **grounding**: content tokens drawn from the goal's *actual* evidence
    (long_memory finding / semantic facts / source) that are **absent from the prompt
    template** — a finding is traceable to inputs, a template is not (this is the line the
    run crossed wrong: reached the topic, severed at the answer);
  - require it **answers its own question**: a declarative resolution of the goal's
    `definition_of_done`, not a restatement of the question.
- [ ] **Tie credit to significance, not gate-pass (anti-Goodhart).** Closure uses the
      predicate only as a *floor* (may/may-not close); reward stays graded on real
      downstream significance (effect ledger), so there is no single threshold to optimize
      against.
- [ ] **Make the bar ratchet (standing task).** Any low-quality output that slips through
      becomes a new anti-exemplar; the predicate must then reject it. The standard only
      rises — it never silently loosens.
- **Honest ceiling:** no pure function equals "Platonic good." This guarantees (a) no *known*
  slop shape passes, (b) the predicate provably separates the good/bad set Ric authored,
  (c) the bar only ratchets up, (d) credit tracks real significance — leaving a shrinking
  residual for periodic human review. That residual is where a high standard is *maintained*,
  not where it leaks.
- **Used by (define once here):** T1.1 (`artifact_satisfied` content), T1.P, T1.G
  (throughput = real works), T2.4 (note bodies).
- **Done when:** the predicate passes the exemplars, rejects every on-disk anti-exemplar from
  this run, and is the single shared check wired into all four call sites.

---

### PHASE 1 — The capstone loop (the actual blocker)
*T1.1 + T1.2 in parallel, then integrate. T1.3 belongs here (load-bearing for "finishes
things"). Ends with the closure validation run, which is the gate to Phase 2.*

#### ☐ T1.1 — Goal closure core  *(WS-1, capstone)*
**Root cause pinned:** `sync_proposed_goals()` calls `api.create_goal(...)` at
`brain/goal_io.py:373` and **discards the returned `Goal`** — `goals/api.py:203` returns
it with its id, but nothing captures it or writes it back onto the v1 node. So
reconciliation falls back to title/name matching (`goal_io.py:199`), and `v2_id=None` on
all v1 ledger entries / `origin=None` on all 1,576 v2 records (a goal failed 64× then
re-committed).
- [ ] Capture the `create_goal` return and **write the v2 id back onto the v1 node** at
      projection time so completion/failure reconciles by id, not title.
- [ ] **Add a direct regression test** for v1-node `v2_id` writeback (a v1-originated goal
      projected to v2 must carry the id back; failed/completed events must map by id).
- [ ] Require a **satisfaction handshake** for felt-origin goals: `DONE` must carry
      `satisfied_need` + evidence; no evidence → not done (today 0/256 DONE met any
      definition).
- [ ] **Make production a precondition of closure, not a downstream hope (de-risks "0
      output").** The capstone test (below) **must include an `output_producing` /
      `requires_artifact` making-goal** whose handshake = a real artifact. Then "closure
      green" *entails* "a real work exists" — production can't be silently skipped. **Close
      the `artifact_satisfied` content loophole** (`goals/model.py:107` currently passes on
      *any file present* — a stub `s_*_ok.txt` or a template-bodied note satisfies it):
      require real content, not mere file existence, **via the shared predicate from T0.5**
      (the same calibrated check used by T1.P, T1.G, and T2.4).
- [ ] On satisfaction, **relax the spawning drive/need** — close the loop back to affect.
      This is where the `contentment` drain plugs in (the "act → satisfied → fades → act
      again" loop). **Highest-value single wire in the system.**
- [ ] **Overshoot guard (don't create a new bug):** the relaxation must be *bounded* — a
      single closure nudges the drive down, it does not zero it. A drive that collapses to 0
      kills motivation just as badly as one pinned at 1.0 (cf. the ceiling pathology in
      T0.2). Clamp the per-closure decrement and keep a non-zero floor.
- [ ] **Absorbs Goals-Master-Plan §A:** migrate readers of `context["committed_goal"]`
      onto `global_workspace.bound_goal()` (single-accessor contract).
- **Built/pending validation (verify in the T1.G run, don't rebuild):** the
      artifact-required completion gate `artifact_satisfied()` (`goals/model.py:107`, tests
      `tests/goals_test/test_artifact_completion_gate.py` — **note: it checks file *existence*
      only; strengthen to content per the bullet above**) and committed-slot starvation
      eviction `_evict_spent_committed_goal()` (`intrinsic_goals.py:182`, tests
      `tests/brain/test_intrinsic_goal_slot_eviction.py`). These close two sub-mechanisms of
      hollow completion; confirm they behave under the live closure run.
- **Files:** `brain/goal_io.py` (`:199`, `:373`), `goals/api.py:203`,
  `global_workspace.bound_goal()`; `comp_goals.json` (data).
- **Depends on:** T1.2 for trustworthy foresight (soft — start in parallel, integrate after).
- **Done when:** a goal spawned from a felt need reaches DONE *only* with satisfaction
  evidence; the originating drive measurably drops after closure **without collapsing to
  zero**; `contentment` rises on satisfaction and resumes its drain afterward; the
  64×-style re-commit loop cannot occur; the id-writeback regression test passes.

#### ☐ T1.2 — Prediction & rule authority  *(WS-3)*
- [ ] **Outcome-based rule authority:** a rule's firing priority decays automatically with
      sustained prediction error; wrong-100% rules lose the priority floor (today PLANNING
      is wrong 893/893 yet keeps firing heavily).
- [ ] **Drain the revision queue:** revisions apply or are rejected within a bounded
      window, never sit `pending` (today 37 entries, all `pending`).
- [ ] **Fix the `accuracy` field** so it reflects `correct/total` (stuck at 0.5 while true is 0.0).
- [ ] **Over-retirement guard (don't create a new bug):** authority *decay* must not become
      authority *deletion* of a whole domain. A domain that is wrong because it is
      under-learned (SOCIAL already has **0 learned rules** despite `connection` being a core
      drive) needs *acquisition*, not having its last rules stripped. Decay priority toward a
      floor, not to zero; exempt low-sample domains from retirement until they have enough
      firings to judge. `N` (mispredictions-in-a-row to trip) is a tunable — set it with a
      minimum-sample gate.
- **Files:** rule store / prediction path; `prediction_domain_stats`, `rule_revisions.json` (data).
- **Blocks:** T1.1 quality.
- **Done when:** a rule that mispredicts N times in a row (above the min-sample gate) loses
  priority with no human action; a proposed revision reaches applied/rejected within a
  bounded window; no domain is left with zero usable rules purely by retirement.

#### ☐ T1.3 — Mortality forward-pressure (pin the clock source, then build)  *(WS-8a)*
The urgency machinery (late/terminal phases injecting motivation/impasse/loss/meaning)
is built but **never fired** in the run. **Correction to the original diagnosis:**
`mortality.py:382` *already* derives `phase` from `_felt_fraction()`, **not** the real
life-clock — so "it's gated on the real clock" is wrong. The real problem is **which felt
clock**: `_felt_fraction()` is **lifespan-noise based** (a function of the hidden lifespan
roll), *not* the temporal felt-cycle / session-arc clock in
`brain/cognition/temporal_state.py:157`. The two disagree, and urgency is keyed to the one
that doesn't advance meaningfully in a run.

- [ ] **DECISION REQUIRED (owner, before any code):** pick the urgency clock source —
      (a) the temporal felt-cycle/session-arc clock (`temporal_state.py:157`); (b) a
      calibrated `_felt_fraction` with a felt-lifespan that actually ramps within a run;
      or (c) a real/felt blend. Keep actual *termination* on the real clock either way
      (preserves the death-screen fix). Do not implement until this is chosen.
- [ ] Then wire the chosen source into `_phase`/`_felt_fraction` and verify the ramp is
      meaningful, not instant (felt-time ran a full felt-lifespan in ~1 real day).
- **Files:** `brain/cognition/mortality.py` (`_phase`, injections, `_felt_fraction` ~122,
  `_life_fraction`), `brain/cognition/temporal_state.py:157`, `lifespan.json` (data).
- **Done when:** over a normal-length run the mortality phase advances past "early" and at
  least the `late` urgency injections fire and are visible in affect.

#### ☐ T1.P — Forced-production test (deterministic; gates T1.G)  *(de-risks "0 output")*
The reason "production is downstream of closure" is currently a *bet*: production was only
ever exercised by the slow autonomous run, which can't tell **"producer broken"** from
**"producer never invoked"** (the run: *"the bad case never occurred because production
barely ran"*). This test removes that ambiguity **before** the expensive run.
- [ ] Deterministic harness: inject a committed `output_producing`/`requires_artifact`
      making-goal, **force** the selector onto the producer path (`compose_section` /
      `decide_to_write_code`), run to completion.
- [ ] Assert a **real-content** artifact lands on disk (judged by the **T0.5 predicate** —
      not a `s_*_ok.txt` stub, not the `grounded_parts` template skeleton) and the
      making-goal reaches DONE through the strengthened `artifact_satisfied`.
- **Done when:** the producer demonstrably makes real work *on demand*, in seconds, with no
  dependence on the autonomous loop choosing to route there. After this passes, the only
  open variable left for T1.G is **routing** (covered by the T0.3 funnel).

#### ☐ T1.G — CLOSURE VALIDATION RUN  *(the Phase-1 gate)*
A single multi-cycle run that proves the capstone loop and discharges three already-built
validations at once. *(Mind the known restart gotcha — a wedged relaunch invalidates the
run; see the restart procedure before starting a multi-day run.)* **Prereq: T1.P green** —
do not use the slow run to discover producer bugs the fast test catches.
- [ ] **Capstone acceptance (the new one):** felt-need goal closes on evidence, spawning
      drive drops (bounded, not to zero); **the capstone set includes a making-goal that
      reaches DONE only via a real artifact** (production proven inside the gate).
- [ ] **Production throughput floor + kill-criterion (turns the bet into a checkpoint):**
      the run must yield **≥N real finished works** (set N ≥ 1 to start; raise it once the
      path is healthy) — *real* meaning it passes the **T0.5 predicate**, not stubs/templates.
      If throughput is below the floor **even though T1.P passed and
      closure is green**, that **falsifies "production is merely downstream of closure"** and
      **triggers a dedicated producer/selection task** (don't ship the run as green). Read it
      from the T0.3 production funnel to see which edge dropped.
- [ ] **Goals-Master-Plan §A:** v1→v2 id-writeback verified live (D2).
- [ ] **Production-Loop §5.2 staged smoke run:** bounded goal ("Write a three-section
      synthesis of what I know about emergence"); pass = committed goal hydrated before
      selection, lens active ≥80% of non-rest cycles, explicit `compose_section` handoff,
      producer executes, `brain/data/tracked_work/*.md` exists, ≥1 `tracked_work` row with
      novelty>0 + significance>0, no double-credit, goal stays open until required section
      count, a simulated threat can still pre-empt.
- [ ] **Production-Loop §5.3 autonomous demo run:** ≥1 `output_producing` candidate
      generated + ≥1 committed with production model intact, attempts carry goal/action
      provenance, credited effects aren't path noise/duplicates, aspiration contribution
      moves only after qualifying evidence. *(Verify with Python JSON parsing, not
      `grep -c` on `decision_stats.json`.)*
- **Do not proceed to Phase 2 until this run is green.**

---

### PHASE 2 — Selection + coverage
*After Phase 1 integrates.*

#### ☐ T2.1 — Selector wiring  *(WS-2 — partly built)*
**Built:** the selector already consumes learned stats, EVC, associability, and outward
satiety. **Remaining delta (the two that explain the run):**
- [ ] Feed **direct positive exploitation** from `action_reward_ema.get_expected()` into
      the score (the highest-reward action `run_forgetting_cycle`, EMA 0.755, was selected
      only 2×).
- [ ] Feed **general per-action satiety** (suppressing) — not just outward satiety (a
      fully-satiated action `look_outward`, satiety 1.0, was still selected most, 5,082).
- [ ] Confirm whether the terminal goal-lens is a third decoupled selector input
      (`goal_lens_top_signal_relevance = 0.0` in 381/400 final cycles).
- **Done when:** a high-reward, low-satiety action's selection frequency rises vs baseline;
  a fully-satiated action's frequency falls.

#### ☐ T2.2 — Survival / maintenance subsystem  *(WS-4)*
- [ ] **Dedup recruits on the deficit key**, not the entry-count-bearing title (627
      recruits → 233 distinct goals because the title carries a raw count).
- [ ] **Fix the remedy:** `run_forgetting_cycle` pruned 0 every run — a restoration goal
      whose action can't restore is a guaranteed perpetual recruit.
- [ ] Land the **autonomic-vs-felt boundary** so file-size/WAL/cache work never becomes a
      conscious goal.
- [ ] Allow tier-closure on the **satiety** predicate independent of the objective gate
      (satiety stayed 0 all life; satiety-close was blocked by "objective not met").
- **Files:** survival/recruit path, `forgetting` cycle; `forgetting_log.json` (data).
- **Depends on:** T1.1 (shares satisfaction/satiety closure machinery).
- **Done when:** one sustained deficit → one live restoration goal whose remedy
  demonstrably reduces the deficit and closes on satiety; no conscious goal title ever
  contains a raw file/entry count.

#### ☐ T2.3 — Aspiration coverage floor + credit-by-intent  *(WS-7 Changes 2, 3)*
*(Seed-at-birth, scoreboard, and the orphaned-`will` mapping are in T0.3.)* End-of-life
coverage was 20% / 0% / 0% / 0% — three never moved off zero.
- [ ] **Generation coverage floor (Change 2, biggest lever).** Over a rolling window each
      aspiration gets a minimum share of newly-generated goals — round-robin floor on top
      of the existing drive-weighted generation. *Where:* `intrinsic_goals.py` `driven_by`
      selection.
- [ ] **Credit by intent, not biased text (Change 3, full blend).** Use the goal's own
      `driven_by`/`serves` tag as a strong prior, blended with outcome keywords. *Where:*
      `_evidenced_aspiration`. (Builds on the orphaned-`will` mapping fixed in T0.3; for a
      general drive like `will`, credit by content/`serves` rather than forcing one prior.)
- **Files:** `intrinsic_goals.py`, `_evidenced_aspiration`, `cognition/will.py`;
  `drive_aspiration_credit.json` (data).
- **Design constraint:** count-agnostic (iterate `_ASPIRATIONS`) — a 5th aspiration gets
  coverage with no further wiring.
- **Done when:** every aspiration shows non-zero generated + attempted; no single
  aspiration captures >80% of credit unless genuinely earned; a "make things"/"be useful"
  goal is credited to that aspiration even when its text reads generic.
- **Honesty guard:** the floor must lift generation/attempts, **never** auto-credit —
  credit still requires real evidence, or you've moved the hollow-closure bug up a layer.

#### ☐ T2.4 — Production content: route output body from the finding, not the template  *(run issue #4; persists from 06-18)*
**Problem.** The note/output body carries the goal's *planning template*, not its *answer*.
The most common note (×56) was literally *"what I actually know about [topic]: question or
desired change; relevant evidence; reasoned conclusion…"* — the `grounded_parts` prompt
skeleton, not the finding. Provenance now reaches the *topic* (the 06-18 "100 identical
notes" form-fix landed) but is **still severed at the answer.**
- [ ] Route the body from the goal's actual `long_memory` finding / produced content, not
      its `grounded_parts` prompt skeleton. *Where:* `leave_note._seed_from_goal` (and any
      sibling composer that fills from the template).
- [ ] **Reuse the T0.5 predicate** — one definition of "real finding, not template
      skeleton," used both to *gate closure* (T1.1) and to *reject hollow note bodies* here.
      Don't write the check twice.
- **Depends on:** T1.1 (closure must produce real findings before there's anything to route;
  this is also why it's Phase 2, not Phase 0 — validating it needs production to actually fire).
- **Done when:** a produced note/output contains the goal's finding, and a body that is just
  the planning skeleton is rejected by the shared predicate.

---

### PHASE 3 — Aspiration completion balance
*Only after closure (T1.1) is green.*

#### ☐ T3.1 — Partial credit on real progress  *(WS-7 Change 4)*
- [ ] Graded credit on genuine sub-progress (a real milestone/artifact step) so
      aspirations accumulate signal between full completions.
- **Guard:** rides on the **same satisfaction-evidence rule** as closure — it cannot
  become rubber-stamping.
- **Done when:** at least 2–3 aspirations show genuine *completions* over a full life
  (moves 20/0/0/0 toward real balance).

---

### Track-1 open-edge inventory (the concrete "dead wires" to close)

The §2 open-loop thesis in shorthand — every felt/learned signal that goes nowhere is a
task above. Verdicts: ✅ wired · 🟡 half-wired · ⚪ dead wire · 🔧 broken part.

| Signal | State | Action | Task |
|---|---|---|---|
| **contentment** | ⚪ | wire the drain to closure — the satisfaction loop | T1.1 |
| need→goal→satisfaction handshake | ⚪ not built | build it | T1.1 |
| goal closure (v1↔v2 id) | 🔧 | write id back; require evidence for DONE | T1.1 |
| **vitality** | ⚪ | wire ("rest when low") or delete | T0.1 |
| allostatic_load (no underscore) | 🔧 | retire, show the good `_allostatic_load` | T0.1 |
| action reward (value half) | 🟡 | feed reward *level* into selection | T2.1 |
| satiety | ⚪ (selection) | let satiety suppress the score | T2.1 |
| prediction accuracy / rule firing | 🔧 | auto-retire wrong rules; fix the field | T1.2 |
| drive-credit → aspirations | 🟡 | seed + fix orphaned `will` (T0.3); spread + credit by intent (T2.3) | T0.3, T2.3 |
| note/output body | 🔧 | route from the finding, not the planning template | T2.4 |
| positive_valence | 🟡 (over cap) | enforcement built; remove the duplicate ceiling table | T0.2 |

Confirmed **solid — do not re-fix:** affect coherence (opponent-process decay), the
`_allostatic_load` interoceptive regulator, causal self-model (398 edges), experiential
learning substrate (314 facts, 18 skills, native LM 22.1M tokens), ops/persistence
(0 crashes, clean restarts). Foundations are sound; the gaps are in the middle layers.

**Caveats:** not every bug is an open edge (the forgetting remedy, narrative interval,
ceiling leak are genuine component faults). Re-confirm `[prior pass]` claims against raw
data before assigning effort. SOCIAL has 0 learned rules despite `connection` being a
core drive (0.63) — a learning gap, overlaps T1.2's owner.

---

## TRACK 2 — Embodiment (host-resource awareness) — **AS-BUILT, pending validation/tuning**

*Independent track from the 2026-06-15 hibernation panic (host kernel-panicked mid-
hibernate on a full SSD; none of nine watchdogs saw it because all look inward at Orrin's
process, none outward at the machine). Full design spec, evidence, and rationale:*
`archive/orrin_embodiment_architecture.md` *and* `archive/EMBODIMENT_BUILD_PLAN.md`*.*

> **Status (verified in source 2026-06-25): all four components are implemented and
> wired.** This is no longer an implementation track — the remaining work is the open
> *measurements* (TE.0) plus tuning and a validation pass. Different owner; deferrable
> unless host-panic risk is active.

### The three mappings (keep separate — never collapse) — *as implemented*

| Mapping | Nature | Where built |
|---|---|---|
| Absolute capacity → metabolism (cadence, caps, concurrency) | absolute, set at boot | `body_budget.py` (fraction → metabolism) |
| Deviation from set point → affect (interoception) | relative to *this body's* normal | `host_interoception.py` + `body_band.py` |
| Absolute safety floors → reflex (disk < 10 GB is dangerous anywhere) | absolute, host-independent | `reaper/host_resources.py` |

> Brainstem uses absolute floors; cortex uses relative deviation. The crash was a body
> whose felt-normal was "fine" until the substrate hit an absolute wall it had no reflex for.

### ✅ TE.1 — `HostResourceGuard` — **BUILT & WIRED**
`reaper/host_resources.py`, instantiated in `watchdogs.py:267`; its `heavy_cycles_paused`
gate is honored in `brain/loop/finalize.py:449,539`. Outward gaze, gentle staged
escalation (warn → pause dream/reading → reserve hard kill), hysteresis on resume.
- [ ] **Validation only:** reproduce the 2026-06-15 signature (one-way swap climb / disk
      floor) in a test and confirm it trips below cognition and warns before the cliff.
- [ ] **Tuning:** confirm the 10 GB disk floor + soft/hard swap lines on the 8 GB box (uses
      TE.0 measurements).

### ✅ TE.2 — Host interoception (the felt body) — **BUILT & WIRED**
`brain/cognition/host_interoception.py`, called from `brain/loop/sense.py:363`. Reuses the
band-learner so disk/swap/memory/battery are felt as **departure from the learned band**,
not absolute level; battery surfaced as gentle urgency/relief, not wired hard into distress;
silent during somatic infancy until host bands converge.
- [ ] **Validation only:** confirm host trouble is felt when genuinely present and ordinary
      near-limit operation reads as neutral (no chronic-scarcity false distress).

### ✅ TE.3 — Infancy band-learner — **BUILT**
`brain/cognition/body_band.py` (`BodyBands`): baselines to the *band* (floor/ceiling/
amplitude), converges when the variance *description* stops widening, carries the
refuse-to-imprint danger line (§10.5/10.6), and owns the somatic-infancy gate.
- [ ] **Open design check:** confirm the somatic vs. developmental infancy split is honored
      (gated on TE.0 question "does the self-model distinguish first-birth from restart?").
- [ ] **Validation only:** wake on a live/in-use machine, confirm no lull is imprinted as
      normal and a sick boot (disk ~95% full) is refused, not baselined.

### ✅ TE.4 — RAM budget knob — **BUILT**
`brain/cognition/body_budget.py`: `budget_fraction()` / `set_budget_fraction()` express the
grant as a **fraction of the machine** feeding metabolism + interoceptive "100%"; a
non-overridable survival reserve floor sits underneath; a too-small grant is refused with a
"give him at least X%" message.
- [ ] **Validation only:** confirm a live resize routes through re-baseline, and the floor
      cannot be dialed past the survival line (uses TE.0 "minimum viable body").

### ☐ TE.0 — Open measurements (the remaining real work on this track)
Genuinely open; several feed the tuning/validation above. The first two run as a single
calm-infancy session with no scaffolding.
- [ ] Steady-state baseline: healthy memory pressure + swap depth on the 8 GB box.
- [ ] **Is the current allostatic integrator fed absolute level or deviation-from-baseline?**
      **Note — T0.1 likely already answers this for the *broken* integrator:** the pinned
      top-level `allostatic_load` integrates *raw* `exploration_drive` deviation (absolute),
      which is the mechanism T0.1 retires. So this measurement is really asking whether the
      *correct* `_allostatic_load` (listed as solid — do **not** re-fix) stays healthy in a
      calm infancy. If load still climbs to 1.000 with no stressor *after* T0.1 lands, only
      then is there a second absolute-vs-deviation bug to chase. Run it as a post-T0.1
      confirmation, not a fresh investigation.
- [ ] Oscillation shape: gentle around a center, or slams between empty/full as dream/read
      cycles fire? (Single band vs. per-phase bands.)
- [ ] Does the self-model distinguish true first-birth from restart? (Gates TE.3's
      one-vs-two-code-paths check.)
- [ ] Minimum viable body: smallest grant that completes a full dream **and** reading cycle
      without thrashing — validates TE.4's slider floor.

---

## One line for the higher-up

The substrate is sound; the failure is a system-wide pattern of **open loops with no
corrective authority**, concentrated in prediction and goal-closure. Fix it by switching
the unit of work to **one fully-wired loop at a time**, tested at the loop, sequenced
bottom-up — starting with v1↔v2 closure binding (T1.1) and PLANNING rule authority (T1.2).
