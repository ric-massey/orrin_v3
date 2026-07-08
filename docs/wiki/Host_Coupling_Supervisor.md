# Host Coupling & Supervisor

`supervisor/` plus `watchdogs.py` keep the runtime alive and keep it from harming the machine it
runs on. The design principle: the same host metrics feed **three deliberately separate mappings**
(see [Host Coupling](Host_Coupling.md) for the conceptual view):

1. **Absolute floors → reflex.** `supervisor/host_resources.py` (`HostResourceGuard`) watches
   disk/swap/memory below cognition and pauses heavy cycles at safety floors — separate from the
   deliberative loop, because a thrashing loop can't be asked to rescue the substrate it runs on.
2. **Deviation from a learned band → control signals.** `brain/cognition/host_resource_monitor.py`,
   `resource_self_monitor.py`, `host_band.py` — so a small or busy machine is not registered as
   chronic distress.
3. **Absolute capacity → cadence.** `brain/cognition/resource_cadence.py` — a small machine runs at
   a slower cadence, not a degraded one.

## Supervisor watchdogs

Started by `watchdogs.py` (`start_watchdogs`):

- `heartbeatdetector.py` — liveness: notices when the loop stops emitting heartbeats.
- `error_checker.py` / `errors.py` — error-rate monitoring with an exception ratchet.
- `liveness_cycle.py` — cycle-progress watchdog.
- `lifespan.py` — a **per-process** uptime cutoff that resets on every restart. This is distinct
  from the runtime-lifetime clock (`brain/cognition/runtime_lifetime.py`), which is a persistent,
  finite lifetime budget — see [Existence and Lifecycle](Existence_and_Lifecycle.md).
- `memory.py` — process memory watchdog.
- `no_goals.py` / `repeat.py` / `trend.py` — behavioral guards: no active goals, repetitive
  behavior, and degrading trends.
- `resource_floor.py` + `resource_floor_calibration.py` — the calibrated absolute floors the guard
  enforces (observe-only until calibrated for the machine).

## Calibration on a new machine

`brain/cognition/infancy.py` learns *that machine's* normal oscillation before the runtime trusts
its own deviation signals, and `brain/cognition/host_budget.py` exposes a user-facing RAM budget
slider that feeds both the cadence policy and the reported "100%".

## Code pointers

- `supervisor/supervisor.py` — assembly
- `supervisor/host_resources.py` — the reflex guard
- `watchdogs.py` — watchdog startup
- `brain/cognition/host_band.py`, `resource_cadence.py`, `infancy.py`, `host_budget.py`
