# Orrin

**Orrin is an experimental research prototype** — an attempt to build a continuously-running
"digital mind" with its own affect (emotion) system, drives, goals, memory, and metacognition.
It runs a perpetual cognitive loop, decides what to think about next on its own, and only reaches
for a large language model as one tool among many. The brain is **symbolic-first**: it
reasons, plans, and regulates its own emotional state without an LLM, and uses one
(when available) only inside specific functions that explicitly call for it.

> Version 3.30 (experimental) · Python ≥ 3.10 · Apache 2.0

> ⚠️ **Status: experimental prototype.** Orrin is a research exploration, not production
> software. It's one developer's ongoing experiment in cognitive architecture — expect rough
> edges, breaking changes between versions, unstable internal APIs, and emergent behaviour that
> isn't always predictable or reproducible. The neuroscience and AI literature it draws on is
> used as **inspiration and scaffolding, not as a validated or peer-reviewed implementation**.
> Run it to explore and tinker with, not to depend on. There are no guarantees of correctness,
> stability, or fitness for any purpose.

<!--
  SCREENSHOT: drop a high-quality capture of the Face & Brain UI here, e.g.
  ![Orrin's Face & Brain UI](docs/images/face_and_brain.png)
  A short caption ("Orrin mid-cycle: live affect, active cognitive function,
  goals, and thought stream") helps first-time readers see the "digital mind".
-->

---

## Contents

- [What it is](#what-it-is)
- [Interacting with Orrin](#interacting-with-orrin)
- [What Orrin actually does (its actions)](#what-orrin-actually-does-its-actions)
- [Repository layout](#repository-layout)
- [Requirements](#requirements)
- [Setup](#setup)
- [Running](#running)
- [Running with Docker](#running-with-docker)
- [Remote access](#remote-access)
- [How state grows (and stays bounded)](#how-state-grows-and-stays-bounded)
- [Resetting state](#resetting-state)
- [Tests](#tests)
- [Troubleshooting](#troubleshooting)
- [Architecture notes](#architecture-notes)
- [Known limitations & what's next](#known-limitations--whats-next)
- [Contributing](#contributing)
- [License](#license)

---

## What it is

Orrin is not a chatbot, and it isn't a finished product. It's a long-lived process — and a
working sketch of an idea — that:

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
  inheritance, Pearl-style causal reasoning, predictive processing).
- **Remembers, consolidates, and forgets** — working memory, long-term memory, dream-cycle
  consolidation, and an embedding-based memory store.
- **Monitors its own health** via a "reaper" liveness subsystem, and exposes everything
  through a live Face & Brain UI and Prometheus metrics.

The design rule throughout: **the brain never silently depends on an LLM.** Set no API key
and Orrin still runs — it simply skips the LLM-backed tool calls and stays symbolic.

### At a glance

```
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

The cognitive loop runs continuously; the daemons run alongside it (the Executive advances
goal steps off-thread, Memory ingests/consolidates, the Reaper watches for stalls and
errors, and the Backend streams everything to the UI and Prometheus).

---

## Interacting with Orrin

Orrin runs on its own initiative — it is **not** prompt-driven — but you are not just a
spectator. There are two ways in:

- **Type to it through the Face UI.** Anything you type is `POST`ed to the backend
  (`/api/agent/input`), drained by the cognitive loop on its next cycle, woven into Orrin's
  perception/working memory, and answered back to the Face (`/api/agent/response/{id}`).
  Orrin chooses *when* and *whether* to respond — replies arrive on its cadence, not
  instantly like a chatbot.
- **Watch it think.** The Brain view streams live affect, the active cognitive function,
  goals, memory reads/writes, self-model, dreams, and a running thought stream. Much of the
  experience is observational: you are watching a mind pursue its own goals.

Orrin also reaches *out* — it can announce to the dashboard, leave notes on your desktop,
and notice whether you're active at the machine.

## What Orrin actually does (its actions)

When Orrin "acts," it calls real tools, not just internal state updates. Current capabilities include:

- **Files & code:** read/write files, search/grep its own source, run sandboxed Python
  (timeout-guarded), and — gated behind the LLM tool — write, review, and commit extensions
  to its own codebase (`self_extension`).
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
| `reaper/` | Liveness & error subsystem — heartbeat detection, error checking, lifespan/death continuity. |
| `backend/` | FastAPI telemetry bridge + UI launcher (`:8800`). Streams the brain's state to the UI. |
| `frontend/` | Vite + React + TypeScript "Face & Brain" UI (`:5173`). |
| `observability/` | Prometheus metrics exporter (`:9100`) and dashboard server. |
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
  watchdog, openai, python-dotenv, psutil, prometheus_client, and spaCy). spaCy itself is
  always installed; what's optional is its language model (`en_core_web_sm`), which improves
  knowledge-graph entity extraction and has a regex fallback if absent.
- Node.js + npm (for the frontend UI; `main.py` invokes `npm` to launch it).

API keys (both optional, but each unlocks a capability):

- **`OPENAI_API_KEY`** — without it Orrin runs symbolic-only and skips LLM tool calls.
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

## Running

The simplest way — auto-restart on crash, keeps the machine awake (macOS):

```bash
./run_orrin.sh
```

Or launch directly:

```bash
python main.py
```

`main.py` starts the cognitive loop plus the background daemons, the FastAPI telemetry
backend (`:8800`), the Prometheus exporter (`:9100`), and (by default) the Face & Brain UI.

### Useful environment switches

Orrin reads ~70 `ORRIN_*` variables in total; the table below is the curated subset most
people actually reach for. The rest are discoverable via `grep -rho 'ORRIN_[A-Z_]*' .`.

| Variable | Default | Effect |
|----------|---------|--------|
| `ORRIN_UI` | `1` | Set `0` to skip launching the web UI. |
| `ORRIN_UI_OPEN` | `1` | Set `0` to start the UI but not auto-open a browser tab. |
| `ORRIN_EXECUTIVE_DAEMON` | `1` | In-process Executive that advances goal steps. Set `0` to disable. |
| `ORRIN_EXECUTIVE_DAEMON_INTERVAL` | `7` | Seconds between Executive goal-step advances. |
| `ORRIN_CYCLE_SLEEP` | `1` | Seconds between cognitive cycles. |
| `OPENAI_API_KEY` | _(unset)_ | When absent, all brain LLM tool calls are skipped (symbolic-only mode). |
| `SERPER_API_KEY` | _(unset)_ | When absent, web search errors and "looking outward" falls back to local file search. |
| `ORRIN_LLM_TOOL_ONLY` | `1` | Gate the LLM to tool-only use (no free-form generation). |
| `ORRIN_LLM_DAILY_TOKEN_BUDGET` | _(unset)_ | Daily LLM token cap — cost control. |
| `ORRIN_STRICT` | `0` | Strict fail-closed mode (surface errors instead of degrading silently). |
| `ORRIN_ONCE` / `ORRIN_BENCHMARK` | _(unset)_ | Single-cycle / benchmark run modes — useful for testing. |
| `ORRIN_FORGET_ON_START` | `0` | Wipe accumulated state on startup (like a reset). |
| `ORRIN_BACKEND_HOST` / `ORRIN_BACKEND_PORT` | `127.0.0.1` / `8800` | Where the telemetry backend binds. |
| `ORRIN_DATA_DIR`, `ORRIN_GOALS_DIR`, `ORRIN_LOGS_DIR`, `ORRIN_REPO_ROOT`, `ORRIN_WORLD_ROOT` | _(repo-relative)_ | Relocate state trees — relevant to the Docker-volume advice above. |

### The UI

You normally **don't** start the UI yourself. When `ORRIN_UI=1` (the default), `main.py`
launches the backend API *and* spawns the Vite dev server as a child process — installing
npm dependencies automatically on first run — then opens a browser tab to
`http://localhost:5173`. The page connects to the backend over a WebSocket and renders
Orrin's live state.

> The UI is served by the **Vite dev server**, not a pre-built static bundle. `main.py`
> runs `npm run dev` for you; you only run it by hand as a fallback.

Other ways to bring up the UI:

```bash
python backend/main.py          # backend API + UI, without the cognitive loop
cd frontend && npm run dev       # frontend only — manual fallback if auto-launch fails
```

The UI surfaces Orrin's live affect, active cognitive function, goals, memory,
self-model, relationships, dreams, and a thought stream.

---

## Running with Docker

If you'd rather not install Python, Node, PyTorch, and the embedding models on your host,
the repo ships a `Dockerfile` and `docker-compose.yml` that bundle the whole stack.

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

> **Security:** the tunnel URL is the only secret — anyone who has it can read the dashboard.
> Treat it accordingly and stop the tunnel when you're done.

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

- **`npm` not found / UI won't start.** `main.py` shells out to `npm` to launch the Vite dev
  server. Install Node.js + npm and ensure `npm` is on your `PATH`, or set `ORRIN_UI=0` to run
  headless.
- **Port already in use (`8800`, `9100`, or `5173`).** The backend, Prometheus exporter, and
  Vite server bind these respectively. Free the port or relocate the backend with
  `ORRIN_BACKEND_PORT`.
- **"Symbolic-only mode" — Orrin won't use the LLM.** Expected when `OPENAI_API_KEY` is unset:
  the brain runs fully, just skips LLM-backed tool calls. Add the key to `.env` to enable them.
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
- **Convergence layer.** Affect and action are integrated through arbiters
  (`brain/affect/arbiter.py`, `brain/think/action_arbiter.py`) so the "instinctual" and
  "analytical" subsystems propose rather than race on shared state. A single writer owns the
  affect file; daemons submit proposals to a lock-guarded inbox.
- **Homeostasis.** Affect decays toward per-signal baselines/setpoints under a velocity
  budget, not toward a flat midpoint.
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

## Known limitations & what's next

This is an experimental prototype, so the caveats are real and the surface keeps moving. Being
upfront about the rough edges and the direction of travel:

- **No stability guarantees.** State formats, environment variables, internal APIs, and on-disk
  layouts change between versions without migrations — a long-running "mind" may not survive an
  upgrade. Treat `reset_orrin.py` as a normal part of the workflow, not a last resort.
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
- **LLM provider is OpenAI-only.** The LLM tool targets OpenAI models; there's no pluggable
  provider abstraction yet. (Symbolic-only mode means this is never a hard requirement.)
- **Convergence layer is landing.** The single-writer affect arbiter + lock-guarded proposal
  inbox described in [Architecture notes](#architecture-notes) is being merged from the
  `convergence-layer` branch — confirm you're on a build that includes it.
- **Language organ is in progress.** A native language subsystem is an active workstream; see
  [`docs/ORRIN_LANGUAGE_PLAN.md`](docs/ORRIN_LANGUAGE_PLAN.md).
- **Hero screenshot pending.** The Face & Brain UI capture (`docs/images/face_and_brain.png`)
  referenced at the top isn't checked in yet.

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
