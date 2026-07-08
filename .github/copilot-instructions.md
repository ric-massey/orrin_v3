## Quick orientation for AI coding agents

This file captures the minimal, actionable knowledge an AI assistant needs to be productive in Orrin
(v3). See `CLAUDE.md` for the fuller agent guide. Keep suggestions small, testable, and aligned with
existing patterns.

1) Big picture (how the system is organized)
- Main loop / orchestrator: `main.py` drives the runtime; `supervisor/` + `watchdogs.py` contain the
  liveness/error/resource/lifespan watchdogs that can pause or shut down the process when invariants fail.
- Memory subsystem: `memory/` contains an always-on daemon that tails a WAL, embeds items, compacts, and serves retrievals (`memory/memory_daemon.py`, `memory/ingest.py`, `memory/retrieval.py`).
- Goals subsystem: `goals/` is the planner/executor. `goals/goals_daemon.py` scans for NEW goals; `goals/runner.py` executes steps via handlers registered in `goals/registry.py`.
- LLM surface: `brain/utils/generate_response.py` is the single gated chokepoint for LLM calls across
  pluggable providers (OpenAI / Anthropic / Gemini / local, in `brain/utils/llm_providers/`). It handles
  the tool-only allowlist, fail-closed contract, retries, and prompt logging. (`main.py` puts `brain/` on
  `sys.path`, so it is imported as `utils.generate_response`.)
- Observability/UI: `observability/` provides metrics; `frontend/` + `backend/` provide the Face & Brain UI (telemetry bridge). Dashboards poll local endpoints (/metrics, /memory/health).

2) Key files to inspect when changing behavior
- LLM: `brain/utils/generate_response.py` — env vars: `OPENAI_API_KEY`, `ORRIN_LLM_TOOL_ONLY` (defaults on; gates which callers may invoke the LLM), `ORRIN_LLM_DAILY_TOKEN_BUDGET` (router spend cap), `ORRIN_STRICT` (dev mode: re-raise swallowed programmer errors).
- Goals: `goals/goals_daemon.py`, `goals/runner.py`, `goals/policy.py`, `goals/registry.py`, `goals/store.py`, `goals/wal.py`.
- Memory: `memory/memory_daemon.py`, `memory/ingest.py`, `memory/wal.py`, `memory/compaction.py`, `memory/retrieval.py`.
- Supervisor: `supervisor/supervisor.py`, `supervisor/liveness_cycle.py`, `watchdogs.py` — these implement safety checks and lifecycle constraints.
- Data layout: `data/` (goal state: `data/goals/state.jsonl`, snapshots, WALs, and `data/logs` for runtime logs and LLM prompt logs).

3) Project-specific conventions and patterns
- WAL-first persistence: many subsystems write/read from write-ahead logs and snapshots. Prefer small, idempotent writes and ensure readers can tail the WAL.
- Daemon naming: long-running components end with `_daemon.py` and are expected to be resilient, idempotent, and to signal the supervisor on fatal conditions.
- State paths: resolve through `brain/paths.py` constants, never hand-built or `__file__`-relative paths (a hardcoded path bypasses `ORRIN_DATA_DIR` and breaks test isolation).
- Handlers & registration: goal handlers live under `goals/auto/handlers/*` and are discovered/registered via `goals/registry.py` — follow that convention when adding new handlers.
- LLM calls: Use `from utils.generate_response import generate_response` (resolves to `brain/utils/generate_response.py`) to centralize retries, logging, and config handling. The wrapper accepts `config={'expect_json': True}` for structured outputs. Note: callers are allowlisted (`ORRIN_LLM_TOOL_ONLY`); unknown callers are refused by default.

4) How to run, test, and debug (developer workflows)
- Environment: Python 3.10+ required. Create a venv and install deps:
  - `python -m venv .venv && source .venv/bin/activate`
  - `pip install -U pip && pip install -r requirements.txt`
- Tests: run from repo root with pytest. A minimal command: `python -m pytest -q` (repo includes `pytest.ini`).
- LLM local dev: set `OPENAI_API_KEY` before running code that calls `utils.generate_response`. Run in a safe test mode by mocking `utils.generate_response` or using the wrapper's retry behavior. Set `ORRIN_STRICT=1` in development so swallowed programmer errors fail loudly.
- Logs & prompts: runtime logs and LLM prompt dumps are under `data/logs/` (see `ORRIN_LLM_PROMPT_LOG` override).

5) Integration points & external dependencies
- OpenAI Responses API via the `openai` Python SDK; the code expects the newer `OpenAI` client and uses `responses.create`.
- UI dashboards rely on local HTTP endpoints (metrics/memory health). Observe `observability/dashboard_server.py` and `UI/` apps for details.

6) Examples (copyable snippets)
- Call LLM consistently:
  from utils.generate_response import generate_response
  text = generate_response("Summarize X", config={"expect_json": False, "temperature": 0.3})

- Register a new goal handler: add a file under `goals/auto/handlers/` that exports the handler class/function and ensure `goals/registry.py` will import/discover it.

7) Testing and change guidance
- Keep changes small and add focused unit tests under `tests/` that exercise the altered module. Look at existing tests under `tests/` for patterns (e.g., `tests/memory`, `tests/goals_test`).
- For changes touching persistence (WAL/snapshots), include tests that simulate restarts and verify idempotence.

If anything above is unclear, point me to the module you'd like expanded and I will update this file with more examples or runnable checks.

---
Please review and tell me which sections to expand or if you want additional examples (CLI usage, specific test commands, or common refactor patterns).
