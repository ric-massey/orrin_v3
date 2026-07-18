# The Five Sources of "Good" — Quality Grounding Design (2026-07-18)

Status: **Direction + build plan. Not started.** One piece (the originality veto)
landed 2026-07-18 as a byproduct of the Run 9 exemplar-scrape finding; the rest is
open. Sequenced *after* the Run 9′ acceptance gate and dovetails with
`RUN9_DEEP_ANALYSIS_2026-07-15.md` Finding 7 (the difficulty ladder). This is the
"how does Orrin know what is good?" doc — the value-grounding companion to the
mechanism-level quality-standard component.

## Origin

This began as a question Ric worked out from first principles: *how do humans
define "good"?* The answer that survived scrutiny — and that this doc builds
against — is that humans do not begin with a definition of good; they **build one
from several interacting sources, continually corrected by actual consequences.**
Five sources, roughly:

1. **Grounded consequences.** Some outcomes matter without an abstract judge —
   pain/safety, hunger/nourishment, failure/success, wasted/efficient effort,
   rejection/acceptance. The brain compares what happened against what it expected
   and updates preference from the error (reward-prediction-error learning is one
   established account of part of this). "That method was good because it *worked*,
   cost less, and made no new problem." Judgment trained against reality, not a
   free-floating aesthetic call.
2. **Exemplars and prototypes.** After many good explanations/songs/programs you
   form both specific remembered cases and compressed central patterns, so a new
   thing can trigger "this resembles the good ones." Fuzzy, structural, learned —
   not exact string-match. (This is the brain-side cousin of the quality standard's
   golden set, and of the originality veto's *opposite* — the veto catches "this is
   copied", exemplars capture "this has the shape of good".)
3. **Integrated subjective value.** "Good" is not one property. The brain fuses
   usefulness, effort, novelty, coherence, danger, beauty, social meaning, current
   goals, and expected consequences into a single context-sensitive value
   (orbitofrontal / ventromedial prefrontal systems are implicated). You don't
   compute it consciously; experience compresses it into "that was good."
4. **Social training.** Imitation, praise/criticism, teachers, shared standards,
   watching which work survives contact with reality. Part of "good writing" is
   real communicative success; part is absorbing what your community treats as good.
5. **Reflective revision.** "Why did I like that? Was it effective or merely
   impressive? Am I rewarding confidence instead of accuracy?" The layer that turns
   intuitive judgment into explicit rules and sometimes corrects learned
   preference — but it never starts from nothing; it inspects a value system
   already shaped by 1–4.

**Working definition.** *Good is a learned prediction about which patterns will
satisfy our needs, goals, values, social expectations, and model of the world —
continually corrected by actual consequences.*

The corollary that makes this a design doc and not an essay: **Goodhart's law is
not an Orrin bug, it is a property of any valuer that cannot directly sense the
thing it values.** For abstract targets like "is this excellent research?" there is
no direct quality sensor — humans *and* Orrin infer quality from fallible
correlates, and every correlate can be optimized away from the thing it once
tracked (impressive-language→intelligence, grades→understanding,
popularity→truth). So the goal is not "replace cognition with deterministic
checks." It is: **use deterministic checks for genuinely deterministic properties;
build the broader judgment from multiple independent signals, exemplars,
consequences, explicit purposes, and revision.** An n-gram check can establish
"this was copied too closely." It cannot establish "this is good work."

## Where Orrin stands: four weak analogs and one missing keystone

| # | Source | Orrin's current analog | State |
|---|--------|------------------------|-------|
| 2 | Exemplars/prototypes | `quality_standard/` golden set + predicate; `originality.py` veto | **Weak but real.** Bar has ~0 live hours (first promotion 2026-07-17); veto now guards it. |
| 3 | Integrated value | multi-factor selector, `value_ema`, commitment score, Pearce–Hall rate | **Weak but real.** Fuses many signals; was trained on race-noised labels (Finding 7c). |
| 4 | Social training | human ratification (`ratify.py` + UI); Orrin can't edit his own bar | **Weak but real.** The disposer exists; the proposer had nothing good to propose until recently. |
| 5 | Reflective revision | metacognition, regret, `evolve_core_value`, self-model updates | **Weak but real.** Can inspect and revise, but inspects a value system missing its floor. |
| 1 | **Grounded consequences** | effect ledger pays *events*; understanding goals close on **satiety** | **Structurally absent.** See below. |

Sources 2–5 exist in weak form. The keystone — #1 — is the one Orrin cannot feel.

## The missing floor: outcomes that matter without a judge

A human knows a research method was good partly because **it worked** — it answered
the question, it survived contact with reality. That is the one source of "good"
that needs no exemplar and no human: a grounded consequence.

Orrin has no analog for the *epistemic* case. His "Understand X more deeply" goals
close on **quenched drive** (satiety) — a metabolic event ("I have attended to this
enough"), not an epistemic one ("I can now answer what I couldn't before").
Nothing anywhere tests whether he can answer, after the goal, a question he could
not answer before it. The effect ledger grounds *production* consequences (an
artifact exists, is reused) but not *understanding* consequences (a question is
answered, and the answer changes a later decision).

This is why every other source is currently measuring against other sources instead
of against reality:

- Exemplars (#2) are graded by the predicate and by prior exemplars.
- Integrated value (#3) is trained by reward that pays events, not answered
  questions.
- Social training (#4) ratifies what the proposer surfaces from #2.
- Reflection (#5) inspects #2–#4.

**The whole stack is a hall of mirrors until #1 exists.** Your essay's own logic
says the other four are supposed to be *corrected by* consequences; without the
grounded floor there is nothing doing the correcting, and Goodhart has free run
because every proxy is checked only against another proxy.

## The build: make #1 real, then make the other four sound against it

### Rung 0 — epistemic close-out (the keystone; Run 10 item 14)

Give understanding goals a grounded success test that isn't satiety.

- **At goal creation**, derive a concrete question from the *gap* that spawned the
  goal. The intrinsic generators already carry that gap symbolically (curiosity /
  prediction-error / uncertainty on some concept) — surface it as a stored
  `question` on the goal. No LLM required.
- **At close**, the artifact must *answer* that question, and the answer is scored
  **against the question**, not against effort or length. Satiety may still gate
  *attention*, but it cannot close the goal alone.
- **Ground it in a consequence**: the strongest version is "the answer changes a
  later decision" — trace via the decision reason payload when a later selection
  cites the answered question / its memo. That is the analog of "the method
  survived contact with reality."
- **Observable** (already written into the Run 10 gate): every completed
  understanding goal carries `question` + `answered: true/false`; ≥ 1 goal whose
  answer changes a later selection/decision.

This is B18 (metacognitive calibration) in embryo: predict-then-verify against a
question is exactly a feeling-of-knowing probe.

### Then — soundness passes on 2–5, each corrected by the new floor

- **#2 exemplars.** Keep the originality veto (built). Add difficulty to the
  ratchet: exemplars carry the difficulty of the goal that produced them, so the
  bar rises with demonstrated competence, not just with volume (Finding 7e's
  `definition_of_done`-tightening).
- **#3 integrated value.** Re-baseline outcome learning on honest labels (Finding
  7c) — the reward EMAs / Pearce–Hall rate / `value_ema` from Runs ≤ 8 are suspect
  where research goals are involved. Once #1 exists, "answered a hard question"
  becomes a reward source distinct from "did an event."
- **#4 social training.** Nothing to add structurally; it becomes *useful* once the
  proposer surfaces genuinely-good work (post-veto, post-floor) instead of scrapes.
- **#5 reflective revision.** Point regret / value-evolution at the new floor:
  "I closed this on satiety but never answered the question" is a reflective
  correction that is currently impossible to represent.

## Design principle: put enforcement where the self-model can't reach it

A structural law behind almost every run failure, stated here because it is not
written down anywhere and it governs *how* the fixes above should be built:

> **A safeguard that routes through the judgment or state of the thing it
> safeguards inherits that thing's blind spots. It fails in exactly the cases the
> monitored system cannot see — which are the cases you built it for.**

The whole run history is this law:

- **The relocating monopoly (Runs 2–8).** Each fix measured the layer where the
  monopoly *currently was* — ignition source, generator flavor, commit sort, value
  EMA. It reappeared one layer up every time, on the surface nothing was yet
  measuring. The monitor moved; the pathology moved with the un-measured surface.
- **Reward blind to impossibility (Run 9).** `decide_to_write_code` was blocked
  369/369 times and held the #2 reward EMA, because the thing measuring "effect"
  could not represent "this was impossible." A self-report of activity graded
  itself as success.
- **Ignition saturation (Run 9).** The gate read 100% ignited because the signal
  feeding its threshold was pinned at 1.00, and the metacognition that would notice
  "I'm always thinking" could not see that *its own input* was saturated. The
  monitor shared the monitored system's blind spot by construction.

The rule that follows: **for any invariant whose violation is costly, push
enforcement OUT of the self-model and into a channel the self-model cannot
rationalize or route around** — a deterministic gate, a fail-closed test, an
external check. The self-assessed version is a nudge, not a wall; it is bypassed
not by disagreement but by the system mis-perceiving that the safeguard applies.
This is why every *durable* fix in this project is a mechanical guard, not a
reflection Orrin writes about himself: content-keyed credit (credit can't be
pumped), the anti-monopoly refractory, the launch/reset guards, and the
originality veto wired into the promotion gate (§Already built). A principle Orrin
"holds" about his own quality is worth less than a gate that refuses.

The scope, because it cuts both ways: you **cannot** push everything to
enforcement — Orrin is meant to be a self-directed agent, not a rule-executor, and
hard-coding his open-ended cognition would defeat the point. So the rule is
targeted: **mechanical enforcement for the load-bearing invariants** (corrigibility,
credit-can't-be-pumped, quality-can't-be-self-graded, no-monopoly, and — the one
this doc adds — understanding-can't-close-on-satiety-alone); **self-assessment for
the open-ended cognition** above that floor. The engineering skill is knowing which
is which, and the failure mode is trusting a self-assessed safeguard for an
invariant that needed a wall. The grounded floor (#1) is itself an instance: it
moves the *success test* for understanding goals out of Orrin's own satiety
judgment and into a question-answered check he cannot satisfy by feeling done.

## Sequencing

1. **Now → Run 9′ passes.** The acceptance gate proves *stability* (regulatory
   learning). Do not build curriculum on race-noised verdicts (Finding 7c).
2. **First honest life with exemplar promotion + the veto live.** Confirms #2's
   floor is trustworthy and un-scrapeable.
3. **Rung 0 (epistemic close-out).** The keystone. Turns satiety-closure into
   answered-question closure — #1 comes online.
4. **The difficulty ladder** (Finding 7e): recent verified-success streak → harder
   `definition_of_done` + build-on-prior required → quality bar ratchets from the
   resulting exemplars. Target: the Run 11 planning conversation.

Nothing here is exotic; most of it is *wiring existing pieces to a floor that does
not yet exist*. The one genuinely new thing is the floor itself — and it is the one
thing the whole value stack is supposed to stand on.

## Already built toward this

- **Originality veto** (`quality_standard/originality.py`, 2026-07-18) — protects
  #2 from canonising copied work. A deterministic check for a deterministic
  property, used as a veto, never as a quality judge — the exact discipline this
  doc argues for. See [Quality Standard](../wiki/Quality_Standard.md).
- **Effect ledger** — grounds *production* consequences (artifact exists / reused).
  The template for what #1 needs on the *understanding* side.
- **Intrinsic generators** — already compute the gap each understanding goal comes
  from; rung 0 surfaces that gap as a scorable question rather than discarding it.

## Related

- `../Behavioral Evaluation & Runtime Diagnostics/RUN9_DEEP_ANALYSIS_2026-07-15.md`
  Finding 7 — the difficulty ladder (the growth axis this floor unblocks).
- `../NEXT_RUN_TESTS.md` Run 10 item 14 — the epistemic close-out gate line.
- `../wiki/Quality_Standard.md` — the mechanism-level component + the veto.
- `archive/QUALITY_STANDARD_EVOLUTION_PLAN_2026-06-28.md` — the golden-set design.

*Written 2026-07-18, from Ric's five-sources analysis. The quality stack has been
measuring itself; this is the plan to give it a reality to measure against.*
