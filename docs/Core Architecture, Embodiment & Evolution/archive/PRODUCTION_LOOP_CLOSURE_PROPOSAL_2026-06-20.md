# Production Loop Closure — Reviewed Fix Proposal

> **IMPLEMENTATION STATUS (2026-06-23): code complete.** All fixes F0–F6 are
> implemented and tested; the 5.1 deterministic verification suite (tests #1–#10)
> passes, full suite green (1007 passed). What's built:
> - **F0** boot reachability invariant — `brain/loop/boot_checks._verify_production_capability`.
> - **F1** canonical `hydrate_goal_model` (`goal_comprehension.py`) at every commit
>   boundary (`goals/api`, `goal_io`, `goal_store`, `intrinsic_goals`).
> - **F2** structured plan actions + `brain/agency/compose_section.py`; `recognise_step_action` prefers `action.function`.
> - **F3** deliberate handoff (`_needs_deliberate_action`) + bounded recruitment (`selection/candidates`, `score_setup`).
> - **F4** making-goal path + **tier-3 artifact re-use credit** (`effect_ledger.note_artifact_use`/`drain_pending_reuse`, `finalize._pay_artifact_reuse`).
> - **F5** `leave_note` seed-provenance gate (rejects path/lock/noise; refuses boilerplate when a goal needs a real artifact).
> - **F6** durable per-cycle telemetry → `brain/data/production_loop.jsonl` (`finalize._emit_production_telemetry`).
>
> **Remaining (runtime, not code):** §5.2 staged smoke run and §5.3 autonomous demo
> run — these require actually running Orrin and reading `production_loop.jsonl` +
> `effect_ledger.jsonl` from the run archive; they are the next verification step.

**Date:** 2026-06-20
**Status:** IMPLEMENTED (code + 5.1 tests) — runtime demo runs 5.2/5.3 pending
**Evidence base:** `docs/Behavioral Evaluation & Runtime Diagnostics/demo_runs/2026-06-19-run/`, archived runtime state at `brain/data/_archive/snapshot_20260619_081225_pre_reset/`, and source inspection on 2026-06-20
**Scope:** goal creation/commit hydration, cognition registration, structured plan execution, deliberate-action handoff, `leave_note` provenance, and persistent telemetry
**Related:** [[GOALS_AND_UNDERSTANDING_FIX_PROPOSAL_2026-06-20]], `project_reward_denominator`, `project_binding_workspace`, `project_explore_exploit_value`

---

## 0. One-line statement

The 2026-06-19 life did prove that the effect ledger honestly rejected 146 worthless `note_novel` effects, but it did **not** prove that a fully comprehended production goal was merely losing action competition. The archived runtime shows a more basic integration failure: `compose_section` was absent from the persisted cognition manifest, the committed goal lacked the comprehension/production fields consumed by the lens, and the Executive's plan router could not map a production step to `compose_section`. The sound fix is therefore to close the **representation → plan action → deliberate execution → effect** chain and verify each boundary at runtime, rather than hard-routing around the selector.

---

## 1. What the run actually proved

The reliable findings are:

- The life ran for 11,633 cycles and shut down cleanly.
- The run reports contain 146 effect rows, all `note_novel`, all with `novelty = 0.0` and `significance = 0.0`.
- The four aspiration summaries remained at 0%.
- The archived `decision_stats.json` has no `compose_section` entry.
- The archived `cognitive_functions.json` also has no `compose_section` entry.
- The archived committed goal exists, but has no `grounded_parts`, `definition_of_done`, `requires_artifact`, or `tracked_work`.
- The archived final context contains a committed goal:

  `Open question: Is this goal really mine, or have I inherited it?`

- The Executive step router knows research/search/note actions, but not `compose_section`; its generic `write`/`record` rule routes to `leave_note`.

This supports the conclusion that the production loop did not close. It does **not** support the narrower claim that a correctly registered, comprehended `compose_section` action was present for 11,633 cycles and simply lost to a weak `+0.18` prior.

### Claims from the first draft that must be retired

1. **“`compose_section` was structurally reachable but underweighted.”**
   Not demonstrated. It was absent from the archived persisted candidate manifest.

2. **“The active goal was comprehended but the lens was dark.”**
   Not demonstrated. The archived committed goal did not carry the comprehension fields.

3. **“The loop clears and re-derives `committed_goal` every cycle.”**
   Incorrect. `ORRIN_loop.py` replaces the slot when the GoalsAPI returns goals, but does not clear an existing slot when the pull is empty. Several pursuit/completion paths can clear it, but commitment coverage must be measured rather than inferred.

4. **“All 146 effects correspond to 146 deliberate `leave_note` selections.”**
   The archived decision stats record only 19 `leave_note` selections. All 146 effects were `note_novel`, but exact invocation provenance needs instrumentation.

5. **“Production failure was the sole cause of terminal allostatic load.”**
   The relationship is mechanically plausible and correlated, but the run does not isolate causality. Production relief is one expected discharge path, not the only possible contributor.

---

## 2. The verified integration defects

### D1 — Runtime reachability was not established

`compose_section` exists in source and is hot-registered by `_boot_context`, but the archived `cognitive_functions.json` from the run does not contain it. Both the selector and `discover_callable_maps()` are filtered by that persisted manifest.

Source presence is therefore insufficient evidence that an action is selectable. A production function is runtime-reachable only when all of these agree:

1. it is callable in `COGNITIVE_FUNCTIONS`;
2. it is present in `cognitive_functions.json`;
3. it survives `_is_selectable_name` and `_is_dispatchable`;
4. it appears in the selector's action pool or a recognized Executive handoff;
5. the dispatcher can supply its arguments.

There is currently no boot invariant that checks this chain.

### D2 — Comprehension is lost on a direct intrinsic commitment

Goal comprehension is run in `GoalsAPI.create_goal`, `goal_io.sync_proposed_goals`, and the v1 `add_goal` path. However, `generate_intrinsic_goals()` can directly create `context["committed_goal"]` through `_build_committed_goal()`.

`_build_committed_goal()` copies title, description, milestones, `requires_artifact`, and deadline, but does not call `comprehend_goal()` and does not carry:

- `grounded_parts`
- `definition_of_done`
- comprehension-derived `plan`
- `tracked_work`
- an explicit production action/artifact strategy

This is the most direct explanation for the archived shallow committed goal. The goal may later be synchronized to another store, but the immediately active representation—the one read by the lens and producer—is already incomplete.

There are also legacy/existing goals in the stores that predate comprehension. They need one-time lazy hydration when they become commit candidates; otherwise only newly created goals benefit.

### D3 — Plans describe production in prose but do not encode a production action

The plan schema is currently treated mainly as:

```json
{"step": "Write a clear synthesis", "status": "pending"}
```

`recognise_step_action()` then infers a function from text. Its generic `write`/`record`/`note` rule maps to `leave_note`. `compose_section` is absent from `_KNOWN_FN_NAMES` and from the production intent rules.

This makes the wrong action the default motor program for written production. It also makes action semantics depend on wording: changing “compose” to “write” can change the selected tool.

The goal model needs an explicit action contract:

```json
{
  "step": "Draft the thesis section",
  "status": "pending",
  "action": {
    "function": "compose_section",
    "artifact_kind": "tracked_work",
    "section": "Thesis"
  }
}
```

Text inference should remain a backward-compatible fallback, not the authority.

### D4 — The existing Executive handoff can support production, but is not wired for it

The architecture already has the correct control path for a substantial generative act:

1. The Executive inspects the next plan step.
2. `execute_step_action()` refuses a non-procedural action in `_procedural_only` mode.
3. `pursue_committed_goal()` records `_needs_deliberate_action`.
4. The deliberate selector receives bounded recruitment toward that function.
5. Threat/safety arbitration still runs after analytical selection.

This is safer and more coherent than a hard `if artifact_goal: return compose_section` rule.

What is missing:

- structured action extraction from the plan;
- `compose_section` runtime registration/candidate integrity;
- a reliable deliberate boost that does not require an unrelated impasse threshold before an explicitly pending action becomes viable;
- protection against epsilon exploration replacing an explicit planned handoff indefinitely;
- progress synchronization after the deliberate function succeeds.

`compose_section` already marks its pending plan step complete and persists the goal, so it can participate in this handoff once the preceding boundaries are fixed.

### D5 — Output origination exists, but commitment must preserve its semantics

`intrinsic_goals._making_goals()` already creates artifact-gated `output_producing` goals such as:

> Turn what I know about X into a written synthesis

Aspiration pressure and proposal competition also exist. The proposal should not add another goal generator.

The defect is that the winning proposal's production semantics can be lost when `_build_committed_goal()` creates the active copy. In addition, a “written synthesis” is not classified as `tracked_work` by the current long-form keyword set, so comprehension needs an explicit artifact strategy rather than relying only on nouns such as “book” or “paper.”

### D6 — The note fallback admits low-quality provenance

`leave_note()` scans recent long memory for textual markers such as `"from searching"` and `"[world_perception]"`, then uses the payload as a motive seed. This can admit filesystem/path output and `.lock`/`data` fragments.

The run supports the claim that note content was junk-sourced. However, the repair should use structured provenance and content-quality checks, not only a blacklist of filenames.

### D7 — The proposed verification reads telemetry that is not persisted

`_goal_lens_telemetry` currently lives in `context`. The first draft's command:

```bash
grep -oE "active_cycles[^,]*" brain/data/*goal_lens*
```

does not correspond to an existing durable file.

Commitment coverage, lens coverage, explicit handoffs, and production attempts must be written to an existing durable telemetry stream or a dedicated bounded record before a demo run can verify them.

---

## 3. Revised fix

### F0 — Add runtime integration invariants

At boot, verify and emit a visible failure if a required production function is not reachable through the actual runtime surfaces.

For `compose_section`, assert:

- callable registry membership;
- persisted manifest membership after boot registration;
- dispatchability;
- selector membership when used as a deliberate action;
- capability metadata exists;
- a dry plan-action resolution maps `{"function": "compose_section"}` to the callable.

Do not silently continue with a “wired” claim if any check fails. The system may continue fail-safe, but telemetry must report `production_capability_unreachable`.

**Acceptance:** a boot test proves `compose_section` is in the post-boot registry, manifest, deliberate candidate pool, and plan-action resolver.

### F1 — Create one canonical goal-model hydration boundary

Add one idempotent helper, conceptually:

```python
hydrate_goal_model(goal, context=None, *, persist=False) -> goal
```

It should:

- preserve existing progress/history;
- call comprehension only when required fields are missing or stale;
- populate `grounded_parts`, `definition_of_done`, milestones, and plan;
- assign an explicit artifact strategy:
  - `tracked_work` / `compose_section` for synthesis, essay, report, guide, paper, manuscript, chapter, or other cumulative prose;
  - the appropriate existing producer for code, message, or one-shot note goals;
- persist the hydrated model once, not recompute it every cycle.

Call it at every boundary that can create an active goal:

- `GoalsAPI.create_goal`;
- `goal_io.sync_proposed_goals`;
- `goal_io._goal_to_v1` for legacy v2 goals missing comprehension;
- `intrinsic_goals._build_committed_goal`;
- fallback/boot goal adoption;
- lazy migration when an old live goal first becomes committed.

This must be the only authority for deciding what artifact action satisfies the goal.

**Acceptance:** every committed artifact goal has non-empty `definition_of_done`, `grounded_parts`, and an explicit production action before the lens is applied.

### F2 — Make plan actions structured and executable

Extend plan steps with an optional `action` object. Update the plan readers to prefer it:

```python
fn = step["action"]["function"]
```

Only when structured action metadata is absent should `recognise_step_action(step_text)` infer from prose.

For tracked prose:

- comprehension emits one or more `compose_section` steps;
- section identity is stable;
- completed section IDs are persisted;
- rerunning a completed step is idempotent;
- the effect ledger's required-section target remains authoritative for goal completion.

For backward compatibility:

- add `compose_section` to explicit recognized function names;
- make “draft/compose a section/chapter/synthesis” map to `compose_section`;
- keep generic “leave/send a note” mapped to `leave_note`;
- do not route every occurrence of “write” to `compose_section`.

**Acceptance:** a hydrated making goal produces a next pending step whose resolved function is exactly `compose_section`, without relying on fuzzy semantic matching.

### F3 — Use the existing conscious-action handoff; do not hard-override selection

Keep `compose_section` non-procedural unless a separate safety review explicitly approves background autonomous drafting. The Executive should defer it and set:

```python
goal["_needs_deliberate_action"] = "compose_section"
```

Then strengthen the existing deliberate recruitment path:

- an explicit pending action gets a bounded additive priority even when `impasse_signal <= 0.3`;
- impasse may amplify the priority, but is not required to make the action reachable;
- genuine threat/safety arbitration remains later in the selection path and can pre-empt it;
- epsilon exploration should not displace an explicit pending planned action on every attempt;
- repetition/rut protections still apply after a successful production step.

This is an ignition path in the functional sense—an explicit plan recruits its required action—but it remains corrigible and compatible with the selector's additive design.

**Acceptance:** in a deterministic selector test, a committed tracked-work goal with a pending `compose_section` handoff ranks that function above unrelated wandering actions under ordinary affect, while a threat proposal can still win.

### F4 — Preserve output-goal origination semantics through commitment

Do not add a new originator. Verify the existing making-goal path end to end:

```text
starved output aspiration
  → _making_goals candidate
  → proposal competition
  → committed hydrated goal
  → explicit compose_section plan action
```

Add observability for where this chain stops:

- making candidates generated;
- making candidate selected/rejected;
- committed goal's `driven_by` and `serves`;
- artifact strategy assigned;
- production action handed off;
- effect credited/rejected and why.

**Acceptance:** a synthetic starved-output scenario commits an `output_producing` goal whose active copy still has `requires_artifact`, `definition_of_done`, and a production action.

### F5 — Make `leave_note` a safe short-form fallback

When a committed goal calls for a short note:

1. seed from the hydrated goal's grounded parts and criterion being served;
2. include the owning goal ID through the existing expression motive;
3. prefer structured long-memory provenance (`event_type`, origin/tool metadata);
4. reject path listings, lock files, empty delimiter output, and low-information token sets before composition;
5. if no qualifying seed exists, emit no artifact rather than another boilerplate note.

`leave_note` must not substitute for a tracked-work action. A tracked-work plan step should resolve only to `compose_section`.

**Acceptance:** path/lock fragments cannot become a note seed, and short-form notes linked to a goal pass goal-alignment scoring only when their content is relevant.

### F6 — Persist production-loop telemetry

Add durable, bounded fields to the existing telemetry/history stream:

- `committed_goal_present`
- `committed_goal_id`
- `goal_model_hydrated`
- `goal_lens_active`
- `goal_lens_top_signal_relevance`
- `goal_lens_retrieval_mean_relevance`
- `pending_production_action`
- `production_handoff_count`
- `production_attempt_count`
- `production_success_count`
- rejection reason from the effect ledger

Do not create another competing goal summarizer. Extend an existing telemetry owner.

**Acceptance:** commitment and lens coverage can be computed from a run archive without reading transient process memory.

---

## 4. Sequencing

| Phase | Change | Why first |
|---|---|---|
| **C0** | Runtime reachability invariant and tests | Prevent another run from testing code that is not actually in the candidate/execution surfaces |
| **C1** | Canonical goal hydration at every commitment boundary | Gives the lens and plan executor the representation they require |
| **C2** | Structured plan actions and `compose_section` resolution | Connects comprehension to a concrete motor program |
| **C3** | Bounded deliberate-action recruitment | Makes the planned action fire without bypassing safety arbitration |
| **C4** | Making-goal end-to-end test | Verifies aspiration pressure can reach a real producer |
| **C5** | `leave_note` provenance hardening | Stops junk while preserving a valid short-form fallback |
| **C6** | Durable telemetry and staged demo | Makes the next verdict evidence-based |

Do not tune global selector weights before C0–C2 pass. The archived run cannot distinguish a weak score from an absent candidate and an unhydrated goal.

---

## 5. Verification

### 5.1 Pre-run tests

Required deterministic tests:

1. Post-boot registry/manifest/candidate integrity for `compose_section`.
2. Direct intrinsic commitment preserves comprehension and artifact strategy.
3. Legacy goal hydration is idempotent and preserves progress.
4. Structured plan action resolves to `compose_section`.
5. Executive defers `compose_section` to the deliberate lane.
6. Deliberate selector recruits the pending function without bypassing threat arbitration.
7. One successful section writes one tracked file, one non-zero effect, and one completed plan step.
8. Duplicate or off-goal sections earn no credit.
9. A multi-section goal does not complete before its required section target.
10. Filesystem/path noise cannot seed `leave_note`.

### 5.2 Staged smoke run

Use a known, bounded test goal rather than waiting for stochastic origination:

> Write a three-section synthesis of what I know about emergence.

Pass criteria:

- committed goal is hydrated before cycle selection;
- lens active on at least 80% of non-rest cycles while the goal is live;
- an explicit `compose_section` handoff appears;
- `compose_section` executes at least once;
- `brain/data/tracked_work/*.md` exists;
- at least one `tracked_work` row has `novelty > 0` and `significance > 0`;
- the same section is not credited twice;
- the goal remains open until its required section count is met;
- a simulated threat can still pre-empt production.

### 5.3 Autonomous demo run

Only after the smoke run passes, test the intrinsic chain. Success requires more than “one non-zero row”:

- at least one `output_producing` candidate is generated;
- at least one is committed with its production model intact;
- production attempts have explicit goal/action provenance;
- credited effects are not path noise or duplicates;
- aspiration contribution moves only after qualifying evidence;
- commitment/lens coverage is measurable from durable telemetry.

Use Python JSON parsing for verification. Do not use `grep -c compose_section decision_stats.json`; `decision_stats.json` is an object keyed by function name, and Executive-lane actions may be recorded in cognition history rather than the deliberate decision counter.

---

## 6. Risks and constraints

- **Hard override risk:** directly returning `compose_section` from `select_function` would bypass normal score competition and weaken the architecture's additive/corrigible discipline. Rejected.
- **Double execution risk:** if `compose_section` becomes both procedural and deliberately selectable, the Executive and conscious lane can execute the same step. Preserve one owner and idempotent section IDs.
- **Comprehension churn:** hydrating every cycle would repeatedly rewrite plans. Hydrate once, version the model, and preserve progress.
- **Artifact farming:** explicit production routing must continue through novelty, structural significance, goal alignment, and required-section gates.
- **Wrong producer risk:** not every artifact goal is prose. The hydrated model must choose a producer by artifact kind instead of routing all output goals to `compose_section`.
- **False commitment diagnosis:** a single conscious-stream phrase cannot establish that the slot was empty. Measure the slot directly each cycle.

---

## 7. Final assessment

The proposal's high-level objective is sound: the comprehension-to-production loop is not closed. Its original causal account and F1/F2 remedies were not sound enough to implement safely.

The archived evidence points to boundary failures, not merely weak motivation:

```text
making proposal
  ─X→ hydrated committed representation
  ─X→ explicit production plan action
  ─X→ runtime-reachable compose_section
  ─X→ deliberate handoff
  ─X→ qualifying effect
```

Fix and test those boundaries in order. Once they pass, selector-weight tuning becomes a legitimate empirical question. Before they pass, increasing priority or adding a hard route would mask the integration defects and make the system harder to reason about.

---

*Reviewed against archived runtime state and current source on 2026-06-20. This document revises the proposal only; it does not claim the closure changes are implemented.*
