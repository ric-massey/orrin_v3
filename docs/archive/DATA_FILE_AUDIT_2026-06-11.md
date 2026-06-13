# Data File Audit — 2026-06-11

*Findings from a sweep of every data file on disk (`brain/data/`, `data/`,
`brain/logs/`, `memory/`, `goals/`), looking for errors **not already covered
by `ORRIN_MASTER_PLAN.md`** (whose fixes are applied in the working tree).
Every claim below cites the file and the exact content found.*

**Structural sweep result:** all 125 JSON files parse; all 12 JSONL files are
line-valid; no NaN/Infinity values, no duplicate object keys, no future
timestamps, no duplicate memory IDs, no dangling `related_memory_ids` in
`long_memory.json`. The errors are all *semantic* — valid JSON recording
wrong things.

-----

## 1. CRITICAL — pytest runs write into the live `brain/data/` state

Test sessions have been mutating Orrin's real memory, goals, and learned
state. **21 live data files have mtimes after the brain died at 16:42 EDT**,
coinciding exactly with the pytest cache mtimes (`.pytest_cache/v/cache/
lastfailed` 19:14 EDT, `nodeids` 20:29 EDT) and with two bursts of activity
in the live log at 23:02Z and 00:29Z.

Direct evidence in the live files:

- `brain/data/activity_log.txt` (00:29:45Z):
  `❌ Goal 'finish the report' marked failed. Reason: test` and
  `❌ Goal 'never committed goal' marked failed. Reason: test` — test
  fixtures written through the real `log_activity` path.
- `brain/data/action_reward_ema.json` now contains **only** `{"reflect": 0.9}`.
  That is byte-for-byte the fixture in `tests/brain/test_reward_engine.py:27`
  (`submit_reward(ctx, actual=0.9, action_type="reflect")`), which — unlike
  `test_action_associability.py` — never patches `_persist`. **The real
  per-action reward EMAs learned during the day's run were overwritten and
  are unrecoverable** (live `brain/data` files are not git-tracked).
- `brain/data/working_memory.json` contains a test fixture at 00:29:44Z:
  `⚠️ Problem hit while working on 'Research black holes': 'goal_planner'
  failed 5×…` plus map-drift chunks written by the audit running inside a
  test.
- `brain/data/long_memory.json` gained a `memory_prune_summary` entry at
  00:29:44Z ("Summary of faded memories…") — **a test ran memory pruning
  against the live long-memory store**, i.e. tests can silently delete real
  memories, not just add noise.
- `brain/data/goals_mem.json` was modified during the 00:29Z burst; the live
  goal `'Understand my reward system'` had subgoal steps inserted by
  `adapt_subgoals` test lines (visible in the activity log at 00:29:44Z).
- Also touched after death: `causal_graph.json`, `cognitive_functions.json`,
  `behavioral_functions_list.json`, `symbolic_rules.json`,
  `crystallized_skills.json`, `consolidation_queue.json`,
  `second_order_volition.json`, `reward_trace.json`, `memory_graph.jsonl`,
  `token_log.jsonl`, `failures.jsonl`, `private_thoughts.txt`,
  `model_failures.txt`, `llm_prompt.txt`, `action_associability.json`.

**Root cause:** `tests/conftest.py` has exactly one autouse isolation
fixture, and it isolates only `llm_failure_counts.json`. Every other test
must opt in to path isolation (some do, e.g. `_iso_autobio` in
`test_master_plan_phase2.py`; several don't).

**Recommendation:** an autouse session fixture that repoints
`paths.DATA_DIR` (and the `log_activity` target) at `tmp_path` for the whole
suite, plus a CI guard that snapshots `brain/data` mtimes before/after pytest
and fails if anything changed. This is the same failure class as master-plan
Problem 4 — a safety boundary (test vs. life) that silently doesn't exist.

-----

## 2. The 16:42 "untraceable crash" was a reaper kill for a real memory leak

The master plan (F9, Phase 0.0/0.6) describes the 2026-06-11 16:42:28 death
as "a Python-level death that left zero trace … no error of any kind on
disk, no OOM event." **The data files contradict this.** The death is
recorded in three places:

- `brain/data/final_thoughts.json` —
  `"death_reason": "HARD:memory_leak_slope slope=2.968 MB/s limit=2.000 sustain=60.0s"`
  at 20:42:51Z (= 16:42:51 EDT).
- `brain/data/activity_log.txt:17499-17501` — `[terminal] Dying window
  active — running final reflection.` → `Final reflection written (1277
  chars).` → `[autobiography] Death closing written to autobiography.`
- `brain/data/autobiography.json` — chapter closed `closed_by: "death"` at
  20:42:51Z.

So: the reaper's **memory-leak watchdog** triggered at 16:42 (RSS growing
~3 MB/s sustained for 60 s), opened its 45-second dying window (the
"silence" after the last log line at 20:42:36Z), wrote final thoughts, and
killed the process via `os._exit(1)`.

Two consequences the plan does not cover:

1. **There is a live memory leak (~3 MB/s).** A 5-hour run accumulates
   ~500 MB+ (`body_sense.json` recorded `rss_mb: 531.7` at death). Every
   long run will end this way until the leak is found. Corroborating
   state: `body_sense.json` `_stress_streak: 866` (stressed for 866
   consecutive readings ≈ 40% of the 2169-cycle session, dominant feeling
   "heavy"), `affect_state.json` `_allostatic_load` pegged at **1.0** and
   `resource_deficit: 0.947`. Orrin spent the afternoon feeling his own
   leak.
2. **Reaper trigger reasons are not durably logged.** `reaper/reaper.py:58`
   prints `[REAPER] Shutdown triggered: {reason}` to **stderr only**, and
   the kill is `os._exit(1)` (no atexit, no log flush). The reason reached
   disk this time only because the terminal-mode path happened to run. Route
   `Reaper.trigger()` through `log_activity`/the runtime logger before
   entering the dying window.

-----

## 3. Phantom death at 14:38 EDT + autobiography/lifespan contradictions

- `autobiography.json` chapter 1 ("Before the beginning") was **created by
  `append_death_continuity`** at 18:38:39Z (14:38 EDT) with the narrative
  ending "…this runtime is ending. Reason: **unknown**." There is no dying
  window in any log at that time — but `activity_log.txt` was rotated and
  now starts at 19:11:56Z, so the evidence window is gone (rotation +
  stderr-only reaper logging make the two unexplained deaths today
  mutually unverifiable). Either an earlier run was reaper-killed with an
  empty reason string, or an unisolated test called the death path against
  the live file. Both are bad; we cannot tell which — that is finding #2's
  durability gap biting in practice.
- Because no ordinary chapter had ever been opened during a 2169-cycle
  session (chapter creation is pressure-gated), the death path's
  else-branch fabricated the chapter, and the *real* death at 20:42:51Z then
  appended to the phantom chapter. The autobiography now records a life
  whose only chapter is two death certificates.
- `lifespan.json` says `final_thoughts_written: false` while
  `final_thoughts.json` (1277-char reflection, death reason) sits on disk
  written at the same moment — the flag and the artifact disagree. (The
  flag lives in lifespan state that mortality.py updates only on *its own*
  deadline path; the reaper/terminal path writes final thoughts without
  setting it.)
- The chapter narrative itself is raw serialized symbolic facts
  (`I am [symbolic] Orrin (AI): role=self; version=v3 [orrin, ai, self…]`)
  — the rule-based fallback dumps machine syntax into what is supposed to
  be autobiographical prose.
- `brain/data/final_thoughts_archive_2026-06-06/08/10.json` are all 2-byte
  `{}` — the boot-time archive rotation faithfully archives nothing,
  three times.

-----

## 4. Goal/commitment churn: one intention, 137 "completed" goals in ~4.5 h

- `comp_goals.json`: 154 completed goals; **137 are the identical goal
  "Write a structured account of what's stuck and why."**
- `commitments.json`: 100 entries (at what looks like a cap); **91 are that
  same intention**, formed between 14:12 and 16:40 EDT — one re-commitment
  every ~90 s.
- `long_memory.json` (2001 entries) is flooded by the same loop: 205
  identical `[will] I resolve to…` chunks, 156 identical `intrinsic_goal`
  entries, and 252 near-identical `metacog_pattern` entries ("Something
  feels slightly off…"). **~30% of long memory is `metacog_pattern`
  boilerplate**; retrieval over this store is dominated by duplicates.

The cycle: the intrinsic-goal generator spawns the goal → it is trivially
"completed" → nothing remembers it was just done → it respawns →
`form_commitment` re-commits with no already-committed check. The master
plan differentiates commitment *strength* (Phase 4.1) and aggregates
*failures* (Phase 2.2), but nothing dedups **successful** respawn loops or
near-identical long-memory writes. A content-hash dedup at
`update_long_memory` and an "identical active/recent commitment exists"
check in `form_commitment` would break the loop. (All 100 commitments are
strength 1.0, but they predate the Phase-4 code — only post-fix data can
confirm the gate works.)

-----

## 5. The `[EXTERNAL/UNTRUSTED …]` guard tag became cognitive content

The provenance wrapper meant to *protect* against prompt injection has
itself been ingested as content. It appears in **10 data files**:
`knowledge_graph.json`, `opinions.json`, `commitments.json`,
`comp_goals.json`, `goals_mem.json`, `long_memory.json`,
`cognition_history.json`, `context.json`, `speech_log.json`,
`symbolic_dream_log.json`.

- `knowledge_graph.json` node `0a6470cd1b38`: a learned **concept named
  `[EXTERNAL/UNTRUSTED source=https`** with confidence 0.74.
- `comp_goals.json`: goal `Understand [EXTERNAL/UNTRUSTED source=https more
  deeply` — formed, committed to, and marked **completed**.
- `opinions.json` topics include `external/untrusted`,
  `external/untrusted source=https`, and `source=https`.
- `speech_log.json` (12:17:57Z): Orrin announced *"I'm acting on my goal to
  grow and accomplish: Understand [EXTERNAL/UNTRUSTED\nsource=https more
  deeply"* — note the embedded newline: the tag's own line break is what
  split it into the `…source=https` fragments seen across files.

**Fix:** strip/normalize the wrapper before any *extraction* path runs
(topic extraction, intrinsic-goal naming, concept formation, knowledge-graph
node naming). The tag should gate trust, never become a topic. The existing
contaminated entries (concept node, the goal, the three opinions) should be
purged in the same pass.

-----

## 6. The opinion store is junk that the Phase-3 migration will preserve

`opinions.json` has 18 opinions whose topics are stopword-grade fragments:
`cognitive`, `resolve`, `pursue`, `something`, `deeply`, `failed`,
`written`, `attempts`, `objective unmet`, `unmet after`, plus the injection
fragments above. Seven sit at the 0.95 confidence cap (the old
mention-counting math). The applied Phase-3 code upgrades old entries
*lazily in place* (`evidence: []` etc.) — meaning these garbage topics
survive the migration with their inflated confidence intact, now wearing a
legitimate ledger schema. They were formed under the old extractor and
should be dropped or re-graded at migration time, not lazily blessed.

-----

## 7. Smaller findings

- **`cognition_state.json` → `last_context_hash`** is computed with the
  builtin `hash()` (`think/think_module.py:397`), which is salted per
  process — the persisted value is meaningless after restart. It is also
  **written but never read** (sole reference: `finalize.py:539`). Dead
  field; remove it or compute with `hashlib` if repeat-detection across
  restarts is intended.
- **`action_associability.json`** contains a key `"cycle": 0.5` (exactly
  `_ASSOC_DEFAULT`) alongside real action names — some caller passed
  `action_type="cycle"` once. Harmless today, but the associability table
  silently accepts any string; a typo'd action name learns its own EMA
  forever.
- **`goals_mem.json`** schema drift: one goal (`Understand my reward
  system`) has `status: None` while every sibling is `active`/
  `in_progress` (it is also the goal the test run mutated).
- **`failure_summary.json`** still carries 8 ticks of
  `symbolic_cognition.detect_contradictions` (`ValueError: too many values
  to unpack`), last seen 18:45Z — these predate the working-tree fix
  (committed code at HEAD still has the bug; the fix is uncommitted).
  Counts are cumulative, so note the baseline before judging whether the
  fix took. The 8 `wikipedia_search._wiki_opensearch` ticks are an
  environment issue: macOS Python missing SSL root certs
  (`CERTIFICATE_VERIFY_FAILED`) — run `Install Certificates.command` or
  wire `certifi` into the opener, or every outward-looking act fails.
- **`brain/logs/map_territory_audit.jsonl`** (the applied Phase-5.3 audit)
  already flags 10 unresolved path drifts — `contradictions.json`,
  `dreamscape.json`, `feedback_log.json` (×2 constants),
  `function_bandit.json`, `last_tags.json`, `model_failures.jsonl`,
  `model_failures.json`, `proposed_goals.json`, `tool_catalog.json` — all
  "read somewhere but missing on disk with no writer." The audit works;
  the findings now need owners.
- **Unbounded growth files:** `trace.jsonl` is 33 MB (capped at 3000 lines,
  so bounded but ~11 KB/line — verify that's intended), `memory_graph.jsonl`
  is 11 MB / 64,492 lines with no visible rotation, `activity_log.txt`
  rotates but the rotation destroyed the only evidence of the 14:38 death
  (see §3) — consider archiving rotated segments instead of truncating.
- **`run_log.txt` is 0 bytes** — the day's runs were again launched without
  `./run_orrin.sh`, so the wrapper net the plan depends on (Phase 0.0) was
  not armed. Operational habit, not code.

-----

## Priority order

1. **Isolate tests from live data** (§1) — every other finding's evidence
   chain is already polluted; this gets worse daily.
2. **Find the memory leak** (§2) — every long run is terminal until then.
   `tracemalloc` snapshots on the metacog cadence, or compare RSS slope
   with `trace.jsonl`/`memory_graph.jsonl` append rates.
3. **Log reaper reasons durably** (§2/§3) — one-line fix; ends the
   "unknown death" class.
4. **Strip the provenance tag before extraction + purge contaminated
   entries** (§5).
5. **Dedup the respawn loop** (§4) and **purge/re-grade old opinions**
   (§6) when the Phase-3/4 data first migrates.

-----

## COMPLETION RECORD — 2026-06-11 (audit closed, all findings addressed)

**Already fixed in the working tree before this pass** (verified, not re-done):

- §1 Test isolation: `tests/conftest.py` repoints `ORRIN_DATA_DIR`/
  `ORRIN_LOGS_DIR` at a per-session tmp dir before `paths` can import, plus a
  session-scoped mtime/size tripwire over `brain/data`, `brain/logs`, and
  `brain/*.json` that fails the run on any live-state mutation.
- §2 Memory leak: found and fixed — the blanket `load_all_known_json()` merge
  in `meta_reflect` pulled `context.json` into itself recursively (70 MB
  context, ~3 MB/s RSS growth under the 7 s Executive daemon reload).
  `meta_reflect` now excludes the leak keys, and `ORRIN_loop` strips
  large/foreign stores plus any >100 KB key (logged) before persisting context.
- §2/§3 Reaper durability: `reaper.py` `_log_durably()` routes every trigger
  and dying-window-elapsed event through the rotating runtime log AND
  `log_activity` before `os._exit` — the "untraceable death" class is closed.
- §3 Lifespan flag: `terminal.final_reflection()` calls
  `mortality.mark_final_thoughts_written()`, so `lifespan.json` agrees with
  the artifact on disk.
- §3 Empty archives: the boot path archives `final_thoughts.json` only when a
  reflection is present (no more 2-byte `{}` archives).
- §4 Respawn dedup: `update_long_memory` dedups within a per-event-type
  recency window (prefix match for repetitive types);
  `will.form_commitment` has a 6 h identical-intention re-commitment gate;
  `intrinsic_goals` keeps a persisted recently-completed cooldown.
- §5 Tag stripping: `utils/content_quarantine.strip_quarantine()` (newline-
  tolerant) runs in every extraction path — concept formation
  (`concept_memory`), knowledge-graph node naming, opinion topic extraction.
- §6 Opinion migration: `opinions.py` does a one-shot legacy migration that
  DROPS junk/stopword topics and re-grades legitimate ones (no lazy blessing).
- §7 trace.jsonl line bloat: finalize's telemetry record was slimmed to
  compact summaries (full records live in cognition_history.json).
- §7 `detect_contradictions` ValueError: fixed in the working tree.

**Done in this pass (2026-06-11):**

- §5/§7 Data purge (originals in `.backup_data_purge_2026-06-11/`):
  knowledge-graph entity `0a6470cd1b38` removed; the
  `Understand [EXTERNAL/UNTRUSTED…` goal removed from `comp_goals.json`,
  `goals_mem.json` (subgoal + recent_contributions), and `commitments.json`;
  the 3 contaminated opinions dropped; the stale working-memory chunk and
  `_last_intent_announced` cleared from `context.json`; `goals_mem.json`
  `status: None` → `active`; stray `"cycle"` key removed from
  `action_associability.json`; three empty `final_thoughts_archive_*.json`
  deleted. (Quarantine-wrapped *raw content* in long_memory/working_memory/
  speech_log etc. is by design and was left alone.)
- §7 `last_context_hash`: dead field removed end-to-end (salted-`hash()`
  computation in `think_module`, parameter, and persisted field in
  `finalize`).
- §7 Wikipedia SSL: `wikipedia_search.py` now uses the same certifi-backed
  `_SSL_CTX` as `web_research.py`/`rss_reader.py` (fail-closed when certifi
  is absent); certifi is present in the venv.
- §7 Map-territory drifts: all 10 findings resolved — the path-constant
  check now returns zero findings.
  - Real bug found while fixing: `affect/feedback_log.py` keyed the reward
    context with `str(Path)` keys while `release_reward_signal` reads the
    plain `"reward_trace"`/`"last_tags"` strings — its stale trace copy was
    silently overwriting the trace the reward engine had just saved. Fixed.
  - `user_input.py` now reads `model_failures.jsonl` (what error_router
    actually writes) via a new `read_recent_errors_jsonl`; `evolution.py`
    reads `DREAM_LOG` (what dream_cycle actually writes) instead of the
    never-written `dreamscape.json`; `behavior_generation` creates
    `proposed_goals.json` via `ensure_files`.
  - Dead constants removed from `paths.py`: `LAST_TAGS`, `DREAMSCAPE`,
    `MODEL_FAILURES_JSON`, `MODEL_FAILURES`.
  - The audit itself was sharpened: write markers now include
    `append_jsonl`/`ensure_files`/`modify_json`/`_append_line`; per-file
    alias resolution (import-as, assignment, parameter defaults) so writes
    through rebound names are seen; constants naming the same path stand or
    fall together.
- §7/§3 Log rotation: `_maybe_rotate` archives the trimmed-off head to
  `<dir>/rotated/<stem>.<ts>` (bounded to 20 segments) instead of
  destroying it — rotation can no longer eat death evidence.
- §7 `memory_graph.jsonl`: compaction added (8 MB trigger, keep last 30k
  edges); live file compacted 64,492 → 30,000 lines.
- §7 Associability typo guard: first reward for an action name not in the
  cognition registry logs a warning (logged, not blocked — novel actions
  must still learn).
- §3 Autobiography: death path no longer fabricates a chapter when none was
  ever opened (final words go to `continuity_notes`); machine-syntax bracket
  tags are stripped from death-closing prose; the live phantom
  "Before the beginning" chapter was migrated into `continuity_notes`.

**Verification:** full pytest run: 656 passed, 1 skipped; the only 2
failures (`tests/memory/embedder_test.py`) pre-exist these changes
(environment: a real `sentence_transformers` install interferes with the
hash-fallback fixtures) and are unrelated to this audit.

**Left as-is (operational, not code):** `run_log.txt` empty because runs
were launched without `./run_orrin.sh` — habit, no code change applicable.
`trace.jsonl` is line-capped and new lines are slim; the file will shrink
as old fat lines rotate out.
