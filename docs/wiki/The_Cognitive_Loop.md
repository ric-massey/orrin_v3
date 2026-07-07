# The Cognitive Loop

Overview
The cognitive loop is Orrin's heartbeat. Each cycle performs perception, memory retrieval, workspace preparation, ignition decision, action selection, execution, reward accounting, persistence, maintenance, and idle consolidation. The loop separates fast reactive cycles from deeper deliberation phases.

Phases
1. Perceive — gather inputs: sensors, UI events, host telemetry.
2. Recall — fetch relevant memories using embedding similarity and recency biases.
3. Prepare Workspace — assemble action proposals from subsystems.
4. Ignition — decide whether to deliberate or stay reactive using the deliberation gate.
5. Select Function/Action — bandit-based selector chooses the cognitive function to run.
6. Execute — run the function; produce effects and artifacts.
7. Reward Accounting — assign immediate and delayed rewards to update bandits and signals.
8. Persist — write WAL checkpoints and durable artifacts.
9. Maintain — housekeeping, health checks.
10. Idle/Consolidate — background memory consolidation, embedding pipeline.

Timing and tuning
- Cycle duration and ignition thresholds are configurable via ORRIN_* settings in Configuration_Reference.md.
- Deliberation is more expensive but results in more complex behavior; tuning balances CPU, cost, and responsiveness.

Code pointers
- brain/loop, brain/cognition, memory/README, goals/
