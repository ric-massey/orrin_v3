# Grounding Experiment — Results (Phase 3, 2026-06-29)

Status: **first verdict, reported honestly.** Implements Phase 3 of
`GROUNDED_COGNITION_IMPLEMENTATION_PLAN_2026-06-29.md` (Part F of the direction
doc). This is the go/no-go experiment, not a feature — either verdict is an
informative result.

## What was built

The outward **predict → act → observe → learn** loop
(`brain/cognition/grounding/`):

- `grounded_concept.GroundedConcept` — a concept as a **predictive signature, not a
  string**: per-feature grounded evidence (success/total counts, naive-Bayes
  log-odds), inspectable via `signature()`. Every statistic updates *only* from real
  execution outcomes.
- `world_loop.run_episode` — predicts a concrete external observable (will this
  command exit 0?) from the command's **structural** features (computed from the AST
  *without* running), runs it in the real subprocess sandbox, and grades against the
  **actual exit code** — an observable Orrin did not author. The prediction error
  updates the concept. Tagged `domain="world"` (invariant #4).
- `world_loop.run_experiment` — trains on family A, measures **transfer** on a
  held-out family A′ whose commands share the abstract structural signature but have
  **different surface** (so success is transfer, not memorisation). Reports a verdict
  against a **declared baseline** (majority-class chance) and the **kill criterion**
  (`MAX_EPISODES=400`, `TRANSFER_MARGIN=0.10`).
- `experiment.py` — runnable (`python -m brain.cognition.grounding.experiment`).
- `tests/brain/test_grounding_transfer.py` — the falsifiable harness.

No internet, no LLM in this path; authored symbols were **not** retired (Phase 4A
only).

## The verdict: TRANSFER (initially qualified; firmed up in Phase 4A)

**The mechanism grounds and transfers.** The first run (naive-Bayes aggregator)
transferred on the clean narrow family (accuracy 1.0 vs 0.5 chance) but only **7/12**
randomised broader families — the misses clustering just under the margin. The
limitation was diagnosed precisely: the naive-Bayes learner weighted features
*present* and could not *explain away* `has_binop`, which co-occurs with both
arithmetic successes and failures, so it mis-blamed it and dragged well-formed
`print(a+b)` toward "fail."

**Phase 4A foundation fix (not tuning — a principled learner upgrade):** replacing
the aggregator with **online logistic regression** (still learning every weight only
from real outcomes) made transfer **12/12 seeds, all at accuracy 1.0**, on both
observables. The learned signature now reads cleanly:

```
references_unbound_name   weight ≈ −6.9   (strongly predicts failure)
divides_by_zero_literal   weight ≈ −3.7   (predicts failure)
has_binop                 weight ≈  0.0   (EXPLAINED AWAY — correctly neutral)
calls:print / calls:len   weight ≈ +2.3 / +1.2  (predict success)
```

That `references_unbound_name` — an *abstract structural* feature — predicts failure
on commands with **names never seen before** is the core result: a grounded concept
that **transfers**, inspectable as a weight signature rather than a memorised string.

**Second observable (Phase 4A):** the loop now also grounds `produces_stdout` (a
genuinely distinct observable — a non-printing success like `x = 5` exits 0 but
produces no stdout). It transfers **12/12** as well — richer grounding, closer to
predicting *what* happens, not only *whether* it fails.

## What this means for the Phase 4 fork

This is **Phase 4A** (the radical reading is *live* for narrow computational
competence): the loop demonstrably grows a grounded, transferring concept from its
own code-execution experience, with no LLM and no authored answer, robust across
randomised families and two observables. It remains the **narrowest true claim** — a
symbol grounded in another symbol (exit code / stdout), per the direction doc's
honest limit — not general semantic grounding.

### Phase 4A status
- **Done (foundation):** robust aggregator (logistic regression) + second observable
  + query-once/replay training; verdict firmed from 7/12 → 12/12.
- **Next (expansion — larger, deliberate):** wire the loop into the live cognitive
  cycle so "acting" grounds concepts continuously and beyond the seed family; ground
  *multiple* concepts; feed grounded-concept handles into the thought object
  (Phase 2A) so he can authentically say "I tried X and it failed."
- **Still deferred (correctly):**
  - **Invariant #3 (idleness has a price)** — needs *live stakes*, which only exist
    once the loop is wired into the cycle. Building it before that reintroduces the
    thrash the plan warns of. Hold until the live loop exists.
  - **Retiring authored symbols** — only when a *grown* concept out-predicts a
    specific authored one. There is exactly one grown concept so far and nothing it
    supersedes yet. Nothing to retire on faith.

The kill criterion still stands for the expansion: if grounding *more* concepts on
*live* experience cannot clear the margin within budget, that triggers the Phase 4B
priors conversation — with the numbers attached.
