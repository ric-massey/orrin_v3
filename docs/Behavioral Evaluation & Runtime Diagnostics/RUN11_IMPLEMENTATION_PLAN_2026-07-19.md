# Run 11 Implementation Plan — verified build order (2026-07-19)

Executable companion to `RUN11_BACKLOG_2026-07-19.md` (rationale, directives, and
the §10 gate live THERE; this doc is build order + code targets). Every target
below was verified against the working tree at `4d69ce5` on 2026-07-19 — file
paths and line anchors are real, not remembered. Where a backlog item's
assumption didn't survive contact with the code, the correction is marked
**[GT]** (ground truth).

## Corrections from the ground-truth pass [GT]

1. **The 20k-cycle run is ~25–30 wall-hours, not 4.6 days.** The backlog assumed
   ~20 s/cycle; Run 10 measured **~4.5 s/cycle average** (11,565 cycles /
   14.6 h, sleep phases included). §8 endurance is real but 4× smaller than
   feared: E1 stays load-bearing (floor is cycle-denominated: ~2.2 GB at 20k),
   E2 rotation already exists (`brain/data/rotated/` for activity_log +
   private_thoughts; `data/goals/wal-rotated/`) — E2 reduces to a coverage
   audit. E3's env vars already exist (`ORRIN_LIFESPAN_MIN_DAYS`/`MAX_DAYS`,
   `runtime_lifetime.py:70`) — E3 is picking staging values for a ~30 h life.
2. **C1 layers onto a live mechanism, not a bare constant.** The ignition gate
   (`brain/think/deliberation_gate.py:36`, `_SIGNAL_STRENGTH_TRIGGER = 0.60`)
   already runs B1 sameness-habituation (same file, ~95–130): eff = raw /
   (1 + k·n_identical) per (source, quantized-value) key. Run 10 shows the pair
   working-but-insufficient (drive_mastery still 42.3 % of ignitions, 98.8 %
   duty cycle). The percentile gate replaces the *constant*; habituation stays
   as the sameness antagonist. Do not build C1 as if the gate were naive.
3. **Decisions adopted** (per the backlog's own recommendations — flag at
   review if wrong): **E4** = brief daily visits during the run (contact
   scoreable + real input + reunion exercise). **L3 Life Ambition = IN**
   (its monopoly-gate precondition measured green: 40.4 % occupancy without
   C2). **F-LN6 diagnosis precedes any daemon fix** (no guessing).

---

## Slice 1 — pipes, membranes, Thought Object (unflagged; `make verify` + ~2k smoke life before Slice 2)

### 1A. Bug fixes (§1, all sites verified)

| # | Target | Change | Test / observable |
|---|---|---|---|
| F-LN1 | `brain/cognition/intrinsic_generators.py` `_open_question_goals` (~123–166) | Skip entries with `event_type == "unanswered_question"` or content prefix `[unanswered_question]` — symmetric with the existing `[input/` skip (line ~139) | Unit: synthetic long-memory record of his own outbound question is not mined. Life: zero "Open question:" goals sourced from own speech |
| F-LN2 | `brain/cognition/planning/step_attempts.py` failure path (~155–168) | After `mark_goal_failed`, merge via `goal_arbiter.apply(merge_updated_goal_into_tree, …)` — the exact call the retry path makes at ~137 | Unit: replay Run 10's double-failure; assert one failures.jsonl row. Life: no goal_id repeats in failures.jsonl |
| F-LN3 | same module as F-LN1 | Router (not filter): questions whose subject is self-referential route to the introspection path (M4's behavioral introspection), never `kind="research"` | Life: failures.jsonl junk class = 0. Superseded by T1 when it lands |
| F-LN4a | `brain/cognition/planning/goal_closure.py` (~230–247) | Move `stamp_closeout(goal)` BEFORE `mark_goal_completed` (archive append currently precedes stamping); add creation-time `question` stamping in intrinsic_generators' understanding-goal `_mk_goal` calls | Every completed understanding goal in `comp_goals.json` carries `question` + `answered` |
| F-LN4b | `goal_closure.py` + `brain/cognition/epistemic_closeout.py:115` | `answered=False` on an understanding goal blocks the satiety-close OR spawns a follow-up goal carrying the question (wall: understanding-can't-close-on-satiety, backlog §6.3) | 0 understanding goals close answered=False without follow-up; NOT-answered count == follow-up count |
| F-LN4c | `epistemic_closeout.py` `question_for` | Derive question from the goal's content/DoD/evidence, not the "What is not obvious about X?" template | ≥8 distinct question shapes on a 10-goal sample |
| F-LN5 | `brain/control_signals/homeostasis.py:304` `saturation_tripwire` | Add time-at-bound fraction trip (≥95 % of trailing 500 cycles at a bound far from setpoint); keep consecutive-streak as the fast path | Harness: fires on Run 10's 86 %-at-1.00-with-dips drive_mastery series (current code provably doesn't) |
| F-LN6 | `brain/goal_io.py:251` `_committable_from_v1_tree` + the daemon runner pickup | **Instrument only** (Slice 1): log a one-line decision per research-capable goal — queued / skipped + reason. Diagnose from the smoke life; fix in Slice 2 with evidence | Smoke life produces a complete handoff-decision log; the 8-h-silence cause is named before any daemon change ships |
| F-LN7 | `brain/data/production_funnel.json` writers | Wire stages beyond `candidate` at the real transition points, or delete the instrument | Any deeper stage appears, or the file is gone |
| F-LN8 | `tests/` (new harness) | Zero-with-prejudice: blocked action writes its EMA penalty and leaves the selectable set — proven by forced-fire test (R9-F7 pattern) | Test green; not inferred from EMA rank |

### 1B. Membranes (§2 — design source: agent memory `project_anatomy_membrane`)

- **M1+M4 together** (M1 without M4 reopens the goal-spam hole): mechanical
  path-filter at the file-read chokepoint denying `brain/**.py` (and source
  generally) to reasoning-layer callers; agency organs (code_writer,
  auto_repair, Architect, self_extension) keep tool-level access, but source
  text never enters working memory / workspace / self-model updates. M4
  retargets `search_own_files`-based introspection (the causal-frontier goals —
  see `project_causal_frontier_introspection`) to behavioral evidence: memory
  retrieval, signal-history stats, ledger summaries, failure counts.
- **M2**: the same path-filter covers `brain/data/` (state files are organs:
  `runtime_lifetime.json` = true death date, `bandit_state.json` = own
  preference weights). fs_perception's "body_touched" pattern stays.
- **M3**: machine transcripts (activity_log, thought stream, private log)
  become Ric-only; his past reaches him via the memory system + derived
  aggregates. **Diary exception**: self-authored artifacts stay readable.
- **M5**: coarse/felt time in reasoning-layer content; µs stamps stay in
  telemetry.
- **M6**: short design pass first (boundary-violation events → integrity
  pressure → repair recruitment — a drive, not a checklist); build only if the
  design pass lands clean, else defer with reasons.
- Smoke-life watch: M1/M4 interplay — introspective goals must still be
  *generatable and completable* from behavioral evidence (this is the exact
  seam the ~2k smoke life exists to shake out).

### 1C. Thought Object (§4-T1 — spec verified complete: `docs/Language &
Cognition/THOUGHT_OBJECT_SPEC.md`, schema + register split defined)

Build order inside the item: (1) the object + builders (Motive is the
half-built precursor — `express_to_user.Motive`); (2) adapters so working
memory can carry objects alongside strings; (3) migrate the ~12 string readers
(opinions, opinions_formation, self_extension, skill_synthesis,
experimentation, rumination, summarize_w_memory, … — inventory in
`project_prose_bus_label_authority`) to typed fields with `content` as
display-only; (4) T2: perception/World events enter structured, prose rendered
at the membrane. This is the longest Slice-1 item — budget it accordingly and
land it before Slice 2 so the de-clamps are built against structured currency.

---

## Slice 2 — de-clamps, drives, growth (each behind its own flag, ALL ON for Run 11)

### 2A. Clamp → antagonist conversions (§6.1; sites verified)

| Flag | Retires | Site | Replacement |
|---|---|---|---|
| `ORRIN_ADAPTIVE_IGNITION` (C1) | `_SIGNAL_STRENGTH_TRIGGER = 0.60` | `deliberation_gate.py:36` | Rolling-percentile gate over the actual signal distribution (pinned signal can't saturate a percentile); B1 habituation stays; `MAX_SILENT_CYCLES = 3` (line 41) stays as the liveness floor |
| `ORRIN_NEGLECT_PRESSURE` (C2) | `_STALE_REFRACTORY_CYCLES = 250` / `_RECOMMIT_BLOCK_PULLS = 300` | `commitment_value.py:71,79` | Per-aspiration neglect accrual added to commit_score — unserved pull grows until displacement; refractory demoted to dead-man backstop |
| `ORRIN_TOPIC_SATIETY` (C3) | `_RECENTLY_COMPLETED` title cooldowns | `intrinsic_goals.py:44,502` (+ goal_planning's plan-fail cooldown writer) | Topic-satiety: repeated completion quenches demand (habituation of appetite), respawn ends because want is gone |
| `ORRIN_NOVELTY_PRICING` (C4) | `_SYMBOLIC_CAP_WINDOW_S = 600` window cap | `effect_ledger.py:83–89,496` | Marginal-novelty pricing vs recent symbolic history; the novelty/hash pricing core is a wall and STAYS |
| `ORRIN_BOREDOM_DRIVE` (C5) | rut-breaker forced switch | `think_utils/selection/boosts.py`, `score_setup.py` (rut sites) | Boredom signal → outcome devaluation through the normal economy (promote the existing devaluation patch to a drive) |
| `ORRIN_ENERGY_ECONOMICS` (C6) | default-mode damping flags | `seek_novelty.py`, `inner_loop_symbolic.py`, `speech_pipeline.py` (default_mode sites) | Effortful functions cost activation; priced out at low activation naturally |
| — (C7) | miner pass-level dedup | retired by T1 provenance | — |

### 2B. New organs (§6.1b)

- **C8 entropy monitor**: generalize the stagnation pattern
  (`update_signal_state.py:359` — Shannon entropy of action picks) into a
  per-distribution rolling-entropy instrument (commitment occupancy, ignition
  sources, credited-content kinds, action picks) routing collapse into the felt
  layer. New module under `brain/control_signals/`; readable by the §10 gate.
- **C9 + E1 global entropy budget**: one ledgered view per life-quarter of
  grew / compressed / forgotten; idle consolidation gains a compression arm
  (many memos → one principle → drop the memos; embedding compaction). E1 is
  the enforcement arm and the 20k memory ceiling depends on it.

### 2C. Magic numbers (§6.2)

- **N1**: sweep selection/drive/satiety/credit layers; every surviving constant
  gets an owner line in `HARD_NUMBER_REGISTER.md` (run folder).
- **N2 (with D4)**: drain/recover rates derived from demand-relief learning
  (`demand_expectations` already learns which actions relieve which needs —
  close the loop to rates; per the proposal: tune for **oscillation, not
  extinction**).

### 2D. Drives & LLM-free cognition (§5 — proposal verified: Issues A–D at
`docs/Language & Cognition/ORRIN CREATIVITY NOVELTY PROPOSAL 2026-06-25.md`)

- **D1 (Issue B, CRITICAL)**: migrate illegitimate LLM call sites to the
  symbolic pattern. Inventory = the `_LLM_TOOL_CALLERS` allowlist in
  `generate_response.py` — audit each caller: tool-use (stays) vs
  understanding/creation (migrates). Acceptance: symbolic-only mode produces
  the same *kinds* of cognition.
- **D2 (Issue A)**: connection-maker rewards structural surprise over
  nearest-neighbor similarity.
- **D3 (Issue C)**: novelty drive retuned not to self-extinguish (root-cause
  fix arrives with the predictive core post-run; this is the honest interim
  tune).
- **D4 (Issue D)**: with N2 above.

### 2E. Growth (§3 — anchor: RUN9_DEEP_ANALYSIS §7e "the ladder already exists
in pieces", line 251)

- **G1 ladder** (`ORRIN_LADDER`): verified-success streak → stricter
  `definition_of_done` + build-on-prior required; difficulty carried on
  exemplar metadata so the bar ratchets on demonstrated competence.
- **G2 strong form**: decision reason payloads record when a selection cites an
  answered question / its memo — "the answer changed a later decision" becomes
  a readable event (F-LN4a/b are its floor).
- **G3**: frontier/aspiration generators read mastery (exemplar difficulty,
  answered questions) instead of sampling flat. Note: they now have nonzero
  world-knowledge to consume (10 outward causal edges).
- **G4**: at launch, decay-out or reset reward EMAs / Pearce–Hall state /
  value_ema poisoned by pre-Run-9 dishonest labels — the ladder learns from
  clean ground.

---

## Slice 3 — long-arc + endurance (§7, §8)

1. **L1** homeostasis completion (invariant #1, ~70 % built per
   GROUNDED_COGNITION plan line 15 — verified claim).
2. **L2** Grounded-cognition Phase 4B fork + Phase 5 (per its status line;
   Phase 5 is narrower than written — the plan's own note).
3. **L3 Life Ambition — IN** (precondition green). Apply its own corrections
   (verified in-doc): **no `will.py` exists** — targets are
   `intrinsic_objectives.py` + `commitment_value.py`; scoreboard path per the
   doc. Build LAST and only after C2's neglect-pressure is landed and
   smoke-checked (§9's own ordering).
4. **L4** benchmarks B8–B18. **L5** housekeeping (gate_report wiring, B1
   timeline undercount, cleanup Phases 3–7, wiki sync LAST).
5. **E1** compression (2B above) · **E2** rotation coverage audit [GT: mostly
   exists] · **E3** staging lifespan for a ~30 h / 20k-cycle life [GT: ~4.5
   s/cycle measured] · **E4** daily visits (adopted) · **E5** resource_history
   stays on + health snapshots + disk/power checked at launch · **E6** restart
   drill: sleep/wake + network outage against `run_orrin.sh` (pipe-safe +
   HUP fixes are in at `4d69ce5`; verify, don't assume).

### Slice 3 triage result (2026-07-20, build pass)

Ground-truthed each item against the tree before building (standing rule):

- **E3 DONE** — `run_orrin.sh` now echoes the lifespan band in the launch
  stamp and documents the staging values: `ORRIN_LIFESPAN_MIN_DAYS=1.1
  MAX=1.3` for a ~20k-cycle natural death (Run 10's rolled span was 505 days —
  no prior life ever died naturally; this run should).
- **E2 DONE (audit)** — every top grower from Run 10's own data is bounded:
  production_loop.jsonl (cap 20k lines), resource_history (30k/8 MB),
  events/trace (3k), habituation.json (5k keys), long_memory (pruner),
  activity/private logs (2 MB rotate → `rotated/`). The 43 MB/life `rotated/`
  archive is the flight recorder, intended. No uncovered append path found.
- **L1 MOSTLY ALREADY BUILT** — plan tasks 1–2 exist and are tested
  (`test_homeostasis.py::test_every_signal_has_an_explicit_setpoint`,
  `…restoring_force_acts_on_every_signal`, the allostasis standing-pressure
  test; 18/18 signals declare baselines). Only task 3 (retire the 5 secondary
  decay authorities) remains — **deferred post-run**: an affect-core sweep
  days before a 20k life is exactly the destabilization the run discipline
  forbids, and the by-construction tests pin the invariant meanwhile.
- **L2 DEFERRED post-run** — Phase 3's experiment harness exists and is green
  (`test_grounding_transfer.py`: real subprocess outcomes, transfer above
  baseline), so the 4A branch is live in principle; but Phase 4A/5 is a
  multi-week program (grounded skill discovery, hierarchy, predictive
  pruning) and belongs after the growth run, likely folded into the §11
  predictive core.
- **L3 Life Ambition** — sequenced per its own ordering: build **after** the
  2k smoke life confirms C2 neglect-pressure behaves, before launch.
- **L4 benchmarks B8–B18 DEFERRED** — offline claims-vs-evidence battery, no
  runtime coupling; can be built during the run without touching the life.
- **L5** — `gate_report` wired into the dream cycle (flush-then-report, the
  backend's empty-session hazard doesn't apply there). B1 timeline undercount
  + cleanup Phases 3–7 deferred with L4; wiki sync stays LAST (post-capture).

---

## Launch checklist (§9 step 4, expanded)

1. Venv synced to CI's unpinned mypy/ruff (standing gotcha) → `make verify`
   green.
2. Full test suite including the new harnesses (F-LN5 wobble series, F-LN8
   zero-with-prejudice, F-LN2 double-failure replay).
3. Clean reset — restore `control_signals_model.json` seed from git (standing
   reset gotcha); confirm `habituation.json` zeroed; stale
   `data/goals/artifacts/` cleared.
4. **Commit before launch** — SHA lands in the boot Run stamp (Run 10 started
   the reproducibility streak; keep it).
5. G4 state re-baseline runs as part of reset, not as a mid-life event.
6. Launch headless (`ORRIN_UI=0`), run-lock on, smoke window watched (first
   500 cycles: failures.jsonl class-check, handoff-decision log flowing,
   ignition duty cycle under C1).

## Scoring note for the eventual capture

Score against backlog §10 (finalized, with Run 10 baselines). Two standing
traps: read close-out stamps from the scored store (F-LN4a makes comp_goals
authoritative — verify before trusting); flag-bisection is the diagnostic tool
if the life goes strange — flip flags, don't rebuild.

*Written 2026-07-19 after the ground-truth pass; companion to
RUN11_BACKLOG_2026-07-19.md; sites verified at `4d69ce5`.*
