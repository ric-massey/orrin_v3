# Run 7 Capture — 2026-07-12 life

*End-of-run evidence snapshot, taken 2026-07-13 before any reset, from a stopped
instance (no Orrin process; heartbeat `clean_shutdown: true`). This file is the
manifest plus raw headline numbers. Analysis passes and the §8/Run-7 gate verdict
are **not yet written** — read `docs/NEXT_RUN_TESTS.md` §6 and
`RUN7_FIX_PLAN_2026-07-11.md` §4 before drawing conclusions from these files.*

## Run boundaries (verified)

| Fact | Value |
|---|---|
| Launch | 2026-07-12 10:33:18 MDT (16:33:29Z first log lines), pid 3555 |
| Instance | single; `crash.log` has exactly one session-start line; `production_loop.jsonl` cycle counter strictly increasing 1→11,060 → **zero relaunches** |
| Death | operator stop → graceful shutdown 2026-07-12 18:36 MDT (2026-07-13T00:36:45Z), `heartbeat.clean_shutdown: true` at cycle 11,051 |
| Cycles | **11,060** in ~8h 03m (one clean segment, ~2.62 s/cycle) |
| Code | commit `bb3685a` (Pre-Run-7 tidy) on top of `a63b160` (Run 7 fix plan F1–F8) |
| Reset | clean: `_archive/snapshot_20260712_103249_pre_reset` taken at launch minute; cycle starts at 1; `habituation.json` all 5,034 entries born this run |
| Dirty tracked seeds | `cognitive_functions.json`, `meta_rules.json`, `vocab_weights.json` mutated by the run (expected) |
| Mid-run surgery | none |
| run_log.txt | not present — this life was not launched via `run_orrin.sh` tee, so there is no root run log to capture |

## Headline numbers (raw, unjudged)

- `outcome_metrics.json` (single daily row, 2026-07-12): goals completed **14** /
  failed **14** / retired **21**; `store_desyncs_repaired` **0**;
  `satiety_closures` **12**; `mean_significance` 1.205;
  `median_seconds_to_complete` 49.5 s; completion_rate 0.23.
- `production_loop.jsonl` **11,060 rows** (one per cycle): `production_attempt`
  **38**, `production_success` **26**, `goal_model_hydrated` **908**,
  `committed_goal_present` 11,058. (Run 6: 443 attempts / 384 successes, ~93 % of
  it one memo — the attempt collapse is the pump deflating, not a comparable drop.)
- `effect_ledger.jsonl` **161 rows** (Run 6: 593) — **new F-plan schema: no
  `credited` field on rows; credit now lives at the evaluator** (Run 7 deviation
  list). Kinds: bookkeeping 116, **file_write 33** (Run 6: 433), tool_run_effect 5,
  reuse 4, note_novel 3; `dedupe: true` on 11 rows.
- **No memo loop.** The 33 file_writes spread across ~20 distinct targets; the
  most-rewritten single file was written **2×** (Run 6: one memo 403×). 5
  `research_memo.md`, and **one `synthesis.md`** (first captured synthesis;
  Run 6: 0), under `intrinsic-2026-07-12T17:53:40…/`.
- `commitment_signals.json`: `aspiration-self_understanding` `value_ema`
  **0.5196** (Run 6 pumped value: 0.8142) — the anti-pump held. But committed-goal
  share is still **10,052 / 11,060 cycles = 90.9 %**, with `stale_cycles` 10,291
  and `avoid_streak` 6,852 on the incumbent: the monopoly survived **without**
  a pumped value signal.
- Aspiration `contribution_count`: self_understanding **1**, world_knowledge
  **3**, genuine_contact **0**, output_producing **7**.
- `quality_standard_revisions.json`: **13 rows** (Run 6: 200, of which 189 were
  the looped memo).
- `failures.jsonl` **55 rows**: 52 `goal_failure` sites, plus **2×
  `PermissionError` on the exemplars dir and 1× boot-time `OSError: exemplars dir
  not writable at boot`** — the F-plan diagnostics-first check fired; the
  `write_exemplar` EACCES root cause remains unresolved.
- `production_funnel.json`: **candidate-only** (72 events, no later stages) —
  §6 check 2 must state this explicitly.
- `speech_log.json` 74 rows, typed (share_finding 25, express_state 20,
  uncertainty 13, answer 12, ask_grounded_question 2, greet_return 1);
  `presence_notifications.json` **3**.
- Daemon artifacts: **105 files written this run** across ~15 goal folders;
  **18 readable .md** (16 distinct memo titles across 12 folders — Run 6 wrote
  one title into 10+ folders).
- 28 log rotations captured (8 activity_log + 20 private_thoughts).

## What is in this folder

```
RUN_CAPTURE_2026-07-12.md      this manifest (analyses pending)
INDEX.md                       reading order
data/                          brain/data snapshot (small stores plain, big stores .gz,
                               rotated_logs.tar.gz, effect_artifacts.tar.gz — 26 sidecars)
goals_daemon/                  root data/ snapshot (state.jsonl, wal.log.gz, snapshots/,
                               artifacts.tar.gz, runtime_state.json)
artifacts_readable/            plain copies of this run's .md memos + synthesis, structure preserved
logs/                          brain/logs (runtime log, goal_progress, map_territory_audit, crash.log)
```

Coverage against `NEXT_RUN_TESTS.md` §4 must-captures: all present (`run_log.txt`
does not exist this run, noted above). Same 58-file `data/` set as the Run 6
capture; no new Run 7 stores existed to add (F1–F8 instrumented existing stores).
