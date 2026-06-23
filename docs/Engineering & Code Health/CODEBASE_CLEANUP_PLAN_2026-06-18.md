# Orrin Codebase Cleanup Plan

**Created:** 2026-06-18  
**Scope:** engineering cleanup only; preserve Orrin's observable behavior unless a
separate change explicitly authorizes behavior changes.

Detailed structural findings are recorded in
`docs/Engineering & Code Health/ENGINEERING_STRUCTURE_AUDIT_2026-06-18.md`.

## Implementation status (updated 2026-06-22c)

- **Phase 6 — STARTED (static dead-code analysis + first verified removals).**
  Adopted `vulture` as the dead-code candidate generator (dev tool, not wired
  into `make verify`); ran it across `brain/backend/runtime/goals/memory/reaper/
  observability`. Confirmed the plan's warning holds: the 60%-confidence list is
  dominated by dynamic-dispatch false positives (FastAPI route handlers, DI
  setters, the JS-RPC bridge methods, and registry-walked cognition/behavior
  functions), so every candidate is verified by import/grep tracing before any
  deletion. Landed four behavior-preserving removals, each its own revertible
  commit, full gate green after (**964 passed / 1 skipped**, mypy 50 clean, ruff
  clean — unchanged from baseline):
  - unreachable `return {}` in `mortality.evaluate` (try/except both always
    return);
  - the ~127-line dead `contextual_emotion_priming()` in `emotion_utils.py`
    (zero callers anywhere; only an archived-doc reference) + its four
    now-orphaned imports;
  - the dead `long_memory_file` param of `summarize_chat_to_long_memory()`
    (the value was accepted and ignored — `update_long_memory()` owns the path),
    and the caller's now-unused `LONG_MEMORY_FILE` import;
  - the dead `goals/auto/seeder.py` stub (abandoned since the initial commit, no
    `__init__.py`, not on any dynamic-load path) + its now-empty directory.
  Deliberately left out of scope: `contextual_bandit.update_with_pe`'s ignored
  `lr`/`l2`/`pe_lr` params — the caller passes `lr=_ach_lr` expecting it to be
  used, so that is a latent behavior bug, not dead code (Phase 6 rule 5: no
  behavioral tuning), to be addressed separately. **Remaining Phase 6:** the
  bulk dead-function triage (262 brain/-side vulture candidates, each needing
  caller tracing), duplication consolidation (JSON/state/env/logging/retry),
  pass-through/re-export removal, stale-alias cleanup, and doc archival.

## Implementation status (updated 2026-06-22b)

- **Phase 5.1 — selection/ and planning/ packages fully strict-typed.** The mypy
  `--strict` allowlist (`pyproject.toml [tool.mypy].files`) grew from 14 → 46
  modules. Both coordinators the plan names are done: `select_function()` had its
  `Dict + *args/**kwargs` signature replaced by an explicit keyword-only
  `threat_detector_response` param (sentinel preserves the legacy tuple-return
  detection), and `pursue_committed_goal` (`planning/goal_execution.py`) is typed.
  The **entire** `brain/cognition/planning/` package (all 30 modules) plus the
  `selection/` package and `select_function.py` now pass `--strict`. Shared
  import surfaces were made explicit re-exports (the `name as name` idiom) so
  strict importers don't trip `no_implicit_reexport`: `json_utils.extract_json`,
  `reward_signals.release_reward_signal` (signature typed), and the `goals.py` /
  `intrinsic_goals.py` / `pursue_goal.py` / `select_function.py` re-export blocks.
  All edits behavior-preserving (annotations, `float()`/`str()` coercions at the
  same boundaries, one dead duplicate-constant removal). Verified green: full
  suite **954 passed / 1 skipped**, `mypy` clean on 46 files, ruff clean.
  **Remaining Phase 5.1:** loop-stage coordinator typing (`brain/loop/`).

- **Phase 5.2 — FE↔BE telemetry contract DONE (codegen + two-sided runtime
  validation).** `backend/server/schema.py` (pydantic) is now the single source of
  truth, enriched with `Goal`/`FnEvent` models (the well-specified blocks that
  were `Dict[str, Any]`); the free-form blocks (executive/monitor/workspace/
  interoception) stay passthrough because the producer genuinely doesn't constrain
  them. `backend/server/generate_telemetry_ts.py` (`make telemetry-types`) renders
  `frontend/src/lib/telemetry.gen.ts` — zod schemas + `z.infer` types — replacing
  the hand-mirrored wire types in `types.ts` (which now holds only the *merged*
  client view-model, legitimately stricter than the partial wire). Runtime
  validation at BOTH boundaries: `validate_frame()` in `hub.merge` (producer,
  non-fatal + capped logging) and `TelemetryFrameSchema.safeParse` in
  `telemetry.ts` (consumer). `tests/observability_tests/telemetry_codegen_test.py`
  re-renders in-memory and fails CI if the committed `.gen.ts` is stale, so the FE
  types can never silently drift again. Added `zod@^4` to the frontend. Verified:
  full suite **960 passed / 1 skipped**, mypy 46 clean, ruff clean, FE
  typecheck/lint/build green.
  **Remaining Phase 5:** loop-stage typing, 5.4 persisted-state migrations.

- **Phase 5.3 — `type: ignore` triage STARTED (foundational utils done).** Triaged
  the blanket (un-coded) ignores by category. Key realisation: ignores in
  NON-allowlisted files are inert (mypy never reads them under `files=[...]`), so
  the triage is done as a module enters strict — which is also `warn_unused_ignores`
  (part of `--strict`), so the gate now keeps these honest. Brought
  `brain/utils/{num,log,json_utils}.py` (json_utils is imported by 200+ modules) to
  strict, narrowing/removing their ignores in the process: removed unused
  import-guard ignores (redundant under the global `ignore_missing_imports`),
  narrowed fallback `X = None` assignments to `# type: ignore[assignment]`, and
  replaced the `json.load`→`T` blanket with a `cast(T, …)`. Allowlist 46 → 49.
  Also removed 7 provably-unused blanket ignores and narrowed one `[assignment]`
  across brain/ core (loop_helpers, body_sense, reflect_on_cognition,
  function_catalog, cognition_registry, sandbox) — verified by
  `mypy --warn-unused-ignores`. Gate green: 960 passed, mypy 49 clean, ruff clean.
  **Remaining 5.3:** the still-used blanket ignores in the not-yet-strict
  subtrees (goals/, memory/, reaper/, runtime/) get narrowed as those modules
  enter the allowlist.

- **Phase 5.4 — persisted-state schema + migrations DONE (subsumption + discipline
  lock).** Built on the existing spine (`brain/utils/schema_migration.py`,
  `CURRENT_SCHEMA_VERSION`). (1) SUBSUMPTION: the knowledge-graph store no longer
  versions itself in isolation — `knowledge_graph_core._SCHEMA_VERSION` now derives
  from the global `CURRENT_SCHEMA_VERSION`, so a graph-format change bumps the
  global version + registers a spine migration instead of a private store version.
  (`mind_archive`/`life_capsule` already embed the global `state_schema_version`;
  their `MIND_`/`CAPSULE_SCHEMA_VERSION` are separate *container* formats, left as
  is.) (2) DISCIPLINE: new `tests/brain/test_schema_migration_roundtrip.py` adds a
  reusable round-trip harness (old fixture → migrate → asserted shape + idempotency),
  a worked TEMPLATE for the next migration, and a CI lock asserting every registered
  `_MIGRATIONS` step has a round-trip test (`set(_MIGRATIONS) ⊆ _ROUNDTRIP_TESTED`)
  — so a future format change without a round-trip test fails CI. Added
  `schema_migration.py` to the strict allowlist (50 modules). Gate green: 964
  passed, mypy 50 clean, ruff clean.
  **Remaining Phase 5:** loop-stage typing (5.1 tail); 5.3 ignore-narrowing in the
  not-yet-strict subtrees. The 5.2/5.4 deliverables and the selection+planning
  typing are complete.

## Implementation status (updated 2026-06-22)

- **Phase 4D — DONE.** Both selection/planning files are dense with
  import-time-computed constants whose helpers cross-reference each other, so the
  safe order is bottom-up: extract the dependency *base* first, then layer
  scoring/features on top. Each slice is a pure move re-imported to preserve the
  public API (`from …select_function import …` / `…pursue_goal import …`),
  cut with AST node spans, and verified by the selector/goal suites + full suite
  (**923 passed / 1 skipped**, ruff clean):
  - `select_function.py` **2,268 → 1,755**, new `brain/think/think_utils/selection/`
    package: `text.py` (tokenize / overlap / `_capability_overlap`), `catalog.py`
    (manifest cache + loaders + learned-stats — the cycle-free base), `state.py`
    (`_dominant_emotion` / `_focus_goal_name` readers), `constants.py` (shared
    `FALLBACK_ACTIONS`), `scoring.py` (emotion prefs, `_SEMANTIC_PRIORS`,
    devaluation, novelty, bandit pick/hint), `features.py` (`extract_features`).
    Bugs the suite caught + fixed: tests patched the old module's cache (repointed
    at `catalog`); `catalog.py` one dir deeper made `parents[2]` data-paths wrong
    (→ `parents[3]`); a heuristic mis-cut the nested `_SEMANTIC_PRIORS` dict
    (switched to AST spans).
  - `pursue_goal.py` **1,673 → 1,355**: `plan_versioning.py` (drift scoring + plan
    snapshot/rollback) and `goal_planning.py` (intent classification + symbolic
    plan + causal first-step + plan assembly). `_causal_first_step` re-exported
    for the causal-closure test.
  Then extracted the remaining helper layers, each verified green:
  - `select_function.py` **→ 1,519**: `candidates.py` (selectability +
    dispatchability + cognition-only candidate loaders, with the shared
    `_ALWAYS_EXCLUDE` joining `constants.py`); the leftover small readers folded
    into `state.py`, `_emo_mode_function_map` into `scoring.py`,
    `_planned_action_recruitment` into `candidates.py`.
  - `pursue_goal.py` **→ 1,091**: `goal_closure.py` (survival preempt,
    idempotent completion, tier-satiety close, Wrosch degrade/disengage +
    re-promote; the `_FINALIZED_IDS` dedup dict moved here and re-imported as the
    same object so finalize-once stays coherent).

  Then finished both files:
  - `select_function.py` **→ 1,488**: `_workspace_routes_for` → `routing.py`
    (the last cohesive helper); `select_function()` stays as the selection
    coordinator (the plan keeps the coordinator, like `run_cognitive_loop`) with
    its policy frozenset constants, every helper layer now in
    `selection/{text, catalog, state, constants, scoring, features, candidates,
    routing}.py`. Its body is a single scoring accumulator (every section mutates
    one shared `scores` dict + ~15 locals), so it's coordinator-by-nature rather
    than a sequence of extractable stages.
  - `pursue_goal.py` **→ 228** (a thin facade): the two coordinator functions
    split into their own modules — `goal_execution.py` (`pursue_committed_goal`
    + the counters it exclusively owns: `_last_pursuit_ts`/`_COOLDOWN_S`/
    `_pursuit_call_count`/`_DELIBERATE_MAX_ROUNDS`/`_STEP_MAX_ATTEMPTS`) and
    `goal_adaptation.py` (`assess_goal_progress` / `adapt_subgoals` + their
    blocker/milestone helpers + `_last_adapt_ts`/`_ADAPT_COOLDOWN_S`). Verified no
    cross-calls between the groups so the `global`-reassigned counters travel
    cleanly with their sole writer; `pursue_goal.py` keeps the deliberate
    goal-action commands (`attend_goal`/`redirect_goal_plan`/`abandon_goal`/
    `_stuck_enough`) and re-exports the rest, so every caller path is unchanged.
    The subgoal-adaptation test now patches `_save_plan_version` + the cooldown
    counter in `goal_adaptation` (their new home).

  **Net:** `select_function.py` **2,268 → 1,488**, `pursue_goal.py`
  **1,673 → 228**; thirteen focused modules now hold the selection/planning
  layers (`selection/{text, catalog, state, constants, scoring, features,
  candidates, routing}.py`; `planning/{plan_versioning, goal_planning,
  goal_closure, goal_execution, goal_adaptation}.py`). The plan's full split —
  candidate generation / feature calculation / policy-scoring / constraints for
  selection; planning / execution / adaptation / persistence (+ closure) for
  pursuit — is complete, all public names re-exported so no caller changed, every
  slice verified by the selector/goal suites + full suite. **All of Phase 4
  (4A–4E) is now done.**

With **all of Phase 4 (4A–4E) now complete**, the remaining work is
**Phase 4.5** (finish the decomposition gaps a 2026-06-22 file-level audit found:
`select_function()` is still a single 1,120-line function, a few Phase-4-extracted
modules exceed the 600-line limit, and ~30 other modules over 600 lines were
never in Phase 4's scope), then Phase 5 (types & contracts), Phase 6 (dead code /
duplication / API cleanup), and finishing Phase 7 (CI enforcement — the
`make verify` gate is in; the coverage ratchet, size/complexity report,
dependency-vulnerability reporting, and ownership tables remain).

- **Phase 4A `ORRIN_loop.py` — cleanly-separable stages extracted (loop-body
  decomposition still open).** Extended the boot net with
  `test_single_cycle_advances_cognition_counter` (a single-cycle run must persist
  an advanced `cycle_count.json` — proof a cognitive cycle actually executed, not
  just booted), then extracted three cohesive lifecycle stages into a new
  `brain/loop/` package (placed there, not under the registry-walked
  `brain.cognition`): `telemetry.py` (the fail-safe UI/telemetry emit helpers —
  4A's "telemetry publication"), `invoke.py` (`_invoke_cognition` +
  `_build_kwargs_for`, the single cognitive-dispatch point), and `boot.py` (4A's
  "boot/context construction": `_validate_boot_files`,
  `_verify_production_capability`, the ~490-line `_boot_context`).
  `run_cognitive_loop` re-imports what it calls, so call sites and external import
  paths are unchanged. Each was a pure move, verified by the loop net (which runs
  `_boot_context` + emits telemetry + completes a cycle every run) + the full
  suite (**922 passed / 1 skipped**, ruff clean); three dependent tests were
  repointed at the new module homes. Then began decomposing the
  `run_cognitive_loop` **body** itself: the cycle's ~510-line perceive/refresh
  prologue (reload context, sync working memory, inject the cycle's signals, run
  `process_inputs` + binding, fast-answer a waiting Face message) became
  `brain/loop/sense.py::sense_and_refresh(_goals_api, timestamp) -> (context,
  affect_state)`, with the existing first stage `_apply_transient_signal_decay`
  moved alongside it. `ruff` F821 caught the one real coupling — the prologue
  binds the loop-local `affect_state` that downstream stages read — so the stage
  returns it and the loop unpacks (exact binding preserved). Then continued
  one stage at a time down the cycle: `brain/loop/reflect.py`
  (`integrate_recall_and_baseline` — post-perception memory recall + signal
  integration + emotional-baseline snapshot; `tier1_health_check` — the
  setpoint_regulation interoception read) and `brain/loop/deliberate.py`
  (`prepare_workspace` — executive lane + metacog→workspace prep;
  `ignite` — the conscious-ignition gate). Each was a context-mutating stage with
  no leaked control flow (clean `ruff` F821 each time), verified by the loop net +
  full suite (**922 passed / 1 skipped**, ruff clean) and committed individually.
  **ORRIN_loop.py 3,709 → 1,872** (−49%), split into
  `brain/loop/{telemetry, invoke, boot, sense, reflect, deliberate}.py`.
  Then completed the loop-body decomposition, one net-verified stage per commit:
  the three dispatch paths into `brain/loop/execute.py`
  (`execute_behavior_action` / `execute_cognition_function` / `execute_fallback`,
  each returning `(context, reward, acted_this_cycle)` — `ruff` F821 caught that
  the earlier path extractions had orphaned `acted_this_cycle`, which feeds
  `action_debt`, so each path now returns exactly what its inline code computed);
  `brain/loop/account.py` (`account_action` — acted recovery, drift, action-debt,
  stall watchdog, trace); `brain/loop/maintenance.py` (`run_maintenance_tier` —
  the cadence-driven closure tier); and `brain/loop/finalize.py`
  (`persist_and_periodic` — goal/memory sync, evaluator, prediction, dream,
  workspace; `finalize_cycle` — health monitor, plasticity, affect convergence,
  long-memory consolidation). An import-time SyntaxError caught a loop-level
  `break` (the ORRIN_ONCE exit) an indent-grep had missed, so the finalize
  boundary was corrected to leave loop-control in the loop. Shared `_OUTWARD_FNS`
  moved to `brain/loop/constants.py` to avoid a circular import.

  Finally pulled the loop's setup/teardown out too: `services.py`
  (`start_background_services` — ToolRunner/Evaluator/Layer-0 embodiment/Executive
  bring-up returning the handles the loop needs; `shutdown_loop` — ToolRunner stop
  + session epilogue + embedder release) and `maintenance.py::periodic_housekeeping`
  (the end-of-cycle GC/summaries/finetune cadence).

  **ORRIN_loop.py 3,709 → 314 (−92%).** `run_cognitive_loop` is now a 233-line
  coordinator — signal/goals/memory wiring → `start_background_services` →
  `_boot_context` → the staged `while` pipeline (`sense_and_refresh →
  integrate_recall_and_baseline → tier1_health_check → prepare_workspace → ignite
  → think → dispatch(A/B/C) → account_action → persist_and_periodic →
  run_maintenance_tier → finalize_cycle → periodic_housekeeping → pulse/sleep`) →
  `shutdown_loop` — with only genuine coordination (dispatch branching,
  decision-id, reward-rate, loop control) left inline. Twelve stage modules under
  `brain/loop/`, each verified by the loop net (every stage runs in a real cycle)
  + the full suite (**923 passed / 1 skipped**, ruff clean). Soft-limit
  exceptions: `boot.py` (631, one ~490-line `_boot_context`) and `execute.py`
  (855, Path B is ~610 lines) — both single-function intact moves, sub-divisible
  in a later pass. **4A is complete** (and, as recorded above, so is 4D — all of
  Phase 4 is now done).

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
  suite stayed green.

- **Phase 4B RuntimeContext restructure — DONE.** The coupled boot core is out
  of `main.py`. A typed `runtime/context.py::RuntimeContext` (mutable dataclass)
  captures the boot-produced state; `main.py` runs the boot sequence, builds the
  context once, wires the Stop/Reset/Restart buttons to it, and calls
  `runtime.desktop.run(ctx)`. The lifecycle stages that used to close over
  `main`'s module globals now take `ctx` explicitly:
  `runtime/lifecycle.py` (heartbeat `pulse_loop`, `stop_cognition`,
  `graceful_shutdown`, `wipe_to_newborn`/`reexec`/`reset_to_newborn`/
  `restart_process`, the signal-handler factory, vital-calibration stress) and
  `runtime/desktop.py` (`run()` — the cognitive-loop start, ORRIN_ONCE watcher,
  and the pywebview/tray vs headless-heartbeat orchestration). main.py **1,332 →
  597**; every new module is under the 600-line soft limit. The two mutable
  teardown guards + the cog-loop handle moved onto the context (no more
  `global`). Pure moves verified by the boot characterization net (all three
  paths — single-cycle, lock-refusal, SIGINT — exercise the new
  `run → desktop → lifecycle` chain end to end) + the full suite **921 passed /
  1 skipped**, ruff clean. **Phase 4 remaining:** 4A `ORRIN_loop.py` and 4D
  `select_function.py` / `pursue_goal.py`.

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

  **Remaining tail (re-audited 2026-06-22 — supersedes the earlier "main.py
  inserts brain/" note, which is now stale):** `main.py` and `backend/main.py`
  insert only the *repo root* on `sys.path` (main.py explicitly does NOT add
  `brain/` — it comments that doing so "would shadow the frozen importer"), so
  the dual-root hazard is gone at the entry points; removing even the repo-root
  bootstrap is gated on committing to editable-install-only. Genuine residuals:
  (1) **No package dependency-direction / layering check exists** — the plan's
  "define allowed dependency directions / forbidden reverse deps fail an
  architecture check" item was never built; `test_boundary_contracts_and_audit.py`
  enforces *runtime data contracts at function seams*, not package layering, so
  nothing prevents an import cycle (e.g. `brain/utils` → `brain/cognition`). This
  is the one checklist item actually missed. (2) `goals/handlers/generic.py`
  does a guarded runtime `sys.path.insert` to reach `brain.*` (a consequence of
  `goals` being an intentional top-level package; defensible). (3) ~7 test files
  still `sys.path.insert` (several insert `BRAIN_DIR`, the old dual-root
  spelling) — harmless while they use `brain.*` imports, but a cleanup tail.
  Correctly exempt (not residuals): `life_capsule.py` (guarded by `__main__`,
  never runs on import), `brain/scripts/*` (standalone-script bootstraps), and
  `self_code`/`dynamic_loader`/`sandbox` (the self-authored-code machinery the
  plan explicitly exempts). Root packages `goals`/`memory`/`reaper` stay
  top-level by design.

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

## Phase 4.5 — Finish the decomposition Phase 4 left open

**Why this exists.** A 2026-06-22 audit of the actual files (not the status
notes) found that Phase 4 succeeded for four of its five named targets but
overstated "done" in two ways: one target still contains a monolithic function,
a few freshly-extracted modules already exceed the 600-line soft limit, and
Phase 4's scope never touched the ~30 other oversized modules in the tree. This
phase closes those gaps. It is still **engineering-only** — preserve observable
behavior and telemetry contracts; every slice is a pure move/extraction verified
green by the existing suites, same as Phase 4.

### 4.5A. Break up the `select_function()` body (the survived monolith)

`select_function.py` went 2,268 → 1,488 lines, but the file is now a **single
1,120-line function**. The helpers were extracted cleanly into `selection/`; the
coordinator itself was not. "Coordinator by nature" is only half true — it is a
linear scoring accumulator over one `scores` dict, which is exactly the shape
that decomposes into ordered, individually-testable scoring stages.

- Extract each contributing section (emotion prefs, semantic priors, novelty,
  devaluation, bandit hint, constraint masking, routing) into a
  `selection/score_*.py` step with the signature
  `apply(scores: dict, ctx: SelectionContext) -> None` (or returns a delta dict).
- `select_function()` becomes an explicit pipeline: build context once, run the
  ordered list of scoring steps, then pick. Target the coordinator under ~250
  lines.
- Each scoring step gets a direct unit test asserting its contribution to
  `scores` in isolation — the current single-function shape makes that
  impossible today.

**DONE.** The per-function boost computations were already extracted to
`selection/boosts.py` and the post-pick refinement to `selection/pick.py`. The
remaining monolith was decomposed into an explicit pipeline:
- `selection/score_actions.py` — the ~195-line per-action scoring loop as
  `score_candidates(actions, defs, ScoreInputs, context)`; the loop body is
  byte-for-byte unchanged (its ~42 inputs bundled in a `ScoreInputs` dataclass
  that makes the loop independently testable).
- `selection/score_setup.py` — `build_score_inputs(...)`, the per-cycle assembly
  of weights/priors/boost maps that produces the `ScoreInputs`.
- `select_function()` is now a thin coordinator: build context once, build score
  inputs, run the loop, pick, assemble the reason payload — **162 lines** (well
  under the ~250 target).

`select_function.py` 779 → 345; the two new modules are 340 and 281 lines (both
under the 600 soft limit). The scoring math is pinned unchanged by the 29
selector characterization/invariant tests; full `make verify` green.

### 4.5B. Bring over-limit extracted modules under the soft limit

Phase 4's own extraction produced modules above the 600-line limit it set.
Re-split these (or document a concrete exemption per the exit criteria):

- `brain/loop/execute.py` — **855 → 579 DONE** (reward shaping → `cognition_reward.py`)
- `brain/loop/boot.py` — **631 → 527 DONE** (preflight validators
  `_validate_boot_files` / `_verify_production_capability` → `boot_checks.py`)
- `brain/loop/sense.py` — **628 → 564 DONE** (affect-decay stage
  `_apply_transient_signal_decay` → `signal_decay.py`)
- `brain/cognition/planning/goal_execution.py` — **647 → 573 DONE** (milestone
  gate `_bootstrap_goal_plan` → `goal_planning.py`, beside `_generate_plan`)
- `brain/think/think_utils/finalize.py` — **630 → 572 DONE** (rule-based
  `_state_satisfaction` + its outward-action constants → `satisfaction.py`)

**4.5B complete** — all five Phase-4-extracted over-limit modules are now under
the 600-line soft limit, each by a single bottom-up extraction with the public
API re-exported from the original module.

### 4.5C. Decompose the monolithic modules Phase 4 never scoped

Phase 4 only aimed at five named files. A repo-wide scan still shows **32 source
modules over 600 lines**. Prioritize the largest, applying the same bottom-up,
re-export-the-public-API method that worked in 4C/4D:

- `brain/cognition/intrinsic_goals.py` — **1,745 → 506 DONE** (now under the
  limit). Split into a 4-module package by concern, each re-exported so external
  callers keep their import paths:
  - `intrinsic_aspirations.py` (403) — enduring aspirations + learned
    driven_by→aspiration credit + P3 fairness pressure.
  - `intrinsic_helpers.py` (381) — tier/zone classification, `_mk_goal`
    construction, goal-subject filters, weighted sampler, + the recently-completed
    cooldown ledger (shared state).
  - `intrinsic_generators.py` (553) — the symbolic (LLM-free) goal generators.
  - `intrinsic_goals.py` keeps the load gate, cadence, P7 commitment competition,
    and the `generate_intrinsic_goals` orchestrator.
- `brain/cognition/planning/goals.py` — **1,652 → 453 DONE** (now under the
  limit). Split into a package by concern, each re-exported so the ~55 external
  callers keep their import paths:
  - `goal_store.py` (334) — the goal-tree read/write/mutate leaf (load/save,
    add, merge, prune, status marking).
  - `goal_plan_ops.py` (285) — plan/step operations + dynamic subgoal adaptation.
  - `goal_outcomes.py` (475) — completion/failure/significance transitions.
  - `goal_criteria.py` (106) — artifact / completion-criteria gating.
  - `goal_belief.py` (133) — self-belief falsification on goal success.
  - `goals.py` keeps decomposition, pursuit, focus selection, and the
    `maybe_complete_goals` sweeper.
- `brain/evidence/life_capsule.py` — **1,308 → 550 DONE** (now under the limit).
  Split along the capsule's raw→cleaned→derived→interpreted layering:
  - `life_capsule_ingest.py` (452) — constants, `classify_action`, IO/hash/time
    helpers, and the per-stream parsers (the raw→cleaned leaf).
  - `life_capsule_metrics.py` (355) — `_compute_metrics`, the claims ledger, and
    the token-budgeted LLM bundle (derived→interpreted).
  - `life_capsule.py` keeps the SQLite/CSV assembly, raw copy, provenance, the
    `build_life_capsule` orchestrator, the reader API, and the CLI.
- `brain/cognition/knowledge_graph.py` — **1,239 → 338 DONE** (now under the
  limit). Split into a 3-module package, public API re-exported:
  - `knowledge_graph_core.py` (491) — schema/vocab/bootstrap constants,
    extraction patterns, utils, graph I/O, low-level in-place entity/relation ops
    (the leaf).
  - `knowledge_graph_extract.py` (473) — text→graph extraction (regex + spaCy NER
    + definitional), building on the core.
  - `knowledge_graph.py` keeps the public entity/query/ingest/maintenance API and
    LLM dream consolidation.
- `brain/think/think_utils/action_gate.py` — **1,136 → 427 DONE** (now under the
  limit). Split into a 3-module package, public API re-exported:
  - `action_gate_helpers.py` (377) — the support leaf (pending-action queue,
    novelty/outcome stamping, reflection, adaptive context, injectors,
    `_current_focus_name`, and the action constants).
  - `action_gate_execute.py` (388) — `take_action` (action dispatch/execution).
  - `action_gate.py` keeps the `evaluate_and_act_if_needed` decision orchestrator.
- `brain/cognition/opinions.py` — **1,114**
- then the long tail (`update_affect_state.py` 882, `prediction.py` 867,
  `dream_cycle.py` 862, `theory_of_mind.py` 828, … down to 600).

Work largest-first, one module per change, each verified by the relevant suite
plus the full suite before moving on. Do not batch — the value is that each
landing is independently revertible.

### 4.5D. Add the package dependency-direction check Phase 3 missed

A 2026-06-22 re-audit found Phase 3 delivered its real goal (the dual-root
import hazard is gone, 0 bare imports, locked by the `test_import_contract.py`
ratchet) but **never built one of its own checklist items**: "define allowed
package dependency directions / forbidden reverse dependencies fail an
architecture check." The ratchet guards import *naming*, not *direction* — so
nothing today prevents an import cycle such as `brain/utils` → `brain/cognition`.
`test_boundary_contracts_and_audit.py` is unrelated (it enforces runtime data
contracts at function seams, not package layering). This belongs in 4.5 because
decomposition (4.5A–C) is exactly when new cross-package edges get introduced;
the check should exist before the monoliths are carved up, not after.

- Define the allowed dependency directions explicitly (a layered ordering, e.g.
  `paths`/`utils` → `core`/`config` → `affect`/`cog_memory` → `cognition` →
  `think` → `loop`/entry points; `goals`/`memory`/`reaper` as top-level
  consumers of `brain.*`, never the reverse).
- Add an architecture test (extend the existing import-contract test, or add a
  sibling) that parses each module's imports and **fails on any edge that points
  against the declared order** — i.e. a lower layer importing a higher one, or
  any back-edge from `brain.*` into `goals`/`memory`/`reaper`.
- Wire it into `make verify` so a forbidden reverse dependency breaks the build,
  the same way the bare-import ratchet already does.
- While here, retire the small Phase-3 `sys.path` tail the re-audit catalogued
  (the ~7 test files inserting `BRAIN_DIR`; the guarded `goals/handlers/generic.py`
  insert) where doing so doesn't fight the intentional top-level packaging.

### Exit criteria

- `select_function()` is a pipeline of ordered scoring steps, each unit-tested;
  the coordinator is under ~250 lines.
- No Phase-4-extracted module exceeds 600 lines without a documented exemption.
- The count of source modules over 600 lines is tracked and trending down; every
  reduction is a pure structural move with unchanged behavior/telemetry.
- A size/complexity report (Phase 7) is wired in so this list cannot silently
  regrow.
- Allowed package dependency directions are declared and enforced by a test in
  `make verify`; a forbidden reverse dependency or import cycle fails the build.
  The residual Phase-3 `sys.path` tail is retired except where it serves the
  intentional top-level packaging.

## Phase 5 — Strengthen types and contracts

**Goal:** replace Orrin's pervasive implicit-`dict` protocols with explicit,
machine-checked interfaces. The defining symptom is signatures like
`select_function(context: Dict, *args: Any, **kwargs: Any)`: nobody can tell what
`context` holds, so nothing is checkable and every refactor is a guess. This
phase makes the contracts explicit *and enforces them in CI*, so the structural
gains from Phase 4/4.5 can't silently rot.

**Sequencing — interleave with Phase 4.5, do not run after it.** Phase 4.5
re-splits the same modules Phase 5 would type, so type-checking them first is
wasted churn and re-splitting them is easier *with* types. Therefore:

1. **Do 5.0 (checker + gate) first, before the bulk of 4.5.** Standing up the
   type checker and wiring it into `make verify` is the prerequisite that makes
   every subsequent move verifiable.
2. **Then type each module as 4.5 carves it up** — a 4.5 re-split lands already
   typed and checked, rather than being re-touched in a later phase.

The remaining Phase 5 items (telemetry contract, persisted-state migrations) are
independent and can proceed in parallel.

### 5.0 Adopt and gate a type checker (decided, not deferred)

- **Use `mypy`** (Python-native, no Node toolchain dependency; matches the
  existing `make`-driven gate). Pyright was considered and rejected to avoid a
  second language runtime in the Python CI path.
- Configure it in `pyproject.toml` with a **per-module strictness allowlist**:
  global config is lenient (so the untyped legacy tree doesn't explode the
  build), and each module that has been typed is added to a `strict = true`
  override block. New/extracted modules join the strict list as they land.
- Add a `py-typecheck` target and fold it into `make verify` alongside the
  existing tests/ruff/`fe-typecheck`. This is the enforcement spine — without
  the gate, the rest of the phase decays.

### 5.1 Define typed structures (and close the `**kwargs` boundary)

- Define explicit types — `@dataclass(slots=True)` for owned mutable state,
  `TypedDict` for dict-shaped payloads that must stay JSON-serializable,
  `Protocol` for the service interfaces the coordinators depend on — for:
  - runtime/cycle context (the real-world name today is `cycle_state.py`; there
    is no `RuntimeContext` — reconcile to one named type)
  - affect state and proposals
  - action proposals/results
  - telemetry frames
  - goal execution outcomes
  - persisted state envelopes and schema versions
- **Tighten the call boundaries that defeat typing.** Defining the structs is
  worthless while call sites still splat `*args: Any, **kwargs: Any` — the splat
  erases the type at every hop. For each coordinator (`select_function`,
  `pursue_committed_goal`, the loop stages), replace the `Dict`+`**kwargs`
  signature with the explicit context type and remove the passthrough. This is
  the item most likely to be skipped and the one that makes the rest real.

### 5.2 Make the FE↔BE telemetry boundary a real contract

Telemetry crosses both a process and a language boundary, so static types alone
give false confidence — they describe intent, not what actually crosses the wire.
Build a contract with two layers:

- **Static (codegen, not snapshot).** Author the telemetry frames as the
  single source of truth (pydantic models) and **generate** the TypeScript types
  from their JSON Schema. A shared *fixture* test was considered and rejected: a
  fixture drifts silently and only catches shapes someone remembered to add.
- **Runtime (boundary validation).** Validate on emit (pydantic on the backend
  producer) and on parse (a schema guard such as zod on the frontend consumer),
  so a malformed or version-skewed frame fails loudly at the boundary instead of
  corrupting the UI state downstream.

### 5.3 `type: ignore` cleanup (gated by 5.0, not freestanding)

Once the checker runs, triage the ~33 `type: ignore` comments by category — real
contract mismatches first (fix them), optional-dependency imports last (keep,
but narrow to `[import-untyped]`/specific codes rather than blanket ignores). Do
this per module as it enters the strict allowlist, not as a separate sweep.

### 5.4 Persisted-state schema + migrations

- Build on the **existing** spine — `brain/utils/schema_migration.py`
  (`CURRENT_SCHEMA_VERSION`) and `test_schema_migration.py` already exist from
  the Desktop "Group G" work; this is not greenfield.
- Bring every persisted envelope under that single global version (the
  knowledge-graph store still versions itself in isolation — subsume it), and
  require a **round-trip migration test per envelope** (old fixture → migrate →
  asserted new shape) whenever a format changes.

### Exit criteria

- `make verify` fails on a type error in any allowlisted (strict) module; the
  strict list grows monotonically and is never shrunk to make a change pass.
- No coordinator on the typed path still takes `Dict` + `**kwargs: Any`; the
  context type is explicit and checked.
- Telemetry TS types are generated from the backend schema (not hand-authored),
  and both producer and consumer validate frames at runtime.
- Every persisted state change requires a schema-version bump and a round-trip
  migration test; the per-store version is subsumed by the global one.

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
7. Phase 5.0 first (type checker + `make verify` gate), then Phase 4.5
   interleaved with the rest of Phase 5: finish the `select_function()` body,
   bring over-limit extracted modules under the soft limit, and decompose the
   out-of-scope monoliths (largest-first, one module per change) — typing each
   module as it is re-split rather than in a later pass. Telemetry contract (5.2)
   and persisted-state migrations (5.4) proceed in parallel.
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
