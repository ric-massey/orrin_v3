# Glossary of Terms

This glossary defines key terms used throughout the Orrin codebase and wiki. Each term includes a short definition and links to deeper pages.

Affect state / Control signals
- Short: Scalar and structured internal variables (reward, activation, demands) used to regulate behavior.
- See: /docs/wiki/Control_Signals.md

Workspace / Ignition
- Workspace: transient set of candidate proposals competing for attention.
- Ignition: thresholded decision to run deliberation rather than a low-power reactive cycle.
- See: /docs/wiki/The_Cognitive_Loop.md and /docs/wiki/Workspace_and_Ignition.md

Bandit selector
- Multi-armed bandit that selects cognitive functions (arms) using exploration/exploitation.
- See: /docs/wiki/Action_Selection_and_Bandit.md

Executive / Goals daemon
- Executive: in-process scheduler that advances goals on a short cadence.
- Goals daemon: durable, WAL-backed store that owns long-lived goals.
- See: /docs/wiki/Goals_Executive_vs_Daemon.md

Consolidation / Forgetfulness
- Consolidation: background process that converts short-term experiences to persistent memory (embeddings, indices).
- Forgetfulness: controlled decay policies to bound long-term storage.
- See: /docs/wiki/Memory_System.md

Host coupling
- The mapping of host-level telemetry (disk, memory, CPU) into control signals and behavior adaptation.
- See: /docs/wiki/Host_Coupling.md

Symbolic reasoning
- Rule-based and structured reasoning using world models, causal graphs, and description-logic style representations, independent of LLMs.
- See: /docs/wiki/Symbolic_Reasoning.md

Peer
- External read-only agents/observers that propose signals or audits but must not command behavior.
- See: /docs/wiki/Peers.md

LLM/tool
- External language model used as a tool for generation or interpretation. Orrin aims to be symbolic-first and treat LLMs as optional.
- See: /docs/wiki/LLM_Integration.md

(Additional terms omitted for brevity — update this file as we expand the glossary.)
