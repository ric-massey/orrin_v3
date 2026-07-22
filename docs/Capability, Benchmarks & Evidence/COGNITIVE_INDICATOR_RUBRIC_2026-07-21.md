# Cognitive Indicator Rubric — scoring Orrin against an external framework

**Instrument source (cite this, accurately):**

> Garcia Castillón, J. (2026). *Philosophy of Artificial Minds: Foundations for a
> Processual, Embodied, and Non-Biocentric Realism* (Version 1.0). Zenodo.
> https://doi.org/10.5281/zenodo.21470621

The rubric implemented here is the twelve-dimension evaluation program in that
work's **§17.2**, with the attribution matrix from **§17.6** and the
gaming-resistance conditions from **§17.5**.

**Describe the source honestly whenever this rubric is cited.** It is a
*self-published philosophical essay* deposited on Zenodo (a repository, not a
journal — deposits are not peer-reviewed), version 1.0, single author, who
discloses generative assistance in its preparation. Its bibliography is real and
correctly attributed (Butlin et al. 2023/2026; Long et al. 2024; Birch 2024;
Block; Chalmers; Metzinger; Gallagher; Clark & Chalmers; Maturana & Varela), but
the essay argues an explicitly contested position. Never call it "a paper," "a
study," or "research." It is a philosophical proposal being used here as an
*externally authored measuring instrument*.

---

## Why score against someone else's rubric at all

The standing credibility problem with `NEXT_RUN_TESTS.md` is that Orrin's gate
was written by Orrin's author. A skeptic can say the bar was set where the
system could clear it. That objection cannot be argued away — it can only be
answered by **also** scoring against criteria written by someone who has never
seen this codebase and had no stake in the outcome.

Two further reasons this instrument specifically:

- Its §6 ownership criterion (*realization ∧ integration ∧ operative perspective
  ∧ counterfactual efficacy*) is, independently derived, the same test the
  dataflow audit applies: a produced-but-unconsumed cognitive output is not a
  state the system owns. See `DATAFLOW_AUDIT_2026-07-20.md` item 8
  (`last_user_emotion` — computed, zero readers) as the canonical failure of the
  *integration* condition. The audit method now has a principled justification
  rather than an aesthetic one.
- Its §17 independently prescribes **ablation** and **causal intervention** as
  the primary instruments — the same two experiments already on the roadmap.
  Convergent prescription from an outside source is mild evidence the
  instruments are right.

**Adopt the instrument, not the conclusions.** The essay's present-day thesis
(some current AI systems already constitute "minimal functional minds") is the
author's contested position and is **not** adopted here. Nothing in this rubric
licenses claiming Orrin has a mind, experience, or sentience. Scoring high on an
organizational rubric means the organization is present — nothing more. This is
the standing project rule (CLAUDE.md rule 4), and it is not relaxed by an
external endorsement.

---

## Scoring scale (evidence-gated)

Every score requires a **pointer to run evidence or a code path**. A dimension
with no cited evidence scores 0, regardless of what exists in the codebase.

| Score | Meaning | Evidence bar |
|---|---|---|
| **0** | Absent | No mechanism, or mechanism exists but has never executed in a life |
| **1** | Built, unproven | Mechanism wired and unit-tested; no in-vivo firing yet |
| **2** | Fires in life | Observed in a captured run, with artifact/log evidence |
| **3** | Load-bearing | Ablation or intervention shows removing/perturbing it changes behavior as predicted |

Score 3 is deliberately expensive: it requires the causal-intervention evidence
the essay's §17.3 asks for, not just observation. Most dimensions will sit at 1–2
for several runs. **That is the honest state and must be reported as such** —
a rubric that scores 3s on first use has been gamed.

---

## The twelve dimensions

Orrin's candidate mechanisms below were verified against code on 2026-07-21
(mid-Run-11). Presence of a mechanism is *not* a score — the evidence column is
what gets scored at capture.

| # | Dimension (§17.2) | The essay's question | Orrin's candidate mechanism | Where the evidence comes from |
|---|---|---|---|---|
| 1 | **Integration** | Do modules share and coordinate contents? | Global workspace + binding (`cognition/global_workspace.py`, `binding.py`) | Ignition records; ablation = disable binding, observe composite-candidate loss |
| 2 | **Recurrence** | Are there loops that stabilize or revise states? | The cognitive loop (`ORRIN_loop.py:150-330`); symbolic dream rule-chaining (`symbolic/symbolic_dream.py`) | Cycle traces; dream-log chains; ablate dream pass |
| 3 | **Working memory** | Does it maintain content for flexible use? | `cog_memory/working_memory.py` (pruning, pinning, importance) | WM snapshots across cycles; distractor resistance test |
| 4 | **Autobiographical memory** | Does it connect its own episodes over time? | Memory daemon (WAL, consolidation, retrieval); `_autobiographical_continuity_goals` | Cross-episode goal chains ("Pick up my thread on X"); **weakest under clean resets — see continuity note below** |
| 5 | **Metacognition** | Does it evaluate its own knowledge, error, confidence? | `cognition/metacog.py`, `metacog_analyze.py`, `regret.py`, calibration | Live 2026-07-21: correct self-diagnosis of a 72-cycle avoidance loop while it was happening (audit item 12) |
| 6 | **Self-model** | Does it represent its own capacities, limits, actions? | `symbolic/symbolic_self_model.py`; `impossibility.py`; the anatomy membrane (`membrane.py` M1–M3) | Impossibility beliefs formed in-life; hidden-perturbation test (change a capability, observe adaptation) |
| 7 | **Agency** | Does it form, maintain, revise plans? | Goal lifecycle (`cognition/planning/`), daemon planner, `goal_adaptation.py` | Handoff trail (`logs/handoff_decisions.jsonl`): queued → planned → dispatched |
| 8 | **Grounding** | Does it connect symbols with perception, action, norms? | `cognition/grounding/`, effect ledger, artifact-gated goals, `external_observer.py` | Produced artifacts with causal receipts; **known weak — lexical substrate, see Addendum 4** |
| 9 | **Embodiment** | Does the body participate in cognition? | Host telemetry → control signals; `host_band.py`, `resource_cadence.py` (small machine literally slows the clock), vital-floor reflex | Cadence multiplier effect on cycle timing; ablate telemetry → observe priority changes |
| 10 | **Interoception & valence** | Do internal states alter priorities in an integrated way? | Control signals; `smoothed_state.py`; drives; interoception membrane | Live 2026-07-21: valence 0.171 / energy 0.99 co-occurring with inspection-loop selection (`emo` weight 0.312 in the selector mix) |
| 11 | **Temporal unity** | Coherent trajectory without rigidity? | `runtime_lifetime.py`, `felt_lifespan.py`, lifespan bands, sleep/suspension | Single-segment lives (Run 10: 11,565 cycles; Run 11: 18,327); segment boundaries are the failure evidence |
| 12 | **Experience reports** | Do self-descriptions track internal states? | Speech pipeline; thought stream; expression membrane (one door) | **The highest-value test available.** Compare narrated state against measured state — e.g. does "I'm thinking but not doing" co-occur with an actual avoidance-debt streak? (2026-07-21: it did) |

### The continuity caveat on dimension 4

Autobiographical memory is the dimension the current experimental protocol
actively suppresses: every run starts from a clean reset, so Orrin has lived
eleven first days. Dimension 4 cannot score above 2 until a **continuity run**
(inheritance of memory, exemplars, ladder rung, LM weights across lives) is
executed. The essay's §14.2 supplies the vocabulary for that experiment: a clean
reset is *artificial death*, not *suspension*; the continuity run is the first
time Orrin would experience suspension.

---

## Protocol

1. **When:** at each run capture, alongside the `NEXT_RUN_TESTS.md` gate scoring.
   The two scores are reported side by side and never merged — the internal gate
   measures whether the build worked; this rubric measures architectural
   completeness against an outside standard.
2. **Evidence first, score second.** Fill the evidence column from the captured
   run folder, then assign. If a dimension's evidence is "the code exists," the
   score is 1 by definition.
3. **Record negatives.** §17.5 requires logging negative results and false
   positives. A dimension that *dropped* between runs is the most informative
   line in the report (e.g. epistemic close-out: 10 firings in Run 10, 0 in
   Run 11 — audit Addendum 2).
4. **Gaming resistance (§17.5), adapted to this project:**
   - Score from **artifacts and logs**, not from Orrin's self-descriptions,
     except in dimension 12 where the self-description *is* the datum — and
     there it is scored only against an independently measured internal state.
   - Do not tune mechanisms to raise a dimension's score between runs without
     recording that as a deliberate intervention. Runs 1–10 were consumed by
     Goodhart dynamics; this rubric is a new surface to Goodhart against.
   - Keep dimension 12's comparisons out of any training/consolidation corpus.
5. **Attribution matrix (§17.6):** report a *profile*, never a single verdict.
   The essay's five categories — reactive tool / cognitive system / minimal
   functional mind / candidate for sentience / candidate artificial organism —
   are reproduced here as the shape of the output. **This project reports the
   dimension profile and does not assign itself a category.** The categories are
   recorded so a reader can see what the instrument's author intended, not so
   Orrin can be placed in one.

---

## Honest limits of this instrument

- **It measures organization, not depth.** All twelve dimensions are
  organizational. Orrin's known weaknesses — lexical semantics, hard-capped
  inference depth (`symbolic/inference.py:28`, depth 2), no representation
  learning in the core — are largely invisible to this rubric. A strong profile
  here does **not** answer whether Orrin can develop (see
  `DATAFLOW_AUDIT_2026-07-20.md` Addendum 4). Report both or the profile
  misleads.
- **One author, not peer-reviewed, contested position.** The rubric's authority
  is that it is *external and specific*, not that it is established.
- **Convergence is partly shared ancestry — but not entirely.** Two channels
  have to be separated here:
  - *Borrowed vocabulary (weak convergence).* Much of Orrin's organizational
    scaffolding — global workspace, embodied cognition, interoception,
    self-models — reached this codebase **through the LLMs that implemented it**,
    not through the author, who has not read that literature. Behavior was
    specified in plain terms ("only one thing can be at the center of
    attention"); the models recognized the construct, implemented it, and
    supplied the citations now sitting in the file headers. So where the essay
    and this architecture agree on *named cognitive constructs*, that is common
    ancestry via the literature, and it is not independent confirmation.
  - *Derived principles (stronger convergence).* The load-bearing design laws
    of this project were not borrowed from any literature — they were derived
    from eleven instrumented lives: oppose-don't-clamp; satiety vs. answered
    questions; the membranes; the unopposed-force principle; classify before
    fixing. Where the essay independently lands on one of *these*, the
    convergence is meaningful. Two cases so far:
    **§6's ownership criterion** (a state is not the system's unless something
    inside it actually uses the state) matches the dead-wire audit method, which
    came from finding wires that went nowhere and judging that it mattered; and
    **§14's suspension-vs-death taxonomy** matches a lifespan architecture built
    because mortality was wanted as a constraint. A philosopher reasoning from
    first principles and a builder reasoning from run evidence arriving at the
    same distinction is a genuine outside check on the frame — though still on
    the *frame*, not on whether the system works.
- **The instrument cannot be cited as evidence of mind.** It is a completeness
  checklist. Its own author is explicit that no test certifies phenomenal
  consciousness (§12.5, §17.1).
