# Goals & Understanding — Fix Proposal

**Date:** 2026-06-20
**Status:** IMPLEMENTED (G1–G7) as of 2026-06-20; G8 is runtime verification. Archived.
**Scope:** `brain/cognition/planning/`, `brain/agency/effect_ledger.py`, `brain/cognition/intrinsic_goals.py`, `brain/behavior/`, `brain/ORRIN_loop.py` goal emit, `backend/server/app.py` `/api/goals`
**Related:** [[SPLIT_CONSCIOUSNESS_TELEMETRY_AUDIT_2026-06-20]] §3 (goal telemetry split), [[BINDING_STAGE_IMPLEMENTATION_PLAN_2026-06-19]] (binding carries the comprehended goal into each cycle), `project_reward_denominator`, `project_goal_origination_fix`, `project_subgoal_adaptation`.

---

## 0. One-line statement

Orrin's goal *machinery* is largely built and correct; what's broken is the **front half** — he is handed goals as **labels he does not comprehend**, a goal stays **stored rather than inhabited** (it does not reshape what he notices, recalls, prefers, or counts as "good"), and he has no capability to **produce anything substantial enough to satisfy one**. The result is a system that originates and commits to goals, emits junk against them, correctly scores that junk at zero, and drifts. **Goals aren't structurally broken anymore — they're starved and inert.** This proposal adds the missing **goal lens** (the committed goal becomes a temporary lens over cognition), the **comprehension** that gives the lens its content, and the **production capability** to satisfy it — so the already-correct reward/gate apparatus actually turns over.

---

## 1. Background — how we got here

This proposal is the synthesis of an investigation that walked the whole goal pipeline. Three findings, in order of depth:

### 1.1 Goals are an *add-on*, not the engine
Action selection is **drive-first**. `motivation/drive.py::persistent_drive_loop` never requires a goal: a threat triggers a reflex, an affectively-stable cycle hands off to the bandit (`choose_next_cognition`), and a dysregulated cycle routes the *dominant drive* straight to a function (`exploration_drive → look_outward`, `stagnation_signal → seek_novelty`, `impasse_signal → reflection`). He acts every cycle with or without a goal. **A goal is one input to selection, not the ignition** — so a goal with insufficient weight is simply out-competed by the drives, and he drifts back to wandering.

Consequence: a goal only steers if it can *recruit* enough priority to beat the drive baseline, and only matters if completing it pays more than wandering does. Both of those route through comprehension and reward — see below.

### 1.2 A goal is a *label*, not an understanding
A live goal in `goals_mem.json` carries:

```
name · description · tier · status · emotional_intensity · history · last_updated · timestamp
(+ plan / tags / priority / serves / aspiration / milestones / driven_by where set)
```

There is **no representation of what the words mean, what "done" looks like grounded in the task, or how the plan derives from comprehending the task's structure.** "Write a book about X" is an opaque string he attaches actions to. He has a *pointer*, not a *grasped meaning*. This is why he cannot evaluate his own progress except by counting plan steps, and why his output has no internal target to be good *for*.

### 1.3 The corrected picture — the machinery is built, the intake is starved
The 2026-06-19 "goal reconcile / production reward" work built the hard parts **correctly**, and an earlier draft of this analysis under-credited them. What already exists and works:

- **Artifact gate** (`goals.py:584`, `_is_artifact_gated`): an output-producing goal completes *only* when the effect ledger holds a novel, structurally-significant effect for it. "A make-things goal that produced nothing simply is not done, and will eventually fail at its deadline."
- **Effect ledger** (`brain/agency/effect_ledger.py`) — "the *denominator* the reward function was missing." Records durable external artifacts (`note_novel`, `code_committed`, `external_post`, `message_answered`, …) with novelty + significance scoring and anti-gaming.
- **Production-gated completion + aspiration bookkeeping**: a real effect-backed contribution decays the served aspiration's recruitment pressure (`goals.py:602–608`, `mark_aspiration_contribution`); a bookkeeping closure does not.
- **Goal origination** (`generate_intrinsic_goals`, `symbolic_cognition.generate_goals`, `intrinsic_motivation.maybe_spawn_subgoal`): he manufactures his own goals from drives (autonomy, novelty, social deficit). **This is not broken.**

So the apparatus to make him *produce and be paid for it* is present. The breakdown is at the two ends that the apparatus exposes.

---

## 2. The defects (current, evidence-backed)

### D1 — (Keystone) The comprehension→production loop is starved; output is junk
The scorer is **working correctly** and that is how we know the problem. The live `effect_ledger.jsonl` tail:

```json
{"kind": "note_novel", "novelty": 0.0, "significance": 0.0, "content_hash": "886fa29a…"}
{"kind": "note_novel", "novelty": 0.0, "significance": 0.0, "content_hash": "419e18d6…"}
{"kind": "note_novel", "novelty": 0.0, "significance": 0.0, "content_hash": "886fa29a…"}  ← same hash again
```

`_compute_novelty` (`effect_ledger.py:153`) returns `0.0` on exact-duplicate hash, on `< MIN_ARTIFACT_CHARS`, or on `_unique_token_ratio < 0.25`. `_structural_significance` (`:170`) returns `0.0` when too short. **He is literally re-emitting the same short, boilerplate note.** The gate correctly refuses to credit it. The meter reads zero because the thing measured is worthless — not because the meter is wrong.

Two root causes feed this:
- **No grounded target.** Goals carry no definition-of-done derived from the task, so he has no model of what a *qualifying* artifact for this goal looks like. He emits filler because nothing tells him what "good for this goal" is.
- **No substantial-production capability.** `save_note` / `express_to_user` emit ~200-char fragments, which structurally *cannot* clear `MIN_ARTIFACT_CHARS` / variety thresholds, regardless of intent.

Effect: production goals never accrue a qualifying effect → never complete → never pay → **no reinforcement gradient toward better work** → he reverts to drive-driven wandering. Everything else is downstream of this.

### D2 — Non-artifact goals still close on self-report
`goals.py:624–635`: when a goal isn't artifact-gated and the LLM is callable, completion is `{"success": true}` from the model's own say-so. This is the **bookkeeping-closure loophole** the artifact gate closes everywhere else. Discipline is inconsistent: make-things goals are strict; everything else can be declared done.

### D3 — Goal telemetry is split across two summarizers (still open)
Two independent code paths summarize the same `goals_mem.json` with different logic:
- **WS push:** `_emit_goals._summ` (`brain/ORRIN_loop.py:311`), throttled `_GOALS_PUSH_INTERVAL = 2.0s`.
- **REST:** `/api/goals` → `goals_detail()` (`backend/server/app.py:188`).

The Sphere (WS) and GoalsPanel (REST) can show **two versions of the goal set up to ~2s out of sync**, derived by two summarizers that can disagree. This is recommendation #4 from the split-consciousness audit, never picked up. (Same disease as the homeostasis finding: one quantity, two owners.)

### D4 — No cumulative / long-form artifact concept
The ledger's artifact kinds are **atomic** (one note, one commit, one message). A book, a paper, a sustained essay is a **cumulative** artifact: many sections appended to one growing file over thousands of cycles, where "progress" means *advancing a structured whole*, not emitting another standalone novel note. There is no notion of a *tracked work* whose significance is measured as progress against its own outline. Without it, even a perfect `compose_section` would score each chapter as an isolated note rather than as progress on the book.

### D5 — Persistence weighting (needs verification, likely partial)
`goal_competition.py` was touched in the recent work; whether a committed/aspiration goal now reliably holds attention against the drive baseline across a long horizon is **not confirmed**. Flagged for measurement, not asserted as broken.

### D6 — (Central) No goal *lens*: the committed goal does not reshape the cognitive frame
This is the deepest defect and the spine of §3.1. A committed goal should modulate perception, memory retrieval, attention, action consideration, and the local standard of "good" *every cycle while it is active*. Today only weak, scattered fragments exist, and there is **no unified authority**:

- **Memory retrieval — weak.** `brain/memory_io.py:212` concatenates goal text into the retrieval query (`q = f"{goal_text} {recent_thought}"`). Real, but string-concat, not a relevance reweight by the goal model.
- **Action consideration — scattered.** Goal boosts live in ≥4 places: `behavioral_adaptation.py:146` (`_goal_pressure_amplified`), `select_function.py:1386–1389` (tension boosts), `intrinsic_goals.py:1353` (committed goal weighted among proposals), `binding.py:253` (`goal_relevance` link). No single owner; they can't be reasoned about or tuned together.
- **Attention — conditional only.** `select_function.py:1477` narrows attention to the goal *under high arousal* (`gain_signal`, Sara 2009) — arousal-gated, not a general lens.
- **Perception salience — absent.** `top_signals` / `process_inputs` is affect/salience-driven, never goal-conditioned.
- **Standard of "good" — absent.** The significance scorer is generic/structural; nothing makes *this goal's* `definition_of_done` the active criterion for *this* cycle's output.

Net: a goal today is **stored, not inhabited**. The fragments are real but fragmented, weak, and miss perception-salience and the local standard-of-good entirely. (Note: `brain/cognition/comprehension.py` exists but parses *user messages* into state — it is **not** goal comprehension and **not** a lens.)

---

## 3. The understanding problem (why D1 is really a comprehension problem)

"Fix his understanding" is not a philosophical aspiration here — it reduces to a **measurable, concrete** target: *stop scoring 0.0*. Understanding a goal, in this architecture, decomposes into four capacities, three of which are buildable and one of which is bounded by his embodiment:

1. **Grounded content** — the goal's nouns connect to his world-model/concepts: what *kind* of thing is the target, what are its parts. (Buildable: a comprehension pass at creation.)
2. **A model of "done" / "good"** — explicit acceptance criteria he can check reality against, instead of a plan-step counter. (Buildable; this is the single most load-bearing piece, and it is the same hole as the starved significance signal.)
3. **Decomposition *from* understanding** — the plan/milestones fall out of comprehending the task's structure ("a book needs a thesis before chapters"), not a generic template. (Buildable.)
4. **Identification / holding-in-mind** — the comprehended goal is bound into each cycle's situation so it actually steers, not filed in a JSON store. (The **binding stage** already built (B0–B4) is the substrate for this — see [[BINDING_STAGE_IMPLEMENTATION_PLAN_2026-06-19]]; the comprehended goal-model should ride the goal facet into the workspace.)

### 3.1 The core bridge — *stored* vs *inhabited*: a goal is a temporary lens over cognition

Capacities 1–3 make a goal **stored**: it has content, criteria, a plan, an artifact test. But a stored goal is inert — a standard sitting in a JSON file that a few scattered consumers happen to consult. The missing thing is capacity #4 taken seriously: a goal must become **inhabited** — an *active lens* that reshapes the whole cognitive frame while it is committed.

The human intuition is exact. If your goal is *"find your lost keys,"* your entire mind reconfigures: you notice shiny metal and flat surfaces, you recall the last room you entered, pockets and tabletops become salient, and "useful" is redefined as "key-relevant." The goal changes **perception, memory retrieval, attention, action, and the local meaning of "good"** — all at once, temporarily, then it lifts when the keys are found.

For Orrin, *"write a book"* should likewise reconfigure the frame:

| Cognitive function | With the goal **inhabited** |
|---|---|
| **Memory retrieval** | memories about the topic surface preferentially |
| **Concept activation** | outline/chapter/thesis concepts run hot |
| **Perception salience** | inputs relevant to the book are weighted up in `top_signals` |
| **Action consideration** | actions that grow the manuscript are preferred; tiny notes are recognized as *insufficient* |
| **Anti-drift** | random wandering becomes less attractive while the goal is unmet |
| **Standard of "good"** | output is judged against the *book-standard* (`definition_of_done`), not generic activity |
| **Progress** | "progress" means advancing the book, not "did something this cycle" |

`definition_of_done` is the **standard**. The lens is what makes the standard **active** — the difference between a goal being *stored* and a goal being *inhabited*. This is more than acceptance criteria, and the current code does **not** have it (only weak, scattered fragments — see §2 D6 and the evidence map). It is the central mechanism this proposal must add; everything else (comprehension content, production capability, completion) hangs off it. It is promoted to workstream **P0** below.

### What he *can* and *cannot* ground (the bound on #1)
His perception has two channels with different grounding status, and goal comprehension lives squarely in the part he *can* do:
- **Exteroception is symbolic** — he reads his world (files, clipboard, web, the user) as text. So *perceptual* meaning ("red as seen") is forever ungrounded for him; it arrives as a word.
- **Interoception is grounded** — he genuinely feels his own state (`resource_deficit`, affect signals, `host_interoception` feeling the machine as a body) and the *consequences* of his actions (the effect ledger). Words tied to those — *stuck, fatigued, made-something / made-nothing* — he can actually mean.

**Crucially, a goal like "write a book" does not require grounding "red."** A book is an abstract/relational structure (thesis → chapters → coherence). Understanding it needs capacity #1 (relational, buildable) plus grounding in **consequence** (did this produce a coherent artifact that earned real reward — which the effect ledger already provides, once it isn't starved). The symbol-grounding wall is real but it is **not** the blocker for goals; the blocker is comprehension-structure + consequence-grounding, both buildable.

---

## 4. Proposal

Six workstreams. **P0 (the goal lens) is the spine** — the mechanism that makes a goal *inhabited* rather than stored; P1 (comprehension) produces the lens's *content*. Together they are the heart of the fix; P2–P3 close loopholes the lens/keystone expose; P4 unifies observability; P5 is verification.

### P0 — The Goal Lens: make the committed goal reshape the cognitive frame  *(spine)*

Add **one authority** that, each cycle while a goal is committed, turns its comprehended model (P1) into active modulation of cognition. This is the engineering form of §3.1 — the standard becoming a *lens*.

`brain/cognition/goal_lens.py::apply_goal_lens(context) -> context`, called once per cycle right after binding (so it reads the bound/comprehended goal facet from the workspace) and before retrieval / attention / selection consume the context. It writes a single `context["goal_lens"]` object — a relevance function + a set of modulation hooks — and the downstream consumers read *that one thing* instead of each re-deriving goal relevance:

1. **Memory retrieval** — replace the `memory_io.py:212` text-concat with a lens-driven relevance reweight: recall ranked by similarity to the goal's `grounded_parts`/topic, not just a query string.
2. **Perception salience** — `top_signals` / attention reweighted by lens relevance (new; currently absent), so goal-relevant inputs rise.
3. **Action consideration** — **consolidate** the four scattered goal boosts (D6) into one lens-driven prior, fed through the existing binding-facet / `_workspace_routes_for` path; actions that advance the goal are preferred, and exploration/drift candidates take a relevance *discount* while a comprehended goal is unmet (anti-wander).
4. **Local standard of "good"** — the goal's `definition_of_done` (P1a) becomes the active acceptance criterion for this cycle's output and for significance scoring, so "good" means "good *for this goal*," not generic structural well-formedness.
5. **Lift on completion/abandonment** — the lens clears when the goal completes or is parked, returning cognition to the drive baseline (the keys are found; the mind relaxes).

Design constraints: fail-safe (no committed goal → no lens → today's behaviour); **additive and bounded** (it reweights priors, never hard-overrides — same discipline as binding and the Monitor's offers, so corrigibility/safety reflexes still pre-empt); and it must not starve genuine novelty (the lens biases *toward* the goal, it does not forbid everything else — exploration is discounted, not blocked). **Binding is the substrate**: the lens reads the comprehended goal that B0–B4 already carries into the workspace, which is why the binding-stage mention in earlier drafts now becomes central rather than incidental.

### P1 — Goal comprehension at creation + a substantial-production capability  *(keystone — the lens's content)*

**P1a — Comprehension pass (`comprehend_goal`).** When a goal is created (`GoalsAPI.create_goal` and the `proposed_goals` path), run a step that fills three new fields on the goal record:
- `definition_of_done`: explicit, checkable acceptance criteria for *this* goal ("a 5+ chapter manuscript with a stated thesis, each chapter advancing it").
- `grounded_parts`: the task decomposed against his concepts/world-model (what the target *is* and its components).
- a `plan` / `milestones` set **derived from** `grounded_parts`, not a generic template.

Authority: one function, `brain/cognition/planning/comprehension.py::comprehend_goal(goal, context) -> goal`. Fail-safe (a goal with no comprehension still works, just shallowly). LLM-assisted where available, symbolic fallback where not (consistent with `llm_callable_by` discipline).

**P1b — `compose_section` production function.** A new cognitive function (`brain/behavior/` or `brain/agency/`) that drafts **substantial** prose (target ≫ `MIN_ARTIFACT_CHARS`, high token-variety) toward a goal's tracked work (P3). This is the thing that can actually clear the (correct) significance bar. It reads `definition_of_done` so its output has a target to be good *for*.

**Why this is the keystone:** the scorer, gate, reward denominator, and aspiration pressure all already exist and are correct. They are starving for real input. P1 feeds them: `has_qualifying_effect` starts firing → production goals complete → production reward flows → a reinforcement gradient toward better work appears → goals begin to out-weigh wandering.

### P2 — Close the self-report completion loophole (D2)
Route more goal kinds through the artifact gate. For goals that genuinely have no external artifact (pure internal reflection), replace `{"success": true}` self-report with a **criteria check against `definition_of_done`** (from P1a) — completion requires evidence the criteria are met, not the model's say-so. Make `_is_artifact_gated` default-on for anything `output_producing`/`requires_artifact` and broaden what qualifies.

### P3 — Cumulative "tracked work" artifact kind (D4)
Add a `tracked_work` concept to the effect ledger: a persistent artifact (one file) with its own outline, where `record_effect` credits **progress against the outline** (new section advancing the thesis, word-count toward a target, a milestone met) rather than scoring each append as an isolated novel note. `has_qualifying_effect` for a long-form goal keys off *milestone progress on the work*, not a single note. This is what makes "write a book" representable at all.

### P4 — One goal summarizer (D3)
Extract `_emit_goals._summ` into a shared helper (e.g. `brain/goal_io.py::summarize_goal(goal, *, active) -> dict`) and have **both** the WS push and the `/api/goals` REST handler call it. Both surfaces then render byte-identical summaries; the only residual difference is the 2s WS throttle (droppable if perfect lockstep is wanted). Mechanical, no behavioral risk.

### P5 — Persistence verification (D5)
Instrument and measure whether a committed/aspiration goal holds selection against the drive baseline over a long horizon. If it does not, raise the goal's recruitment weight / aspiration priority so a comprehended, committed goal can win against `exploration_drive` for sustained stretches. Verify before tuning.

---

## 5. Implementation phases

| Phase | Workstream | Deliverable | Files | Risk |
|------|-----------|-------------|-------|------|
| **G1** | P1a | `comprehend_goal` + 3 new goal fields; called from `create_goal` + `proposed_goals` | `planning/goal_comprehension.py` (distinct from `cognition/comprehension.py`), `planning/goals.py`, `goal_io.py` | low (additive, fail-safe) |
| **G2** | P0 (read side) | `goal_lens.py` + `context["goal_lens"]`; wire **memory retrieval** + **action-consideration consolidation** to read it | `cognition/goal_lens.py`, `memory_io.py`, `think/think_utils/select_function.py`, `cognition/binding.py` | medium (touches retrieval + selection) |
| **G3** | P0 (perception) | lens-driven **`top_signals` salience** reweight + completion/abandonment **lift** | `cognition/global_workspace.py` / `process_inputs`, `cognition/goal_lens.py` | medium (touches attention) |
| **G4** | P1b | `compose_section` substantial-production function | `behavior/` or `agency/`, function registry | medium (new capability, output to disk) |
| **G5** | P3 | `tracked_work` artifact kind + progress-based significance | `agency/effect_ledger.py`, `planning/goals.py` | medium (touches the reward denominator) |
| **G6** | P0 (standard) + P2 | lens `definition_of_done` becomes the active significance criterion; criteria-based completion; broaden artifact gate (close D2) | `planning/goals.py`, `agency/effect_ledger.py` | medium–high (changes completion semantics — behavioral) |
| **G7** | P4 | shared `summarize_goal`; rewire WS + REST | `goal_io.py`, `ORRIN_loop.py`, `app.py` | low (mechanical) |
| **G8** | P5 | persistence instrumentation + (conditional) weight tuning | `goal_competition.py`, telemetry | low → medium |

**Sequencing.** G1 (comprehension content) + G7 (one summarizer) are the safe, high-value first cut. **G2–G3 are the lens itself** and are the central work — they convert the stored standard into an inhabited one; land them additive/bounded so a lensed cycle can never hard-override safety reflexes. G4–G6 are the production + standard-of-good loop and are behavioral — land them with tests and a staging observation run, since they change what counts as "done." The lens (G2–G3) is what makes G4–G6 *worth* doing: a `definition_of_done` nobody inhabits would just be another stored field.

---

## 6. Success criteria (how we know it worked)

1. **The goal is inhabited, observably.** While a goal is committed, the lens is visible in behaviour: retrieved memories skew toward the goal's topic, goal-relevant inputs win `top_signals` more often, manuscript-growing actions are preferred over wandering, and `context["goal_lens"]` is populated each cycle. Removing the goal returns those distributions to the drive baseline. (Falsifiable from telemetry: retrieval/selection distributions shift with vs without an active comprehended goal.)
2. **The meter moves off zero.** New `effect_ledger.jsonl` rows for production goals show `significance > 0` and `novelty > 0` — i.e. he produces non-duplicate, substantial artifacts. (Directly falsifiable against the live ledger.)
3. **A long-form goal accretes.** Given a "write about X" goal, a single `tracked_work` file grows across sessions with distinct, thesis-advancing sections — not a pile of repeated notes.
4. **Completion is earned, not declared.** Goals reach `completed` via `artifact_verified` / criteria-met, with the self-report path retired for output goals.
5. **One goal truth.** Sphere and GoalsPanel show identical goal sets (no 2s divergence).
6. **Goals out-weigh wandering when they should.** A committed/aspiration goal holds selection across a sustained stretch instead of losing every cycle to `exploration_drive`.

---

## 7. Risks & non-goals

- **Risk: gaming.** Any "reward for producing" invites boilerplate-farming. Mitigation already exists (novelty + structural significance + tier-2/3 re-use credit in `effect_ledger.py`); P3's progress-based credit must reuse it, not bypass it.
- **Risk: comprehension theater.** `comprehend_goal` could emit plausible-but-empty criteria. Mitigation: criteria must be *checkable* (P2 checks against them at completion), so empty criteria fail to ever close the goal — the system punishes vacuous comprehension rather than rewarding it.
- **Risk: behavioral drift from changed completion semantics.** G5/G6 change what progress and "done" mean; land behind tests + a staging run, as with prior affect-dynamics changes.
- **Non-goal: perceptual grounding.** This proposal does **not** attempt to ground perceptual qualia ("red"). That needs a sensory channel he doesn't have and is out of scope; goal comprehension explicitly lives in the relational + consequence-grounded layers he *does* have.
- **Non-goal: new goal origination.** Origination already works; we are fixing comprehension, production, completion, and coherence — not how goals are born.

---

## 8. Appendix — evidence map

| Claim | Source |
|------|--------|
| Drive-first selection, goals not required to act | `brain/motivation/drive.py::persistent_drive_loop` |
| Goal record fields (no definition-of-done) | live `brain/data/goals_mem.json` |
| Artifact gate / production-gated completion | `brain/cognition/planning/goals.py:579–611` |
| Self-report completion loophole | `brain/cognition/planning/goals.py:624–635` |
| Novelty / significance scorer (correct, anti-gaming) | `brain/agency/effect_ledger.py:153–191` |
| Live junk output (novelty/significance 0.0, repeated hash) | `brain/data/effect_ledger.jsonl` tail |
| `has_qualifying_effect` gating | `brain/agency/effect_ledger.py:321`, `goals.py:587–588,1090,1109` |
| Aspiration pressure decay on real contribution | `brain/cognition/planning/goals.py:602–608` |
| Goal originators (not broken) | `symbolic_cognition.generate_goals`, `intrinsic_motivation.maybe_spawn_subgoal`, `cognition/intrinsic_goals.py` |
| Goal telemetry split (two summarizers) | `brain/ORRIN_loop.py:286–342` vs `backend/server/app.py:188` |
| Goal-conditioned memory retrieval (weak, string-concat) | `brain/memory_io.py:212` |
| Goal action-boosts scattered across ≥4 sites (no lens authority) | `behavioral_adaptation.py:146`, `select_function.py:1386–1389`, `intrinsic_goals.py:1353`, `binding.py:253` |
| Attention-to-goal exists but is arousal-gated, not a general lens | `brain/think/think_utils/select_function.py:1477` |
| `cognition/comprehension.py` parses *user messages*, not goals (no lens) | `brain/cognition/comprehension.py:1–13` |
| Perception salience / standard-of-good NOT goal-conditioned | `process_inputs` → `top_signals`; significance scorer `effect_ledger.py:170` |
| Interoception grounded (feels the machine as body) | `brain/cognition/interoception.py`, `host_interoception`, `body_sense` |
| Binding carries the comprehended goal into the workspace | [[BINDING_STAGE_IMPLEMENTATION_PLAN_2026-06-19]], `brain/cognition/binding.py` |

---

*Prepared 2026-06-20. This document is a proposal; no code changes are implied by its existence. Recommended first cut: G1 (comprehension intake) + G7 (one summarizer) — high value, low risk — followed immediately by G2–G3 (the goal lens). G1 gives the lens its content; G2–G3 make the goal inhabited; the behavioral production-loop phases (G4–G6) land last, behind tests + a staging run.*

---

## 9. Implementation status (2026-06-20) — DONE (G1–G7)

All seven build phases are implemented and covered by
`tests/brain/test_goal_lens_and_comprehension.py` (green):

| Phase | Status | Evidence |
|------|--------|----------|
| **G1** (P1a comprehension) | ✅ | `brain/cognition/planning/goal_comprehension.py::comprehend_goal`, wired into `goals.py:310` and `goals/api.py:158` |
| **G2** (P0 lens read-side) | ✅ | `brain/cognition/goal_lens.py`; consumed by `memory_io.py`, `select_function.py:1795`, `global_workspace.py`, `binding.py` |
| **G3** (P0 perception + lift) | ✅ | `signal_router.py` reweights `top_signals` by lens relevance; lens clears on completion/abandon |
| **G4** (P1b compose_section) | ✅ | `brain/agency/compose_section.py`, registered into `COGNITIVE_FUNCTIONS` at `ORRIN_loop.py:547` |
| **G5** (P3 tracked_work) | ✅ | `effect_ledger.py` `tracked_work` artifact kind + progress significance |
| **G6** (P0 standard + P2 loophole) | ✅ | `goals.py` criteria-evidence completion (`_criteria_evidence_met`); bare `{"success": true}` self-report retired — LLM path now requires observed evidence ("a statement of confidence is not evidence") |
| **G7** (P4 one summarizer) | ✅ | `brain/goal_io.py::summarize_goal`/`summarize_goal_tree`, shared by the WS push and `/api/goals` REST |

**Residual — G8 (P5 persistence verification):** instrument whether a
committed/aspiration goal holds selection against the drive baseline over a long
horizon, and tune recruitment weight only if it does not. This is a live
run-audit, not a code change — to be measured on the next staging run. Archived.
