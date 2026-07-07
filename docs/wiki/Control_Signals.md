# Control Signals (Overview)

What are control signals?
- Structured internal variables that quantify affect and drive: reward, activation, demands, throttle.
- They regulate when to deliberate, how exploratory behavior should be, and safety constraints.

Two readers
- Raw floats: used by low-level selectors and bandits.
- Qualitative renderer: converts signals into text summaries for human-facing UIs and reasoning layers.

Setpoint regulation
- Signals have per-agent baselines and velocity budgets to avoid instability.
- Adjustable via ORRIN_* environment variables.

Code pointers
- brain/control_signals/, brain/control_signals/signal_summary.py
