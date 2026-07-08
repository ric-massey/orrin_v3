# Loop Phases: Detailed Walkthrough

A stage-by-stage companion to [The Cognitive Loop](The_Cognitive_Loop). Each cycle of
`brain/ORRIN_loop.py` runs these phases in order; the whole substrate runs every cycle, but
*deliberate* cognition only when the ignition gate fires.

### 1. Perceive
Non-blocking gather of filesystem changes (`fs_perception.py`), UI/agent events, incoming messages,
and host telemetry, under a time budget so perception can't stall the loop.

### 2. Recall
Embedding-based retrieval (similarity + recency + per-memory strength), with a keyword-overlap
fallback when embeddings are unavailable. See [Memory System](Memory_System).

### 3. Prepare workspace
Subsystems emit candidate contents; **binding** composes co-occurring fragments into unified
situation candidates. All candidates enter the salience competition
([Binding and Workspace Writeback](Binding_and_Workspace_Writeback)).

### 4. Ignition
`should_think()` weighs salience, uncertainty, control-signal spikes, prediction error, goal drift,
and stagnation to decide reactive vs. deliberate. A periodic floor prevents indefinite silence.

### 5. Select function/action
The contextual bandit scores functions from learned value plus control signals, demands, the
workspace prior, and predicted cost; the action arbiter resolves the pick
([Action Selection and Bandit](Action_Selection_and_Bandit)).

### 6. Execute
The chosen function runs; generated code runs in a sandbox (`sandbox_runner.py`). Durable outputs
are recorded on the [effect ledger](Production_and_Effect_Ledger).

### 7. Reward accounting
Immediate reward is assigned now (`finalize_cycle`), and delayed credit is queued for the evaluator
daemons to reconcile later ([Learning and Adaptation](Learning_and_Adaptation)).

### 8. Persist
Durable state and WAL checkpoints are written; goal-step attempts are persisted so a restart can't
desync progress.

### 9. Maintain
Health checks, housekeeping, and supervisor heartbeats.

### 10. Idle / consolidate
At a low-power cadence: memory consolidation, replay, embedding pipeline work, and closed-time
accounting.

## Code pointers

- `brain/ORRIN_loop.py`, `brain/loop/` — the loop and phase implementations
- `brain/loop/deliberate.py` — the deliberate path taken on ignition
