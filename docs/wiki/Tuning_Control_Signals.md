# Tuning Control Signal Setpoints

When to tune
- If reward trajectories are flat, or bandit selections are failing to converge.

Process
- Adjust ORRIN_REWARD_SETPOINT and velocity budgets incrementally.
- Run benchmark scenarios and inspect reward curves.

Rollback
- Use configuration snapshots and small incremental changes.
