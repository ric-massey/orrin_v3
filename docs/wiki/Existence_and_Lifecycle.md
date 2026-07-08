# Existence and Lifecycle

Orrin's runtime is finite on purpose: it has a persistent lifetime budget, phases of
horizon-awareness, a terminal cycle, sealed run evidence, and a recoverable reset. This page maps
that machinery.

## The runtime-lifetime clock

`brain/cognition/runtime_lifetime.py` is the single source of truth for the lifetime budget:

- Rolled **once at first run** — a random span inside a band of roughly 365–730 days (bounded by
  `ORRIN_LIFESPAN_MIN_DAYS` / `ORRIN_LIFESPAN_MAX_DAYS`), persisted in `data/lifespan.json`, and
  counted in wall-clock days across restarts.
- The runtime's internal estimate of remaining lifetime is deliberately **approximate**: a small
  noise offset biases it, so the figure it acts on is not the true one.
- Horizon-awareness grows through four phases — early → middle → late → terminal — which
  progressively colour long-term prioritization.
- When the deadline arrives, the runtime runs its final cycle and the loop exits; the desktop app
  shows an end-of-life screen.

Do not confuse this with the supervisor's `LifespanByCycles` (`supervisor/lifespan.py`) — that is a
per-process uptime cutoff that resets on every restart.

## Restoration

Idle cycles are not dead time: the idle/consolidation phase runs memory consolidation, replay, and
closed-time accounting at a low-power cadence (see [The Cognitive Loop](The_Cognitive_Loop.md)).

## Life capsules (the run record)

`brain/evidence/life_capsule.py` seals one run into a single self-describing `.orrinlife.zip`
(under `exports/life_capsules/`): raw streams preserved, plus cleaned tables, a queryable SQLite
DB, computed metrics, a claims ledger, and a token-budgeted LLM bundle. Hand someone the file and
they can understand the run **without running Orrin**.

The organizing rule is `raw → cleaned → derived → interpreted`, each layer downstream-only; the
builder is a pure function of the raw layer, so anyone can deterministically rebuild the derived
artifacts and check the claims. `life_capsule_ingest.py` and `life_capsule_metrics.py` handle
ingestion and metrics.

## Reset (a new existence)

`reset_orrin.py` starts from fresh state — it is **not** routine maintenance, because state is
self-bounding (capped logs, windowed history, decaying memory; see `docs/CONFIGURATION.md`).

```bash
python reset_orrin.py                # snapshot + reset (recoverable)
python reset_orrin.py --dry-run      # show what would change
python reset_orrin.py --hard         # also clear bandit / decision learning
python reset_orrin.py --no-snapshot  # skip the snapshot (irrecoverable)
```

A reset rolls a new lifetime budget; identity, memory, and learning start over.

## Code pointers

- `brain/cognition/runtime_lifetime.py` — the clock
- `brain/evidence/life_capsule.py` — the capsule builder
- `reset_orrin.py` — reset with snapshot
- `frontend/src/pages/Life.tsx` — the Life room in the UI
