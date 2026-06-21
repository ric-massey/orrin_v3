# Orrin Codebase Cleanup Plan

**Created:** 2026-06-18  
**Scope:** engineering cleanup only; preserve Orrin's observable behavior unless a
separate change explicitly authorizes behavior changes.

Detailed structural findings are recorded in
`docs/Engineering & Code Health/ENGINEERING_STRUCTURE_AUDIT_2026-06-18.md`.

## Implementation status (updated 2026-06-21)

Closed out the low-risk "finishable tails" so the remaining work is purely the
large incremental decompositions (Phase 4A/B/D, 5, 6) plus CI hardening (7).

- **Phase 4A/4B boot characterization net — DONE.** Before extracting any
  lifecycle stage out of `main.py`/`ORRIN_loop.py`, added
  `tests/test_main_boot.py`: subprocess characterization tests that pin the real
  entrypoint's observable boot→shutdown contract against a redirected (tmp)
  state dir — (1) a headless single-cycle run (`ORRIN_ONCE=1`, `ORRIN_UI=0`)
  brings every subsystem up in dependency order, runs one cognitive cycle, and
  shuts down clean (exit 0 + `runstate.json` flipped clean); (2) the
  single-instance flock refuses a second boot with exit 3 before any heavy
  subsystem starts; (3) SIGINT drives the async-signal-safe
  `_on_signal → _main_stop → _graceful_shutdown` handoff to a clean exit. This
  is the safety net the RuntimeContext restructure (the coupled half of 4B + 4A)
  leans on. Writing it surfaced and fixed two real hermeticity/packaging leaks —
  `runtime/crash_log.py` (`brain/logs/crash.log`) and
  `brain/cognition/language/acquisition.py` (`felt_experience.txt` /
  `replay_corpus.txt`) hardcoded `__file__`-relative paths instead of honoring
  the resolved `LOGS_DIR`/`DATA_DIR`; both now follow the relocated state tree
  (a no-op for dev checkouts, correct for tests + a read-only packaged program
  folder). Suite **921 passed / 1 skipped**, ruff clean.

- **Phase 4B watchdog-construction slice — DONE.** First net-protected
  extraction out of `main.py`: the ~165-line block of psutil resource providers
  + host/vital escalation callbacks + vital-floor config moved to
  `runtime/watchdog_setup.py` (`build()` returns a `WatchdogInputs` bundle whose
  `.kwargs` splat straight into `start_watchdogs`; the two inward getters are
  surfaced for the calibration path). It's decoupled from the boot-mutable
  globals — touching only psutil/env/telemetry/working-memory/gc — so it didn't
  need the RuntimeContext work. main.py **1,332 → 1,165**. The boot
  characterization net (which starts the watchdogs in a full boot) + the full
  suite stayed green. **Still coupled in main.py (needs RuntimeContext):** the
  stop/shutdown sequence, the re-exec/reset/restart lifecycle, the `_pulse_loop`
  heartbeat, and `run()` — they read boot-built module state (daemon, store,
  goals, bridge, stop events).

- **Phase 4C (backend/server/app.py) — DONE.** app.py went 1,988 → 225 lines.
  Every route was extracted into focused, sub-600-line modules under
  `backend/server/`: `state.py` (DI/read helpers), `auth.py` (request guards),
  `lifecycle.py` (stop/reset/restart registry, accessed via has_*/safe_* to dodge
  the runtime-rebind trap), and routers `memory`, `source`, `diagnostics`,
  `settings`, `agent`, `update`, `control`, `telemetry`, `cognition`,
  `embodiment`. app.py now holds only app/lifespan setup, router wiring, the WS,
  and the 3 genuinely app-level routes (death, `/`, `/ws/telemetry`). Each slice
  was a pure move verified by TestClient (incl. auth 403/200 paths), ruff, and
  the full suite (914 passed). A Phase-3-tail regression surfaced mid-extraction
  (bare `version`/`goal_io`/`memory_io`/`ORRIN_loop` imports broken by removing
  brain/ from sys.path) was fixed and the import-contract ratchet hardened to
  cover brain-root modules. **Still open in Phase 4:** 4A `ORRIN_loop.py` (do
  last, behind characterization tests), 4B `main.py`, 4D `select_function.py` /
  `pursue_goal.py`.

- **Phase 0/1 — COMPLETE.** Cleared all 26 `F841` unused-variable findings and
  flipped ruff to enforce it (`ignore = []`); `F821` was already zero, so the
  Phase-1 exit criterion is met. The remaining `E5xx`/`E7xx` (line-length,
  semicolons, import-order) stay deferred-by-design — introduce incrementally,
  not exit-gating. Also made `test_tray_fallback` skip when the optional
  `pystray` extra is absent, restoring a deterministic green baseline (Phase 0):
  full suite **914 passed / 5 skipped**.
- **Phase 2 tail — DONE.** Added a fully-pinned `requirements.lock` (408 pkgs,
  `uv pip compile --all-extras`, resolved for Linux/CPython 3.11) tracked via a
  `.gitignore` negation; `requirements.txt` stays the curated direct mirror.
  Swapped the Docker image off the Vite dev server onto static serving — the
  backend already mounts the built dist at `/`, so a multi-stage Dockerfile
  builds the SPA (Node) and the python runtime serves it on :8800 (no Node at
  runtime). `ORRIN_UI_OPEN` is now actually wired in `main.py`. *Unvalidated:* a
  full `docker build`/run (local daemon was down) — code/config verified
  (`npm run build` green, backend serves index 200, `docker compose config` ok).
- **Phase 3 tail — DONE.** Removed the legacy `brain/` `sys.path` insert. Self-
  authored runtime code is now normalized onto `brain.*` at write time
  (`agency/self_code.normalize_self_code_imports`), the two template/prompt
  emitters (`code_writer`, `self_extension`) emit `brain.*`, and a latent
  `repo_root+"/brain"` bug in `goals/handlers/generic` is fixed. Verified every
  entrypoint imports with only the repo root on the path.

## Implementation status (updated 2026-06-20)

Progress since 2026-06-19:

- **Phase 4E (frontend decomposition) — DONE.** Both oversized React files are
  split into focused modules, all pure moves verified by `tsc` + build:
  - `Settings.tsx` 1494 → 75 lines: a thin container + `pages/settings/`
    (shared helpers/types + 10 section files, each <263 lines; shared
    `ToggleRow`).
  - `CognitiveSphere.tsx` 1057 → 294 lines: a container + `cognitiveSphere/`
    (`layout.ts` pure geometry/settings, `Scene.tsx` the R3F scene cluster,
    `ControlsPanel.tsx`, `CognitionExplorer.tsx`).
  **Still open in Phase 4:** 4A `ORRIN_loop.py` (do last, behind char tests),
  4B `main.py`, 4C `app.py` routers (needs a small DI pass so `_DATA_DIR`/`hub`
  stay monkeypatchable), 4D `select_function.py` / `pursue_goal.py`.


- **Phase 7 (CI enforcement) — STARTED.** `.github/workflows/tests.yml` now
  realizes the full `make verify` gate: Ruff + the hermetic pytest suite +
  frontend type-check/lint/build, plus a repo-hygiene job that fails if a
  generated runtime artifact gets re-tracked. The two obsolete embedder
  deselects were removed (Phase 0 made them hermetic; they pass with the real
  sentence-transformers installed).
- **Phase 1 dead-code leftover — DONE.** Deleted the `brain/think/select_function.py`
  compat shim (zero importers). `llm_stub.py` kept (in the self-code
  `_BLOCKED_PATHS` list + catalogued in TEMPLATES.md → genuinely
  review-before-delete).
- **Phase 3 (import normalization) — DONE (one runtime tail).** All 18 brain
  leaf packages (`paths`, `utils`, `core`, `cog_memory`, `cognition`, `affect`,
  `think`, `behavior`, `agency`, `registry`, `symbolic`, `embodiment`,
  `motivation`, `peers`, `benchmarks`, `evidence`, `config`, `eval`) are
  converted to the single `brain.*` namespace across source and tests. This
  closed a real order-dependent `/api/death` failure whose root cause was the
  dual-instance hazard (a reloaded bare `paths` leaking a tmp `DATA_DIR`).
  Coverage went beyond import statements: the cognition/behavior registry walks
  (`iter_modules("brain.cognition")`), runtime dynamic imports (ORRIN_loop
  `__import__`, toolkit `agency.skills.*`, look_outward, dynamic_loader), and
  mock/import strings in tests (`patch("brain....")`). `pytest.ini` now uses
  `pythonpath = .` and the full suite is green with `brain/` off the path. The
  `tests/test_import_contract.py` ratchet lists all 18 leaves and rejects bare
  references in import statements AND in patch/import_module/__import__ strings,
  so it can't regress. The PyInstaller spec bundles the `brain.*` namespace.
  **Remaining tail:** `main.py` still inserts `brain/` on `sys.path` at runtime
  as a compatibility affordance for self-authored code that may emit bare
  imports; removing it is gated on a self-code import audit + app-launch check
  (root packages `goals`/`memory`/`reaper` stay top-level by design).

## Implementation status (updated 2026-06-19)

The low-risk, finite, verifiable phases are **done and verified**; the large
incremental refactors remain open by design (the plan itself warns against
doing them wholesale). Verification gate: `make verify` — Ruff clean, **890
passed / 1 skipped**, frontend type-check + build + ESLint green.

- **Phase 0 — Protect the baseline: DONE.** Embedding test made hermetic
  (root cause was a `DummyST` that rejected production's `device="cpu"` kwarg,
  not the inherited env the note guessed; added a text-specific force-hash flag
  `MEMORY_TEXT_FORCE_HASH` + a regression test for inherited overrides). Green
  baseline recorded. `make` task interface added. Expected test env documented
  in `tests/conftest.py`.
- **Phase 1 — Repository & tooling hygiene: DONE (mechanical reformatting
  deferred).** Stopped tracking `repo_tree.txt`, `trace.jsonl`, `tunnel_url.txt`
  and the runtime `brain/prompts_backup.json`; removed the stale
  `DEPENDENCY_GRAPH.md`. Narrow Ruff config in `pyproject.toml` (`select=["F",
  "E9"]`, `ignore=["F841"]`) — **zero F821**, plus fixed a real `F811` and a
  real `F823` (an `except` block raised `UnboundLocalError` because
  `record_failure` was only imported locally). 31 unused imports removed.
  Minimal frontend ESLint flat config (React-Hooks rules) + `npm run lint`.
  Replaced the copied-`GoalsDaemon` non-test with 9 tests against the
  production class. Deleted `observability/ui_build.py` + 12 confirmed dead
  modules. **Still open:** F841 (26) and the ~440 mechanical E4xx/E7xx
  semicolon/import-order findings (introduce incrementally, no mass auto-fix).
- **Phase 2 — Dependency & packaging consolidation: DONE (Docker UI + uv lock
  deferred).** `pyproject.toml` is now the single source of truth with explicit
  extras (`backend`, `desktop`, `embedding`, `nlp`, `llm`, `llm-extra`, `dev`,
  `all`); `requirements.txt` / `backend/requirements.txt` are documented
  generated mirrors; dev tools (pytest, ruff, coverage) declared; resolution
  verified for core / extras / recursive `all`. **Still open:** swap the Docker
  Vite dev server for a static build (needs a headless static-serve mode in
  `main.py` — an app change, not a dependency one); emit a fully-pinned lock via
  `uv pip compile`.
- **Phases 3–7 — NOT STARTED.** Namespace normalization, orchestration
  decomposition, typed contracts, deep dead-code/v1–v2 settling, and CI
  enforcement are the multi-week incremental tracks; tackle them behind the now
  green/hermetic suite, one slice at a time.

## Current baseline

- Python: 860 tests collected; 858 passed, 1 skipped, 1 failed.
- Current failure:
  `tests/memory/embedder_test.py::test_text_with_fake_sentence_transformers_success`.
  The test is environment-sensitive: an inherited
  `PYTEST_FORCE_HASH_EMBEDDING=1` forces the hash path despite the fake
  sentence-transformer.
- Frontend: `npm run typecheck` passes.
- Ruff: 535 findings:
  - 199 `E702` multiple statements separated by semicolons
  - 107 `E402` imports outside the module header
  - 85 `E701` multiple statements after a colon
  - 31 unused imports
  - 26 unused variables
  - 23 undefined names
- Tracked source: about 146,000 lines.
- Largest modules:
  - `brain/ORRIN_loop.py`: 3,627 lines
  - `brain/think/think_utils/select_function.py`: 2,196 lines
  - `backend/server/app.py`: 1,988 lines
  - `brain/cognition/planning/pursue_goal.py`: 1,673 lines
  - `main.py`: 1,551 lines
  - `frontend/src/pages/Settings.tsx`: 1,261 lines
- Import architecture relies on adding both the repository root and `brain/` to
  `sys.path`. There are roughly 3,000 bare-package import matches across source
  and tests.
- Dependency declarations are split across `pyproject.toml`,
  `requirements.txt`, and `backend/requirements.txt`, and they do not describe
  the same complete environment.
- Generated local files are ignored now, but `repo_tree.txt`, `trace.jsonl`, and
  `tunnel_url.txt` remain tracked.
- The checked-in dependency graph is explicitly stale.
- The working tree already contains unrelated edits. Cleanup work must use
  narrow commits and avoid mixing with those changes.

## Cleanup rules

1. Preserve behavior before reorganizing it.
2. Establish a green, deterministic baseline before enforcing new checks.
3. Separate mechanical cleanup, dependency cleanup, and architectural refactors.
4. Keep each commit reversible and limited to one concern.
5. Do not combine cleanup with feature changes or behavioral tuning.
6. Add boundary tests before splitting large modules.
7. Prefer deleting compatibility code only after all callers have migrated.
8. Introduce lint rules incrementally; do not apply a repository-wide auto-fix.

## Phase 0 — Protect the baseline

**Goal:** make cleanup measurable and safe.

### Work

- Resolve the environment-sensitive embedding test:
  - make `_reload_embedder` explicitly set or clear every relevant embedding
    environment variable;
  - ensure tests do not depend on the developer shell;
  - add a regression test for inherited environment overrides.
- Run and record:
  - `pytest -q`
  - `npm run typecheck`
  - `npm run build`
- Add a fast smoke suite marker or script for high-frequency cleanup work.
- Add coverage reporting, initially informational rather than blocking.
- Document expected test environment variables in `tests/conftest.py`.
- Preserve the existing live-state mutation guard.

### Exit criteria

- Full Python suite passes from a clean shell and from a shell containing
  embedding-related overrides.
- Frontend type-check and production build pass.
- A single documented command runs the standard local verification set.

## Phase 1 — Repository and tooling hygiene

**Goal:** remove noise before changing architecture.

### Work

- Stop tracking generated files:
  - `repo_tree.txt`
  - `trace.jsonl`
  - `tunnel_url.txt`
- Confirm all backup archives, build outputs, caches, runtime state, and local
  tunnel scripts are either ignored or intentionally versioned.
- Add Ruff configuration to `pyproject.toml`.
- Start with high-signal rules:
  - undefined names
  - unused imports and variables
  - duplicate definitions
  - invalid syntax
- Exclude intentional bootstrap files from import-order enforcement temporarily.
- Mechanically expand semicolon-compressed statements in small batches.
- Add frontend linting with a minimal ESLint configuration, including React
  Hooks rules.
- Add `format`, `lint`, `typecheck`, and `test` commands through one documented
  task interface.
- Regenerate or remove `docs/archive/DEPENDENCY_GRAPH.md`; do not retain a stale
  generated artifact as current documentation.
- Replace `tests/goals_test/test_daemon.py`'s copied `GoalsDaemon`
  implementation with tests that import the production class.
- Delete the confirmed stale duplicate `observability/ui_build.py`.
- Review and remove the high-confidence dead modules listed in the engineering
  structure audit.

### Exit criteria

- Ruff has no `F821` undefined-name findings.
- No generated runtime files are tracked.
- Python and frontend checks have stable, documented commands.
- Formatting-only commits contain no behavioral changes.

## Phase 2 — Dependency and packaging consolidation

**Goal:** create one authoritative dependency model.

### Work

- Make `pyproject.toml` the source of truth.
- Split dependencies into explicit groups:
  - core runtime
  - backend/API
  - desktop
  - optional LLM providers
  - media/embedding extras
  - development/test
- Generate or reduce compatibility requirement files instead of maintaining
  independent handwritten lists.
- Add all actual development tools: pytest, Ruff, coverage, and any chosen type
  checker.
- Pin direct dependencies to deliberate ranges and document heavyweight optional
  installs.
- Verify source install, editable install, Docker build, and PyInstaller build
  resolve from the same dependency model.
- Replace Docker's Vite development server with a built static frontend unless
  hot reload is explicitly required by that image.

### Exit criteria

- A fresh environment can be installed from `pyproject.toml`.
- Requirements files, if retained, are generated or validated against it.
- Docker and desktop packaging do not carry undeclared runtime dependencies.

## Phase 3 — Normalize package boundaries

**Goal:** remove the fragile dual-root import model.

### Target structure

Move toward one import namespace, for example:

```text
orrin/
  runtime/
  brain/
  goals/
  memory/
  backend/
  observability/
  reaper/
```

The exact directory move can be deferred; the first requirement is that imports
behave as if one namespace exists.

### Work

- Inventory bare imports such as `from utils`, `from cognition`, `from affect`,
  and `from paths`.
- Define allowed package dependency directions.
- Convert one leaf package at a time to absolute package imports.
- Remove test-local `sys.path` mutation as migrated areas become installable.
- Keep a temporary compatibility layer only where runtime-loaded self-authored
  modules require it.
- Add import-contract tests:
  - modules import after `pip install -e .`;
  - modules import without adding `brain/` to `PYTHONPATH`;
  - forbidden reverse dependencies fail an architecture check.
- Update PyInstaller hidden imports after each package slice.

### Suggested migration order

1. `brain/utils` and `brain/paths`
2. `brain/affect`
3. `brain/cog_memory`
4. `brain/cognition` leaf modules
5. `brain/think`
6. runtime entry points and dynamic loaders

### Exit criteria

- Application and tests run with only the repository package root on the import
  path.
- `pytest.ini` no longer needs `pythonpath = . brain`.
- Entry points do not mutate `sys.path` for normal packaged modules.

## Phase 4 — Decompose orchestration modules

**Goal:** make central flows readable and independently testable.

### 4A. `brain/ORRIN_loop.py`

Extract by lifecycle responsibility, not by arbitrary line count:

- boot/context construction
- cycle sensing and state refresh
- conscious-ignition decision
- cognition execution
- action execution/accounting
- maintenance scheduling
- telemetry publication
- shutdown/finalization

Keep `run_cognitive_loop()` as a thin coordinator. Introduce a typed
`RuntimeContext` or narrowly scoped state objects instead of passing an
unbounded dictionary everywhere.

Before this extraction, add import/startup characterization tests and move
stateful module-import work out of `main.py`, registries, migrations, and path
modules. Refactoring the loop while imports can mutate state makes failures hard
to localize.

### 4B. `main.py`

Separate:

- configuration loading
- process/runtime construction
- backend/UI launch
- watchdog construction
- desktop lifecycle
- signal handling and shutdown

### 4C. `backend/server/app.py`

Split routers by API domain:

- lifecycle/control
- cognition/telemetry
- memory
- settings/secrets
- diagnostics/export
- source inspection

Move request parsing and domain logic out of route functions.

### 4D. Selection and planning

- Split `select_function.py` into candidate generation, feature calculation,
  policy/scoring, constraints, and selection recording.
- Split `pursue_goal.py` into planning, execution, adaptation, and persistence.
- Expose public interfaces rather than cross-module imports of private helpers.

### 4E. Frontend

- Split `Settings.tsx` into provider, runtime, privacy/security, appearance, and
  diagnostics sections.
- Separate data hooks from presentation in `CognitiveSphere.tsx`.
- Consolidate polling, transport state, and local-storage preferences.

### Exit criteria

- Central coordinator modules primarily compose services and stages.
- Extracted stages have direct unit tests.
- No new module exceeds an agreed soft limit, initially 600 lines, without a
  documented reason.
- Runtime behavior and telemetry contracts remain unchanged.

## Phase 5 — Strengthen types and contracts

**Goal:** replace implicit dictionary protocols with explicit interfaces.

### Work

- Define typed structures for:
  - runtime context
  - affect state and proposals
  - action proposals/results
  - telemetry frames
  - goal execution outcomes
  - persisted state envelopes and schema versions
- Select a gradual Python type checker and start with new/extracted modules.
- Remove `type: ignore` comments by category, beginning with real contract
  mismatches rather than optional-dependency imports.
- Generate frontend telemetry types from a shared schema or validate both sides
  against the same fixture.
- Add schema migration tests for every persisted state envelope.

### Exit criteria

- New modules are type-checked.
- Backend producers and frontend consumers share a verifiable telemetry contract.
- Persisted state changes require a schema version and migration test.

## Phase 6 — Dead code, duplication, and API cleanup

**Goal:** delete only after structure and tests can prove code is unused.

### Work

- Run static dead-code analysis and verify every candidate with import/search
  tracing.
- Distinguish dynamic registry/provider modules from ordinary dead modules;
  absence from the static import graph is not sufficient evidence in Orrin.
- Remove pass-through modules and wildcard re-exports when callers have migrated.
- Consolidate repeated JSON/state access, environment parsing, logging, and
  retry logic.
- Find duplicate function names and near-identical modules.
- Remove stale compatibility aliases after one release boundary or explicit
  migration checkpoint.
- Archive historical plans that no longer describe current behavior and maintain
  one current architecture document plus focused decision records.

### Exit criteria

- Every deletion is supported by static tracing and passing tests.
- No current documentation points at deleted or superseded architecture.
- Compatibility layers have owners and removal dates.

## Cross-cutting engineering constraints

- Imports must not start daemons, acquire process locks, rewrite registries,
  migrate persisted state, or wipe/seed a mind.
- Tests must import production implementations rather than copying them.
- The v1/v2 goals and memory systems require explicit ownership tables before
  either adapter is simplified.
- Broad exception handlers must be classified as optional capability, external
  I/O, data/schema failure, programmer error, or shutdown cleanup.
- Ambiguous same-name modules should be renamed only after package-boundary
  normalization, to avoid proliferating compatibility shims.

## Phase 7 — CI enforcement and maintenance policy

**Goal:** prevent the codebase from returning to its current state.

### Work

- CI gates:
  - Python tests
  - frontend type-check and build
  - Ruff
  - frontend lint
  - import-boundary checks
  - generated-file cleanliness
- Add changed-lines or ratcheted coverage instead of an arbitrary global target.
- Add a size/complexity report that warns on new large modules.
- Add dependency vulnerability and outdated-package reporting.
- Define ownership for architecture, runtime state schemas, packaging, and UI
  contracts.

### Exit criteria

- Every cleanup invariant is automated.
- New lint debt cannot be added.
- Large-module and boundary regressions are visible in pull requests.

## Recommended execution order

1. Phase 0: deterministic green baseline.
2. Phase 1: repository hygiene and high-signal lint.
3. Phase 2: dependency consolidation.
4. Phase 3: package/import normalization.
5. Phase 4A and 4B: runtime orchestration extraction.
6. Phase 4C and 4E: backend/frontend decomposition.
7. Phase 5: types and schemas alongside extracted modules.
8. Phase 6: dead-code deletion.
9. Phase 7: enforce the completed standards.

Do not begin with a wholesale `ORRIN_loop.py` rewrite. Its behavior is central,
its state is broad, and active feature work currently touches nearby surfaces.
First make the tests hermetic, establish package boundaries, and extract one
characterized lifecycle stage at a time.

## First cleanup milestone

The first milestone should be a small, low-risk series of commits:

1. Fix embedding-test hermeticity.
2. Add a standard verification command and record a green baseline.
3. Stop tracking generated root artifacts.
4. Add narrow Ruff configuration and eliminate all undefined names.
5. Consolidate dependency declarations without changing installed behavior.
6. Regenerate the dependency graph from the current tree.

This milestone creates the safety rails required for the larger namespace and
orchestration work.
