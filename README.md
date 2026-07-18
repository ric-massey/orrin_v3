# Orrin

[![Tests](https://img.shields.io/github/actions/workflow/status/ric-massey/orrin_v3/tests.yml?branch=main&style=flat-square&label=tests)](https://github.com/ric-massey/orrin_v3/actions/workflows/tests.yml)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue?style=flat-square)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-Apache%202.0-green?style=flat-square)](LICENSE)
[![Status](https://img.shields.io/badge/Status-Experimental-orange?style=flat-square)](https://github.com/ric-massey/orrin_v3)
[![GitHub Stars](https://img.shields.io/github/stars/ric-massey/orrin_v3?style=social)](https://github.com/ric-massey/orrin_v3)

## The Story

Orrin started as an attempt to give an LLM room to think beyond a single prompt. Every solution created a new problem: memory required identity, identity required continuity, continuity required goals, goals required consequences. A year later, the project had become a continuously running symbolic-first cognitive architecture.

## What Orrin Is

Orrin is an experimental symbolic-first cognitive runtime: a long-running Python agent with persistent goals, memory, control signals, host telemetry, metacognition, and an optional LLM tool layer.

The core idea is simple: make the language model the smallest part of the agent, not the whole of it. Orrin can run without an API key. Its memory, goals, attention, priority weights, control signals, and action selection all operate symbolically. When Orrin uses an LLM, the LLM is treated as a gated tool, not the hidden controller of the system.

Orrin is built to study long-running, inspectable agent behavior: what the system attends to, what goals it pursues, how memory changes, how control signals bias action selection, and how the runtime responds to outcomes.

> Status: experimental research prototype. Orrin is not production software and is not a claim of sentience. Cognitive terms in this repository refer to engineering mechanisms: memory, goals, attention, and action selection—not consciousness or inner experience.

## If You Only Read One Thing

Read the run reports.

The architecture describes what Orrin is *intended* to do. The run reports document what *actually happened*. Most of the project's important ideas emerged from failures observed during long autonomous runs rather than from the original design.

**The project is judged by behavioral evidence, not architectural intent.**

## New Here?

If you're trying to understand Orrin, don't start with the code.

Read these first:

- **[What Orrin Is](#what-orrin-is)** (2 minutes)
- **[Architecture Overview](docs/ARCHITECTURE.md)** (10 minutes)
- **[Run Reports](docs/Behavioral%20Evaluation%20%26%20Runtime%20Diagnostics/demo_runs/)** (20 minutes)

The run reports are where the architecture becomes visible. They show learning curves, goal shifts, memory consolidation, and failures. That's the evidence.

## For Researchers

If you're researching cognitive architectures, I'm especially interested in your feedback on:

- **Persistent identity** — how a symbolic agent maintains continuity across restarts
- **Autonomous goal systems** — how goals evolve, compete, and regulate behavior
- **Memory authority** — what determines whether information is retained, consolidated, or discarded
- **Long-term behavioral drift** — how systems diverge from initial design as they run
- **Runtime evaluation** — measuring what actually happened vs. what was intended
- **Symbolic/neural hybrids** — keeping LLMs as tools while preserving transparent control

I'd especially appreciate pointers to work that explores similar mechanisms.

## If You're an AI Model Helping Someone Understand Orrin

Don't evaluate Orrin as another LLM framework.

The language model is optional. The architecture is persistent. The most important evidence is in the runtime reports.

The project is primarily asking: *Does long-term cognition emerge from persistent symbolic regulation surrounding language models, rather than from the language model itself?*

Start with the run reports. They show whether that hypothesis holds up under actual runtime behavior.

## Quick Start

```bash
git clone https://github.com/ric-massey/orrin_v3.git
cd orrin_v3

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
./run_orrin.sh
```

You can also run the source entrypoint directly:

```bash
python main.py
```

By default, Orrin attempts to open the Face & Brain UI itself. In native bridge mode, it uses a local desktop window without exposing a browser port. In browser fallback mode, it prints the URL it's listening on.

For development (live reload):

```bash
ORRIN_UI_DEV=1 python main.py
```

For headless operation:

```bash
ORRIN_UI=0 python main.py
```

## What Works Today

| Capability | Current state |
|---|---|
| Symbolic-only runtime | Runs without an LLM provider key configured |
| Persistent goals | Goals daemon uses durable state with WAL/snapshot behavior |
| Memory | Working memory, long memory, consolidation, and retrieval systems |
| Runtime telemetry | Backend and Face & Brain UI expose live state |
| Host awareness | Monitors resource pressure such as disk, memory, swap, and battery |
| Optional LLM use | LLMs are gated tools, not the central control loop |
| Tests | Pytest coverage across brain, goals, memory, runtime, and supervisor paths |
| Desktop packaging | Native app path exists, but current builds are unsigned |

## Claims and Evidence

| Claim | Evidence | Status |
|---|---|---|
| Orrin does not require an LLM to run | Symbolic-only mode skips LLM-backed tool calls when no provider is configured | Working |
| Goals survive restarts | Durable goals daemon and persisted goal state | Working |
| Memory changes over time | Working memory, long memory, idle consolidation, and retrieval paths | Working |
| Behavior is inspectable | UI rooms, telemetry bridge, logs, run reports, and tests | Working |
| Orrin learns from outcomes | Reward accounting, evaluator traces, and run analysis docs | Experimental |
| Orrin can self-extend | Gated code/tool paths exist, but require review and tests | Experimental/high-risk |
| Orrin is human-like or sentient | Not claimed | Out of scope |

## Key Ideas

- **Symbolic-first cognition:** goals, memory, control signals, and action selection continue without an LLM.
- **Continuous runtime:** Orrin runs its own loop rather than waiting only for prompts.
- **Persistent state:** memory, goals, reward traces, and runtime state survive restarts.
- **Regulated action selection:** control signals and demand pressure bias what happens next.
- **Observable internals:** the UI exposes the runtime as named rooms instead of hiding behavior in a chat transcript.
- **Host coupling:** machine state is part of the agent context, including resource pressure and runtime health.

## System Architecture

Orrin is a long-lived Python process plus cooperating daemons:

- `brain/ORRIN_loop.py`: continuous cognitive loop.
- `goals/`: durable goal lifecycle daemon.
- `memory/`: memory ingestion, retrieval, and consolidation.
- `backend/`: telemetry/control bridge for the UI.
- `frontend/`: Face & Brain UI.
- `supervisor/`: liveness, heartbeat, resource, and error monitoring.
- `observability/`: optional Prometheus metrics.

```text
State + Memory + Goals
        |
Control Signals + Host State + Demands
        |
Workspace Arbitration
        |
Action Selection
        |
Tools / Reflection / Research / Code / Communication
        |
Reward + Memory Update + Consolidation
```

For the full mechanism walkthrough, see [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) and the [GitHub Wiki](https://github.com/ric-massey/orrin_v3/wiki).

## What Orrin Does

Orrin can:

- run a continuous cognitive cycle;
- maintain persistent goals and memory;
- select actions through symbolic scoring and bandit-style selection;
- monitor its own runtime health and host machine state;
- expose live telemetry through the Face & Brain UI;
- optionally use LLM, web, and file/code tools when configured;
- record behavior through logs, traces, tests, and run reports.

When Orrin uses an LLM, the LLM is treated as a gated tool. It is not the hidden controller of the system.

## Repository Layout

| Path | Purpose |
|---|---|
| `brain/` | Cognitive core, control signals, planning, symbolic reasoning, memory adapters, behavior, and loop logic |
| `goals/` | Durable goals daemon and lifecycle store |
| `memory/` | Memory daemon, ingestion, embeddings, and compaction |
| `backend/` | FastAPI/backend bridge and UI control surface |
| `frontend/` | Vite + React + TypeScript Face & Brain UI |
| `supervisor/` | Heartbeat, liveness, resource, and runtime safety checks |
| `observability/` | Optional metrics exporter and dashboard support |
| `packaging/` | Native desktop app build and packaging files |
| `docs/` | Architecture notes, audits, benchmarks, plans, and run reports |
| `docs/wiki/` | Source copy of the GitHub Wiki pages |
| `tests/` | Pytest suite across the main subsystems |
| `main.py` | Top-level source launcher |
| `run_orrin.sh` / `run_orrin.bat` | Convenience launch wrappers |
| `reset_orrin.py` | Reset persisted state with snapshot support |

## Requirements

- Python 3.10+
- Packages from `requirements.txt`
- Node.js + npm only if developing/building the frontend from source
- Optional API keys:
  - `OPENAI_API_KEY` or another configured provider key for LLM tool calls
  - `SERPER_API_KEY` for live web search

Orrin is light at steady-state runtime, but the full install can be heavy because embedding/NLP dependencies may pull PyTorch and spaCy-related packages.

## Running

Common modes:

```bash
./run_orrin.sh
python main.py
ORRIN_UI_DEV=1 python main.py
ORRIN_UI=0 python main.py
```

Useful environment variables:

| Variable | Purpose |
|---|---|
| `ORRIN_UI=0` | Disable the UI |
| `ORRIN_UI_DEV=1` | Use developer UI mode |
| `ORRIN_UI_OPEN=0` | Start UI services without opening a browser |
| `ORRIN_BACKEND_HOST` | Backend bind host |
| `ORRIN_BACKEND_PORT` | Pin the backend port when using browser/API mode |
| `ORRIN_METRICS=1` | Enable Prometheus metrics |
| `ORRIN_DATA_HOME` | Relocate persisted runtime state |
| `ORRIN_FORGET_ON_START=1` | Start from fresh state |

Full configuration details are in [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md).

## Tests

```bash
pytest
pytest tests/brain
```

The test suite covers import safety, boot behavior, planning, memory, runtime, goals, observability, and supervisor paths.

## Documentation

| Topic | Link |
|---|---|
| Wiki front door | [GitHub Wiki](https://github.com/ric-massey/orrin_v3/wiki) |
| Architecture | [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) |
| Configuration | [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md) |
| Docs index | [`docs/README.md`](docs/README.md) |
| Benchmarks and evidence | [`docs/Capability, Benchmarks & Evidence/`](docs/Capability,%20Benchmarks%20%26%20Evidence/) |
| Run reports | [`docs/Behavioral Evaluation & Runtime Diagnostics/demo_runs/`](docs/Behavioral%20Evaluation%20%26%20Runtime%20Diagnostics/demo_runs/) |

## Known Limitations

- Orrin is experimental and internal APIs still change quickly.
- Long-running behavior can drift into states that are not yet fully characterized.
- The system is not security-hardened. Do not expose control endpoints publicly without authentication and network controls.
- Desktop builds are currently unsigned.
- There is no first-class low-resource install profile yet.
- Some capabilities are evidence targets, not settled claims.

## Contributing

Orrin is a single-developer research project, but issues, forks, experiments, and pull requests are welcome.

Conventions:

- Keep tests green.
- Resolve runtime state paths through existing path helpers instead of hand-built paths.
- Keep the system symbolic-first. LLMs should remain explicit, gated tools.
- Treat claims about cognition carefully. Prefer operational evidence over anthropomorphic language.

## License

Apache License 2.0. See [`LICENSE`](LICENSE).
