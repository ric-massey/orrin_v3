# What is Orrin?

Orrin is an experimental **symbolic-first cognitive runtime**: a long-running Python agent whose
core — goals, memory, attention, control signals, and action selection — is symbolic and
inspectable, with the language model as one optional tool among many. It runs continuously on its
own loop rather than waiting for prompts, and it exposes its internals as named rooms in a live UI
instead of hiding behavior in a chat transcript.

> Orrin is a research prototype: **not production software and not a claim of sentience.** Cognitive
> terms name engineering mechanisms — memory, goals, attention, control signals, runtime state, and
> action selection.

## The one core idea

Make the language model the **smallest** part of the agent, not the whole of it. Orrin runs fully
with no API key: its memory, goals, priority weights, control signals, and reasoning continue in
symbolic-only mode. When an LLM is configured, it is treated as a gated tool — see
[Symbolic-First Design](Symbolic_First_Design) and [LLM Integration](LLM_Integration).

## What makes it distinctive

- **Continuous runtime** — a heartbeat loop, not a request/response bot ([The Cognitive Loop](The_Cognitive_Loop)).
- **A consciousness bottleneck** — a global workspace + ignition gate decide what reaches "mind" and
  when to think hard ([Workspace and Ignition](Workspace_and_Ignition)).
- **An affective layer** — regulated control signals bias every decision ([Control Signals](Control_Signals)).
- **Grounded reward** — it is paid for *durable outward effects*, not internal churn
  ([Production and the Effect Ledger](Production_and_Effect_Ledger)).
- **A finite life** — a persistent lifetime clock with phases and a terminal cycle
  ([Existence and Lifecycle](Existence_and_Lifecycle)).
- **Host coupling** — the machine it runs on is part of its context ([Host Coupling](Host_Coupling)).

## Who it's for

- Researchers exploring hybrid symbolic/neural architectures and long-running agent behavior.
- Developers building durable-state agents who want inspectable internals.
- Anyone curious what an agent looks like when the LLM is a tool, not the controller.

## Where to go next

- New here → [Getting Started](Getting_Started)
- Want the mechanisms → [The Cognitive Loop](The_Cognitive_Loop), then the subsystem pages
- Just browsing → [Quick Navigation Guide](Quick_Navigation_Guide) and the [Glossary](Glossary)
