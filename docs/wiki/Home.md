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

- [Getting Started](Getting_Started) — install, run, and read the UI in your first hour
- [What is Orrin?](What_is_Orrin)
- [The Cognitive Loop](The_Cognitive_Loop)
- [Quick Navigation Guide](Quick_Navigation_Guide)
- [Glossary](Glossary)
- [FAQ](FAQ)

## Core Architecture

- [Symbolic-First Design](Symbolic_First_Design)
- [Workspace and Ignition](Workspace_and_Ignition)
- [Binding and Workspace Writeback](Binding_and_Workspace_Writeback)
- [Thinking and Action Selection](Thinking_Action_Selection)
- [Action Selection and Bandit](Action_Selection_and_Bandit)
- [Learning and Adaptation](Learning_and_Adaptation)
- [Loop Phases: Detailed](Loop_Phases_Detailed)

## Subsystems

- [Memory System](Memory_System) / [Memory Subsystem Deep Dive](Memory_System_Subsystem)
- [Control Signals](Control_Signals) / [Deep Dive](Control_Signals_Deep_Dive) / [Module](Control_Signals_Module)
- [Symbolic Reasoning](Symbolic_Reasoning) / [Subsystem Deep Dive](Symbolic_Reasoning_Subsystem)
- [Goals: Executive vs. Daemon](Goals_Executive_vs_Daemon) / [Goals Daemon Subsystem](Goals_Daemon_Subsystem)
- [Peers](Peers) / [Peers Subsystem](Peers_Subsystem)
- [Host Coupling](Host_Coupling) / [Supervisor](Host_Coupling_Supervisor)
- [LLM Integration](LLM_Integration)

## Production and Expression

- [Production and the Effect Ledger](Production_and_Effect_Ledger)
- [Quality Standard](Quality_Standard)
- [Expression Membrane](Expression_Membrane)
- [Self-Code and Extension](Self_Code_and_Extension)
- [Native Language Model](Native_Language_Model)
- [Existence and Lifecycle](Existence_and_Lifecycle)

## The UI

- [Face & Brain UI](Face_and_Brain_UI)
- [Backend & Telemetry](Backend_Telemetry)

## Running and Operating Orrin

- [Configuration Reference](Configuration_Reference)
- [Running with Docker](Running_with_Docker)
- [Remote Access & Tunneling](Remote_Access_Tunneling)
- [Desktop Packaging](Desktop_Packaging)
- [Security Model](Security_Model)
- [Benchmarks and Verification](Benchmarks_and_Verification)
- [Troubleshooting](Troubleshooting)
- [Debugging Memory Issues](Debugging_Memory_Issues)

## Development

- [Contributing](Contributing)
- [Cognition Module](Cognition_Module)
- [Writing a Custom Cognitive Function](Writing_Custom_Cognitive_Function)
- [Extending Symbolic Operations](Extending_Symbolic_Operations)
- [Adding a Custom Peer](Adding_Custom_Peer)
- [Tuning Control Signals](Tuning_Control_Signals)

## Project

- [Roadmap & Status](Roadmap_and_Status)
- [Scientific Foundations](Scientific_Foundations)

Source and maintenance: this wiki's source of truth is `docs/wiki/` in the main repository
(originally based on the WIKI_STRUCTURE.md blueprint, now in `docs/archive/`). Update pages when
code or design changes; keep code pointers in each page.
