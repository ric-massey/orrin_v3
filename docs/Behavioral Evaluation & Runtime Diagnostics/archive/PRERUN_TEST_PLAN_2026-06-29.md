# Pre-Run Test Plan — Fresh Life, 2026-06-29

*What this clean-instance run is testing for, and how to read pass/fail.* Written
**before** the run so the verdict is measured, not remembered. Companion to the
Grounded Cognition docs (`GROUNDED_COGNITION_DIRECTION/IMPLEMENTATION_PLAN_2026-06-29`,
`GROUNDING_EXPERIMENT_RESULTS_2026-06-29`, `THOUGHT_OBJECT_SPEC`) and to the standing
`NEXT_RUN_TESTS.md` production gate.

This is a **fresh birth**: memory, goals, identity, signals, working memory, cycle
count — all wiped to an out-of-repo backup (`~/orrin_fresh_backup_20260629_224626/`).
**Kept:** the seed configs and his trained language organ (he keeps his voice). So
this run starts at cycle 0 with a blank mind and an existing mouth.

The headline question (direction doc Part C): **how long can he run before a human
must fix something?** Today that's "hours." The Phase-1 stabilizers are meant to push
it toward "indefinitely." This run is the first measurement of that on the new code.

---

## 0. Preconditions (must hold or the numbers can't be trusted)

- [ ] **Single clean instance** — one `main.py` on `brain/data/`; boot log shows the
  single-instance lock acquired; no second python on the data dir.
- [ ] **Fresh state confirmed** — `brain/data/cycle_count.json` starts at 0; no stale
  goals/memory leaked from the prior life (the wipe moved 284 entries + the root
  `data/` tree aside). The 8 seed JSONs + `language/` organ are present.
- [ ] **Unit tests green first** — `python -m pytest tests/brain/ -q` (last: **751
  passed**). Don't start a multi-hour run on red code.
- [ ] **Baseline copies** — none needed for state (it's empty by design), but note
  `native_lm` `tokens_seen` at boot so growth is measurable.
- [ ] **LLM availability decided + noted** — tool-only by default; the grounding work
  and the membrane don't need it, but production artifacts (§E) do.

## 1. How long

Target this run: **~7,000 cycles** (`ORRIN_CYCLE_SLEEP=1` → a few hours). That clears
the stability floor (saturation historically appeared within *hours*, so a few hundred
cycles can't disprove slow drift — thousands can) and starts the Phase-2B clock. It is
**not** a full production-acceptance run (`NEXT_RUN_TESTS` wants ~10k for that).

---

## 2. What we're testing for

Grouped by what each item proves. **Source** = the store/log to read it from.

### A. Stability / homeostasis — the Phase-1B prize (the saturation class of bug)
The 2026-06-29 session fixed three stacked positive-feedback loops. This run must show
they stay fixed at life scale.

| # | Watch for | Pass | Source |
|---|---|---|---|
| A1 | **No emotion saturation** — core signals do NOT all rise together and pin near a ceiling (the old ~0.89-in-lockstep flatline) | signals vary; none stuck ≥0.85 for long stretches | `control_signals_state.json`, `smoothed_state.json`, UI gauges |
| A2 | **homeostasis_index breathes** — moves across its band, not pinned at 0 (agitated) or 1 (flat) | oscillates in a healthy mid-band | `affect_state` / telemetry, UI |
| A3 | **No reward runaway** — mood doesn't mint reward that lifts mood | `reward_positive` not self-amplifying to ceiling | `reward_trace.json`, `control_signals_state.json` |
| A4 | **Habituation works** — a repeated thought stops pumping its emotion | recurring WM content de-escalates, doesn't ceiling | `working_memory.json`, `habituation.json` |
| A5 | **Allostasis (the correction)** — a genuine *standing* problem keeps its signal elevated; a *transient* spike decays to baseline | both behaviours visible; no forced-flat, no stuck-high | signal trajectories over cycles |
| A6 | **Graceful, crashless** — like the 06-25 life (5 sessions, 0 crashes) | 0 unhandled crashes; clean death if stopped | `failures.jsonl`, `run_log.txt` |

### B. Membrane as law — Phase-1A (invariant #2)
Internal implementation identifiers must never become perceivable content.

| # | Watch for | Pass | Source |
|---|---|---|---|
| B1 | **No engineering identifiers in perceivable stores** — no `impasse_signal`, `*_signal`, `stagnation_signal_acute`, `affective_regulation`, `[metacog…]` as *content* | scan finds none (bare English mood words like "motivation" are OK) | `working_memory.json`, `workspace_broadcast.json`, `conscious_stream.json`, `knowledge_graph.json`, goals |
| B2 | **No "a strong sense of {raw_key}" leaks** — affect content is felt language; the key rides in the `focus_signal` field | felt prose only in content | `workspace_broadcast.json` |
| B3 | **No identifier-named goals** — no "research the causes of {internal signal}" | none spawned | `goals_mem.json`, `proposed_goals.json` |

*Scan recipe:* load each store, flag any content/title field where an underscored
signal key or `_INTERNAL_MARKERS` token appears (mirror
`tests/brain/test_membrane_invariant.py`).

### C. Goal health — the goal-spam reframe (session fix #2)
| # | Watch for | Pass | Source |
|---|---|---|---|
| C1 | **Causal-frontier goals are introspective + plannable** — "Trace in my own code what drives '{X}'", routed to `search_own_files`/`grep_files`, not web tools | such goals plan, don't fail-3×-and-abandon | `goals_mem.json`, `activity_log.txt` |
| C2 | **No fail-plan → abandon → regenerate-next-variant churn** | no repeating unplannable-goal cycle | goals WAL, `activity_log.txt` |
| C3 | **Goal-title diversity** — no single title completed excessively | no title > ~2× per 1k cycles | `comp_goals.json` |

### D. LM-as-mouth — Phase-2 (clock starts; voice unchanged)
| # | Watch for | Pass | Source |
|---|---|---|---|
| D1 | **Narration pairs accumulate** — the conditional-decoder training set begins | `narration_pairs.jsonl` grows (each = thought-object + narration) | `brain/data/language/narration_pairs.jsonl` |
| D2 | **Voice unchanged today** — conditional render is fluency-gated; templates still stand (no regression to how he speaks) | expression reads as before | `speech_log.json`, UI |
| D3 | **Native LM keeps growing** — lifelong training continues | `tokens_seen` / `train_steps` rise | `native_lm.status()` / logs |

### E. General health & production (standing signals from `NEXT_RUN_TESTS`)
Still the real test of whether he *does* anything, not just runs.

| # | Watch for | Pass | Source |
|---|---|---|---|
| E1 | **Production is real, not noise** — effects have nonzero significance/novelty, bodies are comprehended (not `.lock`/filename scraps) | ≥1 effect with significance>0 | `effect_ledger.jsonl` |
| E2 | **Signal→action follow-through** — strong signals translate to acts (the R1 audit) | no chronic "feel but don't act" | `activity_log.txt`, decisions |
| E3 | **Selection follows learned value** — a low-EMA action's pick-share falls | EMA→selection link visible | `action_reward_ema.json` vs pick-share |
| E4 | **Aspiration diversity** — none stuck at 0%, top < ~60% | balanced contributions | `goals_mem.json` aspiration rows |

### F. Fresh-instance integrity (because we just wiped him)
| # | Watch for | Pass | Source |
|---|---|---|---|
| F1 | **Clean cold boot** — empty state dirs regenerate without error | boots, no missing-file crashes | `run_log.txt`, `failures.jsonl` |
| F2 | **No resurrection** — no old goals/memories reappear from anywhere | stores grow from empty only | `goals_mem.json`, `long_memory.json` |
| F3 | **Seed configs loaded** — cognitive functions, signal model, meta-rules present | normal cognition available | boot log |

> **Not tested live this run:** the **grounding loop (Phase 3/4A)** is an *offline
> experiment harness* (`python -m brain.cognition.grounding.experiment`), deliberately
> **not** wired into the cognitive cycle yet. Confirm it did *not* accidentally wire in
> (no grounding episodes in the live logs). The idleness-cost (#3) is correctly absent.

---

## 3. What to capture (so the result is reproducible)

- [ ] `brain/data/control_signals_state.json` + `smoothed_state.json` — signal
  trajectories (A1–A5).
- [ ] Snapshot of `working_memory.json`, `workspace_broadcast.json`,
  `conscious_stream.json`, `goals_mem.json`, `knowledge_graph.json` — for the membrane
  scan (B1–B3) and goal health (C).
- [ ] `brain/data/language/narration_pairs.jsonl` — count + a few examples (D1).
- [ ] `native_lm` status (tokens_seen delta) (D3).
- [ ] `effect_ledger.jsonl`, `action_reward_ema.json`, `failures.jsonl`,
  `activity_log.txt` (+ `rotated/`) — production/health/errors (E, A6, F).
- [ ] Final cycle count + session/death summary.

## 4. Decision rule

- **A + B are the gate for this run.** They are what the Phase-1 stabilizers were built
  to guarantee and have *no world dependency*. If emotions saturate, the membrane
  leaks, or he drifts within the budget, the stabilizers **failed** — that's a result,
  not interpretation.
- **C + D** confirm the goal-spam reframe and that the LM-as-mouth clock started without
  disturbing his voice.
- **E** is the standing "does he produce" bar — informative, but not the headline of
  *this* run (the fresh mind has little to produce early).
- **F** must hold for any of the above numbers to mean anything.

**Pass = the stability metric moved:** he runs the full ~7k cycles with no human patch,
no saturation, no leak, no goal-spam churn — and `narration_pairs.jsonl` is
accumulating. That is the first evidence that "Ric is his homeostasis" is loosening.

*Created 2026-06-29, before the fresh run. Hand back for the live read once he's a few
hundred cycles in.*
