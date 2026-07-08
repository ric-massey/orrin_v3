# Control Signals: Deep Dive

The mechanism-level companion to [Control Signals](Control_Signals). Covers the data model, the
qualitative renderer, regulation, and how to diagnose signal problems.

## Data model

Control-signal state lives in `context["affect_state"]`: a reward signal, an activation level, a
`core_signals` sub-vector of named pressures, plus demands and throttle. Values are raw floats; the
canonical field set is defined in `brain/control_signals/` (see `apply_signal_feedback.py`,
`model.py`).

## The two readers

- **Raw floats** drive the bandit selector, attention hijacker, and cost-prediction layer directly.
- **The qualitative renderer** (`signal_summary.py`) turns the floats into felt-quality text for the
  reasoning layer — it never exposes a label or a number. This copy is behaviorally load-bearing
  (it shapes how Orrin describes its own state) and is deliberately kept as authored text. Signals
  are adaptation-adjusted first, so habituated states stop dominating.

## Regulation

- **Setpoints** (`setpoints.py`) — signals decay toward per-signal baselines, not a flat midpoint.
- **Velocity budget** (`regulation.py`, `signal_dynamics.py`) — bounded rate of change, so state
  integrates rather than lurches; saturation clipping bounds extremes.
- **Convergence layer** (`arbiter.py`) — a single writer owns the state file; daemons submit
  proposals to a lock-guarded inbox instead of racing.
- **Drift and homeostasis** (`signal_drift.py`, `homeostasis.py`) — long-run baseline maintenance.

## Tuning and diagnosis

Most setpoints are learned or in-code; env-exposed knobs include `ORRIN_ALLOSTATIC_SETPOINT`,
`ORRIN_SIGNAL_DECAY`, and `ORRIN_INTEROCEPTIVE_AFFECT`. When diagnosing:

- **Signal thrashing** → tighten the velocity budget / decay; check for two writers bypassing the
  arbiter.
- **Reward stuck flat** → inspect the delayed-learning daemons (`brain/eval/`) and the effect ledger
  — a flat reward often means nothing is being *produced*, not that regulation is broken.
- **A state dominates forever** → check adaptation/habituation; the renderer should down-weight a
  chronic signal.

The UI's Brain room surfaces the live signal rings and tensions for exactly this.

## Code pointers

- `brain/control_signals/` — full subsystem (setpoints, regulation, dynamics, arbiter, summary)
- `brain/control_signals/signal_summary.py` — the qualitative renderer
