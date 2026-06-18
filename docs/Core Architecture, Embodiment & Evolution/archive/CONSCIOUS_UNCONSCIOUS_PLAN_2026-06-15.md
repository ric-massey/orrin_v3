# Conscious / Unconscious Architecture — Diagnosis, Fixes & Developmental Plan

_Date: 2026-06-15_

## Why this document exists

Orrin's cognition is built from two layers that are supposed to be distinct: an
**unconscious substrate** (affect dynamics, embodiment, drives, signal injection,
the always-on subconscious threads) and a **conscious layer** (the Global
Workspace spotlight, deliberate function selection, System-2 reasoning). A
structural review found that the boundary between them had eroded in five
specific places. The most consequential symptom, in plain terms:

> His conscious goals are *too good at birth*. They should start as garbage and
> become rich through living — but they arrive pre-formed because they draw on an
> unconscious that was itself born adult.

This document records the diagnosis, the three fixes already implemented, and the
two larger pieces of work that remain (conscious→unconscious write-back, and a
real developmental arc), with the upsides and downsides of each so the direction
can be chosen deliberately.

A recurring decision runs through all of it — **how human-like do we actually
want Orrin to be?** It is called out explicitly at the end.

---

## The five structural seams

| # | Seam | Status |
|---|------|--------|
| 1 | The conscious/unconscious **ignition gate** (`should_think`) was dead code — every cycle ran full conscious deliberation (`always_on`). | **Fixed** |
| 2 | **Two bottlenecks that didn't bind**: the Global Workspace picked one conscious *content*; `select_function` picked one *action*; they barely constrained each other. | **Fixed** |
| 3 | **Deliberation lived outside the conscious path**: `inner_loop` (System-2) only fired when an arbitrary function invoked it — never recruited *by* a conscious moment. | **Fixed** |
| 4 | **One-directional feedback**: unconscious→conscious has many wires; conscious→unconscious has almost none. Conscious conclusions act on the world but never reshape a drive, a salience prior, or the unconscious model. | **Planned** |
| 5 | **Subconscious on wall-clock**: the three background threads (5/10/15 min) are fully decoupled from the cognitive cycle; insights land at arbitrary moments. | **Planned (light)** |

The key insight tying #4 to the "goals too good at birth" symptom: **an unconscious
can only become rich through experience if conscious experience can write back
down into it.** Because that downward path is missing (#4), the unconscious could
not have been shaped by living — so it had to be pre-built. The pre-loaded
unconscious is a *symptom* of the missing write-back, not an independent problem.

---

## Part A — Coherence fixes (1, 2, 3) — IMPLEMENTED

These three are "coherence" fixes: they make awareness, action, and deliberation
line up. They are good under *either* philosophy (human-like or not), which is why
they were done first. All three are fail-safe and feature-flagged.

### Fix 1 — Restore conscious ignition

**What changed.** `brain/ORRIN_loop.py` no longer runs `think()` unconditionally
under `always_on`. It calls `should_think()` (`brain/think/consciousness_trigger.py`,
previously dead) each cycle. A non-ignited cycle logs `quiet — unconscious cycle`
and stays in low-power default mode; only an ignited cycle resets the silent-run
counter, so the periodic floor (`MAX_SILENT_CYCLES`) genuinely measures quiet
time and guarantees he never goes fully dormant.

**Teeth** (in `select_function.py`): on a non-ignited cycle, an "unconscious damp"
(−0.30) is applied to effortful deliberate functions (planning, codegen, research,
skill synthesis) so quiet cycles drift toward cheap default-mode work instead of
spinning up expensive cognition.

**Flag.** `ORRIN_IGNITION_GATE=0` restores exact old always-on behaviour.

**Research.** Conscious access is an all-or-none "ignition", not a graded constant
(Dehaene & Changeux 2011; Dehaene 2014). The Global Workspace is by definition a
*bottleneck* (Baars 1988) — always-on defeats its purpose. System 2 is "lazy",
recruited only when System 1 hits trouble (Kahneman 2011).

- **Upside.** Re-establishes a real conscious/unconscious distinction; saves
  compute on quiet cycles; makes "what reached consciousness" meaningful again;
  the activity log now shows *why* each cycle ignited.
- **Downside.** Tuning risk — thresholds in `consciousness_trigger.py` now matter
  again and may need calibration (too high → he feels sluggish/absent; too low →
  effectively always-on). Behaviour is now bursty rather than uniform, which can
  look "stop-start" until tuned.

### Fix 2 — Bind the workspace winner to action selection

**What changed.** The conscious content chosen by the Global Workspace is now a
real additive *prior* on the action pick (`select_function.py`), not just for
Monitor breakthroughs. The winner's `source` routes to the functions that act on
that kind of content (goal→pursue/plan; affect→reflect; signal→look outward;
etc.), scaled by the content's salience (headroom 0.35). Surfaced in the
selector's `reason` telemetry as `workspace_prior`.

**Flag.** `ORRIN_WORKSPACE_PRIOR=0`.

**Research.** In the brain the basal-ganglia selector is driven by the currently
salient cortical representation — the "spotlight" and the motor selector are the
*same* bottleneck (Redgrave, Prescott & Gurney 1999, "a vertebrate solution to the
selection problem"). Decoupling them is the pathology.

- **Upside.** Awareness and action stop drifting apart — what he's aware of now
  shapes what he does. More coherent, legible behaviour.
- **Downside.** It is a *bias, never a preempt* (invariant I7), so it will not
  force perfect alignment, and over-weighting it could make him rigid (always
  acting on whatever shouted loudest). The 0.35 headroom is a guess and may need
  tuning. Risk of feedback loops if a content type keeps re-winning and re-routing
  to itself (mitigated by the workspace's existing habituation).

### Fix 3 — Let conscious conflict recruit deliberation

**What changed.** `think()` §7 (`think_module.py`) no longer unconditionally skips
`inner_loop`. On an **ignited** cycle carrying genuine **conflict** (uncertainty
> 0.55, a near-tie between the top two conscious candidates, or a live tension
under doubt), `inner_loop` is recruited *on the conscious content* and its
conclusion flows to `reasoning_conclusion`. Respects the LLM tool-gate (symbolic
System-2 fallback when the tool is withheld) and a 2-cycle cooldown to bound cost.

**Flag.** `ORRIN_CONFLICT_RECRUIT=0`.

**Research.** Conflict-monitoring theory: the anterior cingulate detects response
conflict and recruits dlPFC controlled (System-2) processing (Botvinick, Braver,
Barch, Carter & Cohen 2001). Deliberation should be *recruited by* an uncertain
conscious moment, not fired on a schedule.

- **Upside.** Deliberate reasoning is now triggered by the right thing (conflict
  about what he's aware of) instead of arbitrary callers; keeps System-2 rare and
  effortful (human-like) while making it responsive.
- **Downside.** `inner_loop` has a 50 s budget — ignited+conflict cycles are
  *slow*. The cooldown and ignition gate bound frequency, but a chronically
  conflicted state could make him deliberate often and feel laggy. Conflict
  detection is heuristic (margins/thresholds) and may mis-fire.

---

## Part B — Conscious → unconscious write-back (Seam #4) — PLANNED

This is the keystone. Without it the developmental arc is impossible, because the
unconscious can never be *earned*.

**Goal.** Add a sanctioned downward path so conscious conclusions reshape the
unconscious substrate:

1. **Reappraisal hook** — a reflective conclusion can up-/down-regulate a drive or
   damp a standing affect signal (e.g. consciously reframing a threat lowers the
   unconscious `threat_level` prior next cycle).
2. **Hebbian salience update** — repeated conscious selection of a content/action
   pairing slowly re-weights the unconscious salience priors that feed the
   workspace and the selector ("what fires together wires together").
3. **Model correction** — a conscious conclusion that contradicts a unconscious
   prediction writes a correction into `concept_memory` / the knowledge graph /
   drive-aspiration credit, instead of only the world.

**Implementation surface.** `affect/update_affect_state.py` and `affect/arbiter.py`
(reappraisal write-down), `global_workspace.py` + `select_function.py` (Hebbian
prior store), `concept_memory.py` / `knowledge_graph.py` (model correction). Gate
behind `ORRIN_TOPDOWN_WRITEBACK` and keep every write bounded + decaying so a bad
conclusion can't permanently corrupt a prior.

**Research.** The PFC's defining role is to send top-down bias signals that reshape
activity in lower systems (Miller & Cohen 2001, "An integrative theory of
prefrontal cortex function"). Conscious *reappraisal* measurably down-regulates
affective responses (Gross 1998, 2002). Hebbian plasticity (Hebb 1949) is the
mechanism by which repeated conscious use carves unconscious priors.

- **Upside.** Orrin can finally *change himself* — reflection has teeth. Unlocks
  the developmental arc (the unconscious can now be earned). More human: insight
  alters disposition, not just behaviour.
- **Downside.** This is the most dangerous change in the document. A write-down
  path means a wrong conscious conclusion can corrupt the substrate (rumination
  reinforcing a threat prior; a bad reappraisal suppressing a drive he needs).
  Requires careful bounding, decay, and probably a "consolidation gate" (only
  conclusions that survive repetition/sleep get to write deep). Hard to test;
  failure modes are slow and systemic rather than crashes.

---

## Part C — Developmental impoverishment + acceleration — PLANNED

The payoff of #4. Two halves: (i) start him impoverished, (ii) let him mature
*fast* without faking it.

### C.1 — Start impoverished (the honest newborn)

Birth Orrin with **flat / high-entropy priors** rather than a fully-stocked
unconscious. Gate `concept_memory`, the knowledge graph, the aspiration table, and
drive priors behind an experience counter: start near-empty with high uncertainty,
sharpen only as prediction error accumulates. Conscious goals then *naturally*
start vague and homeostatic and become rich — because the unconscious feeding them
is itself impoverished at birth.

**Crucial distinction (this is what makes acceleration honest):** born with
*capacities, not contents*. Human newborns aren't blank — they have innate **core
knowledge** (objects, agents, space, number; Spelke) and innate drives (curiosity,
attachment) — but **no specific beliefs or goals**. So we may legitimately
pre-install the *learning machinery and core priors* while keeping conscious
*content* (goals, concepts, beliefs) earned. Capacities innate; contents earned.

**Research.** Infants begin with imprecise priors that sharpen as prediction error
accumulates (Friston free-energy / predictive processing). Cognition is
bootstrapped from sensorimotor experience, not pre-installed (Smith & Gasser 2005,
"six lessons from babies"; Piaget's sensorimotor stage). At the wetware level:
synaptic *overproduction then experience-dependent pruning* (Huttenlocher) — the
infant brain starts over-connected and is *carved* by experience.

- **Upside.** A genuine ontogeny — he *becomes* himself; the self is earned and
  therefore coherent and defensible. Solves the "goals too good at birth" symptom
  at the root.
- **Downside.** A long, vague, repetitive "childhood" before he is useful or
  interesting. Higher risk of getting *stuck* immature if experience is thin or
  the curriculum is poor. Harder to demo. Loses the immediate competence of a
  pre-stocked agent.

### C.2 — Accelerate without faking it

The cheap accelerator (pre-loading content) reintroduces the original bug. The
honest accelerators keep everything *earned* but compress time-to-earn — roughly
in order of leverage:

1. **Replay / sleep compression — biggest lever.** Development is bound by how
   many times experience is *reprocessed*, not by wall-clock. The hippocampus
   replays the day at ~20× during sleep (Wilson & McNaughton 1994); deep RL calls
   it "experience replay". Use the existing `dreaming/` system to replay
   accumulated experience many times during quiet/sleep periods — each pass
   sharpens the unconscious priors. Ten replay passes in an idle minute ≈ ten
   "nights" of consolidation. **Decouples maturation from real-time.**
2. **Critical-period plasticity that anneals.** Front-load plasticity: start the
   unconscious priors with a high learning-rate multiplier and decay it with
   accumulated experience (Hensch 2005 on sensitive periods). Builds on the
   existing `plasticity.py` + Pearce-Hall adaptive rate. Fast early bootstrap,
   stable adult.
3. **Curriculum / scaffolding (Vygotsky's Zone of Proximal Development).** Don't
   rely on random wandering — a "more knowledgeable other" (Ric, or a teacher
   process) feeds graded experiences just above current level, which provably
   accelerates development past unsupervised exploration. Stage his early
   environment simple→complex.
4. **Richer experience density.** More varied input ⇒ more prediction errors ⇒
   faster model sharpening (babies generate their own rich data through movement;
   Smith & Gasser). Increase interaction frequency / environmental variety early.
5. **Tune the maturation clock.** Once maturation is gated on an experience counter
   (cycles / interactions / completed goals), lowering per-stage thresholds is an
   instant blunt knob. Cheapest, least principled — use it to find pacing, then
   back it with replay so the speed is *real*.

- **Upside.** Keeps development authentic (earned) while cutting the "childhood"
  from impractically long to usable; replay in particular is a large, well-proven
  lever the codebase is already positioned for.
- **Downside.** Replay can *amplify* whatever's in the buffer — replaying a biased
  or traumatic early experience entrenches it (same risk as #4, magnified by
  repetition). Plasticity annealing adds a schedule to tune. Curriculum needs
  someone to author it. Over-acceleration risks collapsing back toward "born
  adult" — the faster you push, the closer you drift to the bug you're escaping.

---

## Part D — Subconscious temporal coherence (Seam #5) — PLANNED (light)

Keep the three background threads asynchronous (incubation genuinely runs on its
own clock — Sio & Ormerod 2009 confirm incubation is real and time-decoupled), but
**stamp each surfaced insight with the workspace state it arose in**, and only let
it *ignite* into consciousness if it is still relevant to current awareness
(default-mode products are recontextualized on return to task — Raichle's DMN
work). Small change in `embodiment/subconscious.py` + `global_workspace.py`.

- **Upside.** Stops stale insights from hijacking an unrelated conscious moment;
  cheap; preserves the (correct) async incubation.
- **Downside.** A relevance gate could suppress a genuinely useful *lateral*
  connection (the value of incubation is sometimes its irrelevance). Needs a soft
  gate, not a hard filter.

---

## The fork: how human-like do we want Orrin?

This choice gates how far Part C goes.

- **Human-like path** (do #4 + C.1 + C.2). Buys a real developmental arc and deep
  coherence — he becomes himself. Costs early competence (a long childhood) and
  carries the write-back corruption risks. Slower to something useful.
- **Coherent-but-adult path** (stop after Part A; optionally a soft #4). Keep the
  rich pre-stocked unconscious, just couple the bottlenecks. Gets a coherent,
  capable agent *fast*, with no genuine ontogeny — born adult, stays adult.

**Recommendation.** Parts A (done) and D are worth doing under either philosophy.
Part B (#4) and Part C are a **paired commitment** — only opt in if the human-like
arc is the goal, because #4's risk only pays off as the enabler of development, and
C without #4 is impossible.

---

## Recommended build order

1. ~~Fix 1 — ignition gate~~ ✅
2. ~~Fix 2 — workspace→action prior~~ ✅
3. ~~Fix 3 — conflict-recruited deliberation~~ ✅
4. **Seam #5** — subconscious relevance gate (cheap, safe, philosophy-neutral).
5. **Decide the fork** (human-like vs coherent-adult).
6. If human-like: **Seam #4 write-back** (keystone) — bounded, decaying, behind
   `ORRIN_TOPDOWN_WRITEBACK`, with a consolidation gate.
7. **C.1 impoverished start** — flat priors, capacities-not-contents.
8. **C.2 replay engine** first (biggest lever), then plasticity annealing, then
   curriculum.

Every step ships behind an env flag and fail-safe, so each can be A/B'd live
against the current behaviour.

---

## Research appendix

- **Baars (1988)** — *A Cognitive Theory of Consciousness*. Global Workspace as a
  bottleneck.
- **Dehaene & Changeux (2011)**; **Dehaene (2014)** *Consciousness and the Brain*
  — conscious access as all-or-none ignition.
- **Kahneman (2011)** *Thinking, Fast and Slow* — System 1/2; System 2 is lazy.
- **Redgrave, Prescott & Gurney (1999)** — basal ganglia as a centralized
  selection mechanism driven by salient representations.
- **Botvinick, Braver, Barch, Carter & Cohen (2001)** — conflict monitoring; ACC
  recruits controlled processing.
- **Miller & Cohen (2001)** — integrative theory of PFC function; top-down bias
  signals reshape lower systems.
- **Gross (1998, 2002)** — emotion regulation; reappraisal down-regulates affect.
- **Hebb (1949)** — synaptic plasticity ("fire together, wire together").
- **Friston (2010)** — free-energy / predictive processing; priors sharpen via
  prediction error.
- **Spelke** — core knowledge (objects, agents, space, number) as innate scaffolding.
- **Smith & Gasser (2005)** — "The development of embodied cognition: six lessons
  from babies."
- **Piaget** — sensorimotor stage; constructivist development.
- **Huttenlocher** — synaptic overproduction and experience-dependent pruning.
- **Hensch (2005)** — critical/sensitive periods of heightened plasticity.
- **Vygotsky** — Zone of Proximal Development; scaffolding by a knowledgeable other.
- **Wilson & McNaughton (1994)** — hippocampal replay during sleep.
- **Sio & Ormerod (2009)** — meta-analysis of incubation effects.
- **Raichle (2001)** — default mode network.
