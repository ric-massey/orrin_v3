# Fix-round record — 2026-07-02 (implements `2026-07-02_why_every_problem.md`)

Every fix from the root-cause pass, implemented in one round. Verification:
`make lint py-typecheck test` green — **1,335 passed, 1 skipped** (up from
1,334: one new test added, one contract test updated). All changes uncommitted,
stacked on the earlier post-run fixes (fast-fail GenericHandler +
outcome_metrics flush double-count).

Each entry: what changed, where, and which problem it closes.

---

## 1. Rest drive can no longer pin at 1.0 (the 74% ignition monopoly)

- **`brain/runtime_coupling/demand_engine.py`** — `Demand` gains a
  `leak_per_tick` (proportional leak; default 0.0, existing drives unchanged).
  `tick()` is now `p + buildup − leak·p`, clamped [0,1]. The **rest** drive gets
  `leak_per_tick=0.003` against its 0.002 buildup → equilibrium ≈ **0.67**:
  still signals (>0.35), below the urgent line (0.70), can never saturate.
- **`demand_engine.py` `evaluate_cycle`** — rest keywords now include
  `"consolidat"`, so a consciously-picked `idle_consolidation_cycle` discharges
  rest (the old keyword set matched no function the selector ever picked).
- **`brain/loop/finalize.py`** — when the dream thread actually launches,
  `demand_engine.satisfy("rest", 0.6)` fires at the launch site (the dream runs
  on a side thread, so its name never reaches `evaluate_cycle`).

This is options (a)+(b) from the deeper pass; SL1–SL5 remains the real fix.

## 2. AR2 unblocked: research runner has its hooks

- **`runtime/goal_web_hooks.py` (new)** — `goal_web_search(query, k)` →
  `[{title,url,snippet}]` (Serper when `SERPER_API_KEY` is set, Wikipedia
  article search otherwise — the same capability the conscious lane uses) and
  `goal_web_fetch(url)` → plaintext via `web_fetch._get` + `_html_to_text`
  (20k-char cap). The emotion-state reader also moved here from `main.py`
  (module-size limit).
- **`main.py`** — GoalsDaemon ctx now carries `web_search` **and** `web_fetch`
  (the run died at search, so the missing fetch hook never even surfaced).
  Deliberately **no `llm` hook**: the LLM is tool-only gated, and the handler's
  offline extractive memo is the honest fallback.

## 3. Ledger attribution: no more anonymous, time-blind effects

- **`brain/cognition/global_workspace.py`** — new thread-safe **bound-goal
  mirror**: `bound_goal()` refreshes it on every context-bearing call;
  `last_bound_goal_id()` serves contextless writers (5-min TTL so a long-dead
  goal can't be credited). Plus `reset_bound_goal_mirror_for_tests()`.
- **`brain/symbolic/symbolic_effects.py`** — when no context/goal is supplied,
  falls back to the mirror. Closes the 116-row `goal_id: null` blind spot
  without threading `context` through the symbolic call chains.
- **`brain/agency/effect_ledger.py` `_cycle_from`** — falls back to the
  persisted `get_cycle_count()` when neither cycle nor context is supplied.
  Fixes `cycle: 0` for **all** contextless writers (symbolic engine, goals
  runner) in one place.

## 4. S7: the production funnel sees every lane

- **`brain/agency/effect_ledger.py`** — every recorded row also lands in a
  bounded in-memory deque; new **`drain_recent_rows()`** hands them to the
  funnel telemetry once per cycle. (`reset_for_tests` clears it.)
- **`brain/loop/production_telemetry.py` (new)** — the F6 telemetry block
  extracted whole from `finalize.py` (module-size limit); `finalize` still
  invokes it each cycle. `emit_production_telemetry` now merges the ledger
  drain with the legacy `_effect_rows_this_cycle` context list (dedupe by
  `content_hash`), so `production_attempt_count` counts conscious writers, the
  symbolic engine, and the goals-daemon runner alike.

## 5. S6: aspiration crediting can actually receive

- **`brain/cognition/planning/long_term_driver.py`** — `spawn_frontier_subtask`
  stamps **`serves`** (parent's serves/title) and **`driven_by`** (parent's, or
  `self_understanding`) onto every frontier child — the fields
  `credit_objectives` actually reads.
- **`brain/cognition/planning/goal_store.py`** — the overflow archive path
  stamps displaced live goals `status: "archived"` + `archived_reason:
  "overflow"` instead of dumping them into `comp_goals.json` with a live status
  (the S6 status-at-copy bug).
- **`brain/cognition/intrinsic_objectives.py`** — `_has_real_artifact` (partial
  credit) now also accepts a qualifying **ledger effect** for the goal
  (`has_qualifying_effect`) — the same evidence the completion gate reads. With
  §3's attribution fix, ledger-recorded work finally flows into aspiration
  progress before full goal closure. `credit_objectives` skips
  `status: "archived"` entries.

## 6. Title-dup fixed at the source

- **`long_term_driver.py`** — new `_bare_topic()` (idempotent: unstacks
  `beyond`/`retry` prefixes + delegates to `_strip_goal_scaffold`), applied at
  all three frontier-string sites: `ensure_frontier` seeding,
  `absorb_finished_subtasks`' `beyond {…}`/`retry {…}`, and
  `spawn_frontier_subtask`'s title template (with a defensive re-clean for
  frontiers inherited from older state). "Understand Understand my own mind…"
  can no longer be constructed — which also stops the P6 blemish (the membrane
  quoted the doubled title verbatim into chat).

## 7. Goals-v2 runner: status honesty

- **`goals/runner.py`**:
  - `_execute_step` sets `started_at` before the first tick — a handler that
    raises immediately can no longer leave the goal never-RUNNING (the WAL
    `NEW→READY→READY` pattern).
  - Handler exceptions now call `record_failure("goals.runner.tick.<kind>")`.
  - `_maybe_finalize_goal` **cascades dependency failure**: a pending step whose
    `deps` (transitively) include a FAILED step counts as dead, so a failed
    keystone step now fails the goal instead of leaving dependents WAITING
    forever.
  - Goal-level failures at the finalize site also write the machine-readable
    record (§9).

## 8. Person model writes on interaction

- **`brain/cognition/self_state/person_detector.py`** — new
  `_record_interaction()`: whenever the user actually speaks, the resolved
  person record gets `last_seen`, `messages_received` += 1, and a
  `session_count` bump when the gap since last contact exceeds 30 min — for
  named **and** anonymous persons, on every resolution path (the old code only
  saved at session-mint time, which ran once, at boot). Same-utterance
  double-writes are deduped.

## 9. Failure telemetry is machine-readable

- **`brain/utils/failure_counter.py`** — new `record_goal_failure(goal_id,
  title, reason)` writing `{ts, site: "goal_failure", goal_id, title, reason}`
  lines to `failures.jsonl` (same file + rotation as exception telemetry,
  distinguishable by `site`).
- **`brain/cognition/planning/goal_outcomes.py`** — `mark_goal_failed` (the v1
  chokepoint) calls it.
- **`goals/runner.py`** — v2-native goal failures call it too.

## 10. Stuck-loop economics (AR4 + watchdog)

- **`brain/loop/cognition_reward.py`** — the making-attempt bonus now decays
  with consecutive identical attempts (same fn + same goal, no check-pass
  between): 0.15 → 0.075 → 0.05 → …. Trying to make still beats reading; a
  loop re-running one failing check ~8×/min can no longer pay itself into the
  top reward EMA. A pass resets the streak and still pays the +0.10 bonus.
- **`brain/cognition/planning/goal_execution.py`** — a **give-up** advance
  (max attempts exhausted, no real act) no longer resets `_replan_count` /
  `_stalled`. That reset is what blinded the metacog watchdog (and its
  hard-disengage backstop) to the 1.7 h stuck-step loop.

## 11. Small plumbing

| Fix | File | Change |
|---|---|---|
| `final_thoughts_written` desync | `brain/cognition/runtime_lifetime.py` | the flag is set via a fresh read-modify-write of the lifespan file instead of saving a possibly-stale snapshot wholesale — a concurrent shutdown writer can no longer revert it |
| habituation unbounded growth | `brain/cognition/habituation.py` | hard cap `_STORE_MAX_KEYS = 5000`; over cap, lowest-count/oldest entries evicted in the existing prune pass (the 30-day age rule can never fire inside one life) |
| `health_state.cycle` stuck at 0 | `brain/cognition/health_monitor.py` | stamps the real cycle from context; comment documents that `total_healthy_cycles` counts 1-in-5 **checks**, not cycles |
| analogy debug-string identity | `brain/symbolic/analogy_engine.py` | `best_analogue_answer` returns prose via `symbolic_fluency.explain_analogy` (the converter existed; this path bypassed it); legacy format is the fallback only |
| social pressure with nobody there | `brain/runtime_coupling/social_presence.py` | `_ever_spoke` guard: before the first-ever user contact this process, pressure stays at floor — no more 0.95-pressure "distant" person while alone. Connection hunger remains the drive engine's job |

## 12. Module-size + guardrail housekeeping (fallout of the above)

- `brain/loop/production_telemetry.py` extracted from `finalize.py` (618→529
  lines); `runtime/goal_web_hooks.py` extracted from `main.py` (659→590).
- All new intentionally-silent handlers annotated `# intentional: <category>`
  per the exception-ratchet rule (ceiling 0).
- `tests/brain/test_production_telemetry.py` re-pointed at the extracted
  module; `tests/brain/test_symbolic_effects.py` updated for the mirror
  contract (+1 new test: contextless effects bind via the mirror; the
  "ungoaled" test now asserts against an explicitly empty mirror).

## Explicitly NOT changed (deliberate)

- **SL1–SL5 sleep layer** — still unbuilt; §1 is the stopgap that keeps the
  drive honest until it exists.
- **Allostatic arming line (0.60)** — unreachable by arithmetic, but lowering
  it is behavioral tuning, not a bug fix; standing invariant since 06-29.
- **`_sense_for` felt-surface vocabulary** — the one-sentence surface needs the
  speech-feedback loop connected (P2 roadmap), not a hotfix.
- **Speech self-evaluation cadence** — structurally reply-dependent; nothing to
  fix until there is more conversation.
- **`events.jsonl` DECISION-only, fossil files** (`proposed_goals`,
  `symbolic_plans`), **`trace.jsonl` row size**, **AR5 quota** — documented,
  low-stakes; left for a housekeeping round.
- **Correction to the why-doc:** `stagnation_signal_log.json` is *not* a fossil
  — `seek_novelty.py:263` writes it (it logs actions, not signals); the why-doc
  row was amended in place.

## What Run 3 should show if these landed

1. `drive_rest` cruising ~0.67 with sag-and-recover arcs, not pinned 1.0;
   ignition diet diverse past hour 2; integrative organs writing all day.
2. Research goals reaching `synthesize` and producing a real memo artifact
   (or failing honestly as FAILED goals, never stuck-READY).
3. `production_attempt_count` > 0 and tracking ledger activity (S7);
   `effect_ledger` rows carrying real `cycle` and `goal_id` values.
4. At least one aspiration off 0% (S6) — via completion credit or ledger
   partial credit.
5. No "Understand Understand…" titles anywhere; identity story in prose.
6. `known_persons.json` moving whenever someone talks to him;
   `failures.jsonl` non-empty if anything fails.
7. **S5 and S9 must hold** (the prediction from `did_the_fixes_land.md`): if
   S5 regresses once the lanes are bridged, the significance numbers were
   partly an artifact of what wasn't being counted.

*Written 2026-07-02 after the implementation round. Companions:
`2026-07-02_why_every_problem.md` (the root causes), `2026-07-02_run_analysis.md`
(§8 verdict), `NEXT_RUN_TESTS.md` (the gate).*
