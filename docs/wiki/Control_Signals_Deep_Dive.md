# Control Signals: Deep Dive

Data model
- affect_state: {reward: float, activation: float, demands: dict, throttle: float}

Rendering logic
- Transform raw floats into qualitative descriptions using adaptive vocabularies and habituation correction.

Setpoint regulation
- Per-signal baseline (learned), velocity budgets, and saturation clipping.

Tuning guide
- ORRIN_REWARD_SETPOINT, ORRIN_BANDIT_EPSILON, and other variables control responsiveness.

Common issues and fixes
- Signal thrashing: increase velocity budget or smoothing.
- Reward stuck: inspect evaluator daemon and delayed learning logs.
