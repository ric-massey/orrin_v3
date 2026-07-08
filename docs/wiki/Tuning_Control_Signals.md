# Tuning Control Signals

Control-signal behavior is mostly **learned and in-code** (setpoints adapt to experience), so tuning
is a light touch, not a config dial. Reach for it when regulation misbehaves, not to chase a target
number.

## When to tune

- Signals **thrash** (rapid oscillation that destabilizes selection).
- A single state **dominates** and never habituates.
- Reward looks **stuck** and you've confirmed it's regulation, not a lack of production.

## What you can actually change

| Knob | Effect |
|------|--------|
| `ORRIN_ALLOSTATIC_SETPOINT` | Baseline the signals regulate toward |
| `ORRIN_SIGNAL_DECAY` | How fast signals relax toward setpoint |
| `ORRIN_INTEROCEPTIVE_AFFECT` | Whether interoceptive (host/body) state feeds affect |
| `ORRIN_IGNITION_GATE` | Whether ignition is gated at all (0 = always deliberate) |

Most setpoint and velocity behavior lives in `brain/control_signals/setpoints.py` and
`regulation.py` — change those in code, with a test, rather than adding env knobs.

## Process

1. Change **one** thing, small.
2. Run a scenario benchmark (`ORRIN_BENCHMARK=1`) or a short staging run and watch the signal rings
   / reward curve in the Brain room.
3. Compare before/after; keep only if the pathology improves without new instability.

## Rollback

State is snapshotted on reset, and config changes are small and reversible. If a change destabilizes
a run, revert the single knob and re-baseline. See [Control Signals: Deep Dive](Control_Signals_Deep_Dive)
for the underlying mechanics and [Troubleshooting](Troubleshooting) for symptom→cause tables.
