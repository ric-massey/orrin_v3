# Run 5 Capture — 2026-07-08 life

*End-of-run evidence snapshot, taken immediately after the graceful stop, before any
reset or further writes. This file is the manifest; the analysis passes have not been
written yet. Read `docs/NEXT_RUN_TESTS.md` §2 (nine signals) and §6 (eleven Run 5
read-side checks) before drawing conclusions from these files.*

## Run boundaries (verified from run_log.txt, line-cited)

| Fact | Value |
|---|---|
| Launch | `launch #0` 2026-07-08 08:42:58 local (wrapper pid 94583) — run_log line 1 |
| Instance | single, `single-instance lock acquired (pid 99882)` — run_log line 3 |
| Relaunches / crashes | **zero** — no `crashed`/`restarting` lines in the whole log |
| Death | operator SIGTERM → `graceful shutdown` (run_log line 23324) → `shutdown complete`, 2026-07-08 20:22 local (2026-07-09T00:22:30Z per run_history death entry) |
| Cycles | **12,330** (~11.7 h wall clock, one clean segment) |
| Life span | ~11h 39m, launch to shutdown, no mid-life gaps |
| Code | commit `f0c4698` (Run 5 fixes F1–F9 + addendum F10–F22), **clean reset** before launch same day |
| Reset gotcha | `reset_orrin` empties the committed `control_signals_model.json` seed — was restored from git before launch |
| Dirty tracked files | `brain/data/behavioral_functions_list.json` and `brain/data/cognitive_functions.json` are git-tracked seeds mutated by the run (expected; do not "clean" them before analysis) |

## Headline numbers (raw, unjudged)

From `data/outcome_metrics.json` (single daily row, no midnight straddle this time):
goals completed **13** / failed **6** / retired **18**; `store_desyncs_repaired` **0**;
`mean_significance` **1.176**; `satiety_closures` **0**;
`median_seconds_to_complete` **42.2 s** (vs Run 3's 3,722 s — needs scrutiny, not
celebration). `effect_ledger.jsonl` **200 rows**; `failures.jsonl` **32 rows**;
`production_loop.jsonl` **12,330 rows** (exactly one per cycle — full coverage, no
counter-reset seams since there was no relaunch). Four goal folders produced
`research_memo.md` files and three intrinsic goals produced `synthesis.md`
(see `artifacts_readable/`).

One behavioral flag spotted during capture: `private_thoughts` rotated every
~11 minutes from 15:01 onward (20 of the 29 rotations) — a thought-stream flood in
the back half of the life worth explaining.

## What is in this folder

```
RUN_CAPTURE_2026-07-08.md      this manifest
data/                          brain/data snapshot (cognitive core)
  *.json, *.jsonl              small stores, plain copies
  *.gz                         big stores, gzipped single files
  rotated_logs.tar.gz          all 29 log rotations (9 activity_log + 20 private_thoughts, all from this run)
  effect_artifacts.tar.gz      106 effect-ledger sidecar bodies (F4 capture)
goals_daemon/                  root data/ snapshot (daemon side)
  state.jsonl, wal.log.gz      goals daemon current state + WAL
  snapshots/                   daemon snapshots
  artifacts.tar.gz             full data/goals/artifacts tree
  runtime_state.json
artifacts_readable/            plain copies of every research_memo.md / synthesis.md,
                               original directory structure preserved
```

Coverage against `NEXT_RUN_TESTS.md` §4 (must-capture): all items present —
`outcome_metrics.json`, `effect_ledger.jsonl`, `comp_goals.json` + goals WAL,
`goals_mem.json`, `action_reward_ema.json`, `activity_log.txt` + rotations.

Coverage for the §6 read-side checks: `production_loop.jsonl.gz` (check 1),
`production_funnel.json` (2), goals stores + ledger (3), ledger + sidecars (4, 5),
`long_memory.json.gz` + `memory_graph.jsonl.gz` (6), `evaluator_wal.jsonl.gz` (7),
`decision_stats.json` + activity log (8), goals stores + funnel + ledger (9),
`speech_log.json` (10), `workspace_writeback.jsonl.gz` (11).

## Deliberately NOT captured (still in the live tree — analyze there if needed)

- `brain/data/language/` (38 MB, includes `native_lm.pt` weights)
- `brain/data/_archive/` (34 MB) and `brain/data/telemetry_archive.jsonl` (4.8 MB)
- `brain/data/trace.jsonl`, `reflection_log.json`, `cognition_history.json`,
  `prediction_metrics.jsonl`, `predictions.json`, `telemetry_history.json`
- `data/memory/wal/` (23 MB memory-daemon WAL; `long_memory` + `memory_graph`
  snapshots are captured and are what §6 check 6 reads)

If the analysis needs one of these, take it from the live tree **before** the next
`reset_orrin` — this folder is the only thing that survives a reset.

## What the analysis session should produce (pattern from 07-05)

`INDEX.md`, `DEMO_RUN_2026-07-08.md` (§8 verdict, nine signals),
`2026-07-08_run_analysis.md`, then the deeper passes as warranted. Run 5 gate per
the 07-05 findings: F1 (real composition, no template stamping), F2 (aspirations
survive), F3 (learned-note bodies survive pruning), plus §6's eleven honesty checks.
