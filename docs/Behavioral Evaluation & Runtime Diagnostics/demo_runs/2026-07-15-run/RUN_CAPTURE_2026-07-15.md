# Run 8 capture — 2026-07-15 life

Raw boundaries, preconditions, snapshot manifest, and unjudged headline numbers.
Verdict + gate scoring live in `DEMO_RUN_2026-07-15.md`.

## Boundaries — one life, two runtime segments split by a crash

This life is **9,785 cognitive cycles** but it did **not** run in one process.
A crash killed the `orrin-brain` thread mid-life; the process pulsed on as a
zombie for ~6.5 h until the liveness watchdog flagged it, then the runtime was
relaunched with a fix and resumed the **same** cycle counter (no reset).

| Marker | Local (EDT) | UTC | Cycle |
|---|---|---|---|
| Launch #0 (segment 1) | 2026-07-15 02:27:39 | 06:27:39 | 1 |
| **Crash** — `make_candidate()` TypeError, brain thread dies | 04:57:06 | 08:57:06 | ~4418 |
| Loop's last live heartbeat (`runtime_lifetime.last_active`) | 04:56 | 08:56:23 | 4400 |
| Zombie interval (process alive, cognition dead) | — | 6.56 h | frozen at 4400 |
| Watchdog logs `silent_death` (`lifecycle_events.jsonl`) | 11:29:56 | 15:29:56 | 4400 |
| Relaunch #0 (segment 2, fixed `invoke.py`) | 11:29:47 | 15:29:47 | resumes ~4419 |
| `run_history` Chapter 1 opens | 11:34:58 | 15:34:58 | — |
| Last cognitive cycle | 15:41 | 19:41:37 | 9785 |

`production_loop.jsonl` shows a single 1-cycle discontinuity (4417→4419) at the
seam — exactly cycle 4418 is missing, i.e. the loop died *mid-cycle 4418*. That,
not ~4253, is the true crash cycle: the "cycle 4253 complete" lines flanking the
traceback in `crash.log` are stale block-buffered stdout (the known `tee`
buffering gotcha — the wrapper's pipe runs ~160 cycles behind), while the
CRITICAL logger timestamp (08:57:06Z) and the heartbeat (cycle 4400 at 08:56:23Z,
43 s earlier) are direct writes. Three counters, one lesson: `production_loop`'s
cycle stamps are the only crash-accurate record — the cycle-stall tripwire
follow-up should key on those, not on heartbeat or stdout.

The cycle counter is otherwise continuous, so cross-file cumulative state
(`decision_stats`, `effect_ledger`, driver-slot occupancy) spans the whole life.
**Caveat:** `production_loop`'s *own per-row funnel counters*
(`production_attempt_count` etc.) do **not** — they reset to 0 at the seam
(segment 1 ended at attempts 17 / successes 10 / bookkeeping 81; segment 2 ended
at 20 / 11 / 36). Whole-life row-level truth: **37 attempts, 21 successes**.
Reading segment 2's final row as life totals undercounts by ~half.
`runtime_lifetime.json` treats it as one continuous life (start 06:27 UTC).

### The crash — root cause (see `logs/CRASH_TRACEBACK.txt`)

```
TypeError: make_candidate() missing 2 required keyword-only arguments:
           'kind' and 'direction'
  brain/loop/invoke.py:108  →  return fn(**built)
```

`_invoke_cognition` built the positional/keyword args it could satisfy and
called `fn(**built)`. Its unsatisfied-argument guard only inspected
`POSITIONAL_ONLY` / `POSITIONAL_OR_KEYWORD` params — it did **not** consider
required **keyword-only** params. `make_candidate(*, kind, direction)` therefore
passed the "dispatchable" check with `kind`/`direction` absent, and the call
raised an uncaught `TypeError` that propagated through `execute.py` and
`ORRIN_loop.py` and killed the brain thread.

**Fix (applied between segments, currently uncommitted):**
`brain/loop/invoke.py` adds `inspect.Parameter.KEYWORD_ONLY` to the
unsatisfied-arg set. Post-fix the dispatcher skips the function cleanly —
`error_log.txt` 15:29:20Z: *"make_candidate needs ['kind', 'direction'] — not
directly dispatchable; skipping"* — and segment 2 ran crash-free to death.

**Status:** this is a real dispatcher bug and a real fix. *(Second pass: the fix
is now **committed** in `e70ac98` with the rest of this capture; it still **has no
regression test** — that remains the follow-up.)*

## Preconditions

- Build under test: `RUN8_FIX_PLAN_2026-07-14.md` F1 (absolute staleness
  refractory, `commitment_value.py`) + F2 (admit all four aspirations to the
  directional pool), commit `fc2b635`, on top of Run 7's anti-pump credit.
- Segment 1 ran the committed tree; segment 2 additionally carried the
  uncommitted `invoke.py` crash fix.
- No provider key required (symbolic-first). `ORRIN_STALE_REFRACTORY=1` (default).

## Snapshot manifest

- `data/` — `commitment_signals.json` (per-goal stale/avoid/blocks + new `driver`
  key), `commitments.json`, `comp_goals.json`, `goals_mem.json`,
  `outcome_metrics.json`, `aspiration_scoreboard.json`, `decision_stats.json`,
  `effect_ledger.jsonl`, `action_reward_ema.json`, `runtime_lifetime.json`,
  `cycle_count.json`, `lifecycle_events.jsonl`, `production_loop.jsonl.gz`
  (9,784 rows, one/cycle — the driver-slot source).
- `logs/` — `crash.log`, `CRASH_TRACEBACK.txt`, `run_boundaries.txt`,
  `error_log.txt` (20 lines), `map_territory_audit.jsonl`, `activity_log.txt.gz`.
- `artifacts_readable/` — 21 effect artifacts written this life.

## Raw headlines (unjudged — see the verdict for caveats)

- **Driver-slot occupancy (whole life):** self_understanding **42.58 %**,
  world_knowledge 29.29 %, output_producing 25.30 %, genuine_contact 1.35 %.
  Run 7 was **90.9 %** on a single goal.
- **Per segment:** seg 1 self_understanding 54.2 % / world 38.4 %; seg 2
  output_producing 43.8 % / self 33.1 % / world 21.9 %. Both < 60 %.
- **2,093 driver transitions; longest single hold 75 cycles** (Run 7: 106
  transitions, incumbent held ~5,273 consecutive). The longest hold belongs to
  `ltc_aspiration-self_understa_1` (an LTC child), not a raw aspiration — the
  four aspirations themselves rotated even faster than the headline implies.
  12 distinct ids held the slot, including a self-diagnosis goal literally titled
  *"Figure out why quality_standard.gate.write_exemplar isn't working"* (6 cycles,
  segment 2 — Orrin turned the boot-probe EACCES error into a goal).
- **`refractory_events`: absent. All `recommit_block_pulls` = 0. Max
  `stale_cycles` at death = 8.8, max `avoid_streak` = 5.6** (Run 7: 10,291 /
  6,852). F1 never tripped.
- **`value_ema`** max 0.625, all goals 0.50–0.625 — no pump (Run 6 was 0.81).
- **Completions:** 16 in `comp_goals` / 13 distinct titles; `mean_significance`
  1.242; `median_seconds_to_complete` 112.7 s; `satiety_closures` 16;
  `goals_failed` 7; `store_desyncs_repaired` 0. Counter reconciliation:
  `outcome_metrics.goals_completed` says **17** (one completion never archived to
  `comp_goals`); the scoreboard attributes only **14** (the two
  "Strengthen COGNITIVE/EMOTIONAL symbolic reasoning" completions carry
  `driven_by: null` and are invisible to aspiration attribution).
- **Contribution by aspiration** (`aspiration_scoreboard`): output_producing
  completed **11**, self_understanding 2, world_knowledge 1, genuine_contact 0.
  Sharper: `genuine_contact` has **zero scoreboard events at any stage** — not
  even `generated` — and is the only aspiration in `commitment_signals` with no
  `recent_hashes`. The hole is at goal *generation*, not completion.
- **Effect ledger:** 21 file_write, 15 note_novel, 2 tool_run_effect, 1
  symbolic_artifact, **2 reuse**, 117 bookkeeping. The reuse rows have no
  path/ref *fields*, but both `content_hash`es resolve to captured artifacts
  (`52c805…` = the written-language research memo; `84f366…` = an offline
  synthesis that cites that memo **by filename**) — the reuse chain is fully
  traceable; what's missing is telemetry (`mark_reused` hard-codes `cycle=0` and
  writes no path).
- **`write_exemplar` EACCES persists in-life** — exemplars dir mode `0o40500`
  (no write) at both boot probes. *(Second pass: root cause was the repo-wide
  `uchg` immutable lock + stripped write bits; cleared post-capture 2026-07-15 —
  the dir is now `0o700`. Next life is the first with exemplar promotion live.)*
- **0 tracebacks in segment 2**; the only crash is the segment-1 seam above.
- **Capture gap:** the `goals_daemon/` folder in this capture is **empty** — no
  daemon WAL/snapshot was taken. Consequence: only 3 of the 7 failed goals are
  visible anywhere in this folder (the three `error_log` lines), and comp_goals
  archives completions only. Future captures should include the daemon tree.

*Written 2026-07-15 from the live `brain/data` snapshot.*
