# Benchmarks & Verification

Orrin separates **code verification** (tests, every commit) from **capability benchmarks**
(measured on long autonomous runs) from **run evidence** (sealed capsules and run reports).

## Code verification

- `make verify` is the standing gate: lint (ruff), type checks, import/layering contracts, module
  size limits, and the pytest suite (1,300+ tests across `tests/brain`, `tests/goals_test`,
  `tests/memory`, `tests/runtime`, `tests/supervisor_tests`, `tests/observability_tests`,
  `tests/llm`).
- `make coverage` runs the suite under coverage and gates against a recorded floor
  (`.coverage-floor`) via `brain/scripts/coverage_ratchet.py` — coverage can only ratchet up.

## Capability benchmarks

`brain/benchmarks/` is the single home for benchmark **specs** (what each tests + success criteria)
and the harness that collects evidence and scores them. Two kinds:

- **Passive** — measured just by running the autonomous loop with sampling on (e.g. B1 bounded
  memory, B2 affect-driven switching).
- **Scenario** — need a seeded test goal or specific flags (e.g. B3 offline planning, B4 satiety
  closure, B5 self-repair), seeded with `seed_scenario(...)`.

Run them by launching Orrin with `ORRIN_BENCHMARK=1` (per-cycle sampling + auto-eval). B3 requires
the LLM off to prove offline planning. Results and the claims-vs-evidence ledger live in
`docs/Capability, Benchmarks & Evidence/`.

## Run evidence

- **Life capsules** (`brain/evidence/life_capsule.py`) — each run can be sealed into a
  self-describing `.orrinlife.zip` with raw streams, cleaned tables, a queryable SQLite DB,
  computed metrics, and a claims ledger. See
  [Existence and Lifecycle](Existence_and_Lifecycle).
- **Run reports** — every staging run gets a dated folder under
  `docs/Behavioral Evaluation & Runtime Diagnostics/demo_runs/` with findings, audits, and a
  pass/fail verdict against the acceptance gate in `docs/NEXT_RUN_TESTS.md`.
- `brain/symbolic/benchmark.py` scores symbolic reasoning against ground truth continuously.

## Code pointers

- `Makefile` — `verify`, `coverage`, `coverage-update`
- `brain/benchmarks/__init__.py` — specs + harness + `seed_scenario`
- `docs/Capability, Benchmarks & Evidence/BENCHMARKS.md` — the benchmark ledger
- `docs/NEXT_RUN_TESTS.md` — the current run acceptance gate
