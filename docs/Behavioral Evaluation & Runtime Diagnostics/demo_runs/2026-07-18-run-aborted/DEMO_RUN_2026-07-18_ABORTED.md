# Run 10, attempt 1 — ABORTED (2026-07-18)

**Not scoreable. No verdict.** This life was killed externally at ~1/5 of a normal
lifespan; it is captured for provenance only. The Run 10 gate
(`docs/NEXT_RUN_TESTS.md` §Run 10) remains untested and rolls over to the relaunch.

## Shape

- **Segment:** single, clean. Cycles 1–2671 contiguous in `production_loop.jsonl`.
- **Wall clock:** 2026-07-18 08:04:44 → 09:47:39 EDT (12:04–13:47 UTC), ~1 h 43 m.
- **Mode:** symbolic-only (no provider key; `LLM unavailable` throughout the log).
- **Build:** `b175ed2` (Run 10 build, R10-1..R10-12). Working tree clean apart from
  the state file `brain/data/cognitive_functions.json`.

## Cause of death (not cognitive)

Terminal/window closed at 09:47 → `graceful_shutdown(ctx)` entered → its first
`print()` (`runtime/lifecycle.py:132`) raised `BrokenPipeError` because the
`run_orrin.sh` tee pipe was already gone. Consequences:

1. The remainder of `graceful_shutdown` never ran — subsystems died with the
   process, not via their stop path (`final_thoughts_written: false`).
2. `run_orrin.sh`'s run-lock cleanup did not complete — the repo was left
   `chflags`/`r-x` locked and had to be released by hand
   (`./scripts/orrin_run_lock.sh unlock`) during capture.

The runtime log shows no errors before the shutdown; the last hour is routine.

**Fix shipped post-capture:** shutdown prints made pipe-safe in
`runtime/lifecycle.py` so a dead stdout can no longer abort the shutdown sequence.

## What the 1.7 h fragment showed (observations, not scores)

- **Occupancy** (2,671 cycles): `self_understanding` 55.9 %, `world_knowledge`
  35.2 %, `genuine_contact` 4.0 %, `ltc_…self_understa_1` 2.8 %,
  `output_producing` 2.1 %. Rotation was working — four aspirations plus an LTC
  goal held the slot — but 2,671 cycles is far too short to score S10/occupancy.
- **Production:** effect ledger 79 rows (64 bookkeeping, 11 file_write,
  3 tool_run_effect, 1 note_novel); funnel window all `candidate`-stage;
  0 goals-daemon artifacts; `failures.jsonl` 2 rows. Nothing gate-relevant
  reached maturity in under two hours.
- No crash, no watchdog fire, no desync observed in the fragment.

## Capture

`data/` (brain/data minus `*.lock`), `logs/` (brain/logs), `goals_daemon/`
(full `data/goals` tree incl. WAL + snapshots), verified with `diff -rq` at
capture time. Pruned before commit, per prior-capture convention: `data/_archive/`
(pre-reset snapshots of *other* lives) and `data/language/` (cross-life
`native_lm.pt`, 38 MB — not this life's evidence).

## Disposition

Clean reset performed after this capture; Run 10 relaunch pending on the same
build `b175ed2` + the pipe-safe shutdown fix. Gate and fix-list attribution are
unchanged from the 07-17 run doc.
