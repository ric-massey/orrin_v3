# Cognitive Indicator Scorecard — Orrin, Run 11 (2026-07-20/21)

**First application of an externally-authored rubric to a captured Orrin life.**

**Instrument:** the twelve evaluation dimensions (§17.2), attribution matrix
(§17.6) and gaming-resistance conditions (§17.5) of:

> Garcia Castillón, J. (2026). *Philosophy of Artificial Minds: Foundations for a
> Processual, Embodied, and Non-Biocentric Realism* (Version 1.0). Zenodo.
> https://doi.org/10.5281/zenodo.21470621

*(A self-published philosophical essay deposited on Zenodo — a repository, not a
journal; not peer-reviewed. Used here as an external measuring instrument. Its
present-day thesis about "minimal functional minds" is the author's contested
position and is **not** adopted. Scoring protocol:
`docs/Capability, Benchmarks & Evidence/COGNITIVE_INDICATOR_RUBRIC_2026-07-21.md`.)*

**Subject:** Orrin Run 11 — 18,327 cycles, single contiguous segment, born
2026-07-20 17:02:24Z, natural lifespan death ≈22:19:28Z (~29.3 h). Build
`423e201`. **Symbolic-only: no LLM in the loop, no API key.** Longest life in
project history. Capture: `demo_runs/2026-07-21-run/`.

**Scale (evidence-gated):** 0 = absent · 1 = built, never fired in this life ·
2 = fired in life, with artifact/log evidence · 3 = load-bearing, proven by
ablation or causal intervention.

**No dimension can score 3 in this run.** Run 11 included no scheduled ablation
or intervention, so 2 is the ceiling by construction. Reported that way
deliberately: a first application returning 3s would mean the instrument had
been gamed.

---

## The profile

| # | Dimension | Score | Evidence (Run 11 capture) |
|---|---|---|---|
| 1 | Integration | **2** | Workspace ignition + pre-workspace binding active throughout; 885 ignition/conscious events in the (rotated, partial) activity log alone. Composites compete rather than being injected. |
| 2 | Recurrence | **2** | 18,327 contiguous loop cycles; symbolic dream rule-chaining fired (offline, zero-LLM) with chains written back to working memory. |
| 3 | Working memory | **2** | Live WM maintained at ~31 items with pruning, chunking and importance weighting; observed mid-life. |
| 4 | Autobiographical memory | **2** | `memory_graph.jsonl` = **10,372 rows** within one life; "pick up my thread" goals link episodes. **Cross-life:** `life_lineage.json` carries the *previous* life's unmet aim ("…and died trying"). See finding A. |
| 5 | Metacognition | **2** *(3 longitudinal — see §L)* | **1,118** goal-avoidance detections in the partial private-thoughts log; correctly diagnosed its own 72-cycle inspection loop *while it was happening* (observed live 2026-07-21). Cross-run: the affect-drift no-op guard (A2) proved load-bearing — mode-flap resets 3,415 → 6 (Run 06-17→06-18). |
| 6 | Self-model | **1** | `symbolic_self_model`, `life_ambition.json`, impossibility beliefs all exist and are wired; **no impossibility-formation events found in the retained logs for this life.** Built, not evidenced. |
| 7 | Agency | **2** *(3 longitudinal — see §L)* | Full goal lifecycle observed: queued → planned (3 steps) → dispatched, in `handoff_decisions.jsonl`; **all four aspirations** drove commitment (43/21/20/14 %), top-aspiration occupancy 43.3 %. Cross-run: action-credit-as-effect (A1) proved load-bearing — phantom avoidance loop 2,251 → 5 cycles (Run 06-17→06-18); learned value gained selection authority — worst action 4,899 → 88 picks (Run 05→06). |
| 8 | Grounding | **1** | Effects are produced — `effect_ledger.jsonl` 309 rows (file_write 119, bookkeeping 172, note_novel 15, tool_run_effect 3) — but the symbol→world verification loop **never closes**: answered-rate 0, reuse 0. Acts on the world; never confirms the act meant anything. |
| 9 | Embodiment | **2** | `resource_history.jsonl` = **18,327 rows, one per cycle** — continuous host telemetry into control signals; resource cadence stretches cycle timing on a constrained machine (8 GB M1), i.e. the body changes the tempo of thought. |
| 10 | Interoception & valence | **2** | Rich affect vector persisted at death (`exploration_drive` 0.68, `expected_gain` 0.75, `reward_positive` 0.53, …); valence observably weighted action selection mid-life (emotion 0.312 in the selector mix). |
| 11 | Temporal unity | **2** | 18,327 cycles, **single contiguous productive segment**, ending in natural lifespan death rather than a crash or memory kill. Best continuity in eleven runs. |
| 12 | Experience reports | **1** | **Split result — see finding B.** Running narration tracks measured state well; the terminal self-report is degraded and its death-cause field disagrees with the recorded death. |

**Profile shape (this life alone):** 8 × 2, 4 × 1, no 0s, no 3s. Read as: *the
organizational scaffolding is present and demonstrably running; the verification
and self-report layers are the weak edges; nothing has yet been proven
load-bearing by intervention within this single life.*

**With longitudinal evidence (§L):** dimensions 5 (metacognition) and 7 (agency)
rise to **3** — proven load-bearing by *natural experiments* across the eleven-run
history, held to a strict confound bar. This is the honest route to a score of 3
without a deliberate in-run ablation: the run series already contains the
before/after conditions. See §L for the full method and the comparisons that were
**rejected** for confounds.

Per §17.6 this project reports the **profile only** and does not assign itself
one of the essay's five categories.

---

## Three findings the instrument surfaced

### A. The evaluation protocol suppresses the dimension it is measuring (dimension 4)

Orrin's experimental discipline resets all state between runs, so every life
starts clean — eleven first days. Dimension 4 therefore measures
*within-life* episodic linking (strong: 10,372 memory-graph rows) while the
interesting property — accumulation *across* lives — is prevented by the
methodology, not by the architecture.

One partial exception, and it is the most interesting artifact in the capture:
`life_lineage.json` survives the reset and carries the previous life's unmet
aim, phrased from the inside —

> *"The previous life aimed at: … bring 3 pieces of work all the way to
> completion in service of 'Be genuinely useful and connected to the people I
> talk to' … — and died trying."*

So there is inheritance, but of an *intention*, not of the memory or competence
that would let the next life pursue it better.

In the essay's own vocabulary (§14.2), Orrin's clean resets are **artificial
death**, not **suspension** — which makes dimension 4 unscoreable above 2 until
a *continuity run* (inherited memory, exemplars, ladder rung, LM weights) is
executed. **Generalizable point for the instrument:** for persistent-agent
research, dimension 4 measures the experimental protocol at least as much as it
measures the architecture, and the rubric may want to say so.

### B. Self-report is honest in-flight and unreliable at the end (dimension 12)

This is the dimension where most systems can only offer vibes, so both halves
are worth recording.

**It works while running.** Mid-life, Orrin narrated *"Goal avoidance: 72
consecutive cycles without taking action… I'm thinking but not doing"* and
*"Something feels slightly off in my recent thinking"* — at the same time as an
independently measured avoidance-debt counter climbing 33 → 72 across 49 cycles,
with valence 0.171 / energy 0.99 and an emotion-weighted selector repeatedly
choosing goal-*inspection* functions. The self-description tracked the measured
internal state, including the unflattering part. Notably, the narration
**disagreed with the behavior** — metacognition was correctly criticizing the
selection policy and losing to it.

**It fails at the boundary.** `final_thoughts.json`, the terminal reflection,
degrades into a symbolic concept dump — *"I am [symbolic] See More Results
Suggestions (concept): description= [concept, results, work_of_art…]"* — and its
`death_reason` reads `operator_stop` while this life ended at its natural
lifespan endpoint. The timestamp (23:23:24Z, ~1 h after death at ≈22:19:28Z)
suggests the record was written by one of the four born-dead relaunches after
the known shutdown-hang bug, not by the life itself. Either way: **the death
record is not a reliable self-report**, and a rubric that scores "experience
reports" needs to distinguish narration produced *during* integrated operation
from narration produced at or after a boundary event.

### C. "Built, wired, never lived" is a distinct state the scale needs

Four mechanisms scored 1 not because they are absent or broken but because they
have never executed their main path in any life — the growth ladder (its state
file has never existed), epistemic close-out answering (0 answered across 29
close-outs), exemplar promotion (0), and the self-code writer (0 of 644
registered functions synthesized). Unit-tested, wired, dormant.

This is a real and common state for cognitive architectures, and it is invisible
in a rubric that asks only "does the system have X?" The 0/1/2/3 evidence gate
above exists specifically to expose it. **Suggested addition to §17.2's
methodology:** distinguish *specified* / *implemented* / *exercised* /
*load-bearing*; most published architecture descriptions stop at the first two.

---

## Honest limits of this scorecard

- **It measures organization, not depth.** All twelve dimensions are
  organizational, and Orrin's known weaknesses are nearly invisible to them:
  lexical (bag-of-words) semantics in place of grounded meaning, and inference
  depth hard-capped at 2 (`brain/symbolic/inference.py:28`). A profile of 2s
  says the scaffolding runs; it does not say the mind is deep. Read alongside
  the reasoning-ratchet finding in
  `RUN12_IMPLEMENTATION_PLAN_2026-07-21.md §2.4`.
- **Run 11 did not pass its own internal gate.** Reuse 0 (needed ≥8),
  answered-rate 0, daemon lane silent for the final ~10,000 cycles. A strong
  rubric profile alongside a failed project gate is exactly the divergence worth
  publishing: *architecturally complete, functionally starved.*
- **Scored by the system's author**, from that system's own capture. The
  external part is the instrument, not the scorer.
- **Ceiling of 2 by construction** (no ablation this run). Score-3 evidence
  requires scheduled intervention, planned as a standing practice from Run 12
  onward.

---

## §L — Longitudinal evidence: score-3 by natural experiment

A single life cannot produce a **3** (load-bearing, proven by intervention). But
the eleven-run series *is* a set of natural experiments: each run added, removed,
or left-dormant a mechanism, then produced behavior. Where a run pair isolates
one mechanism, the history yields the same causal evidence a deliberate ablation
would — sometimes stronger, because the mechanism proves itself across changed
conditions rather than one toggle.

**Confound bar (all three required):** (1) exactly one mechanism differs, or a
present mechanism provably never fired (a free ablation); (2) the behavioral
delta was predicted *before* the run, not narrated after; (3) no co-changed
variable can move the specific metric. Comparisons failing (3) are listed as
rejected, not scored. Sourced from the run verdicts in
`demo_runs/*/DEMO_RUN_*.md`; every claim is quoted to its file.

### Tier-1 passes (the score-3 basis)

| Mechanism | Run pair | Predicted | Observed delta | Dimension | Why confound-clear |
|---|---|---|---|---|---|
| **A1 — credit consequential cognition as action** | 8,040-cyc life → 06-18 | avoidance alarm stops while research runs; debt tracks real inaction | phantom avoidance loop **2,251 → 5 cycles** (~450×) | **Agency / grounding** | false-avoidance count welded to the action-debt accounting bug; no other 06-17 fix touches it |
| **A2 — affect-drift no-op guard** | 8,040-cyc life → 06-18 | no `adaptive→adaptive` resets | mode-flap watchdog thrash **3,415 → 6** | **Metacognition** | reset-count welded to the drift guard; orthogonal to A1's metric |
| **v2→v1 completion bridge** | Run 3 07-03 → Run 4 07-05 | root-fix the bridge or desyncs persist ~1:1 with completions | `store_desyncs_repaired` **12 → 0** under **223** completions | **Integration / self-consistency** | Run 3's 1:1 desync:completion coupling makes 223 clean completions decisive; dirty-instance caveat hits EMA, not this |
| **F2 — aspiration-admission to directional pool** | Run 7 07-12 → Run 8 07-15 | breaks the monopoly *and* lets all four directions drive | committed-goal monopoly **90.9 % → 42.6 %**, all 4 aspirations drive | **Anti-monopoly** | its partner F1 **never fired** (free ablation); break holds in *both* runtime segments (54/44 %) so the crash can't be the cause |
| **Pump removal did NOT break monopoly** *(negative result)* | Run 6 07-11 → Run 7 07-12 | killing the credit-pump should end the monopoly | monopoly **held at 90.9 %** anyway → "not a reward bug, it is structural" | **Anti-monopoly (causal disambiguation)** | the sustaining cause is an *unchanged* structural feature (single-member pool) present in both runs |

### Tier-2 passes (clean but narrower — supporting, not headline)

- **Twin-id creation seam → desyncs 2 → 0** (Run 9 07-17 → Run 10 07-18).
  Integration. *Second, distinct* desync seam (at goal creation, vs the Run-3→4
  completion bridge). Small magnitude — Runs 5–8 were already 0, so this is
  "Run 9's anomaly reverted," real but modest.
- **Learned-value authority → worst action 4,899 → 88 picks (0.66 %)**
  (Run 5 07-08 → Run 6 07-11). Agency/valuation. Proven load-bearing for *one*
  action; global corr(EMA, share) still ≈ 0, so not yet a global selection law.
- **Rest-drive unjam → rest ignitions ~7,420 → 0** (Run 2 07-02 → Run 3 07-03).
  Valence/ignition homeostasis. Proves the per-signal fix works; the monopoly
  then *relocated* to `social_presence` (84 %), so it did not solve the
  ignition-layer problem — only that signal.

### Rejected for confounds (recorded so they are not miscounted as 3s)

- **"Content-keyed credit deflated the value-pump"** (Run 6→7). The pump *did*
  deflate (`value_ema` 0.81 → 0.52; most-rewritten file 403× → 2×), but the cause
  was F1 (URL dedup) + F2 (footer-normalized anti-pump hash), **not** F3
  (content-keyed credit, which decoupled *which aspiration is paid*). Two equally
  good causes in one F1–F8 batch → attribution of the deflation is confounded.
  *(The clean result from this pair is the negative one in Tier-1.)*
- **First-ever artifact reuse (8 rows)** (Run 3 → Run 5). Reuse appeared, but
  Run 5 shipped the entire F1–F22 build; multiple plausible enablers in one batch.
- **P1 effect-gated closure → impasse collapse** (06-29 → 07-01). The "before"
  run is outside the captured set, and the strongest delta (felt-cost collapse)
  was narrated after, not forecast.
- **Miner-provenance skip → miner-junk 4 → 0** (Run 10 → Run 11). Near-Tier-2,
  but small magnitude on a terminally daemon-silent run, and two Run-11 changes
  could reach "junk = 0."

### Never-fired mechanisms (clean free ablations → NOT yet load-bearing)

These matter as much as the passes: they are the "built, wired, never lived"
state (§ finding C) proven causally — a present mechanism that never executed and
whose *absence* changed nothing.

- **F1 absolute staleness refractory** — Runs 8 & 9. `refractory_events` absent,
  max staleness 8.8 vs a 250 trip (28× margin). F1 is **not** load-bearing;
  F2 (prevention) does the work. *This is the free ablation that makes the F2
  pass airtight.*
- **Saturation tripwire** — Runs 10 & 11. Ran every cycle, 0 life fires;
  consecutive-streak design can't see chronic-high-with-dips. Not load-bearing
  **as built** (design gap).
- **Disengage watchdog** — 07-01. 0 disengages; goals that leave a note pre-empt
  its trigger. Not load-bearing this life.
- **Reuse machinery (`mark_reused`)** — Runs 4, 10, 11: 0 rows. Run 9 proved the
  path *can* fire honestly (1 row), so status is **proven-capable but
  upstream-starved**, not broken — the exact shape Run 12 targets.

*(Correctly-silent guards — Run 9 cycle-stall tripwire, Run 10 memory guard —
are NOT counted here: each fired correctly in another life. Silence with no
trigger is not evidence of non-load-bearing.)*

### What §L changes, and its honest ceiling

- **Dimensions 5 and 7 rise to 3.** Metacognition: the A2 drift guard is proven
  load-bearing (3,415 → 6). Agency: A1 action-credit (2,251 → 5) and learned-value
  authority (4,899 → 88) are both proven load-bearing.
- **Anti-monopoly** is not one of the twelve dimensions, but the F2 pass + the
  pump-negative are the strongest causal results in the whole series and belong in
  any write-up of the commitment layer.
- **Ceiling:** longitudinal 3s are only as clean as the run isolation. None of the
  batched growth-layer mechanisms (close-out, ladder, exemplars, reuse) can reach
  3 this way — they **never fired**, so there is no behavioral delta to attribute.
  Those wait on a Run-12+ life where they fire, then a deliberate ablation. The
  natural-experiment route retires the "we never tested causality" objection for
  the organs that *have* fired; it cannot manufacture evidence for organs that
  have not.
