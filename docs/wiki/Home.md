# Orrin Wiki

Orrin is an experimental symbolic-first cognitive runtime: a long-running Python agent with
persistent goals, memory, control signals, host telemetry, metacognition, and an optional LLM tool
layer.

It is designed to make agent behavior inspectable over time: what it attends to, what goals it
pursues, how memory changes, how control signals bias action selection, and how the runtime
responds to the machine it runs on.

> Orrin is a research prototype, not production software and not a claim of sentience. Cognitive
> terms in this wiki refer to engineering mechanisms: memory, goals, attention, control signals,
> runtime state, and action selection.

## Start Here

- [What is Orrin?](What_is_Orrin.md)
- [The Cognitive Loop](The_Cognitive_Loop.md)
- [Quick Navigation Guide](Quick_Navigation_Guide.md)
- [Glossary](Glossary.md)
- [FAQ](FAQ.md)

## Core Architecture

- [Symbolic-First Design](Symbolic_First_Design.md)
- [Workspace and Ignition](Workspace_and_Ignition.md)
- [Binding and Workspace Writeback](Binding_and_Workspace_Writeback.md)
- [Thinking and Action Selection](Thinking_Action_Selection.md)
- [Action Selection and Bandit](Action_Selection_and_Bandit.md)
- [Learning and Adaptation](Learning_and_Adaptation.md)
- [Loop Phases: Detailed](Loop_Phases_Detailed.md)

## Subsystems

- [Memory System](Memory_System.md) / [Memory Subsystem Deep Dive](Memory_System_Subsystem.md)
- [Control Signals](Control_Signals.md) / [Deep Dive](Control_Signals_Deep_Dive.md) / [Module](Control_Signals_Module.md)
- [Symbolic Reasoning](Symbolic_Reasoning.md) / [Subsystem Deep Dive](Symbolic_Reasoning_Subsystem.md)
- [Goals: Executive vs. Daemon](Goals_Executive_vs_Daemon.md) / [Goals Daemon Subsystem](Goals_Daemon_Subsystem.md)
- [Peers](Peers.md) / [Peers Subsystem](Peers_Subsystem.md)
- [Host Coupling](Host_Coupling.md) / [Supervisor](Host_Coupling_Supervisor.md)
- [LLM Integration](LLM_Integration.md)

## Production and Expression

- [Production and the Effect Ledger](Production_and_Effect_Ledger.md)
- [Quality Standard](Quality_Standard.md)
- [Expression Membrane](Expression_Membrane.md)
- [Self-Code and Extension](Self_Code_and_Extension.md)
- [Native Language Model](Native_Language_Model.md)
- [Existence and Lifecycle](Existence_and_Lifecycle.md)

## The UI

- [Face & Brain UI](Face_and_Brain_UI.md)
- [Backend & Telemetry](Backend_Telemetry.md)

## Running and Operating Orrin

- [Configuration Reference](Configuration_Reference.md)
- [Running with Docker](Running_with_Docker.md)
- [Remote Access & Tunneling](Remote_Access_Tunneling.md)
- [Desktop Packaging](Desktop_Packaging.md)
- [Benchmarks and Verification](Benchmarks_and_Verification.md)
- [Debugging Memory Issues](Debugging_Memory_Issues.md)

## Development

- [Cognition Module](Cognition_Module.md)
- [Writing a Custom Cognitive Function](Writing_Custom_Cognitive_Function.md)
- [Extending Symbolic Operations](Extending_Symbolic_Operations.md)
- [Adding a Custom Peer](Adding_Custom_Peer.md)
- [Tuning Control Signals](Tuning_Control_Signals.md)

## Research

- [Scientific Foundations](Scientific_Foundations.md)

Source and maintenance: this wiki's source of truth is `docs/wiki/` in the main repository
(originally based on the WIKI_STRUCTURE.md blueprint, now in `docs/archive/`). Update pages when
code or design changes; keep code pointers in each page.
