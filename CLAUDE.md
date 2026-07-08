# CLAUDE.md

Guidance for Claude Code (and other AI agents) working in this repository.

## What Orrin is

An experimental **symbolic-first** cognitive runtime: a long-running Python agent with persistent
goals, memory, control signals, host telemetry, metacognition, and an *optional* LLM tool layer.
The core design rule is load-bearing: **the LLM is the smallest part of the agent, not the whole of
it.** Orrin runs fully with no API key (symbolic-only); the LLM is a gated tool, never the control
loop. See `docs/ARCHITECTURE.md` for the mechanism-level walkthrough and `docs/wiki/` for the
subsystem pages.

## The golden rules

1. **Keep the suite green.** `make verify` is the gate (ruff + mypy + pytest + frontend
   typecheck/build) — it's exactly what CI runs. Run it before you consider a change done.
2. **Symbolic-first, LLM gated.** Any new code must work with no provider key configured. LLM calls
   go through `brain/utils/generate_response.py` only, and callers must be on the `_LLM_TOOL_CALLERS`
   allowlist (`ORRIN_LLM_TOOL_ONLY=1` is the default). The gate fails closed — never fabricate
   content on error; check `llm_ok(result, caller)`.
3. **Resolve state paths through helpers.** Use `brain/paths.py` constants (`DATA_DIR`, `LOGS_DIR`,
   `THINK_DIR`, …), never hand-built or `__file__`-relative paths. A hardcoded path bypasses
   `ORRIN_DATA_DIR` and breaks test isolation (this exact bug turned CI red once — see
   `brain/cognition/language/tokenizer.py` history).
4. **Prefer operational evidence over anthropomorphic claims.** Cognitive terms name engineering
   mechanisms. Don't add sentience language.

## Layout (the map)

| Path | What lives here |
|------|-----------------|
| `brain/ORRIN_loop.py`, `brain/loop/` | The continuous cognitive loop |
| `brain/think/` | Function selection, action arbiter, deliberation gate, inner loop |
| `brain/cognition/` | Perception, workspace, binding, memory adapters, quality standard, language |
| `brain/symbolic/` | LLM-free world/causal models + the rule lifecycle |
| `brain/agency/` | The action side: effect ledger, self-code writer |
| `brain/utils/` | `generate_response.py` (LLM chokepoint), providers, secrets, paths helpers |
| `goals/` | Durable goals daemon (WAL + snapshots), lifecycle, runner |
| `memory/` | Memory daemon (WAL, embeddings, consolidation, retrieval) |
| `backend/` + `frontend/` | FastAPI telemetry bridge + Vite/React Face & Brain UI |
| `supervisor/` + `watchdogs.py` | Liveness, error, resource, lifespan watchdogs |
| `tests/` | Pytest suite (`tests/brain`, `tests/goals_test`, `tests/memory`, …) |

Two state trees, on purpose: `brain/data/` (cognitive core) and root `data/` (daemon WAL/snapshots).
Both are gitignored except a small committed seed. See `docs/CONFIGURATION.md`.

## Running

```bash
python main.py                 # native UI window (pywebview, no port)
ORRIN_UI_DEV=1 python main.py  # dev: Vite :5173 + backend :8800, hot reload
ORRIN_UI=0 python main.py      # headless
```

## Testing notes

- The suite is hermetic: `tests/conftest.py` redirects all state to a tmp dir and a tripwire fails
  the session if any live `brain/data` / `brain/logs` file is touched. If you see "isolation
  breach," you added a path that bypasses `brain/paths.py`.
- Some selector-characterization goldens depend on the MiniLM embedder being available; they skip
  (not fail) when it can't load. CI prefetches the model.
- `make coverage` gates against a ratcheted floor (`.coverage-floor`) — it only moves up.

## Conventions

- Match the surrounding code's style; comments state constraints, not narration.
- Long-running components are `*_daemon.py` — resilient and idempotent.
- Commit/push only when asked. Keep changes small and testable.
