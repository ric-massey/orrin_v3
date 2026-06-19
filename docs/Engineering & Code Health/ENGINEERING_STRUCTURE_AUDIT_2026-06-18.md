# Orrin Engineering Structure Audit

**Created:** 2026-06-18  
**Purpose:** identify structural engineering debt beyond formatting: oversized
files/functions, hidden behavior, duplicated purposes, dead code, stale copies,
and misleading names.

This is a static audit. Dynamic cognition/behavior registries mean that absence
from ordinary Python imports is not enough to prove a module dead. A deletion is
marked **high confidence** only when the module also has no registry, manifest,
JSON catalog, test, or textual runtime reference.

## Remediation status (updated 2026-06-19)

The low-risk milestones are **done and verified** (`make verify`: Ruff clean,
890 passed / 1 skipped, frontend green). The large structural milestones remain
open by design. See `CODEBASE_CLEANUP_PLAN_2026-06-18.md` for the phase view.

- **Milestone A — remove false confidence: DONE.** §3's copied `GoalsDaemon`
  (which in fact held *zero* test functions) is replaced by 9 tests against the
  production class (plan / no-handler→FAILED / blocked / policy choice + FIFO
  fallback / health). Suite made hermetic (§ embedding). Import-safety smoke
  tests added (`tests/test_import_safety.py`) proving the §2 state-mutating
  modules touch only the redirected tmp state dir, never live `brain/data` or
  the instance lock.
- **Milestone B — safe deletions: DONE.** Deleted `observability/ui_build.py`
  (§6) and all 13 high-confidence dead modules in §7 after confirming no source,
  test, registry, JSON-catalog, or live textual caller; removed the stale
  `DEPENDENCY_GRAPH.md` that referenced them. `brain/prompts_backup.json` (§6)
  untracked as runtime state. `llm_stub.py` / `think/select_function.py`
  (review-before-delete) intentionally **kept**.
- **Milestones C–F — NOT STARTED.** Explicit startup (§2), settling the v1/v2
  goals+memory duplication (§5), splitting the oversized functions (§1), the
  broad-exception reclassification (§9), and the ambiguous-module renames (§4)
  are the multi-week tracks, to be done behind the now green/hermetic suite.

## Executive findings

1. Several core functions are too large to review safely:
   `run_cognitive_loop()` is 2,549 lines and `select_function()` is 1,113.
2. `main.py` performs most startup work at import time, including acquiring the
   single-instance lock, migrating state, starting `MemoryDaemon`, and mutating
   process-global hooks.
3. `tests/goals_test/test_daemon.py` contains a modified copy of the production
   `GoalsDaemon`; it does not test the production class.
4. Orrin currently runs two generations of memory and goal systems joined by
   adapters. This is migration architecture, not a settled boundary.
5. Multiple pairs have the same generic name but different meanings
   (`world_model`, `sandbox`, `llm_gate`, `events`, `embedder`,
   `introspection`, `paths`). These names conceal which layer owns what.
6. `observability/ui_build.py` is a stale near-copy of the used
   `brain/utils/ui_build.py`.
7. At least 13 initial-commit modules have no detected runtime or test caller.
8. Importing ordinary modules can create directories, rewrite registries, or
   migrate persisted state.
9. Exception handling is excessively broad: about 2,400
   `except Exception` sites exist across the Python code, including roughly 400
   broad handlers that silently pass. This can make dead paths and partial
   failures look healthy.
10. The current checkout no longer contains the old `orrin_v3.04/` source copy,
    but the full copy remains in Git history; the packed repository is about
    524 MB.

## 1. Oversized files and hidden responsibilities

Line count is a warning, not the decision rule. The stronger signal is a large
function that combines unrelated lifecycle stages, persistence, policy, and
error recovery.

### Tier 1 — split behind characterization tests

| File | Size | Largest unit | Finding | Recommended boundary |
|---|---:|---:|---|---|
| `brain/ORRIN_loop.py` | 3,627 | `run_cognitive_loop`: 2,549 | One function owns sensing, goal synchronization, cognition, action, maintenance, memory bridging, telemetry, and shutdown behavior. | Extract boot, cycle input, cognition lane, action accounting, maintenance, telemetry, and shutdown stages. |
| `brain/think/think_utils/select_function.py` | 2,196 | `select_function`: 1,113 | Candidate filtering, feature extraction, policy weights, bandit integration, threat handling, novelty, and compatibility return shapes are interleaved. | Split candidate source, eligibility, feature vector, scorers, policy arbitration, and result recording. |
| `main.py` | 1,551 | module body plus `run`: 194 | The module body is effectively a second unbounded startup function. Importing it starts and mutates the application. | Create `RuntimeBuilder`/startup stages and keep module import declarative. |
| `brain/affect/update_affect_state.py` | 838 | `update_affect_state`: 803 | Almost the entire module is one state transition with normalization, dynamics, queues, homeostasis, schema repair, and persistence. | Extract pure transition stages and keep one final persistence owner. |
| `brain/cognition/dreaming/dream_cycle.py` | 862 | `dream_cycle`: 767 | Scheduling, replay, symbolic dreaming, memory consolidation, affect proposals, language work, and cleanup are one function. | Create explicit dream phases with a shared result object. |
| `brain/cognition/planning/pursue_goal.py` | 1,673 | `pursue_committed_goal`: 598 | Goal attention, plan generation, action execution, closure, recovery, degradation, and persistence overlap. | Split pursuit state machine, step execution, recovery, and closure policy. |
| `brain/think/think_utils/finalize.py` | 601 | `finalize_cycle`: 502 | Reward, accounting, memory, speech, telemetry, and cleanup happen in one finalizer. | Replace with ordered finalization hooks/stages. |

### Tier 2 — split by existing natural sections

| File | Size | Natural split |
|---|---:|---|
| `backend/server/app.py` | 1,988 | Routers already group naturally into cognition, memory, life, diagnostics, settings, control, update, and agent-input APIs. |
| `brain/cognition/intrinsic_goals.py` | 1,435 | Candidate generators, aspiration persistence/learning, scoring, and final orchestration. |
| `brain/cognition/planning/goals.py` | 1,408 | Goal store/tree operations, decomposition, lifecycle transitions, focus selection, and plan-step operations. |
| `brain/cognition/knowledge_graph.py` | 1,239 | Storage/schema, entity extraction, graph mutation, queries, and inference. |
| `brain/think/think_utils/action_gate.py` | 1,136 | Proposal evaluation, queue policy, action dispatch, and action implementations. |
| `brain/cognition/opinions.py` | 1,114 | Migration/storage, evidence ledger, opinion formation, revision, and reflection. |
| `frontend/src/pages/Settings.tsx` | 1,261 | It already contains separate Updates, Model, Existence, Language, Backup, Trust, Keys, and Reset components; move each to its own file. |
| `frontend/src/components/brain/CognitiveSphere.tsx` | 1,057 | Geometry/layout, Three.js scene, controls, explorer/history, storage, and page container. |

### Size policy

- New production modules: soft limit of 600 lines.
- New functions: soft limit of 80 lines.
- Existing functions over 200 lines require a characterization test before
  extraction.
- A size exception should state why cohesion is improved by keeping the unit
  together.

## 2. Hidden behavior and surprising side effects

### Critical: `main.py` executes startup on import

Before `run()` is called, importing `main.py` can:

- configure offline model environment;
- open and write `brain/logs/crash.log`;
- replace `sys.excepthook` and `threading.excepthook`;
- load `.env` and OS-keychain secrets;
- acquire the single-instance lock or exit the process;
- wipe state when `ORRIN_FORGET_ON_START` is set;
- seed a newborn state tree;
- run schema migration;
- update lifespan/sleep state;
- mark lifecycle state as running;
- construct and start `MemoryDaemon`;
- initialize the goal store/API.

This makes imports unsafe for tests, tools, packaging inspection, and reuse.
Move all of it into an explicit startup object called by `run()`.

### High: imports mutate persistent state

- `brain/registry/behavior_registry.py` discovers and writes
  `behavioral_functions_list.json` at import.
- `brain/registry/cognition_registry.py` discovers and writes
  `cognitive_functions.json` at import.
- `brain/cognition/intrinsic_goals.py` migrates completed-goal files at import.
- `brain/symbolic/temporal_planner.py` deletes orphan plans at import.
- `brain/agency/self_code.py` creates/ensures the self-code tree at import.

Migrations and generated catalogs should be explicit startup tasks with logging,
versioning, and failure policy. Importing a library module should not rewrite the
mind.

### Medium: imports mutate the filesystem or process environment

- `brain/paths.py` creates data, think, log, test, inbox, and outbox directories.
- `memory/config.py` creates memory directories while building its singleton.
- both embedders set Hugging Face offline environment variables at import.
- `brain/behavior/tools/sandbox.py` creates its temp directory at import.
- `goals/metrics.py` initializes metrics at import.

Some of these are harmless in production, but they obscure ownership and make
tests order-dependent. Prefer explicit initialization or lazy creation at the
first operation.

### Medium: one router is mounted twice

`backend/server/app.py` mounts the same read API at both `/...` and `/api/...`
for compatibility. This doubles the visible route surface and keeps old clients
alive indefinitely. Add telemetry/deprecation for bare routes and remove them
after an explicit compatibility window.

## 3. Tests that hide production drift

### Critical: copied `GoalsDaemon`

`tests/goals_test/test_daemon.py` contains approximately 480 lines copied from
`goals/goals_daemon.py`, including its own `GoalsDaemon` class. The copies have
already diverged:

- the test copy implements its own fair scheduler;
- the production version uses `policy.choose_next_steps`;
- startup wake/debug behavior differs;
- compatibility handling for store signatures differs.

Tests can therefore pass against the test implementation while production is
broken.

**Fix:** delete the copied implementation, import the production daemon, and
keep only test fakes/fixtures in the test module. Add direct tests for policy
fallback and scheduler fairness.

## 4. Same name, different purpose

These are mostly not duplicate implementations. The problem is that generic
names hide architectural boundaries and make imports easy to confuse.

| Current names | Actual meanings | Recommended naming |
|---|---|---|
| `brain/events.py` / `brain/utils/events.py` / `goals/events.py` | In-memory deduplicated queue / persistent telemetry JSONL / goal event bus | `runtime_event_queue`, `telemetry_event_log`, `goal_event_bus` |
| `brain/cognition/world_model.py` / `brain/embodiment/world_model.py` | Symbolic entity/fact graph / learned host-environment model | `symbolic_world_model`, `host_environment_model` |
| `brain/cognition/sandbox.py` / `brain/behavior/tools/sandbox.py` | Imaginative LLM experiments / restricted Python execution | `imagination_lab`, `python_sandbox` |
| `brain/utils/llm_gate.py` / `brain/symbolic/llm_gate.py` | Provider availability/authorization / symbolic-first routing and crystallization | `llm_availability`, `symbolic_generation_router` |
| `brain/utils/embedder.py` / `memory/embedder.py` | Brain semantic model (`all-mpnet`) / memory text+image adapter with fallbacks | `semantic_embedder`, `memory_embedder` |
| `brain/affect/introspection.py` / `brain/cognition/planning/introspection.py` | Noisy perceived affect / goal-planning self-review | `affect_perception`, `introspective_planning` |
| `brain/paths.py` / `brain/utils/paths.py` | Canonical state-file catalog / app-data and UI path helpers | `state_paths`, `app_paths` |
| `brain/affect/emotional_feedback.py` / `brain/affect/apply_affective_feedback.py` | Small score-to-delta helper / large active affect integration pass | Delete or rename the dead helper; reserve one public name. |

Renames should follow package normalization so compatibility wrappers do not
multiply.

## 5. Duplicate systems still active

### Memory v1 and v2

- `brain/cog_memory` owns JSON working/long memory.
- root `memory/` owns the daemon, embedding store, WAL, retrieval, compaction,
  and media.
- `brain/memory_io.py` copies data in both directions and explicitly describes
  v1 and v2 coexistence.
- `ORRIN_loop.py` still reads/writes v1 files while also querying the v2 daemon.

This causes duplicated concepts, synchronization work, and uncertain authority.
Choose a final owner for working memory, long-term memory, retrieval, and
compaction. Until then, document each direction of synchronization and make it
idempotent.

### Goals v1 and v2

- `brain/cognition/planning/goals.py` owns the cognitive goal tree and plans.
- root `goals/` owns typed goals, API, daemon, handlers, WAL, and lifecycle.
- `brain/goal_io.py` maps between the two and contains anti-resurrection logic.

This is a migration seam with real failure modes, not merely an adapter. Define
which system owns identity, lifecycle, plan progress, prioritization, and
persistence; then migrate one field group at a time.

## 6. Stale copies and compatibility files

### Confirmed stale duplicate

- `observability/ui_build.py` is about 79% line-similar to
  `brain/utils/ui_build.py`.
- Only `utils.ui_build` is imported.
- Delete the observability copy after one import smoke test.

### Compatibility wrapper with no detected caller

- `brain/think/select_function.py` only wildcard-re-exports
  `think_utils.select_function`.
- No current source/test import of the historical module path was found.
- Remove it after checking external/plugin compatibility requirements.

### Generated backup, not an old code copy

- `brain/prompts_backup.json` currently contains `{}`.
- It is a real output target of `self_reflection.py`, so it is not dead code.
- It is mutable runtime state and should not be tracked as a source artifact.
  Move it under the ignored state tree or seed it explicitly if a seed is needed.

### Historical full source copy

The deleted `orrin_v3.04/` tree remains in Git history. It explains much of the
repository's approximately 524 MB pack size. Do not rewrite shared history
casually. If repository clone size matters, perform a separately planned
`git filter-repo` migration with a backup, collaborator coordination, and force
push.

## 7. High-confidence dead-code candidates

The following public symbols have no detected source, test, registry, manifest,
or JSON-catalog caller. Most were added in the initial import and have not been
integrated.

| File | Why it appears dead | Action |
|---|---|---|
| `brain/idea_service.py` | `make_idea_hook` has no caller and returns an empty hook even when enabled. | Delete. |
| `brain/think/safe_runner.py` | `safe_step` has no caller. | Delete or wire deliberately into the runtime; do not retain as implied safety. |
| `brain/think/state_graph.py` | `StateGraph` has no caller. | Delete. |
| `brain/utils/checkpoint.py` | Snapshot APIs have no caller. | Delete unless checkpoint recovery is placed on the roadmap. |
| `brain/utils/facade.py` | No importer; only re-exports utilities. | Delete. |
| `brain/utils/hash_utils.py` | `hash_context` has no caller. | Delete. |
| `brain/utils/linting.py` | `ruff_fix` has no caller. | Delete; developer lint commands belong in tooling, not runtime. |
| `brain/utils/response_utils.py` | Context response helper has no caller. | Delete. |
| `brain/utils/servers.py` | Old memory/goals SPA server helpers have no caller; current UI/backend supersede them. | Delete. |
| `brain/utils/validators.py` | Both validators have no caller. | Delete or wire at actual boundaries before claiming validation. |
| `brain/affect/emotional_response.py` | `generate_emotional_response` has no caller. | Delete. |
| `brain/affect/emotional_feedback.py` | Defines a second `apply_affective_feedback`; no caller imports this file. | Delete after confirming no plugin imports it. |
| `observability/ui_build.py` | Duplicate implementation, no importer. | Delete. |

### Review-before-delete candidates

- `brain/utils/llm_stub.py`: no runtime caller, but it is named in the
  self-code blocked-path list and `TEMPLATES.md`. Remove those stale references
  in the same change if deleting it.
- `brain/think/select_function.py`: no internal caller, but explicitly claims
  external compatibility.
- provider modules with no static inbound imports are dynamically selected and
  are **not** dead.
- cognition/behavior modules present in JSON catalogs are dynamically callable
  and are **not** dead merely because static imports are absent.

## 8. Duplicate helper implementations

AST-normalized comparison found repeated helper bodies:

- goal/step deserialization is duplicated between `goals/store.py` and
  `goals/wal.py`;
- emotion snapshot logic is duplicated between
  `brain/cog_memory/long_memory.py` and `remember.py`;
- goal JSON shaping is duplicated between `brain/utils/goals_feed.py` and
  `goals/cli.py`;
- `_slope` is duplicated between `reaper/host_resources.py` and
  `reaper/memory.py`;
- step/lock helpers are repeated across goal handlers;
- `brain/utils/ui_build.py` and `observability/ui_build.py` are near copies.

Do not create a generic “helpers” dumping ground. Consolidate only where the
data contract is truly shared:

- model serialization should live next to the model;
- numeric trend helpers can live in `reaper`;
- handler lock operations should live on the handler context/service;
- CLI presentation may remain separate if its shape differs intentionally.

## 9. Error handling that hides faults

The codebase has approximately:

- 2,400 `except Exception` occurrences;
- 400 broad handlers that immediately `pass`;
- 156 explicit “silent except” markers.

Many are valid best-effort boundaries in an autonomous long-running system, but
the current volume makes it difficult to distinguish optional failure from
corruption, contract mismatch, and programmer error.

### Policy

Every broad exception should be classified:

1. **Optional capability:** log once/rate-limit and return an explicit
   unavailable result.
2. **External I/O:** catch the concrete network/filesystem exceptions and
   preserve diagnostic context.
3. **Data corruption/schema mismatch:** never silently pass; quarantine or fail
   loudly.
4. **Programmer error:** re-raise in strict/test mode.
5. **Shutdown cleanup:** best effort is acceptable, but record failures.

Start with `ORRIN_loop.py` (217 broad catches), `main.py` (88),
`dream_cycle.py` (50), `select_function.py` (45), and `backend/server/app.py`
(43).

## 10. Recommended cleanup sequence

### Milestone A — remove false confidence

1. Replace the copied daemon test with tests of production `GoalsDaemon`.
2. Make the test environment hermetic and restore a green baseline.
3. Add import smoke tests proving that importing library modules does not start
   daemons, acquire locks, or mutate live state.

### Milestone B — safe deletions

1. Delete `observability/ui_build.py`.
2. Delete the high-confidence dead modules in small groups.
3. Remove stale references to any deleted module.
4. Run full Python tests and frontend build after each group.

### Milestone C — explicit startup

1. Move all `main.py` import-time operations into startup stages.
2. Move registry persistence and migrations into an explicit migration/catalog
   phase.
3. Make path/config modules declarative.

### Milestone D — settle duplicated architecture

1. Write ownership tables for v1/v2 goals and memory.
2. Instrument adapter traffic and identify fields with a single effective owner.
3. Migrate one responsibility at a time; remove adapter branches after each
   migration.

### Milestone E — split central functions

1. Extract pure functions first.
2. Introduce typed stage results.
3. Keep orchestration order unchanged.
4. Add tests for every extracted stage before changing policy.

### Milestone F — rename ambiguous modules

Perform namespacing/renames after import normalization, with temporary explicit
compatibility modules only where external extensions actually depend on them.

## Verification gates

- `pytest -q`
- `npm run typecheck`
- `npm run build`
- import smoke tests in a temporary state directory
- no change to live `brain/data`
- no new broad silent exception
- no new module over 600 lines or function over 80 lines without justification
- production classes, not copied implementations, are exercised by tests
