# Goals: Executive vs. Goals Daemon

Overview
- Two-tier goal system: Executive (fast scheduler), Goals daemon (durable owner).

Goals daemon
- WAL-backed durable store exposing lifecycle APIs and snapshots.

Executive
- In-process component that advances goals stepwise and bridges loop cycles with the daemon.

Goal lifecycle
- States: active, paused, completed, failed, abandoned.
- Transitions governed by Executive based on resource budgets and control signals.

How to add goals
- Use the goals API to create goal objects; include metadata for priority and estimated effort.
