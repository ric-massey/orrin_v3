# Contributing

Orrin is a single-developer research project, but issues, forks, experiments, and pull requests are
welcome. This page is the wiki-side developer guide; the repo also has
[`CONTRIBUTING.md`](https://github.com/ric-massey/orrin_v3/blob/main/CONTRIBUTING.md) and
[`CLAUDE.md`](https://github.com/ric-massey/orrin_v3/blob/main/CLAUDE.md) (an agent-oriented guide).

## Setup

```bash
git clone https://github.com/ric-massey/orrin_v3.git
cd orrin_v3
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Node.js + npm are only needed to build the frontend from source.

## The gate: `make verify`

This is exactly what CI runs — keep it green before opening a PR:

```bash
make verify        # ruff + mypy + pytest + frontend typecheck/build
make test          # just the Python suite
make coverage      # suite under the ratcheted coverage floor
```

## Conventions that matter here

1. **Keep the suite green.** The suite is hermetic — `tests/conftest.py` redirects state to a tmp
   dir and fails the session on any live-state write ("isolation breach"). If you see that, you
   added a path that bypasses `brain/paths.py`.
2. **Resolve state paths through `brain/paths.py`** constants (`DATA_DIR`, `LOGS_DIR`, …). Never
   hand-built or `__file__`-relative paths — that's what caused a real CI-reddening bug.
3. **Symbolic-first, LLM gated.** New code must work with no provider key. LLM calls go through
   `brain/utils/generate_response.py` only, and callers must be allow-listed. Fail closed — never
   fabricate content on error.
4. **Prefer operational evidence over anthropomorphic language.** Cognitive terms name mechanisms.

## Where things live

See [Cognition Module](Cognition_Module) and the subsystem pages for the map. Long-running
components are `*_daemon.py` and must be resilient and idempotent. Goal handlers register via
`goals/registry.py`; new cognitive functions go through the registry the bandit selects from
([Writing a Custom Cognitive Function](Writing_Custom_Cognitive_Function)).

## Opening a PR

The repo has a PR template with a verification checklist. Keep changes small and testable, add tests
for new behavior, and note anything non-obvious for the reviewer. Don't commit secrets — keys live
in `.env` or the OS keychain (see [Security Model](Security_Model)).

## Reporting issues

Bug and feature templates are provided. Include the run mode, whether an LLM key was configured, and
evidence from `brain/logs/` or a run report — with no secrets or private logs.
