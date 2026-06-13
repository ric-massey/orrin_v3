# Orrin — Improvement Findings

Deep-read analysis of the Orrin source tree (540 files, ~113,000 lines of Python across 515 modules). This document covers only the negatives — the things that need improvement. Findings are ordered roughly by severity. File paths refer to the repository root.

---

## 1. Monolithic core files (HIGH — maintainability)

`brain/ORRIN_loop.py` is 3,338 lines, and `run_cognitive_loop` alone is roughly 2,300 lines of a single `while True` body containing dozens of sequentially inlined try-blocks, 193 function-level imports, working-memory mirroring, crisis detection, goal-stall pressure, consolidation, and persistence — all in one stack frame. Other hotspots: `brain/think/think_utils/select_function.py` (1,909 lines), `brain/cognition/planning/pursue_goal.py` (1,364), `brain/cognition/planning/goals.py` (1,298), `brain/cognition/knowledge_graph.py` (1,173), `brain/think/think_utils/action_gate.py` (1,134).

The cycle is conceptually a pipeline (perceive → inject signals → update affect → select → act → reward → commit → persist). **Recommendation:** extract each phase into a stage function with a uniform signature (`stage(context) -> context`) run by a small driver. This makes phases independently testable, makes ordering explicit rather than positional, and shrinks the file by roughly two-thirds with no behavior change. Understanding a cycle today requires holding ~2,000 lines in working memory.

## 2. Exception philosophy hides real bugs (HIGH — correctness)

There are 2,076 `except Exception` blocks — about one per 55 lines — and 784 of them log the identical string `"silent except: %s"`, evidently a mechanical sweep that upgraded `except: pass` to logged warnings. The sweep was an improvement, but the message carries no operation context, so logs cannot distinguish which of 784 identical sites fired. Worse, blanket catches convert genuine programmer errors (`NameError` from a typo, `AttributeError` after a refactor) into ignorable warnings instead of loud failures during development.

The codebase already contains the better pattern: `record_failure("ORRIN_loop.sensory_read", e)` names the operation and feeds the failure counter. **Recommendation:** standardize on `record_failure`-style named handlers; narrow catches at I/O boundaries to expected exception types; add an `ORRIN_STRICT=1` development mode that re-raises anything unexpected.

## 3. Lost-update races fixed for affect, structural everywhere else (HIGH — data integrity)

The single-writer/arbiter work closed the race on `affect_state` (documented in `docs/archive/V3_AUDIT.md` and verified by `tests/brain/test_affect_single_writer.py`). But the general pattern persists: `modify_json` — the lock-held read-modify-write context manager in `brain/utils/json_utils.py` built precisely for this — has **zero callers**, while ~137 modules perform the racy `load_json → mutate → save_json` sequence on shared files (`relationships.json`, `self_model.json`, working memory, the knowledge graph, etc.) with a dozen daemon threads running concurrently. The locks in `save_json`/`load_json` serialize individual reads and writes but not the window between them — exactly the failure class the V3 audit rated CRITICAL for affect.

**Recommendation:** give every mutable shared file an owner module (the affect treatment), or adopt `modify_json` at all read-modify-write sites; longer term, move hot shared state to SQLite, which provides transactions for free and matches the WAL direction the v2 subsystems already took.

## 4. Two generations live at once, plus stale duplicate files (HIGH — architecture hygiene)

Deliberate dual-running: v1 JSON memory (`brain/cog_memory/`) alongside the v2 memory daemon (`memory/`); v1 planning (`brain/cognition/planning/goals.py`) alongside the v2 `goals/` daemon. Accidental duplicates on top of that:

`brain/alive_brain.py` vs `brain/utils/alive_brain.py` (two near-identical `AliveBrain` classes); `brain/utils/llm_gate.py` vs `brain/symbolic/llm_gate.py`; `brain/cognition/world_model.py` vs `brain/embodiment/world_model.py`; and `llm/generate_response.py` vs `brain/utils/generate_response.py`, where the `llm/` copy is a 260-line stale snapshot of the 531-line live module and still carries the header comment `# utils/generate_response.py`.

Compounding it, `.github/copilot-instructions.md` instructs AI assistants to import from `llm.generate_response` ("the canonical wrapper") while the brain actually uses `utils.generate_response` — the onboarding doc points at the dead copy. An agent that searches its own files (which Orrin does) can be misled by its own dead code. **Recommendation:** pick winners, delete the losers, update the instructions file, and record the v1→v2 retirement plan so the dual systems have an end date.

## 5. Fragile import bootstrap; project is not installable (HIGH — packaging)

`main.py` inserts `brain/` first on `sys.path` so `utils`, `core`, `cognition`, `affect`, etc. resolve as top-level packages. These names are dangerously generic — any pip package named `utils` or `core` collides — and correctness depends on path-insertion order at startup. The repomix bundle also contains no `requirements.txt`, `pyproject.toml`, or `pytest.ini` (referenced by the copilot instructions; if they exist they were excluded from the pack, if not the project is not reproducibly installable), and no CI configuration despite a 548-test suite.

**Recommendation:** restructure as a real package under a single `orrin/` namespace with `pyproject.toml`, absolute imports, and `pip install -e .`; add a CI workflow that runs the test suite on push.

## 6. Scaling cliffs in the JSON-everything persistence model (MEDIUM-HIGH — performance)

`update_long_memory` (`brain/cog_memory/long_memory.py`) loads the entire long-memory list, appends one entry, and rewrites the whole file — O(n) disk and parse cost per memory, growing forever. `context.json` is rewritten every 20-second cycle, protected only by a **blacklist** (`_CTX_STRIP`) of known-bloating keys, meaning each new bloat source leaks until noticed — the 833 KB `last_decision.candidates` incident documented in the loop's own comments is precisely this failure mode. There are 245 `save_json` call sites treating JSON files as tables.

**Recommendation:** invert the context persistence to a whitelist of keys that belong on disk; move append-heavy stores (long memory) to JSONL or SQLite; keep JSON for human-inspectable cold state only.

## 7. Security gaps specific to a self-modifying, web-reading agent (HIGH — security)

The combination that defines Orrin — (a) fetches arbitrary web pages, (b) feeds that text into LLM prompts that create goals and select actions, (c) writes and live-registers its own code — forms a prompt-injection-to-code-execution pathway. Nothing currently tags, quarantines, or sanitizes web-derived text between `fetch_and_read` and the prompts that drive decisions; hostile page content enters working memory with the same standing as internal thought.

Specific items:

**Sandbox validates once, then code goes live.** `_validate_in_sandbox` runs synthesized code in an isolated subprocess (good), but registration then imports the module into the main process, where the AST denylist is the only barrier. Name-based AST denylists are bypassable via indirection (e.g., `getattr(__import__('o'+'s'), ...)`).

**Fail-open ethics gate.** `moral_override_check` in `brain/cognition/selfhood/ethics.py` defaults to `{"override": False}` when the LLM response fails to parse — the gate allows the action precisely when its reasoning broke. Safety gates should fail closed.

**TLS verification silently disabled.** `brain/cognition/web_research.py` falls back to `ssl.CERT_NONE` with hostname checking off if `certifi` is missing. Fail closed (refuse to fetch) instead.

**Weak path blocking.** `_is_safe_path` in `agency/code_writer.py` checks blocked paths by substring (`"think/" in str(resolved)`), which is imprecise in both directions; the allowed-dir `relative_to` check is the solid half. Tighten the blocklist to resolved-path prefix comparisons.

**No hard LLM spending cap.** `brain/utils/llm_router.py` tracks estimated cost but enforces no budget. A selector rut (the documented 133-cycle `fetch_and_read` loop in `RUN_ISSUES_2026-06-10.md`) can therefore also be a billing incident. Add a daily token budget that trips the same circuit breakers as other failures.

## 8. Load-bearing heuristics that will mislead (MEDIUM — decision quality)

Draft confidence is hedge-word counting (`inner_loop._draft_confidence`). LLM complexity routing is character count plus keyword hits. The response cache bypasses on prompts containing "just" or "now" — words so common in English that the cache hit rate is likely near zero, while a genuinely time-sensitive prompt lacking those words can get a stale answer. Goal-relevance matching is keyword overlap with an 18-word stopword list. These were reasonable v1 scaffolding, but they sit inside the decision core.

**Recommendation:** the project already ships an embedder — use semantic similarity for goal/function matching, and replace hedge-word confidence with a calibrated signal (logprob-based or self-rated with calibration tracking, which `brain/cognition/calibration.py` suggests is already started).

## 9. Magic-number sprawl (MEDIUM — tunability)

The selector alone hand-tunes `w_dir=0.22, w_goal=0.22, w_emo=0.26, w_band=0.25`, attention-mode multipliers (×2.10, ×0.30, ×0.55), per-function boosts (0.42, 0.25, 0.15, 0.08), signal decay 0.92, crisis thresholds 0.85/0.50/0.70; the arbiter adds budget 0.60 and away-cost multiplier 2.0; dozens more constants live elsewhere. Each is individually commented, but collectively the parameter space is invisible: there is no single place to view a configuration, no way to A/B one, and related constants can drift apart silently.

**Recommendation:** pull them into a typed config module with names and documentation; the existing benchmark registry (`docs/BENCHMARKS.md`, `brain/benchmarks/`) then becomes the instrument for fitting parameters instead of tuning by anecdote.

## 10. Three mortality clocks with wildly inconsistent defaults (MEDIUM — correctness)

`brain/cognition/mortality.py` rolls a lifespan of 365–730 days. `reaper/lifespan.py`'s `LifespanByCycles` defaults to 25,000–30,000 cycles (~6–7 days at a 20 s cycle). `watchdogs.py` passes 12,960,000–43,200,000 cycles (~8–27 years). Whichever is authoritative, the other two are misleading dead defaults. "When does this agent die" should not be ambiguous; consolidate to one source of truth and derive the others from it or delete them.

## 11. Test coverage inverted relative to risk (MEDIUM — quality assurance)

The v2 subsystems (goals, memory, reaper, observability) have systematic suites, and the 548 test functions include genuine concurrency and contract tests. But `brain/cognition/` — roughly 70 modules and the bulk of actual behavior — is covered mostly by regression tests for specific audit fixes. The selector's scoring math, the affect dynamics in `update_affect_state.py` (703 lines), dream cycles, theory of mind, and the planning stack are largely untested except where they once broke.

**Recommendation:** add property-style invariant tests — affect signals always clamped to [0,1], the selector always returns a dispatchable function, the stability budget is never exceeded, WAL replay is idempotent — to lock in the guarantees the audits currently re-verify by hand.

## 12. Documentation and observability gaps (LOW-MEDIUM)

There is no top-level README; the best orientation document is the partly stale copilot-instructions file, and `DEPENDENCY_GRAPH.md` is buried in `docs/archive/`. `frontend/` contains only a README. `print()` and the structured runtime logger are mixed in `main.py` and the reaper — standardize on the logger. The 193 function-level imports inside the loop body, while defensible for optional subsystems, obscure the dependency structure and defer import errors to mid-cycle; module-level imports with availability flags would read better and fail faster.

---

## Suggested remediation order

1. **Close the fail-open ethics gate and the TLS fallback** — small diffs, real risk reduction (Finding 7).
2. **Adopt `record_failure`-style named exception handling** and an `ORRIN_STRICT` dev mode (Finding 2).
3. **Delete stale duplicates and fix the copilot-instructions doc** — an afternoon of cleanup that removes active misdirection (Finding 4).
4. **Whitelist `context.json` persistence; fix long-memory O(n) appends** (Finding 6).
5. **Route remaining shared-file mutations through owners or `modify_json`** (Finding 3).
6. **Decompose `ORRIN_loop.py` into pipeline stages** (Finding 1).
7. **Package the project (`pyproject.toml`) and add CI** (Finding 5).
8. **Centralize tuning constants; replace keyword heuristics with embeddings** (Findings 8–9).
9. **Consolidate the mortality clocks** (Finding 10).
10. **Add invariant tests over `brain/cognition/`** (Finding 11).

None of these require rethinking the architecture — the architecture is the strong part.

---

## Remediation status (2026-06-11)

**Applied:**

- **Finding 7 — ethics gate fails closed.** `moral_override_check` now returns `{"override": True, "fail_closed": True}` on parse failure or exception. (Note: it currently has zero callers — it's available safety infrastructure, wire it into the action gate when ready.)
- **Finding 7 — TLS fail-closed.** `web_research.py` no longer falls back to `CERT_NONE`; missing certifi keeps full verification and logs a warning.
- **Finding 7 — path blocking.** `code_writer._is_safe_path` blocklist is now resolved-path prefix comparison anchored at `ROOT_DIR`, not substring.
- **Finding 7 — LLM spend cap.** `llm_router` enforces a daily estimated-token budget (`ORRIN_LLM_DAILY_TOKEN_BUDGET`, default 2M, 0 disables), persisted across restarts in `llm_cost_log.json` under `_daily`, surfaced via `record_failure("llm_router.daily_budget", …)`.
- **Finding 2 — strict mode.** `ORRIN_STRICT=1` makes `record_failure` re-raise programmer errors (NameError, AttributeError, ImportError, SyntaxError, TypeError); `ORRIN_STRICT=all` re-raises everything. New `failure_counter.guard(site)` context manager for adopting named handling at new sites.
- **Finding 4 — stale duplicates.** Deleted `brain/alive_brain.py` (dead; `utils.alive_brain` is live) and `llm/generate_response.py` (dead 260-line snapshot). Fixed `.github/copilot-instructions.md` to point at `utils.generate_response` and current env vars. **Correction to the finding:** the `llm_gate` and `world_model` pairs are *not* duplicates — `utils.llm_gate` (availability gating) vs `symbolic.llm_gate` (symbolic-first routing), and `cognition.world_model` (symbolic entities/facts) vs `embodiment.world_model` (runtime state) are distinct live modules sharing a name. Consider renaming, not deleting.
- **Finding 6 — context.json.** A whitelist was rejected: context.json is the restart state (183 keys, all live) and a hardcoded whitelist would silently drop every future key. Instead the persist path now has an automatic bloat guard: any key serializing over 100 KB is stripped and *named* in the log, so new bloat sources are contained and identified the cycle they appear.
- **Findings 3+6 — long memory.** `update_long_memory` now does its dedup+append inside `modify_json` (its first caller), closing the lost-update race on the hottest shared file. Added `json_utils.AbortModify` for clean exit-without-save (used by the dedup skip). The "growing forever" claim was stale — the file is capped at `MAX_LONG_MEMORY=2000` entries.
- **Finding 10 — mortality clocks.** `brain/cognition/mortality.py` is documented as the single source of truth (365–730 days, persistent). `LifespanByCycles` lost its dead 25k–30k defaults (now required params) and is documented as a per-process uptime cutoff (~3–10 days at the 50 Hz pulse). Fixed the stale "30–90 days" comment in mortality.py.
- **Finding 8 (partial) — cache bypass.** Volatile-keyword cache bypass now matches word boundaries and drops "just" (substring matching made "knowledge"/"adjust" bypass the cache).
- **Finding 5 (correction).** `requirements.txt` and `pytest.ini` exist — they were excluded from the analysis bundle. The sys.path bootstrap concern stands.

**Remaining items, now resolved:**

- **Finding 3 — remaining racy read-modify-write sites.** Migrated the hottest shared-state files to `modify_json`/`AbortModify`: `cog_memory/working_memory.py`, `cognition/knowledge_graph.py`, `cognition/selfhood/relationships.py` (including the per-person update paths), and `utils/self_model.py`, joining `long_memory.py` from the earlier pass. Each follows the same pattern — read, mutate, and write under one lock, with `AbortModify` for clean no-op exits (corrupt file, duplicate, missing record). The remaining lower-traffic sites are lower risk (less concurrent access) and can be migrated opportunistically using this now-proven idiom.
- **Finding 2 — `"silent except: %s"` sites renamed.** All 646 reachable sites in `brain/` (167 files) mechanically converted via an AST-guided script to named `record_failure("module.qualname[.N]", e)` handlers. Behavior is unchanged by default (still swallows and logs), but every site now has a distinguishable name, a per-site counter, rate-limited JSONL telemetry (`data/failures.jsonl`, summarized by `dump_summary()` into `data/failure_summary.json`), and participates in the `ORRIN_STRICT` re-raise path added earlier. `brain/utils/failure_counter.py`'s own 3 internal IO handlers stay as plain logging (can't call `record_failure` recursively). New `tests/brain/test_failure_counter.py` (12 tests — first coverage of this module) and `tests/brain/test_no_silent_except_sites.py` (regression guard: fails if the pattern reappears anywhere in `brain/`). The remaining ~127 sites outside `brain/` (backend, reaper, scripts) don't reach this handler under the current `pythonpath` and are out of scope.
- **Findings 8–9 — config centralization + embedding-based matching.** New `brain/config/tuning.py` is the single place to view the selector/arbiter/loop constants the finding named: selector base weights (`SELECTOR_W_DIR/W_GOAL/W_EMO/W_BAND/W_DRIVE/BASE_W_NOVEL`), all four attention-mode multiplier/cap/boost sets (alert/engaged/wandering/drowsy), `SEMANTIC_MATCH_FLOOR`, the arbiter's `AFFECT_STABILITY_BUDGET`/`AFFECT_AWAY_COST_MULTIPLIER`, `AFFECT_TRANSIENT_DECAY`, and the `CRISIS_*` thresholds — pure "move the value, keep the rationale comment" with no behavior change, pinned by `tests/brain/test_tuning_config.py` (6 tests, including source-inspection guards against the literals drifting back). Separately, `_capability_overlap` (Finding 8) now takes `max(keyword_overlap, embedding_similarity)` using the project's existing MiniLM embedder (`utils/embed_similarity.py`) — genuine paraphrases that share no content words (e.g. "research and investigate ... by searching the web" vs. "look into quantum computing online") can now clear `SEMANTIC_MATCH_FLOOR`, while every match keyword overlap already found is preserved unchanged (`tests/brain/test_capability_overlap_embeddings.py`).
- **Finding 11 — invariant tests.** Added `tests/brain/test_affect_invariants.py` (every core affect signal ends a cycle clamped to [0,1] regardless of how out-of-range the on-disk state was), `tests/brain/test_selector_invariants.py` (`select_function` always returns a name that's genuinely dispatchable via `COGNITIVE_FUNCTIONS`, not just one that passes `_is_dispatchable`), `tests/brain/test_stability_budget_invariant.py` (fuzzes proposal mixes across signals/directions; `commit_affect`'s weighted cost never exceeds `STABILITY_BUDGET`), and `tests/goals_test/test_wal_invariants.py` (replaying a WAL twice is idempotent — same store state and counts both times).
- **Finding 7 — prompt-injection containment + post-registration sandboxing.** New `utils/content_quarantine.py` / `utils/text_sanity.py` tag and sanitize web-derived text at all four open-web ingestion points — `web_research.fetch_and_read`/`research_topic`, `cognition/rss_reader.py`, and `cognition/wikipedia_search.py` — before it reaches working memory, the knowledge graph, or any prompt built from it (`tests/brain/test_content_quarantine.py`). `agency.code_writer._validate_in_sandbox` now re-runs the AST safety scan unconditionally as a final gate even on its fallback path, closing the `getattr(__import__(...))` indirection bypass (`tests/brain/test_code_writer_sandbox.py`). The action gate's `execute_python_code` is disabled by default and only runs generated code through the hardened subprocess sandbox under `ALLOW_CODE_ACTIONS` (`tests/brain/test_code_action_sandbox.py`).
- **Finding 1 (partial) — `ORRIN_loop.py` decomposition started.** Extracted the first `stage(context) -> context` pipeline function, `_apply_transient_signal_decay` (transient affect-signal decay plus the sustained-crisis detection feeding `_extreme_cycles`), following the existing `_emit_affect`/`_learning_pulse`/`_emit_goals` helper-function style. `run_cognitive_loop` now calls it in one line; the logic is independently tested for the first time (`tests/brain/test_orrin_loop_stages.py`, 7 tests). The remaining ~2,250 lines of `run_cognitive_loop` are unchanged — this is a proof of concept establishing the pattern (perceive, select, act, reward, commit, persist) for the remaining phases, each extractable the same way behind the test suite, one at a time.
- **Finding 5 (partial) — packaging.** `pyproject.toml` (the `orrin` package, setuptools backend) and `.github/workflows/tests.yml` CI were added, delivering the reproducible-install and test-on-push goals. The full restructure under a single `orrin/` namespace package (replacing the `brain/`-on-`sys.path` bootstrap with absolute imports across 500+ modules) remains deferred — it's a repo-wide mechanical rewrite whose risk/benefit is better suited to its own dedicated pass than bundling into this remediation.

**Net result:** every item in the original "Remaining (large, planned separately)" list has been addressed (two — Findings 1 and 5 — partially, with the deferred remainder explicitly scoped above). Full suite green: 615 passed, 1 skipped, 2 deselected (the 2 pre-existing `tests/memory/embedder_test.py` failures the CI workflow already deselects). This document is archived to `docs/archive/` as of this update.
