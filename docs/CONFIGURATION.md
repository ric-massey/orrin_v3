# Orrin — Configuration & Operations

Companion to the [README](../README.md). The README covers the quickstart; this document holds the
fuller operational detail: the environment-variable reference, Docker, remote access, metrics, state
layout, and reset.

## Contents

- [Environment variables](#environment-variables)
- [State layout (two trees, on purpose)](#state-layout-two-trees-on-purpose)
- [How state stays bounded](#how-state-stays-bounded)
- [Resetting state](#resetting-state)
- [Running with Docker](#running-with-docker)
- [Remote access](#remote-access)
- [Prometheus metrics](#prometheus-metrics)

---

## Environment variables

Orrin reads many `ORRIN_*` variables; the full set is discoverable with
`grep -rho 'ORRIN_[A-Z_]*' .`. Below is the curated subset most people actually reach for.

| Variable | Default | Effect |
|----------|---------|--------|
| `ORRIN_UI` | `1` | Set `0` to skip launching the UI (headless). |
| `ORRIN_UI_DEV` | `0` | Set `1` for the developer UI path — browser tab + Vite dev server (hot reload) instead of the native window. |
| `ORRIN_UI_OPEN` | `1` | Set `0` to start the UI but not auto-open a browser tab. |
| `ORRIN_EXECUTIVE_DAEMON` | `1` | In-process Executive that advances goal steps. Set `0` to disable. |
| `ORRIN_EXECUTIVE_DAEMON_INTERVAL` | `7` | Seconds between Executive goal-step advances. |
| `ORRIN_CYCLE_SLEEP` | `1` | Seconds between cognitive cycles. |
| `ORRIN_IGNITION_GATE` | `1` | Deliberation gate — only salient/uncertain/conflicted cycles ignite into expensive deliberate cognition. Set `0` for always-on. |
| `ORRIN_WORKSPACE_PRIOR` | `1` | Make the workspace-arbitration winner an additive prior on the action pick. Set `0` to decouple. |
| `ORRIN_CONFLICT_RECRUIT` | `1` | Let workspace conflict/uncertainty recruit System-2 deliberation (`inner_loop`). Set `0` to disable. |
| `OPENAI_API_KEY` | _(unset)_ | Default LLM provider key. With no provider configured anywhere, all brain LLM tool calls are skipped (symbolic-only). Other providers use `ANTHROPIC_API_KEY` / `GOOGLE_API_KEY` / etc. |
| `SERPER_API_KEY` | _(unset)_ | When absent, web search errors and "looking outward" falls back to local file search. |
| `ORRIN_LLM_TOOL_ONLY` | `1` | Gate the LLM to tool-only use (no free-form generation). |
| `ORRIN_LLM_DAILY_TOKEN_BUDGET` | _(unset)_ | Daily LLM token cap — cost control. |
| `ORRIN_STRICT` | `0` | Strict fail-closed mode (surface errors instead of degrading silently). |
| `ORRIN_ONCE` / `ORRIN_BENCHMARK` | _(unset)_ | Single-cycle / benchmark run modes — useful for testing. |
| `ORRIN_FORGET_ON_START` | `0` | Wipe accumulated state on startup (like a reset). |
| `ORRIN_LIFESPAN_MIN_DAYS` / `ORRIN_LIFESPAN_MAX_DAYS` | _(built-in band)_ | Bounds for the runtime-lifetime budget rolled on first run/reset (the finite-horizon clock). |
| `ORRIN_DATA_HOME` | _(unset)_ | Use a per-user data directory (set automatically in the frozen desktop app). |
| `ORRIN_BACKEND_HOST` / `ORRIN_BACKEND_PORT` | `127.0.0.1` / `8800` | Where the telemetry backend binds. |
| `ORRIN_METRICS` / `ORRIN_METRICS_PORT` | `0` / _(OS-assigned)_ | Set `ORRIN_METRICS=1` to start the Prometheus exporter (off by default). Port is OS-assigned unless pinned (the Docker stack pins `9100`). |
| `ORRIN_CONTROL_TOKEN` | _(unset)_ | Require this token on the control endpoints (`/api/control/*`, e.g. the UI Stop button). The frontend reads `VITE_CONTROL_TOKEN`. Set it before exposing control beyond localhost. |
| `ORRIN_DATA_DIR`, `ORRIN_GOALS_DIR`, `ORRIN_LOGS_DIR`, `ORRIN_REPO_ROOT`, `ORRIN_WORLD_ROOT` | _(repo-relative)_ | Relocate state trees — relevant to Docker volumes. |

---

## State layout (two trees, on purpose)

Orrin's persisted state is split across **two** directories. This is intentional, not a duplicate:

- **`brain/data/`** holds the **cognitive core's** state: control signals, context, working/long
  memory, world & causal models, run history, learning stats, cognition history. This is the runtime
  state.
- **`data/`** (repo root) holds the **background daemons'** state: `data/goals/` (the goals daemon's
  WAL, snapshots, and state), `data/memory/wal/`, and `data/media/`.

They are separate because the daemons (`goals/`, `memory/`) are their own subsystems with their own
durability machinery (WAL + snapshots), kept apart from the brain's plain JSON state files. New code
should resolve brain paths through `brain/paths.py` constants rather than building paths by hand.

---

## How state stays bounded

Orrin runs for days at a time, so the data files self-bound — you should not need `reset_orrin.py`
just to keep size under control:

- **Append-only logs are capped.** Telemetry/trace files (`events.jsonl`, `trace.jsonl`, …) are
  trimmed after each write (`cap_jsonl`, ~3000 lines / 2 MB, atomic and line-safe).
- **History is windowed.** `cognition_history.json` keeps the last ~500 cycles; heavy payloads
  (candidate lists, full goal context) are stripped to compact summaries before saving.
- **Memory forgets on purpose.** Working memory is small and fixed; long-term memory is consolidated
  during the idle-consolidation cycle and decays/forgets rather than growing without bound.
- **Regenerable runtime files are git-ignored** so they never bloat the repo, while Orrin's actual
  persisted state (memory, identity, learning, models) stays tracked.

---

## Resetting state

`reset_orrin.py` is for **starting from fresh state**, not routine maintenance. It snapshots first, so
a reset is recoverable.

```bash
python reset_orrin.py                # snapshot + reset
python reset_orrin.py --dry-run      # show what would change
python reset_orrin.py --hard         # also clear bandit / decision learning
python reset_orrin.py --no-snapshot  # skip the pre-reset snapshot (reset becomes irrecoverable)
```

---

## Running with Docker

If you'd rather not install Python, Node, PyTorch, and the embedding models on your host, the repo
ships a `Dockerfile` and `docker-compose.yml` that bundle the whole stack.

> **Native window vs. container.** The desktop app runs in a native window with no port; a container
> has no display, so the Docker image runs the **web** UI instead — the Vite dev server on `:5173`
> plus the telemetry API on `:8800`. The image sets `ORRIN_UI_DEV=1` to select that path.

**Pull the prebuilt image (no build).** A multi-arch image (amd64 + arm64) is published to GitHub
Container Registry:

```bash
docker compose pull && docker compose up    # pulls ghcr.io/ric-massey/orrin_v3:latest
```

**Or build it yourself** (builds natively for your machine):

```bash
docker compose up --build
```

Either way, open the UI at **http://localhost:5173** (telemetry API on `:8800`, Prometheus on
`:9100`). That's the entire system — brain loop, daemons, backend, and UI — in one container.

**API keys (optional).** Create a `.env` next to `docker-compose.yml`; Compose reads it
automatically:

```bash
OPENAI_API_KEY=sk-...   # enables LLM tool calls (symbolic-only without it)
SERPER_API_KEY=...      # enables live web search (local-file fallback without it)
```

Notes on the image:

- **One image, both runtimes.** Vite is spawned by `main.py` as a child process, so the image
  carries both Python and Node. Inside the container Vite proxies `/api` and `/ws` to `:8800`, so
  the single published UI port is all you need.
- **Models are pre-cached at build time.** The embedding layer runs offline (`HF_HUB_OFFLINE=1`), so
  `all-mpnet-base-v2` and `all-MiniLM-L6-v2` are downloaded *during the build*. This (plus the
  CPU-only PyTorch wheel) is why the first build is large; subsequent `up`s are fast.
- **State persists in named volumes.** `brain/data/` and `data/` are mounted as named volumes
  (`orrin_brain_data`, `orrin_data`), seeded from the image's tracked seed state on first run. To
  start fresh, remove the volumes: `docker compose down -v`. Use a **named volume**, not a bind
  mount, for `brain/data/` — a bind mount would shadow the seeded state with an empty host directory.

---

## Remote access

To reach the UI from another device (e.g. your phone):

```bash
./expose_orrin.command
```

This opens a **single** public tunnel to the Vite dev server, which proxies both `/ws` (telemetry
WebSocket) and `/api` (REST) through to the backend on `:8800` — the frontend derives both URLs from
the page origin, so one tunnel carries everything. The resulting URL is written to `tunnel_url.txt`;
open `<url>/brain` on the remote device.

> **Security.** The tunnel URL is effectively the only secret for *reading* the dashboard — anyone
> who has it can watch Orrin. Treat it accordingly and stop the tunnel when done. The *control*
> endpoints (`/api/control/*`, e.g. the Stop button) can be gated separately with `ORRIN_CONTROL_TOKEN`
> (frontend reads `VITE_CONTROL_TOKEN`); set it before exposing the tunnel so a viewer can't stop or
> steer the agent.

---

## Prometheus metrics

The exporter is **opt-in**. Set `ORRIN_METRICS=1` to start it; it binds an OS-assigned port unless
pinned with `ORRIN_METRICS_PORT` (the Docker stack pins `9100`). A shipped desktop app opens no extra
listening port by default. The exporter and a small dashboard server live in `observability/`.
