# Control Signals (Overview)

Control signals are Orrin's regulated internal state: a reward signal, an activation level, and a
set of named pressures (demands) that bias what runs next. They are the affective layer, modelled on
core-affect and reward-prediction-error theory (Russell & Barrett; Schultz), and they are stored as
raw numbers in `context["affect_state"]` (with a `core_signals` sub-vector).

## Two readers, on purpose

The two halves of cognition read the same state differently:

- **Background machinery reads the raw floats.** The bandit function-selector, the attention
  hijacker, and the cost-prediction layer use the numbers directly to bias selection.
- **The reasoning layer never sees a number.** `brain/control_signals/signal_summary.py` renders
  the signals into *qualitative* descriptions that name the felt quality ("a heaviness, like moving
  through something thick"), never the signal label or its value. Only that text reaches the
  inner-loop prompt, the self-descriptor, and the speech gate.

The intent: the reasoning layer reads its own *state estimate*, not a raw readout. Signals are
adaptation-adjusted first, so a state the runtime has habituated to stops dominating.

## Regulation

Control signals decay toward per-signal **setpoints** (not a flat midpoint) under a velocity budget,
so state integrates rather than lurches (`setpoints.py`, `regulation.py`, `homeostasis.py`). A
**convergence layer** (`arbiter.py`) means reactive and analytical subsystems submit proposals to a
single writer instead of racing on the shared state file.

## Where they come from and go

- **Sources:** prediction error, demand satisfaction/frustration, host-coupling deviation, peer
  signals, and workspace writeback.
- **Effects:** function selection, ignition likelihood, exploration vs. exploitation, attention
  capture, and how Orrin describes its own state.

## Tuning

Most setpoints are learned or in-code; a few knobs are env-exposed (`ORRIN_ALLOSTATIC_SETPOINT`,
`ORRIN_SIGNAL_DECAY`, `ORRIN_INTEROCEPTIVE_AFFECT`). See
[Tuning Control Signals](Tuning_Control_Signals) and the
[Deep Dive](Control_Signals_Deep_Dive).

## Code pointers

- `brain/control_signals/` — the whole subsystem
- `brain/control_signals/signal_summary.py` — the qualitative renderer (authored copy, load-bearing)
- `brain/control_signals/arbiter.py` — the single-writer convergence layer
