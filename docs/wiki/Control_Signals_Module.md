# Control Signals Module

Module layout
- brain/control_signals/: signal model, renderer, commit_signals(), and setpoint utilities.

Key functions
- commit_signals(): atomically apply a set of proposed signal updates.
- render_signal_summary(): convert numeric signals into qualitative text for UI and reasoning.

Common bugs & fixes
- Non-atomic updates: ensure commit_signals() is used to avoid race conditions.
