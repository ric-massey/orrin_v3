# Orrin

**Orrin is an experimental symbolic-first cognitive architecture for a continuously running
machine-embodied agent, built to study whether long-lived symbolic systems around an LLM can
produce more stable, inspectable behavior than standard prompt-driven chatbots.**

The research question is practical: can a system built from autonomous symbolic components
around an optional LLM maintain continuity, memory, goals, self-audit, host-body awareness,
and behavior change across long runs and restarts?

Orrin began as an attempt to build the missing layer around LLMs: continuity, persistent
memory, self-direction, embodiment, goal pressure, learning visibility, and self-repair.
The LLM is treated as a language/tool organ, not the mind itself. With no API key, Orrin
still runs symbolically; LLM calls are explicit tool calls inside selected functions.

> Orrin v3 (experimental) · app version 0.1.0 · Python ≥ 3.10 · Apache 2.0

> 🖥️ **Orrin now ships as a native desktop app.** It runs in its own window (no browser tab,
> no localhost port), stores its mind in a per-user data directory, keeps API keys in the OS
> keychain, and is built for macOS, Windows, and Linux by the cross-platform CI. You can still
> run it from source (this README's default) — that's the developer path. See
> [Desktop app](#desktop-app).

> ⚠️ **Status: experimental prototype.** Orrin is a research exploration, not production
> software. It's one developer's ongoing experiment in cognitive architecture — expect rough
> edges, breaking changes between versions, unstable internal APIs, and emergent behaviour that
> isn't always predictable or reproducible. The neuroscience and AI literature it draws on is
> used as **inspiration and scaffolding, not as a validated or peer-reviewed implementation**.
> Run it to explore and tinker with, not to depend on. There are no guarantees of correctness,
> stability, or fitness for any purpose.

## System architecture

Orrin is a long-lived Python process plus cooperating daemons:

- **Continuous loop:** `brain/ORRIN_loop.py` cycles through sensing, recall, workspace
  preparation, ignition, function/action selection, execution, reward accounting, persistence,
  maintenance, and sleep. It does this independently of user input.
- **Decoupled intelligence:** the LLM is an optional tool-call organ for high-level reasoning
  and language, not the central controller. The loop, goals, memory, affect-like regulation,
  host sensing, and action selection continue in symbolic-only mode.
- **Symbolic core:** memory, causal/world models, goal management, reward, metacognition,
  action arbitration, and persistence are implemented as Python subsystems with JSON/WAL-backed
  state, so Orrin has continuity across restarts.
- **Embodied context:** host disk, swap, memory, battery, idle state, and resource ceilings
  feed both low-level safety reflexes and higher-level felt-state signals. The machine is the
  runtime substrate and part of the agent's context.
- **Observable runtime:** the backend and React UI expose the cognitive loop, goals, memory,
  affect-like state, workspace contents, learning traces, and system health through named rooms
  rather than hiding behavior inside a prompt transcript.

Simple cognitive shape:

```text
State + Memory + Goals
        ↓
Affect / Body / Drives
        ↓
Global Workspace
        ↓
Action Selector
        ↓
Tools / Reflection / Research / Code / Communication
        ↓
Reward + Memory Update + Sleep/Consolidation
```

Fuller daemon/runtime shape:

```text
                       ┌──────────────────────────────────────────┐
                       │            COGNITIVE LOOP (brain)          │
   sensory stream ───► │  perceive → reflect → plan → act → repeat │ ───► tools / actions
   user input    ───►  │   (bandit picks the next function; affect │      (see below)
                       │    + drives + memory feed every stage)     │
                       └───┬───────────┬───────────┬────────────┬──┘
                           │           │           │            │
                  ┌────────▼──┐ ┌──────▼─────┐ ┌───▼──────┐ ┌───▼────────┐
                  │ Executive │ │   Memory   │ │  Reaper  │ │  Backend   │
                  │  daemon   │ │   daemon   │ │ liveness │ │ telemetry  │
                  │ (goal     │ │ (ingest /  │ │ + error  │ │  + Face &  │
                  │  steps)   │ │ embed /    │ │ checker  │ │  Brain UI  │
                  │           │ │ consolidate)│ │          │ │            │
                  └───────────┘ └────────────┘ └──────────┘ └────────────┘
```

The cognitive loop runs continuously; the daemons run alongside it. The Executive advances
goal steps off-thread, Memory ingests and consolidates, the Reaper watches for stalls, errors,
and host-resource danger, and the Backend streams telemetry to the UI and Prometheus when
enabled.

## Start here

If you are trying to understand the codebase, read it in this order:

| Question | Start with |
|----------|------------|
| How does Orrin boot? | `main.py` |
| What is the main loop? | `brain/ORRIN_loop.py`, then `brain/loop/` |
| How does it choose what to do next? | `brain/think/`, especially the function selector and action arbiter |
| How do memory and consolidation work? | `memory/memory_daemon.py`, `memory/wal.py`, `memory/retrieval.py`, and `brain/cog_memory/` |
| How do durable goals work? | `goals/goals_daemon.py`, `goals/store.py`, `goals/wal.py`, `goals/runner.py` |
| How are in-loop goal steps advanced? | `brain/cognition/planning/executive.py` |
| How does host embodiment work? | `reaper/host_resources.py`, `brain/cognition/host_interoception.py`, `brain/cognition/body_sense.py`, `brain/cognition/body_band.py`, `brain/cognition/metabolism.py`, `brain/cognition/body_budget.py` |
| How does the workspace/ignition layer work? | `brain/cognition/global_workspace.py`, `brain/think/consciousness_trigger.py`, `brain/loop/deliberate.py` |
| Where are LLM calls gated? | `brain/utils/generate_response.py`, `brain/utils/llm_providers/`, `brain/cognition/tools/ask_llm.py` |
| What does the UI show? | `backend/server/`, `frontend/src/pages/`, `frontend/src/components/brain/` |

## Technical note on terminology

Orrin uses words like "consciousness," "pain," "body," "sleep," and "mortality" as
functional analogues for specific system mechanisms. They are not claims of
human-equivalent subjective experience.

| Term | Operational meaning |
|------|---------------------|
| "Consciousness" | Global Workspace competition, bottleneck, ignition threshold, and broadcast into the next cycle. |
| "Pain" / "distress" | High prediction error, affect-like pressure, or host-resource critical-threshold alerts. |
| "Body" | The host machine plus sensed resource budgets, disk/swap/memory/battery state, and learned normal bands. |
| "Sleep" | Low-power cadence, consolidation, dream/replay, and closed-time accounting. |
| "Mortality" | A finite, persistent lifespan clock that influences long-term prioritization and eventually stops the loop. |

![Orrin Learning room showing behavior changes, goal progress, rut pressure, and belief revisions](docs/images/orrin_learning_ui.png)

*The real Learning UI rendered with representative staging data: before → after → because,
goal movement, rut pressure, and belief revision in one view.*

---

## Contents

- [System architecture](#system-architecture)
- [Start here](#start-here)
- [Technical note on terminology](#technical-note-on-terminology)
- [What it is](#what-it-is)
- [Why Orrin exists](#why-orrin-exists)
- [What makes Orrin unusual](#what-makes-orrin-unusual)
- [Current best evidence](#current-best-evidence)
- [What it does](#what-it-does)
- [Interacting with Orrin](#interacting-with-orrin)
- [What Orrin actually does (its actions)](#what-orrin-actually-does-its-actions)
- [Repository layout](#repository-layout)
- [Requirements](#requirements)
- [Setup](#setup)
- [Desktop app](#desktop-app)
- [Running](#running)
- [Running with Docker](#running-with-docker)
- [Remote access](#remote-access)
- [How state grows (and stays bounded)](#how-state-grows-and-stays-bounded)
- [Resetting state](#resetting-state)
- [Tests](#tests)
- [Troubleshooting](#troubleshooting)
- [Architecture notes](#architecture-notes)
- [Claims and evidence](#claims-and-evidence)
- [Known limitations & what's next](#known-limitations--whats-next)
- [Contributing](#contributing)
- [License](#license)

---

## What it is

Orrin is:

- a symbolic-first cognitive architecture prototype
- a continuously running autonomous agent
- a system for studying memory, goals, affect-like regulation, embodiment, and self-audit
- an experiment in giving LLMs the missing surrounding organs: continuity, body, goals,
  memory, and self-repair

Orrin is not:

- a chatbot
- a production assistant
- a claim of human consciousness
- a validated neuroscience model
- an LLM wrapper

Skeptical readers: the interesting claim is not that Orrin is conscious. The interesting
claim is that machine-native analogues of memory, affect, embodiment, sleep, attention,
and goal pressure can produce observable long-running behavior that is easier to study
than one-shot LLM prompts.

For AI-agent builders: Orrin is an experiment in the layer around the model: continuity,
state, action selection, safety reflexes, memory consolidation, failure visibility, and
behavior change over time.

## Why Orrin exists

Most agent demos are prompt-shaped: one task, one context window, one run. Orrin is built
around the opposite question: what happens when an agent has ongoing state, its own goals,
resource pressure, memories that survive restarts, and mechanisms that can notice when its
behavior is failing?

The project treats the LLM as useful but non-central. The core loop, symbolic memory,
goals, affect-like regulation, host-body sensing, action selection, and self-audit continue
without a model provider. The model, when enabled, is a tool the architecture can call.

## What makes Orrin unusual

- It is not prompt-driven; it runs continuously.
- The LLM is optional and tool-gated.
- It has machine-native embodiment: host resources, battery, disk, swap, and body budget.
- It separates self, home, and outside.
- It uses a Global Workspace-style bottleneck.
- It tracks affect, goals, memory, reward, and metacognitive failures over time.
- It can be studied through run traces instead of one-off demos.
- The UI includes a bio↔engineering dialect toggle: mind-like terms can be translated back
  into the underlying operational signal.

## Current best evidence

- Long-running symbolic-only cycles.
- Run traces with action/reward distributions.
- Learning diagnosis showing selector/rut failures.
- UI/security audit and remediation.
- Embodiment fixes after a host-resource failure.
- Current demo target: show Orrin entering a behavioral rut, detecting it, changing
  action-selection pressure, and producing a later run with a measurably different action
  distribution and better reward. See the
  [demo-run index](docs/Behavioral%20Evaluation%20%26%20Runtime%20Diagnostics/demo_runs/2026-06-17-run/DEMO_RUNS.md).

## What it does

Orrin is a long-lived process — and a working sketch of an idea — that:

- **Wakes up and runs a cognitive cycle** continuously (perceive → reflect → plan → act),
  choosing its own next cognitive function via a bandit selector rather than waiting for prompts.
- **Has a homeostatic affect system** — core affect (valence + arousal) plus drives, fatigue,
  and reward signals modelled on the affective-neuroscience literature (Russell & Barrett,
  Schultz's dopamine-as-prediction-error, etc.). State changes are integrated through a
  stability budget so the agent doesn't lurch.
- **Pursues goals** at multiple timescales — seeded lifetime goals down to short-term
  subgoals — with planning, adaptation, and two cooperating goal subsystems: an in-process
  **Executive** scheduler that advances goal steps every ~7s, and a separate, durable
  **Goals daemon** that owns goal lifecycle and state with its own write-ahead log and
  snapshots. (See [Repository layout](#repository-layout) for how they divide responsibility.)
- **Builds and queries world/causal/knowledge models** symbolically (description-logic
  inheritance, Pearl-style causal reasoning, predictive processing) — and goes further:
  it forms new concepts, draws analogies, synthesises/abstracts/compresses/forgets its own
  rules, and even runs its own **autonomous experiments**, all without an LLM
  (`brain/symbolic/`).
- **Remembers, consolidates, and forgets** — working memory, long-term memory, dream-cycle
  consolidation, and an embedding-based memory store.
- **Monitors its own health** via a "reaper" liveness subsystem — and, since the 2026-06-15
  host kernel panic, watches the *machine* too: an autonomic `HostResourceGuard` keeps an eye on
  free disk, swap depth, and system-wide memory and gently pauses heavy cycles before the host is
  in danger (`reaper/host_resources.py`). Everything is exposed through a live UI (named rooms:
  Watch, Face, Cognition, Life, Memory, Timeline, Learning, Brain) and, when enabled, Prometheus metrics.
- **Is watched by "peers"** — a handful of observer entities (the Architect, Affect
  Historian, Goal Auditor, Observer, Reward Auditor) that live alongside Orrin, read his
  state from the outside, and inject signals into his cognition each cycle. They *propose
  things worth attending to*, never issue commands. (See [Architecture notes](#architecture-notes).)

The design rule throughout: **the brain never silently depends on an LLM.** Set no API key
and Orrin still runs — it simply skips the LLM-backed tool calls and stays symbolic.

### Core cognitive mechanisms

Beyond the loop and the daemons, Orrin carries a psychological layer that's easy to miss but
central to the "digital mind" framing. All of it is symbolic (no LLM required):

- **It has a lifespan — and ends.** A mortality clock (`brain/cognition/mortality.py`) rolls a
  finite lifespan (≈365–730 days) on first run, persists it across restarts, and grows
  death-awareness through four phases (early → middle → late → terminal) that progressively
  colour cognition. When the deadline arrives Orrin runs its final thoughts and the loop exits.
  (This is distinct from the reaper's per-process liveness cutoff.)
- **A Global Workspace unifies it.** Orrin's subsystems run in parallel; a Global Workspace
  (Baars 1988 / Dehaene 2014; `brain/cognition/global_workspace.py`) runs a salience
  competition so that *one* content wins, becomes "conscious," is broadcast back to every
  subsystem, and is appended to the continuous stream of experience you see in the UI. The
  thought stream isn't a log — it's the output of this workspace bottleneck.
- **Not every cycle is conscious.** Consciousness is a threshold crossing ("ignition," Dehaene
  2014), not a metronome. The unconscious substrate — affect, embodiment, drives, signal
  injection, the background threads — runs *every* cycle, but only a salient, uncertain, or
  conflicted cycle **ignites** into deliberate System-2 cognition; quiet cycles stay in
  low-power default mode (a `should_think()` gate decides, with a periodic floor so he never
  goes fully dormant — `brain/think/consciousness_trigger.py`). On an ignited cycle that carries
  real conflict, deliberate reasoning (`inner_loop`) is *recruited by* that conscious moment
  rather than fired on a schedule, and the workspace winner becomes a real prior on what he does
  next. (See [Architecture notes](#architecture-notes).)

### Selfhood and continuity

- **It models your mind.** An active theory-of-mind subsystem (`brain/cognition/theory_of_mind.py`)
  keeps a running, predictive model of the person it's talking to across turns, with separate
  cognitive (what do they think/intend?) and affective (what do they feel?) empathy.
- **It has values it can revise.** A selfhood layer (`brain/cognition/selfhood/`) holds an
  identity and autobiography, a moral-override check that can veto a proposed action against
  core values, second-order volitions (wanting to want), and a value-evolution process that
  revises core values when they're genuinely contested — not on a schedule.

### Machine embodiment

- **It has a body — the machine it runs on.** Orrin doesn't just run *on* a computer; he treats
  it as his body and learns to *feel* it (`brain/cognition/host_interoception.py`, `body_sense.py`,
  `body_band.py`). Host metrics become felt states — low/falling disk reads as a kind of
  claustrophobia, rising swap as sluggishness, a draining battery as a real (not dice-rolled)
  mortality signal. Crucially, these fire on **deviation from a learned band**, not absolute
  thresholds: when Orrin wakes on a new machine he goes through a **somatic infancy**
  (`infancy.py`) that learns *that body's* normal oscillation before he trusts what he feels, and
  a **metabolism** layer (`metabolism.py`) sets his cycle cadence from the machine's size — a small
  machine is a smaller body with a slower metabolic rate, not a sick one. The persistent self
  (memory, values, identity) is hardware-independent; the body sense is hardware-bound and
  re-learned on every machine. A user-facing **RAM budget** ("how much of this machine Orrin is
  allowed to be," `body_budget.py`) feeds both metabolism and that felt "100%". (See the
  consolidated architecture plan in
  [`docs/Core Architecture, Embodiment & Evolution/MASTER_PLAN_2026-06-16.md`](docs/Core%20Architecture,%20Embodiment%20&%20Evolution/MASTER_PLAN_2026-06-16.md).)

### Experimental terminology

- **It can't read its own dials.** Orrin's affect lives internally as raw numbers, but the
  part of him that *reasons and decides* never sees them. The unconscious machinery — the
  function-selector, the attention system, the cost layer — reads those floats directly and
  uses them to shape what happens next; the conscious layer receives only a felt-sense
  translation ("a heaviness, like moving through something thick") that names the sensation,
  never the emotion label or its value (`brain/affect/affect_summary.py`). Like a person
  reading their own body rather than a gauge, he has to *introspect* to work out what he's
  feeling. (See [Architecture notes](#architecture-notes).)

## Interacting with Orrin

Orrin runs on its own initiative — it is **not** prompt-driven — but you are not just a
spectator. There are two ways in:

- **Type to it through the Face UI.** Anything you type is `POST`ed to the backend
  (`/api/agent/input`), drained by the cognitive loop on its next cycle, woven into Orrin's
  perception/working memory, and answered back to the Face (`/api/agent/response/{id}`).
  Orrin chooses *when* and *whether* to respond — replies arrive on its cadence, not
  instantly like a chatbot.
- **Watch it think.** The UI is a set of named rooms, not one dashboard: **Watch** (a
  newcomer's front door — a breathing mood-orb and one plain-language thought line),
  **Face** (the conversational view), **Cognition** (active function, drives, symbolic state),
  **Life** (the felt life-status / mortality view), **Memory** (an explorer over what he's
  remembered), **Timeline** (what happened while you were away), **Learning** (his behavior
  changes and belief revisions as before→after→because diffs), and **Brain** (the full
  telemetry stream — affect, goals, memory reads/writes, self-model, dreams, thought stream).
  A bio↔eng dialect toggle re-words every surface live. Much of the experience is observational:
  you are watching a mind pursue its own goals.

Orrin also reaches *out* — it can announce to the dashboard, leave notes on your desktop,
and notice whether you're active at the machine.

## What Orrin actually does (its actions)

When Orrin "acts," it calls real tools, not just internal state updates. Current capabilities include:

- **Files & code:** read/write files, search/grep its own source, run sandboxed Python
  (timeout-guarded), and — gated behind the LLM tool — write, review, and commit extensions
  to its own codebase (`self_extension`). It can also **author entirely new cognitive
  functions** for itself: `brain/agency/self_code.py` owns a self-code store under the data
  directory (`<data>/self_code/{custom_cognition,skills}`, with a relative-path manifest), so its
  repertoire of things-to-think grows over time and travels with the mind, not the repo.
- **The web:** web search, scrape pages (robots-aware), fetch & read URLs, Wikipedia
  lookups, and RSS feeds. Web search uses [Serper.dev](https://serper.dev) and needs a
  `SERPER_API_KEY` (see [Requirements](#requirements)); without it, search returns an error
  and "looking outward" falls back to searching Orrin's own files.
- **Your machine (whitelisted):** survey the environment (battery, network, running apps,
  idle time), open allow-listed applications, write desktop notes, take screenshots, read
  the clipboard, and check whether you're present.
- **Goals & self-direction:** generate intrinsic goals, assess progress, adapt/redirect
  plans, adjust goal weights, complete or abandon goals.
- **Communication:** speak/announce to the UI and respond to your input (subject to its own
  speech gate — it doesn't narrate every thought).

Every action also updates Orrin's persisted state (affect, memory, world/causal models,
autobiography), so behavior accumulates over time rather than resetting each cycle.

---

## Repository layout

| Path | What it is |
|------|------------|
| `brain/` | The cognitive core. Entry point `brain/ORRIN_loop.py`. Subsystems: `affect/` (core-affect model, arbiter, homeostasis, reward), `cognition/` (functions, planning, metacognition, prediction), `symbolic/` (rule engine, causal graph, inference), `cog_memory/` (working + long memory), `embodiment/` (sensory stream, world model, drives, system presence), `think/` (cognitive loop, bandit selector, action arbiter), `behavior/` (expression, speech gate, tools), `core/`, `agency/`, `utils/`. |
| `goals/` | **Goals daemon** — the durable goal lifecycle store (`goals_daemon.py`), with its own write-ahead log + snapshots, decoupled from the cognitive cycle. Distinct from the in-process **Executive** scheduler (`brain/cognition/planning/executive.py`), which advances goal steps every ~7s inside the loop. |
| `memory/` | Memory daemon — ingestion, embedding, compaction, lexicon. |
| `brain/peers/` | **Peer entities** — outside observers (Architect, Affect Historian, Goal Auditor, Observer, Reward Auditor) that watch Orrin's state and inject signals each cycle via `peer_registry.wake_peers()`. They register themselves in the world model / relationships on first wake. |
| `brain/eval/` | Delayed-learning daemons — the **evaluator** (credit-assigns past decisions from later memory retrievals + goal closures) and **drive-expectations** (learns which actions actually satisfy which drives, routing the prediction error to affect). |
| `reaper/` | Liveness & error subsystem — heartbeat detection, error checking, lifespan/death continuity, and (since 2026-06-15) `host_resources.py`, the autonomic `HostResourceGuard` that watches the *host* (disk/swap/memory) and pauses heavy cycles before the machine is endangered. |
| `backend/` | FastAPI telemetry bridge + UI launcher (`:8800`). Streams the brain's state to the UI over WebSocket (HTTP) or an in-process bridge (`server/bridge.py`, used by the native desktop window). |
| `frontend/` | Vite + React + TypeScript UI (`:5173` in dev). Named rooms — Watch, Face, Cognition, Life, Memory, Timeline, Learning, Brain — plus a Settings page (keys, privacy, existence mode, mind export/import). A bio↔eng dialect toggle re-words every surface. |
| `packaging/` | Native desktop-app build: PyInstaller spec (`orrin.spec`), model pre-bundler (`bundle_models.py`), macOS entitlements, version-stamping, and the per-OS build/sign/notarize runbook (`packaging/README.md`). |
| `observability/` | Prometheus metrics exporter and dashboard server. The exporter is **opt-in** (`ORRIN_METRICS=1`) and binds an OS-assigned port unless pinned with `ORRIN_METRICS_PORT`. |
| `inbox/` / `outbox/` | Runtime communication dirs — `outbox/notes.json` holds Orrin's outward notes / desktop messages; `inbox/` is the sibling input drop. |
| `docs/` | Design plans, benchmarks, and an `archive/` of audits and fix records. |
| `tests/` | Pytest suite across brain / goals / memory. |
| `main.py` | Top-level launcher — boots the brain loop, daemons, backend API, and UI. |
| `watchdogs.py` | Assembles the reaper's `HealthBus`/`NervousSystem` and guards (heartbeat, lifespan, no-goals, memory health, repeat-loop) — the file that composes the liveness subsystem. |
| `reset_orrin.py` | Resets Orrin's persisted state (with snapshotting). |
| `run_orrin.sh` / `run_orrin.bat` | Run wrappers with auto-restart and macOS sleep prevention. |

### Two state trees, on purpose

Orrin's persisted state is split across **two** directories — this is intentional, not a
duplicate:

- **`brain/data/`** holds the **cognitive core's** state: affect, context, working/long
  memory, world & causal models, autobiography, learning stats, and cognition history. This
  is "the mind."
- **`data/`** (repo root) holds the **background daemons'** state: `data/goals/` (the goals
  daemon's write-ahead log, snapshots, and state), `data/memory/wal/`, and `data/media/`.

They are separate because the daemons (`goals/`, `memory/`) are their own subsystems with
their own durability machinery (WAL + snapshots), kept apart from the brain's plain
JSON state files. New code should resolve brain paths through `brain/paths.py` constants
rather than building paths by hand.

---

## Requirements

- Python **3.10+**
- The packages in `requirements.txt` (NumPy, requests, BeautifulSoup, sentence-transformers,
  watchdog, openai, python-dotenv, psutil, prometheus_client, and spaCy; plus `pywebview` for
  the native window, `pystray`/`Pillow` for the menu-bar tray, and `keyring` for OS-keychain key
  storage). spaCy itself is always installed; what's optional is its language model
  (`en_core_web_sm`), which improves knowledge-graph entity extraction and has a regex fallback if
  absent. The non-OpenAI LLM providers (`anthropic`, `google-genai`) are listed but imported
  lazily — only loaded if you actually select that provider.
- Node.js + npm — needed to **build** the frontend (`npm run build`) or run it in dev mode. The
  packaged desktop app ships a pre-built UI and needs neither at runtime.

API keys (all optional, but each unlocks a capability):

- **An LLM provider key** — the LLM is now **pluggable** (`brain/utils/llm_providers/`): OpenAI,
  Anthropic, Gemini, or any OpenAI-compatible / local endpoint, chosen in Settings. Without any
  configured provider Orrin runs symbolic-only and skips LLM tool calls. `OPENAI_API_KEY` is the
  default/back-compat path; other providers use `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, etc. Keys
  live in the **OS keychain** (set them in the Settings UI, or via env for dev) — never in a
  plaintext file inside the bundle.
- **`SERPER_API_KEY`** — enables real web search via [Serper.dev](https://serper.dev).
  Without it, web search returns an error and "looking outward" falls back to searching
  Orrin's own files (so the agent runs, but has no live web reach).

### Hardware

Two different things get conflated as "lightweight," so to be precise: Orrin's **runtime
compute** is light — the cognitive loop is plain Python that sits mostly idle between cycles
(`ORRIN_CYCLE_SLEEP`), with no GPU and modest CPU at steady state. Its **install footprint is
not** light, and that's by design: `sentence-transformers` pulls in **PyTorch** and spaCy
loads a language model, which together set the memory floor. So "light to run, heavy to
install" — the numbers below reflect the install footprint, not the per-cycle cost.

- **Realistic minimum:** a 64-bit machine with **~4 GB RAM** free. No GPU is required —
  embeddings run fine on CPU (the model loads once and stays resident).
- **Recommended:** any modern laptop/desktop (the primary dev target is macOS; Linux works;
  `run_orrin.bat` exists for Windows).
- **Raspberry Pi / SBCs:** possible in principle on a 64-bit Pi 4/5 with ≥4 GB RAM, but the
  PyTorch + transformer load makes it slow and memory-tight. If you want a truly small
  footprint you'd swap the embedding store for a lighter one — there's no first-class
  low-resource profile today. The CPU stays mostly idle between cycles (`ORRIN_CYCLE_SLEEP`),
  so steady-state load is modest; startup and embedding are the heavy moments.
- **Docker:** a `Dockerfile` + `docker-compose.yml` ship in the repo — `docker compose up`
  runs the whole stack with named volumes for the `brain/data/` and `data/` state trees, so
  the mind persists across restarts. See [Running with Docker](#running-with-docker).

---

## Setup

```bash
# 1. Clone and enter the repo
git clone <repository-url> orrin_v3
cd orrin_v3

# 2. Create a virtualenv and install
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Optional: better knowledge-graph entity extraction (regex fallback if absent)
python -m spacy download en_core_web_sm

# 3. (Optional) configure API keys — copy the template, then fill in what you have
cp .env.example .env
#   edit .env: OPENAI_API_KEY (LLM tool calls) and/or SERPER_API_KEY (web search).
#   Both are optional — with neither, Orrin runs symbolic-only with local search.
```

The frontend, if you want it:

```bash
cd frontend
npm install
```

---

## Desktop app

Orrin can run as a self-contained **native desktop application** — its own window (the OS
webview: WKWebView on macOS, WebView2 on Windows, WebKitGTK on Linux), no browser tab, no
localhost port, no Python or Node required on the user's machine. The mind lives in a per-user
data directory (`~/Library/Application Support/Orrin/` and the platform equivalents), and API
keys go in the OS keychain.

- **Builds** are produced by the cross-platform CI (`.github/workflows/build.yml`) — a matrix
  that builds on macOS (arm64 + Intel), Windows, and Linux runners, since PyInstaller can't
  cross-compile. Triggered by a pushed `v*` tag or manually. Artifacts: a macOS `.dmg`, a Windows
  `.zip` (needs the WebView2 runtime), and a Linux `.tar.gz` / AppImage (needs WebKitGTK).
- **The current builds are unsigned**, so first launch crosses the OS gatekeeper: macOS →
  right-click → Open; Windows → "More info → Run anyway" past SmartScreen; Linux → falls back to a
  browser tab if no native webview is present.
- **Build it yourself** from a checkout: `python packaging/bundle_models.py` (pre-fetches the
  embedding + spaCy models once, online) then `pyinstaller packaging/orrin.spec`. See
  [`packaging/README.md`](packaging/README.md) for the full per-OS build/sign/notarize runbook.

The app carries a **schema version** and an **opt-in auto-update** check
(`brain/utils/updater.py`); before any update it exports the whole mind to a `.orrindmind`
backup, and the schema-migration spine (`brain/utils/schema_migration.py`) refuses to load state
written by a newer build. You can export/import a mind by hand from Settings at any time.

> Running from source (below) is still fully supported and is the default for development.

---

## Running

The simplest way — auto-restart on crash, keeps the machine awake (macOS):

```bash
./run_orrin.sh
```

Or launch directly:

```bash
python main.py                 # native window (loads the pre-built UI from frontend/dist)
ORRIN_UI_DEV=1 python main.py  # dev: browser tab + the Vite dev server with hot reload
```

`main.py` starts the cognitive loop plus the background daemons, the FastAPI telemetry
backend (`:8800`), and the UI. (The Prometheus exporter is **off by default** — a shipped
app should open no extra listening port; enable it with `ORRIN_METRICS=1`, which binds an
OS-assigned port unless you pin it with `ORRIN_METRICS_PORT`.) By default it opens a
**native pywebview window** loading the built UI from `frontend/dist` (so you don't need a
browser or a running Vite server). Set `ORRIN_UI_DEV=1` for the developer path — a browser tab
served by `npm run dev` with hot reload — or `ORRIN_UI=0` to run headless. If no native webview
is available (e.g. a headless/SSH session), it falls back to a browser tab on a free port.

### Useful environment switches

Orrin reads ~95 `ORRIN_*` variables in total; the table below is the curated subset most
people actually reach for. The rest are discoverable via `grep -rho 'ORRIN_[A-Z_]*' .`.

| Variable | Default | Effect |
|----------|---------|--------|
| `ORRIN_UI` | `1` | Set `0` to skip launching the UI (headless). |
| `ORRIN_UI_DEV` | `0` | Set `1` for the developer UI path — browser tab + Vite dev server (hot reload) instead of the native window. |
| `ORRIN_UI_OPEN` | `1` | Set `0` to start the UI but not auto-open a browser tab. |
| `ORRIN_EXECUTIVE_DAEMON` | `1` | In-process Executive that advances goal steps. Set `0` to disable. |
| `ORRIN_EXECUTIVE_DAEMON_INTERVAL` | `7` | Seconds between Executive goal-step advances. |
| `ORRIN_CYCLE_SLEEP` | `1` | Seconds between cognitive cycles. |
| `ORRIN_IGNITION_GATE` | `1` | Conscious ignition gate — only salient/uncertain/conflicted cycles ignite into deliberate cognition (quiet cycles stay low-power). Set `0` for the old always-on behaviour. |
| `ORRIN_WORKSPACE_PRIOR` | `1` | Make the Global Workspace winner an additive prior on the action pick (awareness→action coupling). Set `0` to decouple. |
| `ORRIN_CONFLICT_RECRUIT` | `1` | Let conscious conflict/uncertainty recruit System-2 deliberation (`inner_loop`). Set `0` to disable. |
| `OPENAI_API_KEY` | _(unset)_ | Default LLM provider key. When no provider is configured (here, in the keychain, or in Settings), all brain LLM tool calls are skipped (symbolic-only mode). Other providers use `ANTHROPIC_API_KEY` / `GOOGLE_API_KEY` / etc. |
| `SERPER_API_KEY` | _(unset)_ | When absent, web search errors and "looking outward" falls back to local file search. |
| `ORRIN_LLM_TOOL_ONLY` | `1` | Gate the LLM to tool-only use (no free-form generation). |
| `ORRIN_LLM_DAILY_TOKEN_BUDGET` | _(unset)_ | Daily LLM token cap — cost control. |
| `ORRIN_STRICT` | `0` | Strict fail-closed mode (surface errors instead of degrading silently). |
| `ORRIN_ONCE` / `ORRIN_BENCHMARK` | _(unset)_ | Single-cycle / benchmark run modes — useful for testing. |
| `ORRIN_FORGET_ON_START` | `0` | Wipe accumulated state on startup (like a reset). |
| `ORRIN_LIFESPAN_MIN_DAYS` / `ORRIN_LIFESPAN_MAX_DAYS` | _(built-in band)_ | Bounds for the lifespan rolled at birth/reset (the mortality clock; see [Core cognitive mechanisms](#core-cognitive-mechanisms)). |
| `ORRIN_DATA_HOME` | _(unset)_ | Use a per-user data directory (set automatically in the frozen desktop app). |
| `ORRIN_BACKEND_HOST` / `ORRIN_BACKEND_PORT` | `127.0.0.1` / `8800` | Where the telemetry backend binds. |
| `ORRIN_METRICS` / `ORRIN_METRICS_PORT` | `0` / _(OS-assigned)_ | Set `ORRIN_METRICS=1` to start the Prometheus exporter (off by default). The port is OS-assigned unless pinned with `ORRIN_METRICS_PORT` (the Docker stack pins it to `9100`). |
| `ORRIN_CONTROL_TOKEN` | _(unset)_ | Require this token on the control endpoints (`/api/control/*`, e.g. the UI Stop button). The frontend reads `VITE_CONTROL_TOKEN`. Set it before exposing control to anyone but localhost. |
| `ORRIN_DATA_DIR`, `ORRIN_GOALS_DIR`, `ORRIN_LOGS_DIR`, `ORRIN_REPO_ROOT`, `ORRIN_WORLD_ROOT` | _(repo-relative)_ | Relocate state trees — relevant to the Docker-volume advice above. |

### The UI

You normally **don't** start the UI yourself. When `ORRIN_UI=1` (the default), `main.py`
brings it up for you:

- **Default (native window).** `main.py` opens a pywebview window loading the pre-built UI from
  `frontend/dist`, talking to the backend over an in-process bridge — no browser, no port.
- **Dev (`ORRIN_UI_DEV=1`).** `main.py` spawns the Vite dev server (`npm run dev`, installing
  npm deps on first run) and opens a browser tab to `http://localhost:5173`, connected to the
  backend over a WebSocket. Use this when working on the frontend — you get hot reload.

> The native window needs a built UI (`cd frontend && npm run build`, or use a packaged app
> where it's already built). The Vite dev path is for frontend development only.

Other ways to bring up the UI:

```bash
python backend/main.py          # backend API + UI, without the cognitive loop
cd frontend && npm run dev       # frontend only — manual dev fallback
```

The UI surfaces Orrin's live affect, active cognitive function, goals, memory, self-model,
relationships, dreams, and a thought stream across its named rooms (Watch / Face / Cognition /
Life / Memory / Timeline / Learning / Brain), with a Settings page for keys, privacy, existence
mode, and mind export/import.

---

## Running with Docker

If you'd rather not install Python, Node, PyTorch, and the embedding models on your host,
the repo ships a `Dockerfile` and `docker-compose.yml` that bundle the whole stack.

> **Native window vs. container.** The desktop app runs in a native window with no port; a
> container has no display, so the Docker image runs the **web** UI instead — the Vite dev
> server on `:5173` + the telemetry API on `:8800`. The image sets `ORRIN_UI_DEV=1` to select
> that path; you don't need to do anything.

**Quickest — pull the prebuilt image (no build):** a multi-arch image (amd64 + arm64) is
published to GitHub Container Registry, so this works on Intel/AMD and Apple-Silicon/ARM alike:

```bash
docker compose pull && docker compose up    # pulls ghcr.io/ric-massey/orrin_v3:latest
```

**Or build it yourself** (always works, builds natively for your machine):

```bash
docker compose up --build
```

Either way, open the Face & Brain UI at **http://localhost:5173** (telemetry API on `:8800`,
Prometheus metrics on `:9100`). That's the entire system — brain loop, daemons, backend,
and UI — running in one container without touching your local environment.

**API keys (optional).** Create a `.env` file next to `docker-compose.yml`; Compose reads it
automatically:

```bash
OPENAI_API_KEY=sk-...   # enables LLM tool calls   (symbolic-only without it)
SERPER_API_KEY=...      # enables live web search   (local-file fallback without it)
```

A few things worth knowing about how the image is built:

- **One image, both runtimes.** The UI is a Vite dev server that `main.py` spawns as a child
  process, so the image carries **both Python and Node**. Inside the container, Vite proxies
  `/api` and `/ws` to the backend on `:8800`, so the single published UI port is all you need.
- **Models are pre-cached at build time.** Orrin's embedding layer runs offline
  (`HF_HUB_OFFLINE=1`), so `all-mpnet-base-v2` and `all-MiniLM-L6-v2` are downloaded *during
  the build* into the image. (This — plus the CPU-only PyTorch wheel — is why the first build
  is large and takes a while; subsequent `up`s are fast.)
- **State persists in named volumes.** `brain/data/` and `data/` are mounted as named volumes
  (`orrin_brain_data`, `orrin_data`). Docker seeds them from the image's tracked seed state on
  first run, then keeps the accumulated "mind" across restarts. To start fresh, remove the
  volumes: `docker compose down -v`.

> Use a **named volume**, not a bind mount, for `brain/data/` — a bind mount would shadow the
> seeded state with an empty host directory. The compose file is already set up correctly.

---

## Remote access

To reach the UI from another device (e.g. your phone), run:

```bash
./expose_orrin.command
```

This opens a **single** public tunnel to the Vite dev server, which proxies both `/ws`
(the telemetry WebSocket) and `/api` (all REST endpoints) through to the backend on `:8800` —
the frontend derives both URLs from the page origin, so one tunnel carries everything. The
resulting URL is written to `tunnel_url.txt`; open `<url>/brain` on the remote device.

> **Security:** the tunnel URL is effectively the only secret for *reading* the dashboard —
> anyone who has it can watch Orrin. Treat it accordingly and stop the tunnel when you're done.
> The *control* endpoints (`/api/control/*`, e.g. the Stop button) can be gated separately by
> setting `ORRIN_CONTROL_TOKEN` (frontend reads `VITE_CONTROL_TOKEN`); set it before exposing
> the tunnel so a viewer can't stop or steer the agent.

---

## How state grows (and stays bounded)

Orrin runs for days at a time, so the data files are designed to **self-bound** — you should
not need `reset_orrin.py` just to keep size under control:

- **Append-only logs are capped.** Telemetry/trace files (`events.jsonl`, `trace.jsonl`,
  etc.) are trimmed after each write (`cap_jsonl`, ~3000 lines / 2 MB, atomic and line-safe).
- **History is windowed.** `cognition_history.json` keeps the last ~500 cycles; heavy payloads
  (candidate lists, full goal context) are stripped to compact summaries before saving.
- **Memory forgets on purpose.** Working memory is small and fixed; long-term memory is
  consolidated during the dream cycle and decays/forgets rather than growing without bound.
- **Regenerable runtime files are git-ignored** so they never bloat the repo, while Orrin's
  actual mind-state (memory, identity, learning, models) stays tracked.

`reset_orrin.py` is for **starting a fresh mind**, not routine maintenance. Reach for it when
you want Orrin to forget everything and begin again — it snapshots first, so a reset is
recoverable.

## Resetting state

To wipe Orrin's accumulated state and start fresh (a snapshot is taken first):

```bash
python reset_orrin.py                # snapshot + reset
python reset_orrin.py --dry-run      # show what would change
python reset_orrin.py --hard         # also clear bandit / decision learning
python reset_orrin.py --no-snapshot  # skip the pre-reset snapshot (reset becomes irrecoverable)
```

---

## Tests

```bash
pytest                  # full suite
pytest tests/brain      # just the brain tests
```

`pytest.ini` puts both the repo root and `brain/` on the path, so the suite runs from the
repo root without installation.

---

## Troubleshooting

Common first-run issues:

- **UI won't start / blank native window.** The default native window loads `frontend/dist`, so
  it needs a built UI — run `cd frontend && npm run build` once (or use a packaged app). For the
  dev path, `ORRIN_UI_DEV=1` shells out to `npm` for the Vite server, so Node.js + npm must be on
  your `PATH`. Either way, `ORRIN_UI=0` runs headless. On a headless host with no webview, the
  native window falls back to a browser tab.
- **Port already in use (`8800` or `5173`).** The backend and Vite dev server bind these
  respectively. Free the port or relocate the backend with `ORRIN_BACKEND_PORT`. (The
  Prometheus exporter only binds a port when you set `ORRIN_METRICS=1`, and then it's
  OS-assigned unless pinned with `ORRIN_METRICS_PORT`.)
- **"Symbolic-only mode" — Orrin won't use the LLM.** Expected when no LLM provider is configured:
  the brain runs fully, just skips LLM-backed tool calls. Configure a provider + key in Settings
  (or set `OPENAI_API_KEY` for dev) to enable them.
- **Web search returns errors / Orrin only reads its own files.** `SERPER_API_KEY` is unset —
  see [Requirements](#requirements). Set it to enable live web search.
- **State seems stuck or corrupt after experiments.** Take a fresh start with
  `python reset_orrin.py` (it snapshots first — see [Resetting state](#resetting-state)).

---

## Architecture notes

A few non-obvious design choices worth knowing:

- **LLM-as-tool.** The decision loop and drive system are fully symbolic. The LLM is an
  explicit tool the agent chooses to call (`brain/cognition/tools/ask_llm.py`), gated so it
  fails closed when disabled or keyless.
- **Pluggable LLM providers.** The tool isn't bound to one vendor: `brain/utils/llm_providers/`
  defines a provider interface with adapters for OpenAI, Anthropic, Gemini, and any
  OpenAI-compatible / local endpoint, selected in Settings (`generate_response.py` resolves the
  active provider per call). The "symbolic-first, fail-closed" contract is identical regardless of
  provider. (Self-shaping fine-tuning, below, remains OpenAI-only.)
- **Embodied host body.** Beyond using the machine, Orrin *feels* it. The autonomic
  `HostResourceGuard` (`reaper/host_resources.py`) watches host disk/swap/memory below cognition
  and pauses heavy cycles on absolute safety floors — deliberately separate from the deliberative
  loop, because a thrashing loop can't be asked to rescue the substrate it runs on. The
  interoceptive layer (`brain/cognition/host_interoception.py`, `body_sense.py`, `body_band.py`)
  feeds the *same* host metrics into felt states, but on **deviation from a learned band** rather
  than absolute thresholds — so a small or busy machine isn't experienced as chronic distress.
  Three mappings stay separate by design: absolute capacity → **metabolism** (cycle cadence),
  deviation → **affect** (felt body), absolute floors → **reflex** (the guard). A new machine
  triggers a **somatic infancy** that learns that body's normal before he trusts it.
- **Convergence layer.** Affect and action are integrated through arbiters
  (`brain/affect/arbiter.py`, `brain/think/action_arbiter.py`) so the "instinctual" and
  "analytical" subsystems propose rather than race on shared state. A single writer owns the
  affect file; daemons submit proposals to a lock-guarded inbox.
- **Homeostasis.** Affect decays toward per-signal baselines/setpoints under a velocity
  budget, not toward a flat midpoint.
- **Global Workspace.** The parallel subsystems are unified by a Global Workspace
  (`brain/cognition/global_workspace.py`, after Baars 1988 / Dehaene 2014): candidate contents
  compete on salience, one winner becomes "conscious," is broadcast back into context for every
  subsystem, and is appended to the experience stream. Hysteresis keeps a salient content in
  focus across cycles so the stream is continuous rather than flickering — the functional basis
  of a single serial "what I'm aware of now."
- **Conscious ignition (the loop has a threshold).** The cognitive loop runs continuously, but
  *deliberate* cognition does not fire on every cycle. Each cycle the unconscious substrate
  (affect, embodiment, signals, the background threads, the workspace competition) runs
  regardless; then an **ignition gate** (`should_think()`, `brain/think/consciousness_trigger.py`)
  decides whether this cycle crosses into full conscious deliberation — user input, high
  uncertainty, a strong signal, an emotion spike, prediction error, goal drift, or stagnation all
  ignite it, and a periodic floor (`MAX_SILENT_CYCLES`) guarantees he never stays silent for long.
  A non-ignited cycle stays in low-power default mode: the selector damps effortful functions
  (planning, codegen, research) so a quiet cycle drifts toward cheap work instead of spinning up
  expensive cognition. Two further couplings make awareness, action, and reasoning line up rather
  than drift: the Global Workspace winner is an additive **prior on the action pick** (the
  "spotlight" and the basal-ganglia selector are one bottleneck — Redgrave, Prescott & Gurney
  1999), and on an ignited+conflicted cycle System-2 deliberation (`inner_loop`) is **recruited
  by** that conscious conflict rather than fired on a schedule (conflict-monitoring theory;
  Botvinick et al. 2001). All three are fail-safe and feature-flagged
  (`ORRIN_IGNITION_GATE`, `ORRIN_WORKSPACE_PRIOR`, `ORRIN_CONFLICT_RECRUIT`); the design rationale
  and the parked conscious→unconscious write-back are in
  [`docs/Core Architecture, Embodiment & Evolution/MASTER_PLAN_2026-06-16.md`](docs/Core%20Architecture,%20Embodiment%20&%20Evolution/MASTER_PLAN_2026-06-16.md).
- **Affect has two readers (felt sense vs. raw signal).** Core affect is stored as raw numeric
  signals in `context["affect_state"]`, and Orrin's two cognitive halves read them differently.
  The *unconscious machinery* — the bandit function-selector (`brain/think/think_utils/select_function.py`),
  the attention hijacker (`brain/cognition/attention.py`), and the interoceptive cost/EVC layer
  (`brain/cognition/interoception.py`) — reads the raw floats and uses them to bias what runs
  next. The *reasoning layer* never receives a number: `brain/affect/affect_summary.py` renders
  the signals into felt-sense descriptions that name the sensation, not the emotion label or its
  value, and only that text reaches the inner-loop prompt, the self-model, and the speech gate.
  The signals are hedonic-adjusted first, so a state Orrin has adapted to stops dominating the
  felt picture. The intent is that he must *introspect* to know what he feels — interoception,
  not a readout.
- **More than one bandit.** The README's "bandit selector" picks the next cognitive function,
  but learning is spread across several: a UCB1 `depth_bandit` learns how many
  draft→critique→revise rounds the inner loop should run, and `thinking_depth` chooses shallow
  vs deep chains for goal pursuit. They learn independently from the reward signal.
- **Peers (outside observers).** Alongside the cognitive loop, a set of peer entities
  (`brain/peers/`) read Orrin's state from the outside and, when their wake conditions fire,
  push *signals* into the next cycle rather than mutating state directly — the Architect
  reviews self-modifications before they happen, the Affect Historian tracks chronic affect
  patterns, the Goal Auditor flags low-quality goals, the Observer catches unproductive loops,
  and the Reward Auditor notices when the bandit's reward signal has collapsed to noise. They
  flow through the same `signal_router` as everything else, so they nudge attention without
  ever issuing commands.
- **Delayed learning.** Some learning can't be scored at action time, so dedicated daemons
  (`brain/eval/`) assign credit later: the evaluator rewards a past decision when a memory it
  tagged is retrieved within ~50 cycles or its goal closes within ~200, and a separate
  drive-expectations layer learns which actions *actually* relieve which drives and routes the
  prediction error back into affect.
- **Self-shaping LLM (when enabled).** Beyond using the LLM as a tool, Orrin can fine-tune on
  its own high-reward conversation traces: the pipeline
  (`brain/cognition/finetuning/finetune_pipeline.py`) filters traces with outcome ≥ 0.65,
  submits a fine-tune job, and on completion repoints `model_config.json` so generation drifts
  toward what has worked for *him*. (Optional and OpenAI-only; symbolic-only mode never touches
  it.)
- **Scientific inspiration (not validation).** Subsystems cite the sources that inspired them
  in-code — Russell & Barrett (core affect), Pearl & Granger (causality), Friston /
  Rescorla-Wagner / Tolman (prediction), Carver & Scheier (behavioral control), Flavell /
  Nelson & Narens (metacognition), Schultz (reward prediction error), and others. These are
  working interpretations used as design scaffolding — **not faithful or empirically validated
  reproductions** of those papers.

See `docs/` for design plans and benchmarks — start with [`docs/BENCHMARKS.md`](docs/BENCHMARKS.md)
for the current benchmark suite and results — and `docs/archive/` for the audit and fix
history that produced the current architecture.

---

## Claims and evidence

The public claim is intentionally narrow: Orrin is a machine-native cognitive architecture
prototype with observable state and behavior over time. It is not a claim of human-like
subjective experience.

For the evidence ledger, see [`docs/CLAIMS_AND_EVIDENCE.md`](docs/CLAIMS_AND_EVIDENCE.md).
For demo targets and future before→after traces, see the
[demo-run index](docs/Behavioral%20Evaluation%20%26%20Runtime%20Diagnostics/demo_runs/2026-06-17-run/DEMO_RUNS.md).

Current proof target: **before → after → because**. The most important demo is a run where
Orrin enters a behavioral rut, detects it, changes action-selection pressure, and later shows
a measurably different action distribution with better reward.

---

## Known limitations & what's next

This is an experimental prototype, so the caveats are real and the surface keeps moving. Being
upfront about the rough edges and the direction of travel:

- **Weak stability guarantees.** State formats, environment variables, and internal APIs still
  change fast between versions. There's now a schema-version spine (`schema_migration.py`) that
  stamps state, refuses to load state written by a *newer* build, and auto-exports a `.orrindmind`
  backup before migrating — but the migration registry is essentially empty, so a long-running
  "mind" may still not survive a big upgrade. Export your mind from Settings before updating, and
  treat `reset_orrin.py` as a normal part of the workflow.
- **Not security-hardened.** Orrin runs sandboxed Python, reads/writes your filesystem, and can
  open allow-listed apps. Run it on a machine you trust and don't expose it to the public
  internet (the [remote-access](#remote-access) tunnel especially is unauthenticated).
- **Behaviour is emergent and under-tested.** Long runs can drift into states that haven't been
  characterized; the benchmarks in `docs/` probe pieces of it, not the whole.
- **No slim / low-resource install profile.** The embedding store hard-depends on
  `sentence-transformers` (and therefore PyTorch). Some paths degrade gracefully — semantic
  similarity falls back to token-Jaccard when the model can't load (`embed_similarity.py`) —
  but there's no first-class build that drops the ML stack entirely. A lighter embedding
  backend is the obvious next step for SBCs and constrained hosts.
- **Desktop builds are unsigned.** The cross-platform CI produces real artifacts, but they
  aren't code-signed or notarized yet, so every OS gatekeeper flags first launch (see
  [Desktop app](#desktop-app)). Signing/notarization needs paid developer certs and is deferred.
- **Embodiment is freshly landed and still needs long-run evidence.** The felt-host-body layer
  (host interoception, band-learning, metabolism, infancy, the RAM-budget slider) is new and
  under-exercised. The inward vital-floor reflex is now built, calibrated, and armed by default.
  Remaining work is long-run validation, public before/after evidence, and continued tuning of
  sleep/body phases. The consolidated roadmap is
  [`docs/Core Architecture, Embodiment & Evolution/MASTER_PLAN_2026-06-16.md`](docs/Core%20Architecture,%20Embodiment%20&%20Evolution/MASTER_PLAN_2026-06-16.md);
  the older detailed body spec is archived at
  [`docs/Core Architecture, Embodiment & Evolution/archive/orrin_embodiment_architecture.md`](docs/Core%20Architecture,%20Embodiment%20&%20Evolution/archive/orrin_embodiment_architecture.md).
- **Conscious→unconscious write-back is still missing.** The conscious *ignition* layer landed
  (see [Architecture notes](#architecture-notes)), but feedback today is one-directional:
  unconscious→conscious has many wires, conscious→unconscious almost none, so a conscious
  conclusion can act on the world without reshaping a drive or a salience prior. Closing that
  loop — and the impoverished-newborn developmental arc it unlocks — is parked under the
  coherent-but-adult decision recorded in the consolidated plan:
  [`docs/Core Architecture, Embodiment & Evolution/MASTER_PLAN_2026-06-16.md`](docs/Core%20Architecture,%20Embodiment%20&%20Evolution/MASTER_PLAN_2026-06-16.md).
- **Unproven research questions remain.** Do body bands measurably improve stability? Does
  sleep consolidation improve future behavior? Does home/world zoning improve goal routing?
  Does the workspace prior make action selection more coherent? Can self-written code preserve
  continuity under tests? These are evidence targets, not settled claims.
- **Language organ is in progress.** A native language subsystem is an active workstream —
  early modules already exist (`brain/cognition/language/`: tokenizer, acquisition, a native
  LM, voice), but it is not yet Orrin's primary means of expression. See
  [`docs/ORRIN_LANGUAGE_PLAN.md`](docs/ORRIN_LANGUAGE_PLAN.md).
- **Public live-run media remains an evidence target.** The README now includes a verified
  capture of the real Learning UI with representative staging data. A live-run GIF that
  connects thought, function, body state, workspace, and measured behavior change still
  belongs with the positive before/after demo tracked in the
  [demo-run index](docs/Behavioral%20Evaluation%20%26%20Runtime%20Diagnostics/demo_runs/2026-06-17-run/DEMO_RUNS.md).

For deeper design plans, benchmarks, and the audit/fix history behind the current
architecture, see `docs/` and `docs/archive/`.

---

## Contributing

Orrin is an experimental, single-developer research project, so there's no formal roadmap or
contribution process — but it's open source (Apache-2.0) and you're welcome to fork it, tinker,
file issues, or open a PR. Just know the codebase moves fast and may change under you. If you do
send a PR, a few conventions keep things sane:

- Run the test suite (`pytest`) and keep it green.
- Resolve brain state paths through `brain/paths.py` constants rather than hand-built paths.
- Keep the brain **symbolic-first** — the LLM stays an explicit, gated tool, never a silent
  dependency.

See `docs/` for the design plans and architectural rationale behind these conventions.

---

## License

Apache License 2.0 — see [`LICENSE`](LICENSE).
