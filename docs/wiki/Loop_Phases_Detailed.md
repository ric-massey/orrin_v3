# Loop Phases: Detailed Walkthrough

Perceive
- Inputs: filesystem events, socket messages, UI interactions, host telemetry.
- Implementation notes: non-blocking IO, time budget enforcement.

Recall
- Embedding-based retrieval with recency bias; fallback token overlap.
- Memory DAOs expose top-K retrieval APIs.

Prepare Workspace
- Subsystems propose actions as candidate objects with metadata (priority, expected cost, prerequisites).

Ignition
- Deliberation gate evaluates proposals, control signals, and resource budgets.

Select Function/Action
- Bandit selector ranks functions based on historical reward and exploration policy (UCB-like).

Execute
- Functions execute within sandboxes, report effects and produce reward signals.

Reward Accounting
- Immediate reward and delayed evaluation via evaluator daemon reconciles long-term outcomes.

Persist & Maintenance
- WAL writes and snapshotting ensure durability.

Idle/Consolidate
- Background embedding, clustering, and index updates.
