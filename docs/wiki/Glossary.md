# Glossary

Key terms used across the codebase and wiki. Each names a specific **engineering mechanism**, not a
claim of subjective experience.

### Affect state / core signals
The regulated internal-state vector in `context["affect_state"]` (a reward signal, activation level,
and a `core_signals` sub-vector of named pressures). Biases what runs next.
→ [Control Signals](Control_Signals)

### Aspiration
A long-horizon, seeded lifetime goal. Aspirations are **fail-able** — guarded so one that stops
producing is failed and replaced, not kept forever. → [Goals: Executive vs. Daemon](Goals_Executive_vs_Daemon)

### Bandit selector
The contextual multi-armed bandit that picks the next cognitive function (each arm is a function),
biased by control signals, demands, the workspace prior, and predicted cost.
→ [Action Selection and Bandit](Action_Selection_and_Bandit)

### Binding
The pre-workspace stage that composes co-occurring fragments into unified *situation* candidates for
the salience competition. → [Binding and Workspace Writeback](Binding_and_Workspace_Writeback)

### Consolidation
The idle-cycle process that moves worth-keeping working-memory items into long-term memory and
replays/decays the store. → [Memory System](Memory_System)

### Control signals
See *Affect state*. Read two ways: raw floats for the background machinery, qualitative text for the
reasoning layer. → [Control Signals](Control_Signals)

### Demand
A named internal pressure (a need) that biases selection and is relieved by particular actions; the
demand-expectations layer learns which. → [Learning and Adaptation](Learning_and_Adaptation)

### Effect / effect ledger
A durable outward effect (file, memo, delivered reply, symbolic production), recorded content-addressed
and novelty-deduped. Reward is denominated in these, not internal events.
→ [Production and the Effect Ledger](Production_and_Effect_Ledger)

### Executive
The in-loop scheduler that advances goal *steps* every ~7s, distinct from the durable goals daemon.
→ [Goals: Executive vs. Daemon](Goals_Executive_vs_Daemon)

### Expression membrane
The single door (`express_to_user`) through which all person-facing output is composed from an
intent, never scraped from internal state. → [Expression Membrane](Expression_Membrane)

### Global workspace
The competition where subsystems' candidate contents vie on salience; one winner crosses the
bottleneck and is broadcast. → [Workspace and Ignition](Workspace_and_Ignition)

### Host coupling
Mapping host telemetry (disk/swap/memory/battery) into three separate channels: reflex floors,
control-signal deviation, and cadence. → [Host Coupling](Host_Coupling)

### Ignition
The thresholded decision to spend a cycle on deliberate cognition rather than staying reactive.
→ [Workspace and Ignition](Workspace_and_Ignition)

### Inner loop
System-2 deliberate reasoning (draft → critique → revise), recruited by workspace conflict rather
than scheduled. → [Thinking / Action Selection](Thinking_Action_Selection)

### Peer
An outside observer (Architect, Signal Historian, Goal Auditor, Observer, Reward Auditor) that
pushes advisory signals, never commands. → [Peers](Peers)

### Quality standard
The human-ratified, non-self-editable bar an artifact must clear to be creditable.
→ [Quality Standard](Quality_Standard)

### Runtime lifetime
The persistent finite lifetime budget (rolled once, counted in wall-clock days) that colours
long-term prioritization and eventually stops the loop. → [Existence and Lifecycle](Existence_and_Lifecycle)

### Salience
The competition score that decides which candidate wins the workspace bottleneck.
→ [Workspace and Ignition](Workspace_and_Ignition)

### Setpoint
The per-signal baseline a control signal regulates toward (not a flat midpoint), under a velocity
budget. → [Control Signals: Deep Dive](Control_Signals_Deep_Dive)

### Symbolic-first
The founding rule: core cognition is explicit and LLM-free; the LLM is an optional, gated tool.
→ [Symbolic-First Design](Symbolic_First_Design)

### Workspace writeback
The decaying downward path that lets a selected moment gently bias the next competition — with no
promotion path to identity. → [Binding and Workspace Writeback](Binding_and_Workspace_Writeback)
