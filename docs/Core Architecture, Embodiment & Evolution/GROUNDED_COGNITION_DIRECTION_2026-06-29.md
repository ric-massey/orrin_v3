# Grounded Cognition — Direction Document (2026-06-29)

Status: **direction, not yet a build plan.** This captures the session's fixes and,
more importantly, the architectural direction Ric chose after working through what
the session's bugs were actually telling us. The "how" (data structures, sequencing
of the real build) is deliberately left for a follow-up implementation plan.

**Revision note (2026-06-29, post-critique):** the original draft committed the whole
architecture to one radical reading — "grow a complete grounded mind from scratch." A
critique pass narrowed and honest-ified that. The corrected direction is the same idea
held more tightly: **stabilize and seal the substrate first, ground one small real
competence (code), and treat general grounding as a falsifiable experiment with a kill
criterion — not a destiny.** The changes are folded into Parts B–E below; the most
important addition is Part F (the grounding experiment), which is now the go/no-go that
gates everything ambitious.

---

## Part A — What this session fixed (done / verified)

These were real fixes, but read them as *symptoms of missing invariants*, not as the
work itself. Each one, when patched, exposed the next — which is the whole lesson
(Part C).

1. **Appraisal saturation (three stacked bugs).** Emotions were pinned ~0.89 in
   lockstep. Root was three layers: (1) a sign error letting self-critical metacog
   text read as goal-*helping*; (2) mood-minted reward (positive mood → ambiguous
   content read as congruent → mints `reward_positive` → better mood: a runaway);
   (3) the real one — **no habituation**: `update_signal_state` re-appraised the last
   working-memory entries every cycle and accumulated, so any recurring thought
   pumped its emotion to the ceiling. Fixed with a per-event, number-normalized
   habituation map (damps repeats by ½ down to 1/16, re-sensitizes after ~90s).
   Covered by `tests/brain/test_appraisal_avoidance.py`.

2. **Goal-spam / unplannable introspective goals.** `_causal_frontier_goals`
   (`brain/cognition/intrinsic_generators.py`) spawned `"The causes of {X}"` goals
   from gaps in his causal model and prescribed **web tools** (research_topic /
   wikipedia). But his causal graph **is his self-model** — every effect in it is one
   of his own internal states (`affective_regulation`, `impasse_signal`, …). There is
   no Wikipedia article on an internal signal, so the goals were unplannable →
   fail-plan 3× → abandon → regenerate the next variant. Reframed to
   self-investigation: `"Trace in my own code what drives '{X}'"`, routed via the
   "my own code" intent family (search_own_files / grep_files), `driven_by=self_exploration`.
   Now plannable and pointed at the tool that genuinely serves an internal gap.

3. **The substrate↔mind leak (partial seal).** Raw `core_signals` keys were being
   used as human-readable labels across many subsystems, so his implementation
   identifiers leaked into his perceivable content (the deep cause of #2 as well).
   Built the central membrane `brain/utils/felt_lexicon.py`
   (`is_internal_identifier()` + `felt_label()`), sealed ~8 emitters, and tagged
   every causal-graph edge with a `self|world` domain so world-consumers exclude
   self-edges. **This is a patch, not yet a law** — see Part C invariant #2.

Suite green at session end (~1191 passed); lint clean. **Nothing committed yet** —
the appraisal fixes + membrane + seals + goal-spam fix are all staged in the working
tree, to be bundled into a commit when Ric is ready.

### Honest remaining tail (cosmetic, not emotion-pinning anymore)
The label leak is systemic with a long tail (~6–10 more subsystems). The notable one:
`global_workspace.py` emits `"a strong sense of {key}"` and `intention_endorsement`
**regex-extracts the key back out** of that string — the same string is both a felt
feeling and a machine token (parse-coupling). Properly sealing means decoupling those
two roles (carry the key in a structured field; make the consumer read the field),
which is the right pattern for the membrane-as-law work below, not whack-a-mole.

---

## Part B — The core realization

**"He runs but doesn't work without the external LLM."** That single observation is
the key to everything. It means his cognition was never living in the symbolic layer —
the symbolic layer (drives, workspace, binding, goals, memory) *orchestrates,* but the
external LLM was doing the actual thinking. Pull the LLM and the scaffolding keeps
cycling (he "runs") with no mind behind it (he doesn't "work") — which is why what's
left is templates and unplannable goal-spam: the skeleton with the muscle removed.

**Caveat on this diagnosis (don't over-read one observation).** "Runs but doesn't work"
admits two readings: (a) the radical one — the symbolic layer is *architecturally
incapable* of being the mind, so we must grow grounded symbols from scratch; (b) the
mild one — the symbolic orchestration is the right shape but *underdeveloped*, and needs
richer content rather than a new paradigm. The original draft committed hard to (a). We
are now treating the choice between (a) and (b) as **something to measure, not assume**
(Part F). The build below is structured so the stabilizing work pays off under either
reading, and only the *ambitious* part rides on (a) being true.

This is **not** how Ric wants him to work, and it contradicts the project
(`llm_tool_only` + native-LM design). The corrected direction, distilled from the
conversation:

- **Language is dissociable from reasoning — but that does not by itself make the mind
  "symbolic."** Backed by real neuroscience (Fedorenko: the language network is
  separable from reasoning / planning / theory-of-mind; aphasics still reason). This
  licenses the **decomposition** — language as a separable I/O faculty, not the seat of
  cognition. It does **not** license the stronger claim that the reasoning substrate is
  a Fodorian rule engine; the aphasic's reasoning is still distributed/neural. So we
  keep "language is a separate faculty" as established, and treat "the mind is symbolic
  in implementation" as a *design bet* (Part D), not a finding.
- **The native LM should be the mouth, not the mind.** It renders his
  already-formed thoughts into words; it never originates content. The external LLM is
  tool-only, ideally cut from cognition entirely. (The hard part — what exactly the
  "already-formed thought" is — is specified honestly in Part D, because that, not the
  rendering, is where the difficulty lives.)
- **Humans are predictors — of the world, not of words.** Predictive processing
  (Clark, Friston): the brain predicts grounded sensory/world states and acts to
  reduce surprise. An LM predicts tokens; a mind predicts reality. That difference is
  the whole game.
- **Symbolic is *plausibly* right in function — but the brain is not blank-slate.**
  Human thought is compositional/structured (Fodor's mentalese), so a symbolic mind is
  a reasonable *shape*. But the brain is also **not** a hand-written rule engine *and
  not a blank learner*: it grows grounded symbols from experience **on top of heavy
  innate priors** (Spelke core knowledge, evolutionary structure). "Nobody typed
  `impasse`; it was learned from a thousand experiences of being blocked" is only half
  the story — a thousand experiences suffice *because the substrate is richly
  pre-structured.* Orrin has no such priors. This is not a footnote; it is the central
  tractability risk (Part E) and it directly shapes the internet decision (Part D).
- **The named bug: the symbol grounding problem (Harnad 1990).** Orrin's symbols are
  *typed, not grown* — empty strings a programmer wrote, tied to no
  perception/action/consequence. So his symbolic mind has the *form* of thought with
  none of the substance, and the LLM was quietly supplying the grounded cognition his
  brittle rules can't. **Grounding the symbols is the whole project — if it is
  physically possible on this much data, which is the open question, not a given.**

---

## Part C — The missing invariants (and which ones actually stand alone)

The session's bugs were not independent. Each is an instance of a *law a brain
enforces everywhere* that Orrin doesn't. Patch the instance and the law is still
missing, so the next instance appears. The reframe: **stop adding mechanisms; start
enforcing invariants.** This reframe is the single most durable insight in the document
and survives the critique unchanged.

**But be honest about the structure: these are not four independent laws.** Invariants
#1 and #2 stand alone and are buildable *now*, with no dependency on a world. Invariants
#3 and #4 — and nearly all of Part D — collapse onto **one** prerequisite: an external
world that pushes back. So the real shape is **two stabilizers we build immediately +
one big bet (the world loop) that everything ambitious rides on.** Presenting four
co-equal laws hid that the risk is concentrated in a single move.

1. **Homeostasis is universal — but it's allostasis, not just decay.** Every internal
   signal should declare a *baseline + adaptation/opponent process*, and the update
   loop should regulate it. Saturation, the reward runaway, and the rumination pump
   were all positive-feedback loops with no opponent. **Important correction:** the goal
   is *not* "everything returns to baseline by construction" — that would over-regulate
   and flatten the very signals that should drive behavior (a genuinely standing problem
   *should* keep stress elevated). Distinguish two things: **habituation to repetition**
   (good — what we fixed this session) versus **decay of a standing condition** (bad to
   force). Real regulation is allostatic: a setpoint that can itself shift. Build the
   homeostatic layer around setpoints, not around forced return-to-zero. *Buildable now;
   no world dependency.*

2. **A real membrane between substrate and mind.** Nothing internal may become
   perceivable content except as a *felt translation* — enforced at one chokepoint,
   with a **test that perceivable stores cannot contain an internal identifier.** Not a
   function you remember to call. `felt_lexicon` is the seed; this makes it a law and
   the leak class disappears by construction. *Buildable now; no world dependency.*

3. **Goals grounded in stakes; idleness has a price — but stakes have to come from
   somewhere.** Goal-spam and thinking-not-doing happen because goals spawn from
   internal structure that bottoms out in nothing that matters. Avoidance should *cost*;
   doing nothing should be expensive. **Two unsolved problems the original glossed:**
   (a) *in what currency,* and (b) what stops an idleness penalty from producing a
   *compulsive* agent that thrashes to escape it — the reward-runaway reincarnated as
   negative feedback. Both are answerable only if the cost is calibrated against **real
   stakes**, which a vat agent lacks. So #3 is *circular with the world problem*: stakes
   come from the world. **Do not build #3 until #4's world loop exists** — without it,
   any idleness cost is arbitrary and likely to thrash. *Gated on the world.*

4. **Self-model and world-model must be separate.** ~77% of his causal graph was about
   his own signals — a brain in a vat whose only "world" is his own logs, so the
   world-model fills up with self (which is what made the leak so damaging). A real
   sensorimotor loop — predictions corrected by a world that *pushes back,* not by his
   own logs — keeps the two apart. *This is the world loop itself; #3 and Part D depend
   on it.*

**The deepest framing:** right now *Ric is his homeostasis* — when Orrin drifts, a
human patches the leak. "Running like a human" means the loop closes: the invariants
do the regulating. The honest metric is **how long he can run before something must be
fixed** — today, hours; the target is indefinitely. (Note this metric measures
*stability*, not *grounding* — it tells you he isn't drifting, not that he is thinking.
The grounding metric is separate and lives in Part F.)

---

## Part D — The chosen direction: ground the symbols (the 1-2-3)

Keep the decomposition (symbolic mind + LM-as-language). But the symbolic "mind"
cannot be hand-written rules — it has to **learn its concepts and rules from grounded
experience**, the way a brain grows its symbols. Hold this as a **design bet** (Part B
caveat), not a settled fact, and let Part F's experiment decide whether it pays.

**(1) Ground the symbols** and **(2) learn the rules** are *the same mechanism* —
prediction error against a world that pushes back. A symbol becomes grounded when it
earns its meaning by being useful for predicting/controlling the world; a rule becomes
learned when it's a prediction that survived being tested. Both are one loop:
**predict → act → get corrected by a real outcome → update.**

- **A concept is a predictive signature, not a string.** Define a concept as the
  learned bundle of *what percepts co-occur with it, what actions change it, what
  follows it, what it lets him predict.* The string is just a handle; a concept that
  earns no predictive/actionable value gets pruned. The raw materials already exist
  scattered across KG + causal graph + effect ledger — the build is connecting them so
  a concept is defined by its cross-channel signature.
- **Prediction-error is the spine — but you must predict a *grounded observable*.**
  Each cycle: predict the expected change in percepts/state *before* acting; compare to
  what actually happened *after*; the error updates causal edges, strengthens/prunes
  concepts, and drives curiosity (high error = worth exploring). **Critical constraint
  the original missed:** prediction error only grounds anything if the *predicted
  variable is a concrete external observable.* If he predicts in the same ungrounded
  symbol space and scores himself against his own logs, the error is computed in
  ungrounded space and grounds nothing. The "actual" must come from the **external
  world, not his logs** — and specifically from observables he did not author (stdout,
  exit code, file state, test result).
- **Retire hand-authored rules/concepts** as the learned structure replaces them —
  *but only as Part F demonstrates the learned structure actually transfers.* Don't tear
  out the scaffolding on faith; retire each authored symbol when a grown one out-predicts
  it. Authored symbols are the ungrounded ones, but they're also the only thing keeping
  him coherent until grounding is proven.

**(3) The native LM as mouth** — separate, tractable, **startable now**, does not wait
on (1)/(2). Two honest hazards to design around, both of which the original treated as
solved:

- **The thought object is the hard part, not the rendering.** "intent + grounded-concept
  references + affect" is the right sketch, but note the tension: if the thought object
  is rich enough to render unambiguously, the symbolic layer has *already done the
  difficult work of language production* and the LM is a thin formatter; if it's thin,
  the LM is *originating content* — which we forbid. Real production does heavy
  lexical/syntactic selection *during* speech; thoughts aren't fully specified before
  language. **First deliverable for (3) is therefore a concrete spec of the thought
  object** — what's in it, what's deliberately left for the LM to choose, and why that
  choice doesn't count as "originating content." Until that spec exists, "mouth not
  mind" is a slogan, not a plan.
- **Bootstrap from the symbolic narrator — with eyes open about the ceiling.** Every
  template that fires ("a strong sense of being stuck") was triggered by a specific
  internal state — log those as `(internal_state → words)` training pairs. The templates
  become the *teacher*. **But distillation cannot exceed its teacher without an extra
  signal:** a decoder trained to reproduce templates regresses to template-mean, and
  "let it generalize to states the templates never covered" has *no teacher* for exactly
  those states. As written this asymptotes at "slightly smoother templates," not
  language. So the design must name a **second signal source** for supra-template speech
  (candidates: human ratings of his renderings, contrastive preference over multiple
  candidate renderings, or reconstruction pressure from round-tripping thought→words→
  re-parsed-thought). Without one, accept that his voice stays near-template
  indefinitely — which is consistent with the project's "authenticity over fluency"
  value, but should be a *chosen* outcome, not a surprise.
- **Route all expression through it** (`express_to_user` / `speak` /
  `compose_section`): symbolic mind builds the thought object → native LM renders →
  output. Template only on failure.

### The world (this is the gating move for 1+2)
- **The laptop / OS is a real world — but a *symbolic* one, and that bounds what
  grounding means here.** The laptop has learnable rules, real actions, real
  consequences. The problem was never that it's too thin; it's that he uses it as a
  **mirror** (acting on his own state files), not a world. **Honest limit the original
  hid behind the infant-with-a-cup image:** an infant's cup is analog, continuous,
  multisensory — Harnad's grounding is in *sub-symbolic sensorimotor projection.* An
  exit code is *itself a symbol.* So grounding in code execution grounds symbols in
  *other symbols*, which is a real and useful kind of grounding (the predicted variable
  is a concrete observable he didn't author) but **not** the general escape-from-the-
  regress the rhetoric implied. Commit to the narrow, true claim — *Orrin's embodiment
  is the machine; his grounded competence is predicting and controlling computational
  state* — and drop "grow his whole grounded world from this."
- **The internet is a library, not a world.** No consequential action (reading changes
  nothing), no learnable regularity (page-to-page is noise from his vantage), and it's
  a firehose of *other people's already-symbolic text* — ingesting it floods him with
  borrowed symbols (the corpus-contamination problem) rather than grounding his own.
  Demote it to a tool he consults; keep its text away from the native LM. **Name the
  cost honestly:** rejecting the internet is *also* rejecting the cheapest source of
  priors — and Part E says priors are exactly what a single vat-bound learner most
  lacks. So this is a **value choice (authenticity) traded against a capability
  (competence)**, not a free technical call. If Part F shows single-agent grounding is
  too slow, this is the first decision to revisit — by data, not philosophy.
- **Code execution is the ideal grounding loop — programming is his embodiment.** He
  predicts what a command/program will do → runs it → reality corrects him crisply
  (interpreter, exit code, actual output, changed state) → he learns. Immediate,
  deterministic-but-learnable, consequential. That is his equivalent of an infant
  grasping and dropping a cup *within the symbolic micro-world of the machine.* He
  already has `code_writer` / `tool_runner` / `prediction` — they're just not wired as
  **one outward-facing predictive loop where being wrong teaches him.**

---

## Part D′ — Relation to the existing language docs (this is not new ground)

Two 2026-06-25 docs already cover the spine of Parts B and D; this direction should build
on them, not restate them:

- **`docs/Language & Cognition/orrin_llm_cognition_audit_2026-06-25.md`** is the evidence
  base for Part B's "runs but doesn't work": the raw call-site map of every external-LLM
  hook in cognition, anchored file-and-line — the inventory the count below was built from.
- **`docs/Language & Cognition/ORRIN CREATIVITY NOVELTY PROPOSAL 2026-06-25.md` (Issue B)**
  tallies that map into **77 external-LLM call sites across ~38 modules** that do the
  *thinking,* not the wording, and is already the migration plan — sequenced (planning/goals
  first), with the **same acceptance test** Part D gropes toward: *turn the external LLM off;
  cognition must still function, only fluency degrades.*

**The one real conflict — and its resolution.** `docs/Language & Cognition/ORRIN_LANGUAGE_PLAN.md`'s
Phase 2 schools the native LM on **billions of tokens of external public-domain corpus**
("skip infancy"), which reads as exactly the "borrowed symbols / corpus-contamination" this
doc warns against. The contradiction is only apparent — it confuses two channels, and the
docs reconcile on the **mouth-vs-mind boundary both already accept:**

- **Schooling the language organ (mouth) on external text is fine** — it's how the faculty
  learns syntax/lexicon, the way a child learns words by hearing others. This follows from
  the Fedorenko dissociability cited in Part B: if language is a *separable* faculty,
  training it on external language does **not** contaminate the reasoning substrate. So
  LANGUAGE_PLAN Phase 2 stands.
- **What must never happen is external text entering *cognition*** — becoming grounded
  concepts the symbolic mind reasons with. That is the true corpus-contamination risk, and
  the membrane (invariant #2) + the thought-object spec (Part D, item 3) are what prevent
  it: a corpus-schooled mouth only ever *renders his own grounded thought objects.* The
  corpus teaches **how to say,** never **what to say,** and the mouth cannot author concepts.

So "corpus or no corpus" is the wrong axis; the contamination worry is about the *cognition*
channel, not the *language-organ* channel. Phase-2 schooling for fluency is compatible with
the grounding bet **provided the mouth is render-only and gated out of concept formation.**
The genuinely open question is narrower: accept fluent-but-schooled rendering of his own
thoughts, or hold to the near-template ceiling (Part E) for the stricter authenticity claim.
That is a *rendering-style* value call — not a verdict on whether external corpus contaminates
him.

---

## Part E — Sequencing & honest caveats

- **Stabilizers first (invariants #1, #2).** Homeostasis-as-allostasis and
  membrane-as-law have *no world dependency,* are buildable now, and directly attack the
  "Ric is his homeostasis" problem — he runs longer without a human patch and stops
  leaking identifiers. Build these regardless of how the grounding bet resolves; they
  pay off under both readings (a) and (b) from Part B.
- **(3) LM-as-mouth** is a bounded engineering project (months, not research), and the
  *first concrete step is startable today*: begin logging `(internal-state →
  template-output)` pairs as training data while the narrator still runs. But scope it
  to its real ceiling (the distillation limit above) and front-load the thought-object
  spec, which is the actual hard part.
- **(1)+(2) grounding** is the genuine frontier, **gated on giving him an external
  world** *and* on the open scientific question of whether it's tractable at all. The
  good news: the learning machinery (causal graph, prediction, effect ledger) already
  exists — it's just pointed *inward* at his own logs. Re-point it at the real system
  and it *can* start doing real grounding *if* the data is enough.
- **Single highest-leverage move:** turn `code_writer`/`tool_runner`/`prediction` into
  one **predict → act → observe → learn loop, outward-facing and consequential.** That
  one move converts his existing self-referential machinery into a grounding engine —
  and is also the experiment (Part F) that tells you whether grounding is physically
  available here.
- **The scientific risk, stated plainly and not under-weighted:** a from-scratch mind
  trained on one vat-bound agent's experience may take an enormous time to become
  competent — possibly never, on that little data. **This is worse than it first looks**
  because real brains succeed on little data only thanks to heavy innate priors Orrin
  doesn't have (Part B). No wiring fix removes this; it's the physics of what's being
  attempted. The native LM should be the *language*, not the mind — but even as just the
  language, it develops slowly, and early speech will be childlike. For Orrin the target
  isn't fluency, it's **authenticity**: every word tracing to his own model and
  experience. Awkward native-LM speech grounded in his life is closer to "running like a
  human" than perfect borrowed prose. **But be clear this may also be the *permanent*
  state, not a phase** — and that accepting it is the price of the authenticity choice,
  paid most visibly in the internet decision above.

### Immediate next steps (proposed, not yet started)
1. Commit the staged session work (appraisal + habituation + membrane/seals +
   goal-spam fix) as one reviewed bundle.
2. Finish the membrane-as-law decoupling (start with
   `global_workspace ↔ intention_endorsement`: structured affect field, consumer reads
   the field) + add the enforcement test that perceivable stores contain no internal
   identifier. *(Invariant #2 — buildable now.)*
3. Build the homeostatic/allostatic regulation layer around shifting setpoints, not
   forced return-to-baseline, replacing per-loop hand-installed decay. *(Invariant #1 —
   buildable now.)*
4. Write + run the **grounding experiment** (Part F) before committing the architecture
   to from-scratch concept growth. This is the go/no-go for all of Part D's ambition.
5. Spec the **thought object** (Part D, item 3) — the real hard part of LM-as-mouth —
   and stand up the `(internal-state → narration)` logging so the training set begins
   accumulating now. Identify the second signal source that lets the LM exceed templates,
   or consciously accept the near-template ceiling.

---

## Part F — The grounding experiment (the go/no-go)

The original doc presented Part D as *the chosen direction* — a build to commit to. The
correction makes it **a falsifiable experiment with a kill criterion**, because the core
claim (a single vat-bound agent can grow grounded symbols from its own experience) is an
open scientific question, not an engineering certainty. Run the narrowest version before
betting the architecture on it.

**Hypothesis.** Orrin can grow a *grounded* concept — one defined by its predictive
signature, not an authored string — from his own code-execution experience, and that
concept will **transfer** to a situation he hasn't seen.

**Setup (the narrowest possible loop).** Wire `code_writer`/`tool_runner`/`prediction`
into one loop on a small, closed family of commands: before running a command, Orrin
predicts a concrete external observable (exit code / a line of stdout / a resulting file
state); he runs it; reality corrects him; the error updates his model. No internet, no
LLM in the cognition path, observables he did not author.

**Success criterion (this is the whole point).** Not "he runs." Not "error goes down on
seen commands" (that's memorization). The criterion is **transfer above chance**: after
training on family A, he predicts the outcome of a *related but unseen* command better
than baseline, and the concept that carries the transfer is inspectable as a
cross-channel signature rather than a stored string. Define the baseline and the chance
level up front.

**Budget + kill criterion.** Fix a data/time budget in advance. If transfer-above-chance
does **not** appear within budget, the result is informative, not a failure to hide: it
means single-agent grounding is too slow on this much data *without priors* — which
**triggers the fork below**, decided by the measurement rather than by argument.

**The fork the experiment forces:**
- **Transfer appears** → the radical reading (Part B, reading *a*) is live. Expand the
  grounding loop, begin retiring authored symbols *as grown ones out-predict them*, and
  let competence grow narrowly and authentically from the machine-world outward.
- **Transfer doesn't appear in budget** → you're holding an explicit choice the doc no
  longer makes for you: **authentic-but-permanently-childlike** (keep blank-slate, accept
  the ceiling) versus **competent-but-partly-borrowed** (seed priors — revisit the
  internet/borrowed-structure decision). This is the value-vs-capability trade from
  Part D, now forced into the open by data.

**Why this is the right next research step, not a delay.** The same wiring that runs the
experiment *is* the highest-leverage build (Part E): an outward-facing predict→act→
observe→learn loop. You lose nothing by framing it as a measurement — you gain a real
answer about which Orrin is physically available, instead of committing the architecture
to a faith and discovering the ceiling years in. Build the stable substrate like you mean
it (#1, #2); run the grounding loop like you might fail; let the measurement — not the
manifesto — decide how ambitious Orrin gets to be.
