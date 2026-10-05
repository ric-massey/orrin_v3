# Butlin-14 Experimental Matrix — Orrin

**Instrument source (cite this, accurately):**

> Butlin, P., Long, R., Elmoznino, E., Bengio, Y., Birch, J., Constant, A.,
> Deane, G., Fleming, S. M., Frith, C., Ji, X., Kanai, R., Klein, C., Lindsay, G.,
> Michel, M., Mudrik, L., Peters, M. A. K., Schwitzgebel, E., Simon, J., &
> VanRullen, R. (2023). *Consciousness in Artificial Intelligence: Insights from
> the Science of Consciousness.* arXiv:2308.08708.

The fourteen **indicator properties** (Table 1 of that report) derived from
recurrent processing theory (RPT), global workspace theory (GWT), higher-order
theories (HOT), attention schema theory (AST), predictive processing (PP), and
agency & embodiment (AE). If a later version of the report is used, re-check the
indicator wording against it before scoring.

**What this document is.** The companion to
`COGNITIVE_INDICATOR_RUBRIC_2026-07-21.md`. That rubric scores twelve
organizational dimensions from a single-author essay; this one scores the
fourteen indicators from a multi-author, theory-derived report and — the point
of the file — pairs every indicator with an **experiment** that could move it
from "exists" to "load-bearing." The two profiles are reported side by side at
capture and never merged.

**What this document is not.** The report itself treats the indicators as
evidence *under computational functionalism*, not as a test for consciousness,
and it does not treat the count of indicators as a verdict. This project adopts
the same limit and goes further (CLAUDE.md rule 4): **an indicator present in
Orrin names an engineering mechanism, nothing more.** No sentience, experience,
or consciousness claim follows from any row of this matrix, at any score.

---

## Scale (same as the companion rubric)

| Score | Meaning | Evidence bar |
|---|---|---|
| **0** | Absent | No mechanism, or the mechanism does not match the indicator's definition |
| **1** | Built, unproven | Wired and unit-tested; never shown firing in a captured life |
| **2** | Fires in life | Observed in a captured run with artifact/log evidence |
| **3** | Load-bearing | Ablation or intervention changes behavior as predicted (or a confound-screened cross-run natural experiment — same bar as the Run 11 scorecard §L) |

Two extra rules for this instrument:

- **Match the definition, not the name.** Orrin has a module named after nearly
  every theory in the report. A row scores against what the indicator actually
  requires (e.g. PP-1 requires predictive coding *in input modules*, not
  prediction somewhere in the agent). Where Orrin's mechanism is adjacent but
  not a match, the row says **adjacent** and scores 0 or 1.
- **Scores below are a pre-capture baseline from a code read on 2026-09-27 plus
  the Run 11 capture.** They are the starting line, not a result. Re-score from
  the run folder at every capture.

---

## Part A — The indicator map

| ID | Indicator (Butlin et al.) | Orrin mechanism (verified in code 2026-09-27) | Match | Baseline | Evidence pointer |
|---|---|---|---|---|---|
| **RPT-1** | Input modules using algorithmic recurrence | Perception (`cognition/perception/fs_perception.py`, `look_around.py`, `environment.py`) is single-pass polling. The *cognitive loop* is recurrent, but that is not the input module. | **Absent** | **0** | — |
| **RPT-2** | Input modules generating organized, integrated perceptual representations | `cognition/binding.py` builds bounded composite "situation" candidates from atomic contents before workspace competition | Partial (integration happens post-input, pre-workspace) | **2** | Binding fed workspace situations all life (07-03 run); Run 11: composites competing throughout |
| **GWT-1** | Multiple specialized systems operating in parallel | Affect/control signals, perception, goals daemon, memory daemon, subconscious threads, metacog monitor each produce candidates independently (`global_workspace._candidates`) | Yes | **2** | Run 11 ignition records; daemons run as separate lanes |
| **GWT-2** | Limited-capacity workspace → bottleneck + selective attention | `cognition/global_workspace.py`: one winner per cycle, salience competition, hysteresis; `cognition/attention.py`: 3-slot filter with affective hijack | Yes | **2** | `workspace_broadcast.json` stream; Run 3/11 ignition logs (incl. the monopoly findings — the bottleneck is visibly real) |
| **GWT-3** | Global broadcast: workspace contents available to all modules | Winner broadcast into context; `bound_goal()` read by ~15 modules (speech, selection, meta-controller, simulate, goal I/O); selection prior in `think_utils/selection/boosts.py`; top-down `workspace_writeback.py` | Yes | **2** | Readers verified by grep; ablation flags exist (see E3) |
| **GWT-4** | State-dependent attention → using the workspace to query modules in succession for complex tasks | Ignition gate (`loop/deliberate.ignite` → `deliberation_gate.should_think`) recruits inner_loop on salience/conflict; Hebbian priming in `workspace_writeback.py` biases next-cycle competition. `symbolic/reasoning_router.py` queries sources in a **fixed** order, which does not count. | Partial | **1** | No capture has yet measured winner(t) → module-queried(t+1) |
| **HOT-1** | Generative, top-down, or noisy perception modules | `symbolic/symbolic_dream.py` (offline rule-chaining), `think/simulate.py` (lookahead), writeback priming (top-down bias on what wins). None of these generates *percepts*. | Adjacent | **1** | Dream chains fired in Run 11 (written to WM) |
| **HOT-2** | Metacognitive monitoring that tells reliable perceptual representations from noise | `think/attention_weights.py` + `think/signal_router.py`: learned per-source credibility, reward-driven. `global_workspace._is_noise` is a fixed filter, not monitoring. | Partial | **1** | No capture has tested a known-noise source |
| **HOT-3** | Agency guided by a general belief-formation/action-selection system, with a strong disposition to update beliefs from metacognitive monitoring | `cognition/metacog.py` + `metacog_analyze.py` notes into WM; `cognition/calibration.py` (Brier/bias → control); impossibility beliefs; rut breaker | Yes | **2** (3 longitudinal) | Run 11: live self-diagnosis of a 72-cycle loop; Run 11 scorecard §L: affect-drift guard 3,415 → 6 mode-flaps |
| **HOT-4** | Sparse and smooth coding generating a "quality space" | MiniLM embeddings (`brain/utils/embedder.py`, `memory/embedder.py`) used in retrieval and selection text similarity — smooth but dense, and over text, not over perceptual states | Adjacent | **0** | — |
| **AST-1** | A predictive model representing and enabling control over the current state of attention | **None found.** `attention.py` has hedonic adaptation (a reactive rule), not a model that predicts attention. No module forecasts the next workspace winner. | **Absent** | **0** | Grep 2026-09-27: no attention-schema / attention-forecast code |
| **PP-1** | Input modules using predictive coding | `cognition/prediction.py`, `symbolic/prediction_engine.py` predict *outcomes*; prediction error drives reward/affect (`think/loop_helpers.py`). Input modules do not predict their input or pass error-only signals. | Adjacent | **1** | prediction_error fires into affect each cycle |
| **AE-1** | Agency: learning from feedback, selecting outputs to pursue goals, flexible across competing goals | Contextual bandit, commitment value + rotation (`commitment_value.py`), goal competition, effect-ledger reward, aspirations | Yes | **2** (3 longitudinal) | Run 8: F2 intervention moved occupancy 90.9% → 42.6%; Run 11 §L: worst action 4,899 → 88 picks after value authority |
| **AE-2** | Embodiment: modeling output→input contingencies and using the model in perception or control | `fs_perception._self_written` discounts self-caused file changes (hard-coded, not learned); efference flag `__acted_this_tick__` in `planning/goal_execution.py`; causal graph learns act→effect edges; host telemetry drives cadence (`resource_cadence.py`, `host_band.py`) | Partial | **1** | Run 10: first outward causal edges; the perception-side discount is not learned |

**Baseline profile:** three 0s, five 1s, six 2s, no in-life 3s.

| Score | Indicators |
|---|---|
| 0 | RPT-1, HOT-4, AST-1 |
| 1 | GWT-4, HOT-1, HOT-2, PP-1, AE-2 |
| 2 | RPT-2, GWT-1, GWT-2, GWT-3, HOT-3\*, AE-1\* |
| 3 | none from an in-life intervention yet (\* = 3 on longitudinal evidence only) |

**Read:** Orrin is a strong GWT-shaped system with a real agency loop and a real
metacognition loop. It is weak exactly where the report's other theories look —
at the *input* end (RPT-1, PP-1, HOT-1/4 all ask about how perception itself is
computed) and at attention-about-attention (AST-1). That shape is expected for a
symbolic-first agent whose perception is file/host polling, and it should be
reported as such rather than patched to raise the count.

---

## Part B — The experiment matrix

One row per experiment. "Flag" means the manipulation already exists; "build"
means a small ablation hook or instrument has to be added first (each new hook
goes into `brain/run_config.py` `SUBSYSTEMS` so it is stamped in the Life
Capsule, per the ablation-panel contract).

| # | Probes | Manipulation | Exists? | Prediction if the indicator is load-bearing | Measure (from the run folder) | Cost |
|---|---|---|---|---|---|---|
| **E1** | GWT-2, GWT-1 | `ORRIN_ABLATE=workspace` vs baseline | **Flag** | Selection decouples from any single focus: pick entropy ↑, goal-step continuity ↓, speech coherence ↓ | Pick distribution entropy; mean run-length of same-goal steps; speech_coherence scores | 2 short lives |
| **E2** | GWT-2 | Capacity sweep: workspace winners k = 1, 2, 3 (and attention slots 3 → 1) | **Build** (make k a boot param) | An inverted-U: k=1 gives continuity but monopoly risk; larger k dilutes focus. If nothing changes, the bottleneck is decorative | Top-focus occupancy; monopoly %; step continuity | 3–4 short lives |
| **E3** | GWT-3 | `ORRIN_WORKSPACE_PRIOR=0` (winner no longer biases the pick) and, separately, a **scrambled-broadcast** control (broadcast a random past winner) | Prior = **flag**; scramble = **build** | Mutual information between winner kind(t) and function pick(t) drops to shuffled baseline under both | MI(winner, pick) from `workspace_broadcast.json` + selection log, vs a label-shuffled null | 2–3 short lives |
| **E4** | GWT-4 | Seeded multi-step scenario that needs rule → memory → causal-graph lookups in sequence; compare baseline vs `ORRIN_IGNITION_GATE=0` vs writeback off | Gate = **flag**; writeback off = **build** | Baseline shows winner(t) predicting which source is queried at t+1 above a shuffled baseline; the gate/writeback ablations flatten that transition matrix | Transition matrix winner(t) → candidate-source(t+1); scenario success and cycles-to-solve | Scenario + 3 lives |
| **E5** | RPT-2 | Ablate binding (composites never offered) | **Build** (`binding` subsystem flag) | Composite winners → 0 and situations that need two cues together are handled worse (e.g. user-present + goal-stalled) | Composite share of winners; contradiction-surfacing and speech-coherence rates | 2 short lives |
| **E6** | HOT-2 | Inject a synthetic signal source emitting random content at realistic salience | **Build** (test-only source, off in normal lives) | Its learned credibility weight falls below every real source within N cycles; it stops winning the workspace | Per-source weight curve in `attention_value_weights.json`; its win share over time | 1 life (or a hermetic harness test first) |
| **E7** | HOT-3 | (a) `ORRIN_ABLATE=metacognition`; (b) covertly bias the reward EMA so forecasts are overconfident | (a) **flag**; (b) **build** | (a) Ruts last longer (the Run 11 72-cycle loop is not caught); (b) calibration bias is detected and control corrects within a bounded window | Rut length distribution; calibration bias EMA before/after; time-to-correct | 2 short lives + harness |
| **E8** | AE-1 | Mid-life reward reversal: swap which of two action families pays | **Build** (scheduled reward flip) | Selection shifts to the newly paying family within a bounded number of cycles; competing goals still rotate | Cycles to cross-over; aspiration occupancy before/after | 1 life |
| **E9** | AE-2 | (a) **Yoked control**: replay a recorded percept stream into a fresh life with actions disconnected from the world; (b) **contingency perturbation**: silently redirect one action's effect (writes land elsewhere) | Both **build** | (a) Causal act→effect edges fail to form in the yoked life; (b) edges for the perturbed action decay and selection moves away from it | Causal-graph edge counts and weights; effect-ledger credit for the perturbed action | 2 lives |
| **E10** | PP-1, HOT-1 | Out-of-pattern file/host events injected into perception (expected vs unexpected) | **Build** | Only relevant **after** a predictive input module exists: unexpected events should dominate what perception passes up. Today, predict **no difference** — that null result is the honest record of the gap | Workspace win share of injected events by expectedness | Harness only until PP-1 is built |
| **E11** | AST-1 | — | **Nothing to test.** Pre-registered for the day an attention-forecast module exists: it must predict the next winner above base rate, and ablating it must worsen control (e.g. monopoly returns) | — | — |
| **E12** | RPT-1, HOT-4 | — | **Nothing to test.** Recorded as absent. Do not build these to raise the count; build them only if an engineering finding calls for them | — | — |

### How to run the matrix

1. **Hermetic first.** E5, E6, E7(b), E10 can be pinned as tests with the
   existing `tests/conftest.py` isolation before spending a life on them. A
   harness pass is not a score of 3; it just proves the manipulation works.
2. **Short lives, same build, same reset.** Each ablation is a clean-reset,
   symbolic-only life of a fixed length (suggest 2,000 cycles) on the same
   commit, compared against a baseline life of the same length. One condition
   per life — `run_config` flags are boot-time by design so the trace is
   attributable.
3. **Pre-register the prediction.** Copy the row's prediction into the run doc
   before launch. A result that only looks right after the fact does not score.
4. **Report nulls.** An ablation that changes nothing is the most useful row in
   the report: it means the mechanism is decorative for that indicator, and the
   baseline score drops to 1 (or 0 if the mechanism turns out not to match).
5. **Cheapest informative order:** E3 and E1 (flags exist, no code) → E7(a) →
   E5 → E6 → E4 → E8/E9.

### Gaming resistance

The companion rubric's §17.5 rules apply unchanged: score from artifacts and
logs, not from Orrin's self-descriptions; any change made to raise a row between
runs is recorded as a deliberate intervention; and **the absent rows stay absent
unless an engineering reason (not this matrix) motivates building them.** A
matrix that goes to fourteen 3s in a month has been Goodharted.

---

## Honest limits

- **The indicators come from theories of the brain.** Several (RPT-1, HOT-4,
  PP-1) are defined at the level of perceptual coding. Orrin's perception is
  file-system and host polling, so those rows mostly measure how far that input
  layer is from a brain's; they say little about whether the agent works.
- **Name-matching is the main risk.** Orrin's modules carry the vocabulary of
  these theories, often supplied by the LLMs that implemented them (see the
  companion rubric's "borrowed vocabulary" note). Every row here was checked
  against the definition, and several were downgraded to *adjacent* for that
  reason.
- **A full profile would still not be evidence of experience.** The report's
  authors say the indicators do not settle the question; this project does not
  use them to try.
