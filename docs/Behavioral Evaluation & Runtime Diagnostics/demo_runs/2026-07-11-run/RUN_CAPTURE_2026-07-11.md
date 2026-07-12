# Run 6 Capture — 2026-07-10 → 2026-07-11 life

*End-of-run evidence snapshot, taken the same morning as the graceful stop, before any
reset. This file is the manifest. Judgments live in `DEMO_RUN_2026-07-11.md` and the
analysis passes. Read `docs/NEXT_RUN_TESTS.md` "Run 6 re-test gate" + §6 (eleven
read-side checks) before drawing conclusions from these files.*

## Run boundaries (verified)

| Fact | Value |
|---|---|
| Launch | 2026-07-10 14:48:27 MDT (20:48:37Z), `single-instance lock acquired (pid 59935)` |
| Instance | single; `production_loop.jsonl` cycle counter strictly increasing → **zero relaunches** |
| Death | operator stop → graceful shutdown 2026-07-11 06:16 MDT (12:16:06Z), `heartbeat.clean_shutdown: true` |
| Cycles | **13,341** in ~15h 28m (one clean segment, ~4.17 s/cycle) |
| Code | commit `e4abfe7` (Companion & Presence, all 6 phases) — this life doubled as that build's staged verification |
| Reset | clean: cycle starts at 1, fresh Chapter 1, daemon store empty of prior-run goals; **`habituation.json` was cleared by `reset_orrin`** (Run 6 meter fix confirmed — all 5,052 entries born this run) |
| Carryover | `data/goals/artifacts/` still holds Run 2–5 artifact *folders* (reset does not sweep them); no prior-run goal was live |
| Dirty tracked seeds | `behavioral_functions_list.json`, `cognitive_functions.json`, `meta_rules.json`, `vocab_weights.json` mutated by the run (expected) |
| Mid-run surgery | none applied to the live process; the `fetch_and_read` URL-dedup fix (`FETCH_REREAD_LOOP_FIX_2026-07-11.md`) was written against the tree **after** death and is uncommitted — it did **not** run in this life |

## Headline numbers (raw, unjudged)

- `outcome_metrics.json` (two daily rows, run straddled midnight — sum both):
  goals completed **17** / failed **13** / retired **24**; `store_desyncs_repaired` **0** both days;
  `satiety_closures` **17** (first-ever nonzero — the meter fix took);
  `mean_significance` 1.141 / 1.187; `median_seconds_to_complete` 46.4 s / 117.6 s.
- `production_loop.jsonl` **13,341 rows** (exactly one per cycle): boolean sums
  `production_attempt` **443**, `production_success` **384**, `goal_model_hydrated` **893**,
  `committed_goal_present` 13,331; tail cumulative fields match the booleans this run.
- `effect_ledger.jsonl` **593 rows**, 546 credited: file_write 387, **bookkeeping 146**
  (the Fix-5 ledger class is live), symbolic_artifact 4, note_novel 4, tool_run_effect 3,
  **reuse 2**.
- **403 of the 433 file_write rows are one memo** —
  `memo_quadrf-can-spot-drones-and-see-wifi-through-my-wall---jeff-g.md`, rewritten in a
  loop at novelty ~0.002 until 41 s before death, and written into **10+ goal folders**.
- `commitment_signals.json` (new Fix-2 instrumentation) present; committed-goal share:
  `aspiration-self_understanding` **12,274 / 13,341 cycles = 92.0 %**.
- `failures.jsonl` **38 rows**, led by **12× `PermissionError` on
  `tests/fixtures/quality_golden/exemplars/research-memo-quadrf-…`** (first at minute 13
  of life) and 9× `no URLs to fetch`.
- `speech_log.json` 75 rows with **typed response_type** (share_finding 31,
  express_state 21, uncertainty 16, …); `presence_notifications.json` **3** all life;
  `relationships.json` holds the five R-room peer models.
- 31 log rotations captured (11 activity_log + 20 private_thoughts; private_thoughts
  rotated every ~18 min from 23:51 local onward — back-half thought flood again).

## What is in this folder

```
RUN_CAPTURE_2026-07-11.md      this manifest
DEMO_RUN_2026-07-11.md         gate verdict (read this first)
2026-07-11_run_analysis.md     timeline + eleven §6 read-side checks + root causes
2026-07-11_goals_system_audit.md  the commitment machinery post-Fix-2, forensically
2026-07-11_deeper_pass.md      fetch-loop + write_exemplar forensics, memory, speech, presence
2026-07-11_who_is_he.md        the person-shaped summary
INDEX.md                       reading order
data/                          brain/data snapshot (small stores plain, big stores .gz,
                               rotated_logs.tar.gz, effect_artifacts.tar.gz — 385 sidecars)
goals_daemon/                  root data/ snapshot (state.jsonl, wal.log.gz, snapshots/,
                               artifacts.tar.gz, runtime_state.json)
artifacts_readable/            plain copies of this run's memos, structure preserved
logs/                          brain/logs (runtime log, goal_progress, map_territory_audit, crash.log)
```

Coverage against `NEXT_RUN_TESTS.md` §4 must-captures: all present. New Run-6
instrumentation captured: `commitment_signals.json`, `presence_notifications.json`,
`trace.jsonl.gz` (bandit updates), per-candidate value components inside `events.jsonl.gz`.
