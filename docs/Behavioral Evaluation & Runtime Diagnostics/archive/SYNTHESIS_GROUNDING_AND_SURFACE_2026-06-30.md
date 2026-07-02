# Synthesis: Grounding Gaps & the Lived Surface (2026-06-30)

> **Purpose.** Distilled main points from a set of review/analysis notes on Orrin.
> Two goals: (A) capture the **feature ideas** worth building (lived-surface UI,
> ablation/sandbox mode), and (B) capture the **diagnosed bugs** worth fixing,
> ranked by how much they block the whole thesis from working. Each item is
> grounded in a claim about what is actually in the code so it can be turned into
> a work ticket.

---

## Part 0 — The through-line (read this first)

The single most-repeated finding: **grounding signals exist but don't reach the
learners.** Orrin *computes* "was this correct" (effect ledger, `_result_is_real`,
sandbox) and "did Ric want this" (`person_model`, `feedback_log`) — but those
signals don't feed the things that actually learn. The good idea (anti-gaming
grounding) is applied in one place and not carried through to the others.

So the fixes are **consistency work, not reconception.** The highest-leverage
move: pick one build, close the full loop end-to-end — *machine verifies → Ric
corrects → both signals train the persistent model and the native weights* — and
prove it compounds over ten rounds. That one circuit is the whole bet, and right
now it's the one that isn't connected.

---

## Part A — Feature ideas

### A1. The frontend should show a *lived surface*, not "everything the machine knows"

Backend cognition is strong and the observability layer is strong. To feel like
**one point of experience**, the UI should not dump the full machine state. It
should show a lived surface:

- what Orrin is **attending to** right now
- what it feels **pressured by**
- what **changed**
- what it is **avoiding**
- what it is **trying to resolve**

Qualities the surface should make legible (these double as product goals):

- **Continuity** — remembers enough to feel like the same entity over time.
- **Attention** — decides what matters now instead of reacting randomly.
- **Useful behavior** — can help, reflect, research, organize, explain, and
  initiate things within limits.
- **Personality without fake-depth** — consistent tone/preferences/rhythms,
  without pretending to be more than it is.
- **Inspectability** — you can see *why* it did something: what pressure caused
  it, what memory influenced it, what goal was active.
- **Stability** — does not spiral, spam, hallucinate wildly, or loop.

### A2. Ablation / "Run Configuration" panel (lesion testing)

Because the README describes Orrin as **separable machinery** (memory, goals,
control signals, host sensing, workspace arbitration, action selection, reward,
persistence, idle consolidation) running a defined loop (sensing → recall →
workspace prep → ignition → action selection → execution → reward accounting →
persistence → maintenance → consolidation), we can **turn systems off before a
run** and observe what breaks. This is ablation testing for the "experience."

Proposed toggles (per-run):

- Memory · Goals · Affect/control signals · Workspace · Metacognition
- Host coupling · Idle consolidation · LLM tools · Research tools · Persistence

Each run gets **stamped with its config**, e.g.
`run_2026_06_27_memory_off_goals_on_workspace_on`, so traces can be compared:

- Memory off → behaves, but **continuity collapses**.
- Goals off → acts but **does not pursue** (drifts).
- Workspace off → behavior becomes **less unified / scattered**.
- Affect signals off → **priorities flatten**, loses urgency/caution/rhythm.
- Host coupling off → stops **feeling embodied** in the machine.
- Metacognition off → stops **noticing its own patterns**.

Value: proves which pieces actually contribute to the experience instead of
assuming they do. Also a compelling **sandbox mode** product/research feature —
users toggle parts of the mind and watch personality/behavior change.

### A3. Cleaner substrate ↔ consciousness separation (the "veil")

The ideal: the **veil is the only path from substrate → consciousness**, so
consciousness can never read raw plumbing. Current state is thread-level +
arbiter-mediated (the convergence layer stands in for strict separation). The
cleaner version would be:

- Substrate as an **always-running state authority**.
- The conscious loop as a **separate always-running reader** that can only see
  the **perceived/felt projection — never the keys.**

Work: seal the leaks so consciousness can never read raw substrate.

---

## Part B — Ranked diagnosis (biggest blockers first)

### B1. Grounding signals don't reach the learners *(root issue — everything else is a symptom)*

The three cut wires from "what was actually right" → "what gets learned":

- **Language model:** reward-filtered experience replay exists
  (`episode_replay.py`, thresholds at reward ≥ 0.65) — but it routes into the
  **bandit's weights**. The native transformer trains on **raw book text with no
  reward filter at all.** The two learners eat different diets: the
  action-selector gets *graded* experience, the language model gets *ungrounded
  imitation.*
- **Goal level:** closes on **familiarity**, not verified effect (see B2).
- **Person level:** modeled from **conversation**, not from **corrections to his
  work.**

Fix this and the thesis has a chance; leave it and nothing else matters.

### B2. Two contradictory goal-closure paths → hollow completion

The **effect-grounded** path and the **satiety** path coexist, and satiety
re-opens the exact door the effect ledger bolts shut. Empirically this is what's
breaking the runs: **7-millisecond DONE flips, stub-only artifact folders,
255-of-256 marked "done"** (one flipping DONE→FAILED in 7ms). Most fixable single
bug: **kill satiety closure, or gate it behind a real recorded effect.**

### B3. No decay on appraisal signals → saturation and looping

Drives and confidence pin at the ceiling with **no homeostatic pullback**, so he
runs "**hot and flat**": repeats the same phrase dozens of times and stops
producing. The affect system can push up but **not relax down.** Until it's
damped, the loop can't sustain varied, exploratory behavior no matter how well
the rest is wired.

### B4. The capability is caged and dormant

`execute_python_code`, `write_file`, `scrape_text` were selected **zero times**
across every run; self-written-code folders are **empty**; the produce-and-check
loop is never exercised. Even the verifiable-work path that *is* built doesn't
run. Fixing B1 also requires making the **doing** actually happen, not just
wiring it.

### B5. Integration risk from sheer surface area

~**507 modules, ~124k lines, one developer**, visible refactor scars
("Phase 4D," "lifted verbatim to stay under the 600-line limit"). Parts are
well-built, but such systems fail in **emergent ways** that only appear when it's
all running — which is what the runs show. Ongoing tax that makes every other fix
harder to land and verify.

### B6. Native learner is tiny + continual learning is fragile

The **4-layer nanoGPT** caps the ceiling regardless of grounding, and lifelong
training courts **catastrophic forgetting** — the "interleave a little replay" in
`read_a_book` is a band-aid over an unsolved problem. Not a wiring fix; a
scaling/research risk underneath everything.

> **Honest split:** B1–B4 are **integration** — concrete and fixable, where every
> hour should go first because they're what's breaking the runs. B5–B6 are
> **structural** — the cost of ambition and the limit of the substrate, which no
> amount of wiring resolves.

---

## Part C — The "learning" failure, in detail (why he can't actually learn physics)

This is a concrete expansion of B1 + B2, worth keeping because it names the exact
joints.

### C1. He reads but never produces-and-checks

`research_topic` queries DuckDuckGo + Wikipedia and stores text in memory — **pure
intake.** He reads; he never solves a problem, derives a result, or computes a
number and checks it. Physics/math are among the **most verifiable** domains that
exist — the check genuinely exists (a right answer) — and he simply isn't reaching
for it.

### C2. "Understood" is encoded as "feels familiar"

In `goal_satiety.py`, a "learn X more deeply" goal closes when
**uncertainty(topic) drops below a threshold** — defined as "further effort stops
yielding new information / repeated searching stops surfacing anything new." That
is the **illusion of understanding encoded directly as a completion rule** — the
single most documented failure mode in human studying (re-read until familiar,
mistake fluency for mastery).

The critical joint: a **real gap is revealed by a failed attempt against a
checkable target**, and that failure aims the digging. Orrin never attempts
anything checkable, so nothing can fail, so the only "gap" available is "this
still feels unfamiliar." His loop and a real learner's loop look identical from
outside but differ at the one joint that matters: **his gap is a feeling, not a
failure.**

### C3. The fix is one wire — a produce-and-check step

Derive a result and grade it against the known answer; work a problem and check
it against the key; make a numerical prediction and compare. Then **being wrong**
(not being unfamiliar) becomes the gap signal that drives what he studies next.
Flips the loop from "read until it stops surprising me" → "attempt until I stop
getting it wrong."

The damning part: **he already has the missing piece.** The sandbox
(`execute_python_code`, with `math`/`statistics`) is exactly an answer-checker for
a derivation or numerical result. Selected **zero times** in every run reviewed.

### C4. Long-term goals never take the wheel

Two more cut wires explain why research bouts never compound into months-long
deepening:

1. **Long-term goals never actually run.** `evolution.py` builds a `long_term`
   goal with subgoals and a roadmap, but closure logic says aspiration and
   long-term goals are "**never committed anyway**." "Committed" is what makes a
   goal get picked up and executed step-by-step. So long-horizon goals are
   **signposts, not drivers** — a title over a pile of short errands.
2. **The short errands close on familiarity** (C2). Each committed research bout
   ends on satiety, not demonstrated understanding.

Result: what should be long-term deepening is a **sequence of disconnected short
reads**, each ending when material stops feeling new, under a heading that never
drives anything. No thread carries "here's the gap I hit last week, go work on
exactly that" across sessions (the long-term goal that would own it never
executes), and none carries it within a session (short goals close on
familiarity). This is why "understand quantum mechanics more deeply" showed up as
a **completed** goal in the June-25 data — it closed on satiety, fast, and got
filed done.

**Fix both:** let the long-term goal actually **commit/drive**, and make its
sub-tasks **close on passing a check** rather than on novelty running out.

---

## Part D — The effector gap (why orchestration has "no hands")

- **No host/web effectors to chain.** `recognise_step_action` maps step text onto
  the registered action set — which is research/introspection tools
  (`research_topic`, `fetch_and_read`, `leave_note`, …). **No browser driver, no
  real-filesystem tool, no shell;** the codegen path is LLM-gated and
  safety-allow-listed. Orchestration runs fine — it just has nothing in its hands
  except thinking and reading. *"A body's nervous system but no hands that reach
  your laptop."*
- **Verifier is leaky at closure.** Despite reafference + satiety + milestone
  gates, runs still show **hollow DONE flips** and artifact folders holding only
  housekeeping stubs. Satiety-based tier closure can mark a growth goal "done"
  when **novelty is exhausted** — not the same as producing the intended artifact.

Accurate framing: the chaining/verification loop **exists and is good.** What's
far off is (a) **wiring real, un-sandboxed effectors** into it — partly
engineering, partly a deliberate decision to remove the safety cage — and (b)
**closing the reliability gap** so the verifier it already has can't be satisfied
without a durable effect.

---

## Suggested fix order (actionable)

1. **B2 / C2 — Kill or gate satiety closure** behind a recorded real effect.
   (Smallest, highest-signal bug; stops hollow DONE flips.)
2. **B1 — Route graded signal into every learner.** Reward-filter the native
   transformer's diet the way replay already filters the bandit's; feed
   corrections (not just conversation) into the person model.
3. **C3 / B4 — Wire the produce-and-check step** and make the sandbox actually get
   selected (exercise the doing).
4. **C4 — Let long-term goals commit/drive**; make sub-tasks close on passing a
   check.
5. **B3 — Add homeostatic decay** to appraisal signals so behavior can relax down.
6. **A3 — Seal substrate→consciousness leaks** (veil as the only path).
7. **A1 / A2 — Build the lived-surface UI and ablation/sandbox panel** (also the
   instrument that will *prove* the above fixes changed behavior).
8. **B5 / B6 — Ongoing:** manage integration surface; treat native-learner scale +
   catastrophic forgetting as a tracked research risk, not a wiring task.
