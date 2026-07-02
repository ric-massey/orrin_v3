# Implementation Plan: Close the Grounding Loop & Build the Lived Surface

**Date:** 2026-06-30
**Derives from:** `archive/SYNTHESIS_GROUNDING_AND_SURFACE_2026-06-30.md`
**Status:** P1–P8 built 2026-07-01 (uncommitted); staging run + ten-round proof pending; gated on NEXT_RUN_TESTS §8.

> **The bet, in one sentence.** Pick one build, close the full loop end-to-end —
> *machine verifies → Ric corrects → both signals train the persistent model and
> the native weights* — and prove it compounds over ten rounds. Everything below
> is sequenced to make that one circuit real, then to instrument it so we can see
> it working.

Each phase lists: **Goal · Files · Changes · Acceptance · Tests · Risks.**
Phases are ordered by leverage: P1–P5 are the grounding loop (integration work,
where the runs are actually breaking); P6 is the veil; P7 is the lived-surface /
ablation UI (the instrument that proves the rest); P8 is the structural tax.

Ground truth verified 2026-06-30 (files that exist, the exact seams, **and what
is already wired** — re-checked against the code, not just filenames, so we don't
rebuild what exists or edit the wrong file):

- `brain/cognition/planning/goal_satiety.py` — `is_sated()`, closes on
  `uncertainty(topic) <= 0.25` (`_UNCERTAINTY_SATED`) or novelty exhaustion. Has a
  cycle-1 guard (`_did_exploration_work`).
- `brain/cognition/planning/goal_closure.py::_maybe_close_on_tier()` — decides
  *whether* to close (growth/core/generic → `is_sated`; `aspiration`/`long_term`
  pass), then routes through `_finalize_goal_completion(...)`.
- `brain/loop/maintenance.py:104-171` — a **second** satiety-close path (population
  sweep every 40 cycles) that calls `is_sated` then `mark_goal_completed(...)`
  **without** `satiety_close=True`. Any P1 gate must cover **both** call sites.
- `brain/cognition/planning/goal_outcomes.py::mark_goal_completed()` — the single
  completion chokepoint. **Already** computes
  `_satiety_ok = satiety_close and not _is_artifact_gated(goal)` (line ~87) and
  **already** gates the +1.0 production reward on `_grounded` (real effect /
  all-milestones / verified artifact). So a hollow satiety close today files DONE
  **but pays no reward** — this is the correct place to add P1's effect gate, not
  `_maybe_close_on_tier`.
- `brain/agency/effect_ledger.py::has_qualifying_effect(goal_id, goal)` — the
  artifact gate. **It is already consulted** in `goals.py::try_to_accomplish`
  (line 198), `goal_criteria.py::_criteria_evidence_met` (line 63), and
  `goal_outcomes.py` deadline logic (line 493). So `output_producing`/
  `requires_artifact` goals **already require an effect**. The genuine gap is
  **non-artifact** growth/"understand X" goals, which satiety-close with no effect.
- **Effect producers are only three:** `express_to_user.py:322` (`note_novel` /
  `message_answered`), `compose_section.py:81` (`tracked_work`), `code_writer.py:172`
  (`tool_written`/`code_committed`). `research_topic`/`fetch_and_read`/reading record
  **nothing**. `file_write`/`tool_run_effect`/`external_post` are valid `EFFECT_KINDS`
  but **no code emits them** yet. ⇒ A pure-reading "understand X" goal can produce a
  qualifying effect **only** if it leaves a note; otherwise P1 makes it un-closeable.
- `brain/cognition/idle_consolidation/episode_replay.py` — reward-thresholds at
  `_REWARD_THRESHOLD = 0.65`, routes into the **contextual bandit** (`_cb.update`).
- `brain/cognition/language/acquisition.py::read_a_book()` / `consolidate_language()`
  / `native_lm.train_on()` — `train_on(text, steps, batch)` takes a **flat text
  block** and samples **uniform-random** windows; there is **no per-segment weight
  parameter**. `consolidate_language` already upweights by *source* (`parts += [x, x]`)
  but not by reward. Reward-weighting the diet requires changing `train_on`'s
  signature + sampling, not just the corpus builder.
- `brain/cognition/theory_of_mind.py::_update_belief_model` — the **actual** model
  of a person's stance/preferences; it already reacts to conversational corrections
  (`is_correction`). `brain/cognition/self_state/person_detector.py` is **identity
  detection only (no preference model)** — P2b should target ToM, not person_detector.
  `feedback_log.py::log_feedback` has no `correction` event type and is called only
  from `repair.py`.
- `brain/behavior/tools/toolkit.py::execute_python_code` (wraps
  `sandbox_runner.run_python`). It is in `behavioral_functions_list.json` but **not in
  any `selection/tag_sets.py` set**, so `select_function` never picks it. It *is*
  reachable via `action_gate_execute.py:315` (LLM-proposed action, behind a
  code-actions-disabled flag) — which is why it shows zero selections. `recognise_step_action`
  (`step_execution.py:180`) maps plan-step text → action names; a new produce-and-check
  action must be registered there too.
- `brain/goal_io.py:231 _NONCOMMITTABLE_TIERS = {"aspiration", "long_term"}`, used by
  `_committable_from_v1_tree` / `committed_goals_v1` (called from `sense.py:225`). **This
  is the real reason long_term goals never commit** — not goal_closure's comment. P4
  must edit `goal_io.py`.
- `brain/control_signals/` — decay is **already present and running each cycle**:
  `signal_dynamics.apply_restoring_forces` (decay → `CORE_BASELINES`),
  `update_hedonic_baselines` (hedonic adaptation), `homeostasis.EMO_CEILINGS` (soft
  ceilings), `decay_habituation`. Action-repetition is **already** damped by
  `exploration_value.py` (per-action satiety) and `selection/pick.py::apply_antirepeat_and_metarut`.
  ⇒ B3 is a **tuning / measurement** problem (pump-vs-decay balance, or LM phrase-level
  repetition), not a "there is no decay" problem. Do not rebuild these.
- Membrane/veil already enforced + tested: `arbiter.py`, `binding.py`, `felt_lexicon.py`,
  and tests `test_boundary_contracts_and_audit.py`, `test_expression_membrane.py`,
  `test_felt_lexicon_membrane.py`, `test_membrane_invariant.py`. Extend these, don't
  start from zero.

---

## Phase 1 — Gate goal closure on a real recorded effect (B2 / C2)

**Goal.** Kill the "feels-familiar" closure path so no non-trivial goal completes
without a durable, novel effect on the ledger. This is the smallest, highest-signal
fix and it stops the hollow 7ms DONE flips and stub-only artifact folders.

**Files.**
- `brain/cognition/planning/goal_outcomes.py` (`mark_goal_completed` — **the single
  chokepoint; put the gate here, at the existing `_satiety_ok` computation**).
- `brain/agency/effect_ledger.py` (`has_qualifying_effect` — reuse, no change).
- `brain/cognition/planning/goal_closure.py::_degrade_or_disengage` (watchdog path).
- (No edit to `_maybe_close_on_tier` or a second copy in `is_sated` — see note.)

**Why the chokepoint, not `_maybe_close_on_tier`.** There are **two** satiety-close
callers (`goal_closure._finalize_goal_completion` and `maintenance.py:158`) and they
both converge on `mark_goal_completed`, which **already** computes
`_satiety_ok = satiety_close and not _is_artifact_gated(goal)`. Gating there fixes
both paths with one edit and can't diverge. Editing `_maybe_close_on_tier` alone
leaves the maintenance sweep able to close hollow goals. (This corrects the earlier
draft, which patched the wrong seam.)

**Changes.**
1. In `mark_goal_completed`, tighten the satiety bypass so a satiety close of a
   **non-artifact** goal also requires a recorded effect (artifact goals already
   require one via `_is_artifact_gated` + the `_grounded` reward gate):
   ```python
   from brain.agency.effect_ledger import has_qualifying_effect
   gid = str(goal.get("id") or goal.get("title") or "")
   _has_effect = bool(gid) and has_qualifying_effect(gid, goal)
   _satiety_ok = (bool(satiety_close) and not _is_artifact_gated(goal)
                  and (_has_effect or not _require_effect_for_closure()))
   ```
   Sated-but-empty ⇒ the milestone gate stays in force; a milestone-less growth goal
   no longer files a hollow DONE. It stays open to be re-aimed (Phase 3).
2. `maintenance.py:158` currently calls `mark_goal_completed(_g, context=context)`
   **without** `satiety_close=True`, so its hollow closes only slip through for
   *milestone-less* goals. Pass `satiety_close=True` there so the sweep goes through
   the **same** gate (otherwise the two paths still disagree on what "sated" allows).
3. One flag, `ORRIN_REQUIRE_EFFECT_FOR_CLOSURE` (`_require_effect_for_closure()`,
   default **on**), so the old behavior is recoverable for A/B ablation, not so it
   silently rots.

**Hard dependency on P3 — call it out.** Because reading records **no** effect and
only notes/tracked_work/tool_written/message_answered do, a pure "understand X" goal
under this gate can close **only** if it emits a note — otherwise it becomes
un-closeable until P3 gives it a `tool_run_effect`. So P1 **must ship with its
watchdog** (change 4) and is only *complete* once P3 lands. Do not land P1 alone and
expect understanding goals to keep closing.
4. **Watchdog (ships with P1, not "someday").** A goal open > `N` cycles with a
   quenched drive and no qualifying effect is **disengaged** via the existing
   `_degrade_or_disengage` (Wrosch), not closed — so nothing becomes immortal. Reuse
   the `PRODUCTION_DEADLINE_CYCLES = 200` cadence in `goal_criteria.py` rather than a
   new constant.

**Acceptance.** A milestone-less `growth` goal whose only "work" was reading closes
**0** times (it disengages via the watchdog instead). A goal that produced a
qualifying effect (`note_novel` / `tracked_work` / `tool_written` / — after P3 —
`tool_run_effect`) still closes. No DONE with an empty/stub artifact folder in the
trace. (Note: `file_write` is *not* an emitted kind today — don't assert on it.)

**Tests.** Extend `tests/brain/test_effect_ledger.py`; add
`tests/brain/test_tier_closure_requires_effect.py`: (a) satiety close + no effect ⇒
stays open (or disengages past the watchdog window); (b) satiety close + qualifying
effect ⇒ closes; (c) `tracked_work` goal honors the sections target already in
`has_qualifying_effect`; (d) the `maintenance.py` sweep path obeys the same gate.

**Risks.** Pure-introspection goals with no artifact channel must be tiered
`trivial`/`minor` (milestone closure) or emit a `note_novel` — audit the goal
generators (`intrinsic_goals`, `evolution`, `intrinsic_generators`) so none can only
ever satiety-close. The watchdog is the backstop, but a goal that disengages every
time is a generator bug, not a closure bug — surface it in the trace.

---

## Phase 2 — Route graded signal into every learner (B1, the root)

**Goal.** The action-selector eats reward-filtered experience; the language model
eats raw imitation; the person model eats conversation. Feed **the same graded
signal** to all three. This is the root issue — fix it and the thesis has a chance.

### 2a. Reward-filter the native LM's diet

**Files.** `brain/cognition/language/acquisition.py`,
`brain/cognition/language/native_lm.py`,
`brain/cognition/idle_consolidation/episode_replay.py`.

**Changes.**
- **`train_on` needs a new signature.** Today `train_on(text, steps, batch)` samples
  uniform-random windows over one concatenated block — there is no way to weight a
  segment. Add a weighted path: `train_on(blocks, steps, batch)` where `blocks` is a
  list of `(text, weight)`, and bias the `torch.randint` window-sampling toward
  higher-weight blocks (weighted choice of source block, then window within it). Keep
  the old `str` signature working (wrap as `[(text, 1.0)]`) so `read_a_book` and every
  other caller is unaffected until migrated.
- **Segment→reward mapping.** The replay corpus is plain text with no per-line reward
  today, so build the weighting at *corpus-assembly* time in `consolidate_language`
  (which already knows each source): keep the existing source-based upweighting but
  express it as explicit weights, and add a reward channel for the
  experience-derived sources by joining episodes to cycle reward from
  `cognition_history.json` (reuse the ≥`0.65` window logic in `episode_replay.py`).
  Book/library prose gets a **neutral, capped** weight so imitation can't dominate.
- Keep a floor of unfiltered prose (language needs breadth), but make it a
  *minority* of the sampled steps, not the whole diet.

**Acceptance.** `native_lm.status()` reports a reward-weighted training mix (add the
field). Held-out `evaluate()` loss on grounded text improves faster than on book text
across rounds; the model stops regurgitating book phrasing verbatim. **Scope note:**
this is a real change to the learner's sampler + a new `status()` field, not a
one-line corpus tweak — size it accordingly.

### 2b. Feed corrections into the person model

**Files.** `brain/cognition/theory_of_mind.py` (`_update_belief_model` — **the actual
preference/stance model**, and it already handles `is_correction` for *conversational*
turns), `brain/control_signals/feedback_log.py` (add a typed `correction` event),
`brain/agency/effect_ledger.py` (significance write-down on a corrected effect).
**Not** `person_detector.py` — it is identity detection only and has no preference
model; wiring corrections there would build nothing.

**Changes.**
- When Ric corrects **produced work** (an artifact/effect, not just a chat turn),
  write a typed `correction` event to `feedback_log` linked to the goal id / effect
  `content_hash`. `feedback_log` has no such type today — add it (small schema add).
- Extend `theory_of_mind._update_belief_model` to consume artifact-`correction`
  events with **higher weight** than conversational inference (it already weights the
  conversational `is_correction` signal — this adds the produced-work channel it lacks).
- Close the loop: a `correction` on an effect lowers that effect's significance
  (a new `effect_ledger` helper, mirror of `mark_reused` in reverse) and
  re-opens/aims the owning goal (ties into Phase 3).

**Acceptance.** After an artifact correction, the ToM belief model's predicted
preference shifts in the corrected direction and the next attempt reflects it. Test
with a scripted correct→retry pair. **Scope note:** the "person model of preferences"
the synthesis assumes exists is really the ToM belief model; there is no separate
preference store to update, so this is an *extension* of ToM plus a new feedback
event, not a wire between two finished pieces.

**Tests.** `tests/brain/test_native_lm_reward_diet.py`,
`tests/brain/test_person_model_corrections.py`.

**Risks.** Over-weighting reward can collapse language diversity → keep the prose
floor. Corrections are sparse → don't let one correction overfit; use the existing
Pearce-Hall adaptive-rate machinery (see memory `project_metacognition_learning`)
to scale how much a single correction moves the model.

---

## Phase 3 — Produce-and-check loop + exercise the caged sandbox (C3 / B4)

**Goal.** Make "understood" mean "attempted and passed a check," not "stopped
feeling new." Turn `execute_python_code` from a zero-selected tool into the
answer-checker for verifiable goals.

**Files.**
- `brain/cognition/web_research.py` (`research_topic`) — add a produce-and-check
  companion action.
- New action wrapping `sandbox_runner.run_python` directly (as
  `toolkit.execute_python_code` does). **Registration is the real work** — an action
  is only selectable when it's in *all* of: (a) the dispatch map the selector calls,
  (b) `brain/data/behavioral_functions_list.json` + `cognitive_functions.json`,
  (c) `brain/data/capability_descriptions.json` with the right tags, and (d) the
  `selection/tag_sets.py` sets (`_EXECUTION_FNS`, a recruit set, `_SAFE_TO_EXPLORE`
  so ε-exploration can force the first pull — cold arms never warm up otherwise, per
  the 5900-cycle "write a cognitive function" starvation noted in `tag_sets.py`).
- `brain/cognition/planning/step_execution.py::recognise_step_action` — add the
  keyword/intent rule so a plan step like "work the problem and check the answer"
  maps to the new action (otherwise plan-driven pursuit can't reach it).
- `brain/think/think_utils/selection/score_actions.py` / `boosts.py` — the anti-read-only
  recruitment nudge (below).
- `brain/cognition/planning/goal_satiety.py` — replace the uncertainty proxy for
  *verifiable* topics with a **check-pass** proxy.
- **Do not** route through `action_gate_execute.py` (the existing LLM-proposed
  `execute_python_code` path, behind a code-actions-disabled flag) — a directly
  selectable cognitive action is cleaner and doesn't depend on the LLM emitting it.

**Changes.**
1. New action: given a claim/derivation from a research goal, emit a small
   checkable target (compute a number, work a problem, compare to a known answer)
   and run it through the sandbox. Record a `tool_run_effect` on success — the kind
   is already in `EFFECT_KINDS` but **nothing emits it yet**, so this is the first
   producer of it; it satisfies Phase 1's gate for verifiable goals.
2. Gap signal flips from *unfamiliarity* to *failure*: a failed check writes the
   specific gap back onto the goal (aims the next step). This is the "attempt until
   I stop getting it wrong" loop.
3. For topics the classifier marks **verifiable** (physics/math/code), `is_sated`
   closes on *check-passed*, not `uncertainty <= 0.25`. Non-verifiable topics keep
   the info-gap proxy (it's the honest signal there).
4. Selection: bias recruitment so a `growth` goal that has done N reads with zero
   checks is *pushed* toward the produce-and-check action (an anti-read-only nudge).

**Acceptance.** On a "learn X" goal in a verifiable domain, `execute_python_code`
is selected > 0 times per run; the goal only closes after a check passes; self-code
folders are non-empty.

**Tests.** `tests/brain/test_produce_and_check.py`: verifiable goal → sandbox
selected, wrong answer keeps goal open with an updated gap, right answer closes it
with a recorded effect.

**Risks.** Classifying "verifiable" is itself fallible — start with an explicit
allow-list of domains (math, physics, code, statistics) and expand. Don't gate
*non-verifiable* goals on a check they can't have.

---

## Phase 4 — Let long-term goals actually drive (C4)

**Goal.** Give the long-horizon goal the wheel so research bouts compound across
sessions into sustained deepening, instead of disconnected short reads under a dead
heading.

**Files.**
- `brain/goal_io.py` — **the real gate.** `_NONCOMMITTABLE_TIERS = {"aspiration",
  "long_term"}` (line 231), read by `_committable_from_v1_tree` /
  `committed_goals_v1`. This — not the goal_closure comment — is what keeps long_term
  goals from ever being committed. (The earlier draft named goal_closure/executive/
  goal_arbiter; none of those is the gate. `goal_closure.py`'s "never committed
  anyway" is just a comment describing this fact; `context["committed_goals"]` is
  populated by `committed_goals_v1` via `sense.py:225`, not by goal_arbiter.)
- `brain/cognition/planning/evolution.py` (builds the `long_term` goal + roadmap —
  the `frontier` field is persisted here).
- `brain/cognition/planning/executive.py` (`_build_queue` / `_committed_goals` /
  `_allocate_steps` — bound the directional goal's share of committed slots).
- `brain/cognition/planning/goal_closure.py` (`_maybe_close_on_tier` — keep the
  `aspiration`/`long_term` "never closes here" branch; the parent stays open by design).

**Changes.**
1. In `goal_io.py`, allow a `long_term` goal to be **committed in a *directional*
   mode** (e.g. a `directional: True` / `never_complete` marker on the goal, or a new
   committable-but-non-terminal status) so `_committable_from_v1_tree` selects it
   while `mark_goal_completed` still never files it DONE. It becomes the active driver
   that spawns and sequences the next concrete sub-task each session; the sub-tasks are
   ordinary committable goals that close on P1+P3 rules.
2. Add a cross-session thread: the long-term goal owns a `frontier` — "the gap I
   hit last week" — persisted with the goal. On resume, it commits the sub-task
   that works that exact gap (feeds off Phase 3's failure-derived gaps).
3. Sub-tasks close on Phase 1 + Phase 3 rules (effect + check-pass), and their
   result updates the parent's frontier. The parent stays open by design.
4. Keep a cap so exactly one long-term goal drives at a time (no thrash); the rest
   remain signposts until promoted.

**Acceptance.** Across ≥3 simulated sessions, a single "understand X more deeply"
long-term goal drives successive sub-tasks that target last session's failed
check — a visible thread, not a pile of same-topic reads all closing on satiety.

**Tests.** `tests/brain/test_long_term_commit_thread.py`: session N failure →
session N+1 sub-task targets that gap; parent never files DONE on satiety.

**Risks.** A committed never-ending goal could starve other goals — bound its share
of committed slots; keep the survival/preempt layer (memory
`project_survival_goal_layer`) above it.

---

## Phase 5 — Homeostatic decay on appraisal signals (B3)

**Goal.** Let drives/confidence relax *down* enough that behavior stays varied and
exploratory instead of "hot and flat" with repeated phrases.

**Reality check (do this FIRST — the machinery already exists).** Decay and repetition
damping are **already built and running each cycle**; the earlier draft proposed
rebuilding them. Before writing any code, confirm *where* the failure actually is:
- `signal_dynamics.apply_restoring_forces` already decays every core signal toward
  `CORE_BASELINES` (`update_signal_state.py:347`).
- `update_hedonic_baselines` already adapts sustained emotions (they lose felt charge).
- `homeostasis.EMO_CEILINGS` already caps per-emotion levels.
- `exploration_value.py` (per-action satiety) + `selection/pick.py::apply_antirepeat_and_metarut`
  already damp a repeated *action*.
So "no homeostatic pullback" is not literally true. The observed symptom ("repeats the
same *phrase* dozens of times") is most likely **LM phrase-level repetition** (a
`native_lm.generate` sampling/repetition-penalty issue) or a **pump-rate-beats-decay-rate
tuning** problem, not a missing decay law. Instrument first: log per-signal
rise/relax curves for a run and confirm which it is.

**Files (only after the reality check pins the cause).** `setpoints.py` /
`signal_dynamics.py` (tune decay/pump balance if drives genuinely pin), and/or
`native_lm.generate` (add/repair a repetition penalty if it's phrase-level).

**Changes.**
1. If drives genuinely pin at ceiling: strengthen the existing
   `apply_restoring_forces` / hedonic-drift rates or lower `EMO_CEILINGS` — **tune the
   existing law, do not add a second one.** Add a "time-at-ceiling" accelerator to the
   *existing* restoring term only if the curves show a true stall.
2. If it's phrase repetition: add a repetition/n-gram penalty in `native_lm.generate`.
3. Expose the relevant constants as tunables so the ablation panel (Phase 7) can turn
   decay on/off and show the "hot and flat" failure mode directly.

**Acceptance.** In a run, no phrase repeats > K times; drive traces show
rise-and-relax curves rather than flat ceilings; production doesn't stall. The
diagnosis note (which cause it was) is recorded so we don't re-litigate B3.

**Tests.** `tests/brain/test_signal_decay.py`: assert the *existing* restoring force
brings a pinned signal toward setpoint over idle cycles (a regression test on current
behavior, tightened if tuned); if a generate-side penalty is added, test that a
repeated n-gram is suppressed.

**Risks.** Too much decay kills urgency/persistence — tune against the survival
floor (`project_survival_goal_layer`) so vital signals don't bleed off. Don't disable
or duplicate the restoring force that already protects the baseline.

---

## Phase 6 — Seal the veil: substrate → consciousness one-way (A3)

**Goal.** Make the perceived/felt projection the **only** path from substrate to
consciousness; consciousness can never read raw plumbing (keys).

**Files.** The convergence layer (memory `project_convergence_layer`:
AffectArbiter + ActionArbiter), `brain/control_signals/arbiter.py`,
`brain/cognition/binding.py`, substrate/felt projection boundary,
`brain/utils/felt_lexicon.py` (currently modified on this branch).

**Start from what's already enforced — don't write `test_veil_boundary.py` from
scratch.** There are already four boundary/membrane tests:
`test_boundary_contracts_and_audit.py`, `test_expression_membrane.py`,
`test_felt_lexicon_membrane.py`, `test_membrane_invariant.py`. Consciousness-side
reads already go through `context.get("perceived_affect_state")` (a raw-key sweep for
that projection found **zero** direct-substrate reads on the perceived path). So the
veil is largely sealed; P6 is *closing residual leaks and adding a standing guard*,
not building the membrane.

**Changes.**
1. Audit remaining places consciousness-side code reads a raw substrate key (start
   from what the four tests above already cover; extend, don't duplicate). Route each
   through the felt/perceived projection.
2. Add a standing lint/test that fails if a consciousness-tagged module imports
   substrate state directly — fold into the existing membrane test suite so there's
   one boundary gate, not five.

**Acceptance.** The extended boundary test enumerates consciousness-side reads; none
touch raw keys. Removing a substrate key's raw accessor breaks no consciousness code.

**Tests.** Extend `test_membrane_invariant.py` / `test_boundary_contracts_and_audit.py`
with the import-graph / access assertion rather than adding a fifth file.

**Risks.** Architectural surface (see B5) — do it *incrementally behind the existing
tests*, not as a big-bang refactor. Because this branch already edits `felt_lexicon.py`
and its membrane test, land P6 changes on top of that in-flight work, not against a
stale base.

---

## Phase 7 — The lived surface + ablation/sandbox panel (A1 / A2)

**Goal.** (A1) a UI that shows the lived surface, and (A2) a Run-Configuration
panel that ablates subsystems and stamps each run — the instrument that *proves*
Phases 1–6 changed behavior.

**Files.** `frontend/` + `backend/` telemetry bridge (memory `project_orrin_ui`),
`runtime/lifecycle.py` (run start / config), the run-stamp / Life Capsule path.

**Changes.**
1. **Lived surface (A1).** A single view showing: attending-to, pressured-by,
   what-changed, what-it's-avoiding, what-it's-trying-to-resolve — sourced from
   workspace/attention + control signals + goal frontier. Not a state dump; a
   curated projection (aligns with the Phase 6 felt projection).
2. **Ablation panel (A2).** Per-run toggles: Memory · Goals · Affect/control
   signals · Workspace · Metacognition · Host coupling · Idle consolidation · LLM
   tools · Research tools · Persistence. Implement as run-config flags read at boot
   in `runtime/lifecycle.py`; each subsystem checks its flag at its entry point.
3. **Run stamping.** Every run tagged with its config, e.g.
   `run_2026_06_27_memory_off_goals_on_workspace_on`, written into the Life Capsule
   so traces are comparable.
4. **Sandbox mode (product).** Expose the toggles to users; render the personality/
   behavior change live.

**Acceptance.** Toggling Memory off yields a run whose trace shows continuity
collapse; Goals off shows drift; Affect off shows flattened priorities — matching
the predictions in the synthesis. Each run's config is recoverable from its stamp.

**Tests.** `tests/runtime/test_run_config_ablation.py`: each flag actually disables
its subsystem at the entry point; run stamp reflects the config.

**Risks.** Toggling deep subsystems can crash the loop — every subsystem must
degrade gracefully when ablated (no-op, not exception). Build the flags to
fail-safe.

---

## Phase 8 — Structural tax (B5 / B6, ongoing)

Not a wiring fix; a standing risk register, worked continuously alongside P1–P7.

- **B5 — Integration surface (~507 modules / ~124k lines / one dev).** Keep the
  `make verify` gate green (memory `project_engineering_cleanup`); after each phase,
  run a full-loop staging run and diff the trace — integration failures show up only
  when it all runs together. Prefer landing P1–P7 in small, independently-verifiable
  slices.
- **B6 — Native learner scale + catastrophic forgetting.** The 4-layer nanoGPT caps
  the ceiling; the "interleave a little replay" in `read_a_book` is a band-aid over
  an unsolved problem. Track as research risk: (a) evaluate a larger native model or
  a pluggable provider (memory `project_desktop_app_progress` Group H), (b) measure
  forgetting explicitly with a held-out probe across training bouts, (c) treat any
  replay-ratio change as an experiment with the forgetting probe as its metric.

---

## The ten-round proof (definition of done for the whole plan)

Wire one complete circuit and show it **compounds**:

1. Orrin attempts a verifiable task and **checks** its own work (P3).
2. Ric **corrects** the result where the check can't (P2b).
3. Both signals **train** the persistent model (bandit + person model) **and** the
   native weights (P2a) — filtered by real effect (P1).
4. The long-term goal **carries the gap** into the next round (P4), with signals
   that **relax** so behavior stays varied (P5).
5. The lived surface + run stamp let us **watch** round-over-round improvement (P7).

Success = measurable improvement on the same task across **ten rounds**, visible in
the trace, reproducible under a stamped run config. That single compounding circuit
is the whole bet.

---

## Dependency order (build sequence)

```
P1 (effect-gated closure) ══► P3 (produce-and-check)   [HARD dependency, not loose:
      │  ships with its watchdog     gives understanding goals a closeable effect;
      │                              without P3 they only disengage]
      ├─► P4 (long-term drives, via goal_io gate)
P2 (graded signal→learners) — parallel with P1/P3 (train_on sampler + ToM correction)
P5 (signal decay) — TUNE existing machinery after a diagnosis pass, not a rebuild
P6 (veil) — extend the existing four membrane tests, parallel
P7 (lived surface + ablation) — after P1–P5 give it something real to show
P8 (structural) — continuous, under everything
```

Start with **P1 + its watchdog** (still the loudest bug), but land it **paired with
P3** — because reading records no effect, P1 alone makes pure "understand X" goals
un-closeable, so the two together are the smallest honest version of the through-line
fix. **P2a is more than a corpus tweak** (it changes `native_lm.train_on`'s sampler);
schedule it as its own slice, not a same-day add-on to P1.
