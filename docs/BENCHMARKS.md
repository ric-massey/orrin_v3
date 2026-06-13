# Orrin Capability Benchmarks

Stored, runnable benchmark suite. The authoritative definitions + scoring live in
**`brain/benchmarks/__init__.py`** (the `BENCHMARKS` registry and evaluators);
this doc is the human-facing run guide.

Two kinds:
- **passive** — measured just by running the autonomous loop with sampling on.
- **scenario** — need a seeded test goal and/or specific flags.

## Run it (next launch)

```bash
export ORRIN_BENCHMARK=1          # per-cycle sampling + auto-eval every 500 cycles
```

Passive benchmarks (B1, B2) need nothing else — just let him run. To also exercise
the scenario benchmarks in the same run:

```bash
python -c "from benchmarks import seed_scenario; seed_scenario('B4'); seed_scenario('B5')"
```

B3 must run with the LLM off, so give it its own run:

```bash
OPENAI_API_KEY= ORRIN_BENCHMARK=1 python -c "from benchmarks import seed_scenario; seed_scenario('B3')"
# ...launch Orrin...
```

Results are written to **`data/benchmark_results.json`** automatically (every 500
cycles) and on demand:

```bash
python -c "from benchmarks import evaluate_all, report; evaluate_all(); print(report())"
```

Raw per-cycle samples accumulate in `data/benchmark_samples.jsonl`.

## The benchmarks

| ID | Kind | Tests | Pass criteria |
|----|------|-------|---------------|
| **B1** | passive | Reaper keeps long-term memory bounded | entries-vs-cycle curve plateaus (final-third growth ≈ 0); not linear unbounded |
| **B2** | passive | Boredom (stagnation_signal) drives novelty-seeking | Pearson(stagnation, novelty-action) > 0.3 **and** >40% novelty when stagnation > 0.6 |
| **B3** | scenario | Multi-step goal solved by the symbolic planner, no LLM | ≥70% success across 5–10 goals; mean cycles-to-complete < 200 |
| **B4** | scenario | Exploration goal closes on **satiety**, not plan-end | closes only after novelty flattens (≥3 barren searches); a trivial note-goal closes in one action |
| **B5** | scenario | Watchdog + hard-disengage kill a useless loop | goal abandoned/failed within a bounded number of cycles (<50 after watchdog), no human input |
| **B6** | passive | Concurrent goal progress (multi-goal Executive) | ≥2 distinct goals advance within a ≤10-cycle window while one conscious focus holds |

Recommended horizons: B1 ≈ 2000 cycles, B2 ≈ 500, B3 ≈ 300/goal, B4 ≈ 400, B5 ≈ 200, B6 ≈ 200.

## Notes

- B4/B5 rely on flags that are now **on by default** in `.env`
  (`ORRIN_TIER_CLOSURE`, `ORRIN_HARD_DISENGAGE`, `ORRIN_SURVIVAL_PREEMPT`).
- B1's RSS reading uses `psutil` if present; the watchdog also exports RSS via Prometheus.
- Scenario evaluators report `not_run` until their goal is seeded, `pending`
  until the run produces a terminal state, and **`not_committed`** when a seeded
  goal sat unplanned for >50 cycles (it never entered the committed set) — so a
  partial or misconfigured run scores honestly.
- `seed_scenario` **commits** the goal by default (creates it through the
  GoalsAPI at CRITICAL priority so the planner/Executive actually work on it).
  Pass `commit=False` for the old behavior (goals_mem.json only).
- Sampling records **both lanes** per cycle: the deliberate pick (`fn`) and the
  Executive lane's functions/goals (`fx`/`gx`). B2 counts novelty in either
  lane; B3 reports per-goal `pursuit_ticks` alongside wall-clock cycles; B6 is
  scored entirely from `gx`.
