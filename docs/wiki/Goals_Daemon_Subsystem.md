# Goals Daemon Subsystem

`goals/` is a separate, durable subsystem that owns goal **lifecycle and state** — planning NEW
goals, scheduling READY steps, and running them via a worker pool — decoupled from the cognitive
cycle. The in-loop counterpart is the Executive (`brain/cognition/planning/executive.py`), which
advances goal steps every ~7s; see [Goals: Executive vs. Daemon](Goals_Executive_vs_Daemon).

## Durability

- `goals/wal.py` + `goals/events.py` — typed events serialized to an append-only, newline-delimited
  JSON write-ahead log. State is reconstructable from the WAL.
- `goals/snapshot.py` — periodic snapshots so recovery doesn't replay from the beginning.
- `goals/store.py` — the state store (`data/goals/state.jsonl` plus WAL/snapshots/artifacts under
  the root `data/` tree, separate from `brain/data/` — see `docs/CONFIGURATION.md`).
- Goal state survives restarts and step attempts are persisted durably, so a restart cannot silently
  reset progress or desync the daemon from the brain's view of a goal.

## Lifecycle

- `goals/goals_daemon.py` — the orchestrator: plans new goals, schedules READY steps, runs them on
  a worker pool, and emits lifecycle events.
- `goals/runner.py` — executes steps via handlers; on a step's DONE transition, any artifacts the
  handler recorded (`Step.artifacts`) are registered on the effect ledger, so goal work earns
  production reward (see [Production and the Effect Ledger](Production_and_Effect_Ledger)).
- `goals/schema.py` / `goals/model.py` — goal and step representations.
- `goals/policy.py` / `goals/triggers.py` — admission policy and event triggers.
- Goals span timescales, from seeded lifetime aspirations down to short-term subgoals, with plan
  adaptation (surgical subgoal reshaping) and reactive replanning when a capability fails
  mid-pursuit.
- **Aspirations are fail-able**: long-horizon goals carry guards rather than living forever, so a
  goal that stops producing can be failed and replaced instead of absorbing attention indefinitely.

## Design notes

- The daemon deliberately **parks generic goals**: work without a concrete handler stays with the
  in-loop Executive, so the daemon lane holds only steps it can actually run.
- Keep goals small and measurable; explicit success criteria make outcome learning reliable. Goal
  closure grounds on the effect ledger (`has_qualifying_effect`), not on self-report.

## Code pointers

- `goals/goals_daemon.py`, `goals/store.py`, `goals/wal.py`, `goals/runner.py`
- `brain/cognition/planning/executive.py` — the in-loop step advancer
- `data/goals/` — WAL, snapshots, state (runtime, gitignored)
