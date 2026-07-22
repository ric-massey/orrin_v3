# Run 12 Implementation Plan — verified build order (2026-07-21)

Single home for two inputs that turned out to describe one problem:

1. **The Run 11 re-test gate** — the 8-item fix list from
   `demo_runs/2026-07-21-run/DEMO_RUN_2026-07-21.md §5` and the Run-12 gate
   paragraph in `NEXT_RUN_TESTS.md`.
2. **`DATAFLOW_AUDIT_2026-07-20.md`** — the read-only "trace the pipes, not the
   warehouses" pass (12 ranked wires + 8 addenda). Its substance is folded in
   below; the standalone file is retired now that this doc carries it.

The audit is not a separate workstream from the gate — its items 1–4 and 11 **are**
Run-12 gate item 2 ("un-starve the daemon feed"), traced to source. The gate says
*what must be true*; the audit says *which wire is cut*. This doc merges them into
build order + code targets.

---

## Governing design decision (2026-07-21): growth's currency is **structured knowledge**, not prose

The audit's Addendum 1 concluded the Growth axis is unreachable symbolic-only
because memos are extractive prose stitches and Orrin can't write an essay
offline. That framed Run 12's keystone decision as **"LLM on vs. off."**
**That is a false choice**, and the code confirms why: the three organs that gate
growth are all **prose-denominated**, and nothing else in the loop is.

- `epistemic_closeout.score_answer` (`:115`) requires "substantive **prose** beyond
  the title" (`_MIN_ANSWER_CHARS = 200`) — a symbolic finding checked against
  telemetry can never satisfy it.
- reuse (`goals/handlers/research.py:_find_prior_memo`) keys on content-word
  overlap between memo `.md` files — prose.
- the originality veto measures **copy-fraction of prose**.

Everything *upstream* of those gates is already structured and already symbolic:
`prediction_engine` (make → `resolve_prediction(correct, mismatch_score)` →
`update_domain_stats`), `autonomous_experiment` (`prediction_test`/`causal_probe`
→ `record_experiment_result` → causal-graph `_ue(...)` + rule crystallization),
`ground_truth` (per-rule grounding score against real outcomes), `causal_graph`,
`concept_formation`, `rule_engine`. The research handler *already* writes
structured JSON artifacts (`_queries.json`, `_search.json`, `_docs.json`,
`_summary_meta.json`) beside the prose memo.

**Decision: redefine the close-out / reuse keystone to accept structured symbolic
artifacts as first-class research products, and run the Run-12 acceptance life
symbolic-only.** A "research product" is not an essay; it is a set of extracted
**propositions** — entities, relations, a testable prediction, a confidence, and
source pointers. **Answered** means a produced structured claim names the gap's
subject and (where the question is telemetry-checkable) was **scored against
Orrin's own observation next cycle** — prediction made → prediction scored → claim
promoted or demoted. **Reuse** means a later goal building on prior *structured*
claims: extending a causal chain, testing a stored prediction, or merging two
concept clusters. **No sentence generation anywhere in that loop.**

The prose memo becomes a **rendering layer** on top of the structured claim —
nice-to-have, LLM- or native-LM-optional — never the thing growth is scored on.
This is the version where Run 12 proves the mind Orrin actually has, instead of
proving that an external LLM can write memos. It is more work than flipping the
LLM on (it changes what `stamp_closeout`, the reuse detector, and the veto look
for), and it snaps together with the goal-grounding argument: "Understand history
more deeply" is prose-only and forces the LLM dependency; **"Characterize what
makes my RSS climb" is answered in structured claims checked against his own
telemetry** — real compression of experience into reusable structure, achieved
fully symbolically.

This decision **retires Slice 1E's "LLM mode" question** and **reshapes Slice 1C**
(the keystone) and **Slice 1B.4** (reuse) below. LLM-assisted remains an optional
*rendering* mode, not a growth prerequisite.

Every target below was verified against the working tree on 2026-07-21 (build
`423e201`, the Run-11 build) — file paths and line anchors are real, re-grepped,
not carried from the audit prose. Where the audit's anchor drifted, the corrected
line is marked **[GT]**.

**Scope split, load-bearing:**
- **Layer 1 (Run 12 acceptance)** — make the goal funnel *completable and honest*
  so the gate can pass. Ships first. Mostly wiring/bug/threshold fixes on organs
  that already exist; the one genuinely new piece is Slice 1C's structured research
  product (`claims.json`) + the re-keyed close-out/reuse gates — built on the
  already-live `concept_formation`/`causal_graph`/`prediction_engine` extractors,
  not new intelligence.
- **Layer 2 (post-gate cognition)** — the human-shaped mechanisms the audit found
  *missing* (prospection, passion/anger, source epistemology, the `origin` field).
  These are new capability, not gate-passers. **Layer 2 on top of an unproven
  funnel is new calibration debt** — it does not ship until Layer 1's gate is green.

---

## 0. The diagnosis in one picture — the five-pinch funnel

Run 11 (and Run 10 before it) failed Feed + Growth for one connected reason: the
lane that does the real work (daemon-lane research → memos → reuse → answered
close-outs → growth ladder) is pinched in five independent places, each of which
alone zeroes the output. Fixing four of five still yields zero.

```
  generate_intrinsic_goals
        │  PINCH 1 — one goal per pass (audit 1)
        │  PINCH 2 — coverage floor steers the single pick away from research (audit 2)
        │  PINCH 3 — bootstrap fires only when no goal committed; bandit path habituated ×3 (audit 3)
        ▼
  proposed_goals ──► goal_io.sync ──► daemon WAL      (handoff is NOT clamped — scope 5)
        ▼
  daemon runner ──► research handler ──► claims.json (structured) + memo.md (rendering)
        │  PINCH 4 — reuse credit keys on PROSE overlap between memos (audit 4)
        │           → re-key to STRUCTURED-claim reuse (extend chain / test prediction / merge clusters)
        │  QUALITY CAP (prose only) — offline stitch, ~250-token vocab (Addendum 1)
        │           → dissolved: structured claims aren't prose, veto re-scoped
        ▼
  GoalFinished (daemon lane)
        │  PINCH 5a — stamp_closeout has ZERO daemon-lane call sites (audit 11)  ◄── keystone
        │  PINCH 5b — score_answer requires 200 chars of PROSE (closeout:115)   ◄── keystone
        │           → "answered" = structured claim names subject AND (if telemetry-checkable) scored vs ground_truth
        ▼
  epistemic_closeout ──► growth_ladder.note_verified_success ──► rung climb
        (never fires: growth_ladder.json has never existed in any life)
```

**The currency change moves the keystone from pinch 5a alone to 5a + 5b:** wiring
the daemon-lane stamp is necessary but insufficient while `score_answer` demands
prose. Both land together in Slice 1C.

**Scope-5 verdict (confirmed in code):** the brain→daemon handoff is *not* the
clamp. `goals/api.py:create_goal` upserts unconditionally; `research` is in
`_EXECUTABLE_KINDS` (`brain/goal_io.py:25`) and `sync_proposed_goals` submits it.
Goals that reach `proposed_goals` with an executable kind *do* reach the WAL. The
starvation is entirely **upstream, in generation volume** (pinches 1–3) and
**downstream, in the close-out wire** (pinch 5). Fix both ends or the middle
never gets exercised.

---

## 1. Ground-truth anchor table (re-verified 2026-07-21)

| Ref | File:line | State on `423e201` |
|---|---|---|
| Single-pick generation | `brain/cognition/intrinsic_generators.py:780` `_varied_symbolic_goal`, `return chosen` at `:883` | Builds a rich pool, returns **one** goal |
| Coverage-floor diversion | `intrinsic_generators.py:250,845` `objective_pressure(...)` + floor block ~`:855` | Single pick diverted to most-starved aspiration |
| Bootstrap-only-when-idle | `brain/loop/sense.py:272` (`if not bound_goal`) + `brain/cognition/intrinsic_goals.py:261-268` | Fires only when no goal committed; bandit path cooldown ×3 |
| Handoff (NOT clamped) | `goals/api.py:create_goal` (unconditional upsert); `goal_io.py:25` `_EXECUTABLE_KINDS`; `goal_io.py:493` submit | Confirmed open |
| Reuse credit gate | `goals/handlers/research.py:296-306` `mark_reused_path`; `_find_prior_memo` `:86` | **Prose:** ≥2 content-word overlap between memo `.md` files |
| Reuse payout | `brain/loop/finalize.py:49-81` `_pay_artifact_reuse` | Consumer exists; starved of input |
| **Close-out stamp (keystone 5a)** | `brain/cognition/epistemic_closeout.py:179` `stamp_closeout`; call sites **only** `goal_closure.py:227` + `brain/loop/maintenance.py` | **Zero call sites in `goals/`** |
| **Answer scorer (keystone 5b)** | `epistemic_closeout.py:115` `score_answer`; `_MIN_ANSWER_CHARS = 200` `:35` | **Prose:** requires "substantive prose beyond the title" |
| Structured research artifacts | `goals/handlers/research.py` `_write_json` at `:199,232,260,330` | Already emits `_queries/_search/_docs/_summary_meta.json` — the hook for `claims.json` |
| Prediction score loop | `brain/symbolic/prediction_engine.py:68` `make_symbolic_prediction`, `:194` `resolve_prediction(correct, mismatch_score)`, `:114` `update_domain_stats` | Built, live — made→scored→ledgered |
| Experiment → causal/rule | `brain/symbolic/autonomous_experiment.py:45` `run_experiment_cycle`, `:290` `record_experiment_result` → `_ue(cause,effect,confirmed=…)` + `_try_crystallize_from_gap` | Built, live — predict-then-check symbolically |
| Grounding ledger | `brain/symbolic/ground_truth.py:54` `record_action_result`, `:99` `grounding_score` | Per-rule score vs real outcomes |
| Growth ladder feeders | `brain/cognition/growth_ladder.py:54` `note_verified_success`; fed only from `epistemic_closeout.py:201` + `quality_standard/gate.py:269` | `brain/data/growth_ladder.json` has never existed |
| Daemon GoalFinished | `goals/runner.py:541,614` (`status=Status.DONE`, `_emit_goal_event("GoalFinished", …)`) | The hook point for pinch 5 |
| Shutdown | `brain/loop/services.py:96` `shutdown_loop` → `session_epilogue`; lifetime in `brain/runtime_lifetime.py` | Hang after epilogue at natural death |
| Avoidance breaker | `brain/cognition/metacog_analyze.py:151` debt counter; `:165` `_try_suppress`; `brain/think/pick.py:287`; `tag_sets.py:59` | Built, wired, **never fired** |
| Offline stitch marker | `goals/handlers/research.py:429` header; `brain/cognition/quality_standard/originality.py:40` `_OFFLINE_STITCH_MARK` | Veto correctly holds stitched memos |
| Native LM (not a fix) | `brain/data/language/native_lm.pt` (37 MB); gate `brain/cognition/language/voice.py` `lm_ready()` ≤120 ppl | ~250 real merges, self-referential vocab; not wired to synth |

---

## Layer 1 — Run 12 acceptance (build order)

Slices are `make verify`-gated. A ~2k-cycle smoke life runs after Slice 1B and
again after Slice 1C before the full acceptance life. Each row lists the gate item
it satisfies (verdict §5 number `[V#]`, audit item `[A#]`).

### Slice 1A — the lifecycle bug (P0, blocks the acceptance life itself) `[V1]`

The shutdown-hang is not a dataflow item — it's why the last hour of Run 11 was a
stall→kill→relaunch loop producing zero cycles. It must land first or the
acceptance life can't end cleanly.

| # | Target | Change | Observable / test |
|---|---|---|---|
| 1A.1 | `brain/loop/services.py:96` `shutdown_loop` + the death path caller | After death artifacts (epilogue, final reflection, death closing) are written, the process must **terminate** (return through the loop's exit, not block). Wrap `session_epilogue` teardown so no post-artifact step can hang the exit. | Natural lifespan death → **1 clean exit, 0 cycle-stall kills** |
| 1A.2 | `brain/runtime_lifetime.py` boot path | A relaunch whose `start_time` lifespan has **already elapsed** must **start a fresh life** (new `start_time`), not re-enter the death path. | `run_history` shows **no born-dead relaunch** after a natural death |
| 1A.3 | `tests/` (new regression) | Boot with a `runtime_lifetime.json` whose lifespan is already elapsed → assert rebirth (fresh start_time), not death-path re-entry. And a shutdown test that the death path returns/exits within a bound. | Test green |

### Slice 1B — un-starve the daemon feed (P0, the #1 finding, 3rd run) `[V2][A1,A2,A3,A4]`

This is the audit's highest-leverage cluster. **Diagnose-then-fix, in this order** —
the audit already named the load-bearing cause (correct-but-unopposed brain-lane
preference), so the instrument confirms it rather than hunts blind.

| # | Target | Change | Observable / test |
|---|---|---|---|
| 1B.0 | `brain/utils/handoff_log.py` (exists; `log_handoff` at `goal_io.py:267,415,454,500,517`) | **Instrument first.** Confirm `logs/handoff_log.jsonl` records `decision`+`kind` per generation/sync. No code change if already complete — just verify the smoke life emits it. | Smoke life: `queued` research counts vs `generate_intrinsic_goals` invocations, quantified |
| 1B.1 `[A2]` | `intrinsic_generators.py:840-883` `_varied_symbolic_goal` | **The surgical point.** Let the pass emit the research subset of `pool` (or top-K by gap score) **in addition to** the coverage-floor pick, so a research candidate is proposed whenever one exists — independent of which aspiration is starved. Floor still guarantees make/connect their share. | `proposed_goals` carries a `kind:"research"` entry after a pass that previously produced a generic/introspective goal |
| 1B.2 `[A1]` | same fn — the `return chosen` single-pick contract | Return the batch (floor pick + research candidate) rather than one goal, adjusting the caller in `intrinsic_goals.py` to append all. One generation pass ≠ one goal. | Per-pass emitted-goal count > 1 when pool has research material |
| 1B.3 `[A3]` | `intrinsic_goals.py:261-268` habituation cooldown ×3 + `sense.py:272` bootstrap-only-when-idle | **De-clamp per the NO-CLAMPS directive** (memory `unopposed_force_principle`): the sub-0.45-value ×3 cooldown stretch + pool-depth ×3 backoff are scar tissue throttling research creation under incumbency. Loosen so research-goal creation isn't gated to zero by a committed monopoly. Do **not** add a new clamp — oppose, don't remove. | Daemon WAL: **no silence > 30 min** across the acceptance life (Run 11: terminal 12.3 h) |
| 1B.4 `[A4]` | `goals/handlers/research.py:86` `_find_prior_memo` → new structured-claim reuse detector | **Re-key reuse to structured claims** (see 1C.4): a later goal reuses when it extends a prior goal's causal chain, tests a prior stored prediction, or merges concept clusters — not when two memos share content words. Prose overlap stays as a weak fallback. | `effect_ledger` shows **≥1 structured reuse row** in the smoke life; **≥8** in the acceptance life |

**Gate observables (verdict §5.2):** no WAL silence > 30 min; research-kind
`state.jsonl` records **≥ 20** (Run 11: 4); **reuse ≥ 8** (three straight runs: 0)
— now reachable via structured reuse, symbolic-only.

### Slice 1C — the structured-knowledge keystone + honesty seams `[V3][V7][A11]` + `[V8]`

This is where the currency decision lands. Two pinches (5a wiring, 5b prose gate)
plus the structured product schema, reuse re-key, and veto re-scope. Without all
of 1C.1–1C.4, 1B buys volume with still-zero growth. **This slice is the extra
work the structured-knowledge path costs versus flipping the LLM on — and the
reason Run 12 proves the mind Orrin actually built.**

| # | Target | Change | Observable / test |
|---|---|---|---|
| 1C.0 | `goals/handlers/research.py` (new `claims.json` beside the existing `_write_json` artifacts at `:199-330`) | **Define the structured research product.** A `claims.json`: `{entities[], relations[], prediction:{claim, checkable_against, confidence}, sources[]}`. Extracted symbolically from the fetched docs via the existing `concept_formation` / `causal_graph` extractors — no sentence generation. The memo `.md` stays as an optional rendering. | Every completed research goal writes a `claims.json` with ≥1 relation or ≥1 prediction |
| 1C.1 `[A11]` | `goals/runner.py:541,614` (`GoalFinished` emit) → `brain/cognition/epistemic_closeout.stamp_closeout` | **Pinch 5a.** Stamp close-out at **daemon-lane completion**. **Membrane note [GT]:** `stamp_closeout` lives in `brain/`; the runner is in `goals/` — do **not** import brain cognition into the daemon. Route it through the reconciliation the brain already runs when a daemon goal returns DONE (`goal_io._reconcile_open_v2_into_v1` / the completion sync), stamping there on the brain side. | Daemon-completed understanding goals carry `question` + `answered` in `comp_goals.json` |
| 1C.2 `[V3][A11]` | `brain/cognition/epistemic_closeout.py:115` `score_answer` + `:35` `_MIN_ANSWER_CHARS` | **Pinch 5b — the prose gate.** Re-define `score_answer` to accept a structured artifact: **answered iff** the goal's `claims.json` carries a claim whose entities/relations name the question's subject **AND** (when the question is telemetry-checkable) a `prediction` that was **resolved against ground truth** — i.e. `prediction_engine.resolve_prediction` fired with `correct=True` (or `mismatch_score` low) next cycle. Prose length stops being the criterion; a rendered memo can still supply the `answer` excerpt if present. | An understanding goal answered by a scored prediction (0 prose) stamps `answered=True`; a stitch-only memo with no claim stamps `answered=False` |
| 1C.3 `[V7]` | `brain/cognition/planning/goal_closure.py:227` + `epistemic_closeout.py` annotation path | Close the **annotation-path leak**: F-LN4b rung-1 blocks 17 satiety closes but 29 "closed but question NOT answered" still slip through an annotation-only path. Rung-1 must govern **all** understanding closes — block or spawn a follow-up carrying the question, never annotate-and-close. | **Zero** `answered=False` satiety closes without a block or follow-up |
| 1C.4 `[A4]` | new structured-reuse detector replacing prose `_find_prior_memo` (`research.py:86`); credit via existing `mark_reused_path`/`_pay_artifact_reuse` | **Structured reuse.** A goal reuses when it (a) extends a prior goal's causal chain (`causal_graph` edge whose cause/effect a prior `claims.json` introduced), (b) tests a prior stored `prediction`, or (c) merges two concept clusters (`concept_formation`). This is the trace a passion leaves — see Layer 2.2; co-design the anti-monopoly interaction. | ≥1 reuse row cites a prior goal's structured claim by id, not word overlap |
| 1C.5 `[A-Add1]` | `brain/cognition/quality_standard/originality.py` veto | **Re-scope the veto.** Copy-fraction-of-prose does not apply to extracted propositions; a structured claim is derivation, not stitch. Exempt structured products from the prose veto; add a structured analog only if needed (a claim that merely restates a single source's assertion, un-tested, un-linked). | Structured-product exemplar promotion no longer 100% veto-held (Run 11: 21/21 held) |
| 1C.6 `[V8]` | `brain/goal_io.py` `_reconcile_open_v2_into_v1` (`:353-360`) + the title-match fallback (`:200-203`) | Kill the last store-desync seam: 1 orphan-RUNNING v2→v1 repair remained in Run 11. Prefer id-first reconciliation; the title-matching fallback is the residual fork window (scope-9 residual risk). | `store_desyncs_repaired` = 0 |

**Goal-shape corollary (moves into 1B generation):** for the structured path to
have telemetry-checkable questions to answer, `_varied_symbolic_goal` should mint
**characterization goals** ("Characterize what makes my RSS climb") alongside the
"Understand X" template — questions whose answer is a prediction checkable against
Orrin's own telemetry next cycle. This is the concrete, symbolic form of the
question-shaped-titles fix (audit Addendum 2 item 3 / F-LN4c) and the grounded
close-out keystone from `QUALITY_GROUNDING_DESIGN_2026-07-18.md`.

### Slice 1D — the skeptic reds (persist from Run 9/10/11) `[V4][V5][V6][A12]`

These are not dataflow items — they are reward/selection pathologies the last
three verdicts flagged and the audit corroborated live (item 12).

| # | Target | Change | Observable / test |
|---|---|---|---|
| 1D.1 `[V4]` | the block path for `decide_to_write_code` (blocked 1,967×, EMA 0.576, 22 causal edges) — `brain/think/` action-gate + reward writeback | Classify a **gate-blocked** action as **impossibility**: write reward **zero-with-prejudice** and **leave the selectable set** while blocked — the R10 fix that isn't reaching this path in symbolic mode. Prove with a forced-fire harness (R9-F7 / F-LN8 pattern), not EMA inference. | Blocked action's EMA → floor; selection count collapses; it stops seeding causal edges |
| 1D.2 `[V5]` | `brain/control_signals/homeostasis.py` saturation tripwire (F-LN5 landed a time-at-bound trip in Run 11 but duty didn't move) + `brain/think/deliberation_gate.py` percentile gate (C1) | Make ignition **breathe**: `drive_mastery` pinned @1.00 all life, duty 98.2 %. The C1 percentile gate is not reducing duty. Recalibrate the saturated signal / force a recalibration event when a signal sits ≥95 % at-bound for 500 cycles. | Ignition duty **< 90 %**; no signal ≥95 % at-bound 500 cyc without a recalibration event in telemetry |
| 1D.3 `[V6]` | effect-credit assignment (`brain/loop/finalize.py` credit path + `commitment`/contribution counters) | Spread effect-credit past `self_understanding`: commitment is diverse (4 aspirations) but contributions were 19/0/0/0. `output_producing`/`world_knowledge`/`genuine_contact` commit but earn nothing. | **≥2 aspirations** with non-zero `contribution_count`; `genuine_contact` > 0 |
| 1D.4 `[A12]` | `brain/cognition/metacog_analyze.py:156-165` `_try_suppress` entry conditions; `tag_sets.py:96` comment | **Realign the avoidance breaker** (built, wired, never fired once — observed live climbing 33→72 debt). Diagnose `_RUT_WINDOW` + debt threshold against real streak dynamics (thresholds set from a shorter-streak regime), OR let the debt counter feed the selector's `goal` factor negatively so inspection functions stop scoring as goal-service while debt is high. **Not a new clamp** — the natural antagonist is 1D's anger wire (Layer 2), but a threshold realign is the Run-12-scope fix. | Max avoidance-debt streak per life + breaker-firing count (currently zero, ever) both reported; breaker fires ≥1 |

### Slice 1E — retired (folded into the governing decision + Slice 1C)

The Run-11 verdict's item 3 posed this as an **LLM-mode product call** ("run
LLM-assisted or descope Growth"). The governing decision at the top of this doc
**dissolves that false choice**: growth's currency becomes structured knowledge,
so Growth is scoreable **symbolic-only** and its keystone work moves into Slice
1C (1C.0–1C.5). The acceptance life runs symbolic-only; LLM-assisted stays
available purely as a **rendering** mode for the human-readable memo, never a
growth prerequisite. Verdicts still state `mode:` up front (standing rule);
Run 12's will read `mode: symbolic-only` and — for the first time — a green (or
at least non-zero) Growth axis in that mode is the thing being proven.

---

## Layer 2 — post-gate cognition (the missing mechanisms)

The audit's addenda 4–8 found that Orrin's motivation system has "exquisite brakes
and no accelerators," and that human cognition uses a handful of organs Orrin
*already has* (prediction engine, causal graph, memo store, growth-layer
verification events) as amplifiers and self-checks, not only as gates. These are
**new capability**; none is a Run-12 gate-passer. They ship on a proven funnel.

Ordered by the audit's own leverage ranking + build cost:

### 2.0 — the `origin` field (highest bug-kill-per-line; extract early) `[A-Add8]`

The single change the audit rated highest-leverage of the whole pass. A first-class
**`origin` field at the WM write chokepoint** (`brain/cognition/.../working_memory.py:125`,
which today defaults `agent="orrin"` for *everything*), closed taxonomy —
`perception | self_output | memory_recall | simulation | dream | user` — set at
write time, with consumers **required to filter by it**:

- question miner mines only non-self origins (retires Run 10 LN-1 self-echo *as a
  class*);
- world-model / KG extraction ingests only `perception + user`;
- novelty discounts `self_output`;
- native-LM corpus excludes `self_output` (the contamination fix, generalized).

This retires the self-echo bug family (efference-copy / reality-monitoring, Add8
items 1–2) case-by-case→as-a-class, and is the structured half of the Thought
Object plan (memory `prose_bus_label_authority`). One field + consumer filters.
**Candidate to pull forward into Layer 1** if the smoke life shows self-echo
recurring — it's cheap and it's a correctness fix, not a new appetite.

### 2.1 — goal origination gains prospection & means-end `[A-Add5]`

Verified absence: no candidate goal is ever evaluated by predicted consequences
(grep across the generation path: only a string literal). Adoption is fairness
across aspirations, never predicted value.

1. **Prospective valuation** — before adoption, run each candidate through the
   prediction engine; score the predicted outcome state against current drive
   pressures; adopt on predicted felt value. Demote the coverage floor to a
   tie-breaker. Every part exists (prediction engine, causal graph, drives); the
   wire candidate → predicted-consequence → drive-valuation is simply absent.
2. **Means-end minting** — a generator that walks the causal graph (23
   confirmed-prediction rules and growing) **backwards** from aspiration-valued
   effects to actionable causes: "do X because it causes Y." Self-justifying and
   close-out-checkable.
3. **Cue-triggered priority** — cue-born candidates (the 2026-07-21 mitochondria
   pattern: read → curious → self-minted research goal) outrank quota-born ones.
   Wanting spikes at opportunity; it does not round-robin.

### 2.2 — accelerators: passion, play, anger `[A-Add6]`

The reframe the audit lands on: **the historical monopolies were malformed
passions** — a positive-feedback loop on one thing, pathological only because it
ran on *fake* returns (timestamp rewrites, self-echo). Passion = the same loop
gated by **genuine** returns.

- **Passion / "earned monopoly"** — an interest ledger at the **topic-cluster**
  level where **verified returns only** (answered close-outs, promoted exemplars,
  ladder events — the growth layer already defines these) deposit persistent
  appetite; the selector/generators honor it as a multiplier, exempt from fairness
  quotas up to a budget. Anti-pump already guarantees fake returns can't deposit.
  **Scoring consequence: S10 as written would fail a passionate Orrin** — when this
  ships, the anti-monopoly gate must distinguish *earned* concentration from
  *pumped* concentration. **This also touches the reuse gate** (reuse is literally
  the trace a passion leaves; some anti-monopoly machinery is anti-reuse machinery)
  — so 2.2-passion and Layer-1 reuse interact and must be co-designed.
- **Play** — an idle-time fraction where the effect ledger, quality veto, and
  failure counters simply don't watch (skills that only pay at competence can't
  survive the incompetent phase while it's scored as failure).
- **Anger / vigor converter** — high-energy negative valence (observed live:
  valence 0.17 / energy 0.99 — textbook frustration → nothing) raises action
  pressure on the **blocked** goal for a bounded window before the learning system
  is allowed to devalue it. The natural antagonist for item 12 (1D.4).

### 2.3 — self-checks: source epistemology, self-testing, audience, counterfactual regret `[A-Add7]`

Five of Add6–7's mechanisms route through the same existing organs; low build cost.

1. **Source epistemology** — a per-source reliability ledger fed by events that
   already exist (confirmed-prediction pipeline, close-out answers): sources whose
   claims later confirm gain weight; contradicted sources lose it. Fixes junk
   search hits, world-model contamination, memo quality. Prereq for internet-as-world.
2. **Self-testing / retrieval practice** — an idle-cycle self-test ("pull a KG
   claim; reconstruct from memory; check against the store; on failure, re-open the
   memo that taught it"). **The surprise:** this makes re-opening his own memos a
   *routine act* — reuse stops being a double-coincidence and becomes a habit's
   side effect. Cheap; every part exists.
3. **Audience-addressed production** — change the memo contract from "stitch
   findings under title" to "explain to a named reader who lacks the sources." A
   memo written as a letter to future-Orrin is structurally reuse-shaped; a
   findings letter to Ric is production + `genuine_contact` in one act.
4. **Counterfactual regret** — `brain/cognition/regret.py` today applies pain only
   (low_affect + uncertainty bumps). Add the missing half via `simulate.py`: on
   regret over a stalled goal, run the counterfactual ("what action was available
   and predicted-better?") and credit that alternative — regret from mood into
   learning signal.

### 2.4 — reasoning ratchet (design note, explicitly post-gate) `[A-Add4]`

Knowledge accumulates (70 live rules, 23 from confirmed predictions), but
**inference depth is a compile-time constant** (`brain/symbolic/inference.py:28`,
hard depth 2). The growth ladder is the existing controller: a rung climb
unlocking inference depth 3 (per-hop confidence decay already keeps long chains
honest) would be reasoning that ratchets *from verified success*. The self-code
writer — the only true capability ratchet — has also never fired (0/644 functions
synthesized). **Both are "built, wired, never lived," same status as the growth
ladder.** Do not touch until Layer 1 makes the ladder fire at all.

---

## 2. Build order & gates (summary)

| Phase | Contents | Gate before proceeding |
|---|---|---|
| **1A** | Shutdown/rebirth bug + regression test | `make verify`; lifecycle test green |
| **1B** | Daemon-feed de-starve (instrument → 1B.1/1B.2 emit research at volume → 1B.3 de-clamp → 1B.4 verify reuse reachable) | `make verify` + ~2k smoke life: WAL silence < 30 min, ≥1 reuse row |
| **1C** | Structured-knowledge keystone: `claims.json` product (1C.0) + daemon-lane stamp (5a) + structured `score_answer` (5b) + annotation-leak + structured reuse + veto re-scope + desync | `make verify` + smoke life: a prediction-scored goal stamps `answered=True` w/ 0 prose; ≥1 structured reuse row; 0 leaked closes |
| **1D** | Skeptic reds: impossibility, ignition breathe, credit spread, avoidance breaker | `make verify` + forced-fire harnesses (not EMA inference) |
| **1E** | *Retired* — folded into the governing decision + 1C; acceptance life is symbolic-only | — |
| **— acceptance life —** | Full ~20k-cycle life, **symbolic-only**; score against `NEXT_RUN_TESTS.md` Run-12 gate (Growth re-scored on structured currency) | Feed + Growth + Health + Honesty axes |
| **2.0** | `origin` field (may pull into L1 if smoke life shows self-echo) | — |
| **2.1–2.4** | Prospection, accelerators, self-checks, ratchet | Only on a green Layer-1 funnel |

**NO-CLAMPS directive (memory `unopposed_force_principle` + `run11_backlog`):**
every Layer-1 fix that touches the generation/selection path removes or opposes a
throttle (1B.3, 1D.4) rather than adding a new one. Classify each finding
broken-pipe / unopposed-force / misaimed-force before patching; a clamp is scar
tissue for a missing antagonist.

---

## 3. Consolidated observables (what the acceptance life must show)

Merged from verdict §5 and the audit's per-item observables:

- **Lifecycle:** natural death → 1 clean exit, 0 cycle-stall kills, 0 born-dead
  relaunches.
- **Feed:** no daemon WAL silence > 30 min; research-kind `state.jsonl` ≥ 20;
  reuse ≥ 8 topical rows with real cycle+path.
- **Growth (structured currency, symbolic-only):** answered-rate > 0 via
  **prediction-scored** structured claims (≥1 understanding goal stamps
  `answered=True` off a `resolve_prediction` hit, 0 prose required); ≥1 non-vetoed
  exemplar canonised (structured products exempt from the prose veto); ≥1 rung
  climb (`growth_ladder.json` exists for the first time ever); ≥1 **structured
  reuse** row (a claim extends/tests/merges a prior goal's claim by id); ≥1 answer
  cited in a later reason payload.
- **Close-out honesty:** 0 `answered=False` satiety closes without block/follow-up;
  daemon completions stamped.
- **Health:** committed occupancy < 60 %; ignition duty < 90 %; no signal ≥95 %
  at-bound 500 cyc without recalibration; ≥2 aspirations with non-zero contribution;
  `genuine_contact` > 0; RSS floor ≤ ~2.2 GB.
- **Honesty:** 0 repeated goal_ids in `failures.jsonl`; 0 store desyncs; mode +
  build SHA stated, commit before launch.
- **Skeptic:** blocked-action EMA → floor + drops from selectable set; avoidance
  breaker fires ≥1 (max debt streak reported).

---

## Open decisions (Ric's call before the acceptance life)

1. **~~LLM mode~~ — DECIDED 2026-07-21.** Growth's currency is structured
   knowledge; acceptance life runs **symbolic-only**; LLM is an optional rendering
   layer only. See the governing decision + Slice 1C. No longer open.
2. **Pull `origin` field (2.0) into Layer 1?** It's a correctness fix (self-echo
   class), cheap, and touches the same generation inputs Slice 1B changes. If the
   Slice-1B smoke life shows any self-echo, promote it into 1B rather than deferring.
3. **Structured-product schema scope (1C.0).** Minimum viable is
   `{entities, relations, prediction, sources}`. Open: whether the first Run-12
   build extracts predictions for **all** research goals or only for
   characterization/telemetry-checkable ones (the rest carrying relations+concepts
   only). Recommendation: start with relations+concepts universal, predictions on
   characterization goals — keeps 1C.2's `answered` scorer honest without forcing a
   prediction where none is checkable.

---

*Merges `DATAFLOW_AUDIT_2026-07-20.md` (retired) + `DEMO_RUN_2026-07-21.md §5` +
the `NEXT_RUN_TESTS.md` Run-12 gate. Anchors re-verified against `423e201`
2026-07-21. Governing decision (2026-07-21): growth's currency is structured
symbolic knowledge, not prose — the acceptance life is symbolic-only and the
keystone (Slice 1C) re-keys close-out/reuse to structured artifacts. Layer 1 =
gate-passers; Layer 2 = new capability, post-gate only.*
