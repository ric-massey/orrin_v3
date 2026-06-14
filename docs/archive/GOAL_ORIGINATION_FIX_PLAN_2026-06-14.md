# Goal Origination & Deliberation — Fix Plan

**Date:** 2026-06-14
**Companion to:** `docs/GOAL_ORIGINATION_CRITIQUE_2026-06-14.md` (the diagnosis).
This document is the implementation plan: what to change, in what order, with
exact files/functions, acceptance criteria, tests, and rollback.

**Guiding principle (from the critique):** Orrin's most genuine cognition is the
symbolic middle layer (causal graph, inference, KG). Both goal origination and
deliberation currently route *around* it. Every fix below points the same way —
**make the symbolic middle layer the primary path; treat the LLM as the optional
enrichment tool the config already disables by default.**

---

## The issues being fixed (attached)

| # | Issue | Verdict | Primary evidence |
|---|-------|---------|------------------|
| I1 | Goal content comes from fixed, narrow seed tables (`_SYMBOLIC_GOAL_SEEDS`, `_EMOTION_GOAL_TEMPLATES`) selected by `max(affect)` | True | `brain/cognition/intrinsic_goals.py:157, 249, 393` |
| I2 | `driven_by → aspiration` is a hardcoded dict lookup, not a learned link | True | `intrinsic_goals.py:702, 746` |
| I3 | The richer KG/question/research generator (`_varied_symbolic_goal`) is **dead in the default tool-only deployment** — the live default falls to the narrow seed table | Worse than claimed | `intrinsic_goals.py:948, 1068` + `generate_response.py:344` |
| I4 | System 2 (`inner_loop`: draft→critique→revise→escalate→debate) is real but runs **only** on the LLM; it no-ops when the LLM tool is unavailable | True | `inner_loop.py:472–474`; `routed_response` → tool-unavailable |
| I5 | The aspiration hierarchy a goal "serves" is asserted by table, not earned by outcome | True | `intrinsic_goals.py:787` |

The middle layer those fixes lean on is confirmed real and LLM-free:
`symbolic/causal_graph.py` (`get_causes:220`, `get_effects:229`),
`symbolic/inference.py`, `cognition/knowledge_graph.py`,
`pursue_goal._causal_first_step:221`.

---

## Phasing overview

| Phase | Fix | Issues | Effort | Risk | Ships |
|-------|-----|--------|--------|------|-------|
| 1 | A — route default through the rich symbolic path | I3, I1 | trivial | low | day 1 |
| 1 | E — `inner_loop` defers honestly when no generative path | I4 | trivial | low | day 1 |
| 2 | B — new symbolic goal generators (causal-frontier, tension, autobiographical) | I1 | moderate | low | week 1 |
| 3 | D — symbolic mode for `inner_loop` (real System-2 restoration) | I4 | difficult | medium | week 2–3 |
| 4 | C — learned `driven_by → aspiration` association | I2, I5 | research | medium | week 3+ |

Phase 1 is two same-day changes that make the default behaviour match — and
exceed — what the critique assumed was already happening. Do them first; they
de-risk everything after.

---

## Phase 1 — Fix A: route the default symbolic path through `_varied_symbolic_goal`

**Problem (I3).** `generate_intrinsic_goals` branches on `llm_available()`
(`intrinsic_goals.py:948`). `llm_available()` (`utils/llm_gate.py:42`) checks
config flag + API key + circuit breaker — it **does not know about tool-only
mode**. In the default deployment (`llm_enabled: true`, key present,
`ORRIN_LLM_TOOL_ONLY=1`) it returns True, so the LLM branch is taken; the call
returns `"tool unavailable"` (`generate_response.py:344`), `llm_ok` → `None`,
and the code falls to the **narrow** `_symbolic_intrinsic_goals` seed table
(`:1068`). The **rich** `_varied_symbolic_goal` (`:828`) — KG concepts +
open questions + recent research — only runs when `llm_enabled` is explicitly
`false`. It is dead in the default config.

**Change.** Branch goal origination on whether the LLM is *actually callable by
this caller*, not on bare reachability.

1. Add a capability helper in `brain/utils/llm_gate.py`:

   ```python
   def llm_callable_by(caller: str) -> bool:
       """True only if `caller` could actually reach the API right now —
       i.e. the LLM is available AND (tool-only is off OR caller is allowlisted).
       This is the gate cognition should use to decide 'LLM path vs symbolic
       path', because llm_available() ignores tool-only and over-reports."""
       if not llm_available():
           return False
       try:
           from utils.generate_response import _llm_tool_only, _LLM_TOOL_CALLERS
           if _llm_tool_only() and caller not in _LLM_TOOL_CALLERS:
               return False
       except Exception:
           pass
       return True
   ```

2. In `intrinsic_goals.generate_intrinsic_goals`, change the gate at `:948`
   from `if not llm_available():` to
   `if not llm_callable_by("intrinsic_goals"):` and call `_varied_symbolic_goal`
   inside it (it already does). Net effect: in the default tool-only config the
   **rich** path now runs.

3. Delete the narrow `_symbolic_intrinsic_goals` (`:210`) and its fallback use
   at `:1067–1073`. The LLM-enabled branch's empty-result fallback should also
   call `_varied_symbolic_goal(context, long_mem)` — there is no reason the
   LLM-empty fallback should be poorer than the LLM-disabled one. Keep
   `_SYMBOLIC_GOAL_SEEDS` only if something else imports it (grep first;
   currently nothing does).

**Files:** `brain/utils/llm_gate.py`, `brain/cognition/intrinsic_goals.py`.

**Acceptance criteria.**
- With `ORRIN_LLM_TOOL_ONLY=1`, `llm_enabled: true`, key present:
  `generate_intrinsic_goals` produces a goal whose title is drawn from
  `_concept_deepening_goals` / `_open_question_goals` / `_goal_from_recent_research`
  when those have material — not a fixed seed title.
- No code path references `_symbolic_intrinsic_goals` after the change.

**Test.** `tests/brain/test_intrinsic_goal_origination.py` (new): seed a KG with
two confident concepts and a long-memory `[research]` entry; force tool-only;
assert the produced goal title contains one of those topics, not a seed-table
string. Also assert the cold-start path (no KG, no memory) still yields a valid
emotion-template goal via `_template_goal_from_emotion`.

**Rollback.** Revert the gate to `llm_available()`; the helper is additive.

---

## Phase 1 — Fix E: `inner_loop` defers honestly when no generative path exists

**Problem (I4).** With the LLM tool unavailable, `run_inner_loop` builds a draft
prompt, gets `None` from `routed_response`, hits `if not draft: break`
(`inner_loop.py:473–474`) on round 1, and returns near-empty content. Callers
can't distinguish "thought hard, concluded little" from "System 2 could not run
at all," and may treat the empty string as a failed thought.

**Change (interim, until Fix D).** At the top of `run_inner_loop` (after the
imports/early setup, before the round loop at `:460`), short-circuit when no
generative path is callable:

```python
from utils.llm_gate import llm_callable_by
if not llm_callable_by("inner_loop"):
    log_activity("[inner_loop] deferred: deliberation requires the llm tool "
                 "(symbolic mode not yet implemented)")
    return {
        "content": "",
        "rounds_used": 0,
        "meta_decision": "defer",
        "critique_applied": False,
        "escalated": False,
        "confidence": 0.0,
        "reason": "deliberation requires llm tool",
    }
```

Then audit `run_inner_loop`'s callers (`think_module`, `state_processor`,
reasoning consumers) so a `meta_decision == "defer"` with this `reason` routes to
the **symbolic planner** (`pursue_goal._symbolic_plan` / `temporal_planner`)
rather than logging a failed thought. `grep -rn "run_inner_loop" brain` to
enumerate.

**Files:** `brain/think/inner_loop.py` + each caller surfaced by grep.

**Acceptance criteria.**
- With LLM not callable, `run_inner_loop` returns `meta_decision == "defer"`,
  `reason == "deliberation requires llm tool"`, and makes **zero**
  `routed_response` calls.
- No caller treats that typed defer as an error/failed-thought.

**Test.** Monkeypatch `routed_response` to raise if called; assert
`run_inner_loop(...)` returns the typed defer dict and never invokes it.

**Rollback.** Remove the early-return; behaviour reverts to empty-draft break.

> Note: Fix E is the honest stopgap. Fix D replaces the early-return with an
> actual symbolic deliberation path. E ships day 1 so nothing silently no-ops in
> the meantime.

---

## Phase 2 — Fix B: widen symbolic goal origination

**Problem (I1).** Even with Fix A, the symbolic generators are
research/concept/question-driven. To make origination read less like a lookup
and more like "wanting something specific," add generators sourced from learned
structure and from his own history. These become additional candidates inside
`_varied_symbolic_goal` (`intrinsic_goals.py:836`, the `candidates += …` block).

**New generators (each returns `List[Dict]` built via `_mk_goal`):**

1. **`_causal_frontier_goals(limit=2)`** — pick an aspiration's `driven_by`
   outcome whose causes are weakly known and propose investigating what brings
   it about. Use `causal_graph.get_causes(outcome, min_score=0)`; if the best
   `causal_score` is below `_CAUSAL_LEAD_MIN_SCORE` (0.50), the cause is a
   genuine gap → goal "Find out what actually brings about *{outcome}*." This is
   a goal emerging from a hole in his **learned causal model**, not an affect
   bucket. (Grounding: Newell & Simon means-ends; the gap *is* the motivation.)

2. **`_tension_goals(limit=1)`** — surface a conflicting belief pair from
   `inference`/contradiction structure and propose "resolve whether X or Y."
   Reuse the contradiction machinery `inner_loop._critique_contradiction` was
   meant to invoke, but symbolically (`inference.py` forward-chaining over the
   relation graph). Provenance is internal and specific.

3. **`_autobiographical_continuity_goals(limit=2)`** — read `autobiography.json`
   / `THREADS_FILE` for an unfinished commitment or a thread last touched long
   ago, and propose its concrete next step. This is the "specific thing you can
   picture" the critique says is missing — sourced from his own history.

**Wiring.** Add the three to the `candidates` list in `_varied_symbolic_goal`
between the existing concept/question generators and the emotion-template
fallback. The existing dedup/cooldown/`_acceptable_goal_subject` filters
(`:844–862`) already gate them — no changes needed there. Keep the
emotion-template as the always-valid floor (`:864–866`).

**Files:** `brain/cognition/intrinsic_goals.py` (new helpers + wiring); read-only
use of `symbolic/causal_graph.py`, `symbolic/inference.py`, `paths` for
`AUTOBIOGRAPHY_FILE`/`THREADS_FILE`.

**Acceptance criteria.**
- Given a causal graph with a valued outcome whose top cause scores <0.50, a
  causal-frontier goal appears in the candidate pool.
- Given a stale alive thread, a continuity goal referencing its title appears.
- All new candidates pass `_acceptable_goal_subject` and dedup unchanged.

**Test.** Unit-test each generator in isolation with a fixture graph/threads
file; integration-test that `_varied_symbolic_goal` can return each type and
never crashes when its source is empty (returns `[]`, falls through).

**Rollback.** Remove the three from the `candidates` list; helpers are inert.

---

## Phase 3 — Fix D: symbolic mode for `inner_loop` (real System-2 restoration)

**Problem (I4).** `inner_loop` has an LLM-shaped primary path with **no symbolic
equivalent**, so when the LLM tool is disabled the named home of deliberation is
dark. This is the same "promote the symbolic path to primary" conversion
`docs/LLM_COGNITIVE_AUDIT.md` prescribes for other call sites — `inner_loop` is
the one that never had a symbolic path written.

**Change.** Implement `run_inner_loop_symbolic(topic, context_text, context,
max_rounds)` with the same return contract, and have `run_inner_loop` dispatch to
it (replacing Fix E's early-return) when `not llm_callable_by("inner_loop")`.
Map each step to the symbolic owner already in the repo:

| inner_loop step | symbolic replacement | module |
|---|---|---|
| draft | plan/decision as the "draft" | `temporal_planner`, `symbolic_search` |
| `_critique_primary` | rule check + reflection | `symbolic/rule_verifier.py`, `symbolic_reflection.py` |
| `_critique_contradiction` | belief-conflict detection | `symbolic/inference.py`, `causal_graph.py`, `knowledge_graph.py` |
| `_critique_value_alignment` | value check | `selfhood/values_check.py::evaluate_input_against_self`, `symbolic_self_model.py::self_assess` |
| critique synthesis | rank issues by rule confidence | (no LLM) |
| ToT branch judge | score candidates | `symbolic/pattern_scorer.py` + rule-confidence ranking |
| meta-decision | keep `meta_controller.decide` | already symbolic-capable |
| confidence | derive from rule-coverage / inference confidence, not uncertainty-word density | `intrinsic_motivation.uncertainty`, inference `_MIN_INFER_CONF` |

The loop structure (rounds, escalation thresholds, depth-bandit reporting) is
preserved; only the per-step generators swap from `routed_response` to the
symbolic owners. Iterate: draft a plan → run the three symbolic critics →
revise the plan (re-run planner with the critique as a constraint) → escalate by
widening search depth rather than calling a deeper model.

**Files:** new `brain/think/inner_loop_symbolic.py` (or a `_symbolic` branch
inside `inner_loop.py`); read-only use of the modules above.

**Acceptance criteria.**
- With LLM not callable, `run_inner_loop` returns non-empty `content` derived
  from the symbolic planner + critics, `meta_decision` ∈ {act, output, defer},
  and makes **zero** `routed_response` calls.
- The three critic categories each demonstrably alter a draft in a crafted case
  (a value-violating draft is revised; a KG-contradicting draft is flagged).
- Depth-bandit `record_outcome` still receives a reward.

**Test.** `tests/brain/test_inner_loop_symbolic.py`: monkeypatch
`routed_response` to raise; feed a topic with a known causal cause + a
value-relevant framing; assert the output incorporates the causal lead and
passes `values_check`. Assert determinism is acceptable (seeded).

**Risk/rollback.** Medium — the symbolic critics may be weaker than the LLM
critics initially. Gate behind a flag (`ORRIN_INNER_LOOP_SYMBOLIC=1`, default on
only when `not llm_callable_by`); if quality regresses, fall back to Fix E's
honest defer. The depth bandit will learn whether symbolic rounds add value.

---

## Phase 4 — Fix C: learned `driven_by → aspiration` association

**Problem (I2, I5).** `_DRIVE_TO_ASPIRATION` (`intrinsic_goals.py:702`) is a
static inversion of a 4-row table; `_serves_aspiration` (`:746`) is a `dict.get`.
A goal "serves" an aspiration because the table says so, not because its outcome
moved that aspiration. `credit_aspirations` (`:753`) then rolls completions up by
that asserted link (`:787`).

**Change.** Make the mapping a **learned** association that drifts with evidence,
keeping the table as the cold-start prior:

1. Persist a small association table `data/drive_aspiration_credit.json`:
   `{driven_by: {aspiration_title: weight}}`, EMA-updated.
2. On goal completion (in `credit_aspirations`, where outcomes are already
   tallied), credit the aspiration whose *valued outcome* the completed goal's
   result actually advanced — derived from existing reward/causal credit signals
   (`data/domain_action_credits.json`, `action_reward_ema.json`,
   `causal_graph.get_effects` of the goal's action). Update the EMA weight for
   `(driven_by → that aspiration)`.
3. `_serves_aspiration(driven_by)` returns `argmax_weight` over the learned
   table, falling back to `_DRIVE_TO_ASPIRATION` when a drive has no evidence yet
   (cold start). So the link starts as the prior and becomes earned.

**Files:** `brain/cognition/intrinsic_goals.py` (rewrite `_serves_aspiration`,
extend `credit_aspirations`), new data file via `paths`.

**Acceptance criteria.**
- A drive with no completion history maps via the prior (unchanged behaviour).
- After repeated completions whose outcomes advance a *different* aspiration than
  the prior, `_serves_aspiration` shifts to the evidenced one.
- `credit_aspirations` remains idempotent and never auto-completes an aspiration
  (existing protection at `:797` preserved).

**Test.** Simulate N completions crediting an off-prior aspiration; assert the
learned mapping crosses over after enough evidence and that cold-start drives
still use the prior.

**Risk/rollback.** Medium (touches the aspiration accounting). Feature-flag the
learned lookup; if disabled, `_serves_aspiration` is exactly today's behaviour.

---

## Cross-cutting test & verification

- **Regression:** run `tests/brain/` (esp. `test_phase4_causal_closure.py` and
  any intrinsic-goal/aspiration tests) after each phase.
- **Default-config smoke:** a scripted run with `ORRIN_LLM_TOOL_ONLY=1`,
  `llm_enabled: true`, key present — confirm (a) intrinsic goals come from the
  rich symbolic path, (b) `inner_loop` either defers honestly (Phase 1) or runs
  symbolically (Phase 3), (c) no `tool unavailable` bursts in
  `model_failures.txt`.
- **Offline smoke:** `llm_enabled: false` — confirm identical goal-origination
  behaviour to the tool-only default (the whole point of Fix A is that these two
  configs now converge).

## Done-when

- I1/I3: default-config goals are KG/question/research/causal-frontier-sourced;
  the narrow seed table is deleted.
- I4: `inner_loop` never silently returns empty — it either runs symbolically
  (D) or defers with a typed reason (E).
- I2/I5: `_serves_aspiration` is a learned link with the table as cold-start
  prior.
- The default tool-only deployment and the offline deployment produce the same
  symbolic cognition — the LLM is purely additive enrichment when callable.
