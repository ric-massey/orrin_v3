# Why every problem happened — Life of 2026-07-02 (root-cause pass)

Every problem surfaced by the run's doc set (`run_analysis`, `deeper_pass`,
`did_the_fixes_land`, `what_did_he_make`, `who_is_he`, `DATA_FILE_AUDIT`), traced
into the codebase to a specific mechanism with file:line references. Grouped the
way the docs raised them. Analysis only; no code changed by this write.

**The one-sentence pattern:** almost nothing here is a broken organ — it's eleven
missing handoffs (a ctx key, a context kwarg, a `serves` stamp, a funnel list
nobody appends to) plus one un-dischargeable drive that starved everything
downstream of consciousness.

---

## 1. The two §8 gate failures

### S7 — production funnel counted 0 despite 687 produce_and_check executions

The funnel counter in `brain/loop/finalize.py:74-85` counts an "attempt" only
when `context["_effect_rows_this_cycle"]` is non-empty — and exactly two writers
ever populate that list by hand: `brain/agency/code_writer.py:178` and
`brain/behavior/express_to_user.py:330`. `record_effect()` itself
(`brain/agency/effect_ledger.py:348`) writes the durable ledger but never appends
to the per-cycle context list, and `produce_and_check`
(`brain/cognition/produce_and_check.py:254`) calls `record_effect` directly.

So *any* lane's produce-and-check — conscious or executive — is invisible to the
funnel. It's not just a daemon-lane split; even the 8 conscious picks couldn't
have counted. **Fix shape:** key the attempt counter on the ledger (or make
`record_effect` append to the context list), not on two hand-fed callsites.

### S6 — all four aspirations at 0 (four whys, one per broken link)

1. **No `serves`/`driven_by` on completed goals.** The ltc frontier subtasks are
   built in `spawn_frontier_subtask`
   (`brain/cognition/planning/long_term_driver.py:156-171`) with `parent` but
   **no `serves` or `driven_by` keys**, and `credit_objectives`
   (`brain/cognition/intrinsic_objectives.py:406,425`) reads only
   `serves`/`driven_by`, never `parent`. The v2 housekeeping/deps goals likewise
   carry neither. Only `intrinsic_goals.py:177` stamps `serves` — one generator
   of many.
2. **comp_goals "in_progress" entry (status-at-copy).** `save_goals`'s overflow
   path (`brain/cognition/planning/goal_store.py:170-181`) archives goals
   displaced past `MAX_GOALS` into `comp_goals.json` **with their live status**.
   The "completed goals" file doubles as an overflow dump, and
   `credit_objectives` skips non-completed entries.
3. **31 ledger rows attributed to `ltc_aspiration-*` never credited.** There is
   **no code path from the effect ledger to aspiration credit**.
   `mark_objective_contribution` has exactly one caller
   (`brain/cognition/planning/goals.py:216`, artifact-gated completion), and
   `credit_objectives` reads only the goal pools. Worse, rows attributed to the
   aspiration itself hit `intrinsic_objectives.py:394`, which explicitly skips
   `kind == "aspiration"` entries — aspirations are credit *targets*, so direct
   attributions are structurally ignorable.
4. **Thin sample.** Only 3 completions — itself downstream of the rest scream
   (§2).

---

## 2. The hidden driver: the rest scream (74% of ignitions)

### Rest pinned at 1.0 with no discharge

`Demand.tick()` (`brain/runtime_coupling/demand_engine.py:115-117`) is monotonic
buildup with **no decay term** — P5's homeostatic decay was applied to the
appraisal signals (curiosity/motivation/confidence), never to DemandEngine
drives. Rest's only release is `evaluate_cycle`'s keyword match
(`demand_engine.py:276-278`) on function names containing
`dream/sit_with/meditate/integration/rest` — no function the selector actually
picks matches, and the real dream cycle is (a) capped at one per **6 hours**
(`brain/cognition/idle_consolidation/consolidation_cycle.py:26`) and (b) run on
a side thread (`brain/loop/finalize.py:496-501`), so its name never reaches
`evaluate_cycle` anyway. `_rest_mode` (`brain/loop/sense.py:207-219`) only
injects a reflection-bias signal — it discharges nothing. The sleep layer
(SL1–SL5) that would give `slept_seconds` meaning is designed, unbuilt.

### The ~10:30 organ blackout is the same why from the other side

`should_consolidate` requires 6h between dreams plus 5 min of user-idle
(`consolidation_cycle.py:82-91`), and every integrative organ (crystallization,
symbolic concepts, rule firings, world-model audit) is fed by conscious-lane
cycles — once `drive_rest@1.00` owned ~1,100 ignitions/hour, nothing else won
the workspace to feed them. The drive asking for space to integrate starved
every integration organ.

---

## 3. Goal-machinery seams

### AR2 — `RuntimeError: ctx.web_search hook not provided`

The daemon ctx is built at `main.py:465-470` with exactly four keys
(`repo_root`, `get_memory_health`, `api`, `get_emotional_state`);
`goals/handlers/research.py:168-170` hard-requires `ctx.get("web_search")`. The
capability exists (`brain/behavior/tools/toolkit.py:204`) — it was simply never
put in the dict. One line.

### Failed keystone step → goal stuck READY (status-honesty gap)

Two whys in `goals/runner.py`:

1. The exception path (`runner.py:272-282`) resets `started_at = None`, so
   `StepStarted` never fires and the goal never even flips to RUNNING — hence
   WAL `NEW→READY→READY`.
2. `_maybe_finalize_goal` fails a goal only when
   `any_failed and not any_pending` (`runner.py:442-444`) — the research goal's
   synthesize/memo steps wait on the dead search step forever, so `any_pending`
   stays true and no rule cascades a terminal dependency failure.

### The stuck-step loop that pays itself (S9 caveat)

Chain of four:

1. Generic reasoning-template step names ("Establish observable consequence")
   semantically match `produce_and_check` at sim 0.35 — the floor is 0.22
   (`brain/cognition/planning/step_execution.py:152-159`).
2. On an unverifiable topic `produce_and_check` returns `changed: False`
   (`brain/cognition/produce_and_check.py:228-231`), so the step never advances
   and re-matches every executive tick.
3. AR4 pays +0.15 per attempt "pass OR fail" with no repeat-cap
   (`brain/loop/cognition_reward.py:86-87`), feeding the 0.7651 EMA.
4. The monitor's honored `stuck_step` verdicts only nudge kind-bias / the
   impasse signal (`brain/cognition/metacog.py:149,297-303` — "soft offers only
   BIAS a deliberate pick"), and the deliberate lane that would act on the bias
   was monopolized by the rest scream. The hard backstop exists
   (`metacog.py:305`) but keys on the `stall` counter, which resets whenever
   `novel` observations change (`metacog.py:250-252`) — and produce_and_check
   records a reach outcome with info_gain 0.2 *on every failure*
   (`produce_and_check.py:286`), plausibly feeding exactly the "progress" that
   defeats the watchdog.

### S3 — satiety closures 0 (composite)

The sweep (`brain/loop/maintenance.py:120-165`) runs 1-in-40 maintenance cycles,
checks max 5 goals, and **excludes the committed goal** — which is where the
understanding work lived. For the rest, `is_sated`'s work-gate
(`brain/cognition/planning/goal_satiety.py:108`) needs a completed plan step or
`novel_count(goal_id) > 0`, and the executive lane's executions never record
per-goal novelty; the uncertainty proxy needs `uncertainty(topic) ≤ 0.25` on
topics that are mangled title-dup strings no knowledge ever accrues against.
And even a sated goal is *refused* closure without a qualifying ledger effect
(`maintenance.py:178-181` + the P1 gate) — which connects to the
`goal_id: null` seam (§5): the work's effects were anonymous, so the goal
looked effect-less.

### Title-dup ("Understand Understand my own mind…")

`long_term_driver.py:126` builds the next frontier as `f"beyond {prior title}"`
and `spawn_frontier_subtask` (line 155) wraps it in
`f"Understand {frontier} more deeply"` — never calling `_strip_goal_scaffold`
(`brain/cognition/intrinsic_helpers.py:290`), which was written for precisely
this re-wrap bug but only wired into the KG/intrinsic path.

### goals_failed inflated to 3,909

The `outcome_metrics` flush double-count; already diagnosed and fixed post-run
(`brain/cognition/planning/outcome_metrics.py` + `goals/handlers/generic.py`,
uncommitted, suite green 1,334).

---

## 4. Person, social, speech surface

### Person model dead (`known_persons.json` mtime = birth second)

For a speaker who never states a name, `detect_and_set_person_id`
(`brain/cognition/self_state/person_detector.py:355-359`) returns the cached
anonymous record **without saving**; the only writes happen at session-identity
minting, which ran once — at boot, before anyone spoke. Nothing in the chat path
writes on *interaction* (no last_seen bump, no note, no message count when
`_user_spoke_this_cycle` fires). The taught definition of "built" had no organ
to land in.

### Social pressure 0.95 while alone

`social_presence` models "the current user's engagement" from a session clock
started at boot (`brain/runtime_coupling/social_presence.py:36,90,100`):
pressure builds at 0.0008/s of silence whether or not a person has ever
connected — there is no "nobody here" state, so 6,858 s of solitude reads as a
0.95-pressure "distant" person.

### Felt surface one sentence wide (50/50 announcements, 94/100 notes)

All roads lead to `describe_dominant_signal`'s fallback
(`brain/control_signals/signal_summary.py:267`): when `_sense_for` has no phrase
for the dominant emotion, the constant string *"something present but hard to
name"* is emitted. The vocabulary is a fixed lookup; the loop that would grow it
is the speech-evaluation loop below, which barely runs.

### Speech self-evaluation barely runs (15/344 evaluated, 9 retrieved)

`evaluate_last_reply` fires only when *real new user input* arrives
(`brain/think/speech_evaluator.py:5`, called from
`brain/think/think_utils/user_input.py:164`) — quality is measured by the
human's next reply. Announcements and notes never get replies, so they are
structurally unevaluable; a mostly-alone life evaluates ~nothing.
`learned_phrases.json` is empty for the same reason: phrase promotion requires
`PROMOTE_MIN_SCORE` engagement scores that the idle evaluator never produces.

### P6 blemish (raw goal titles in replies) & the analogy debug-string identity

The membrane's "why" is `goal.get("title")` verbatim
(`brain/behavior/express_to_user.py:72`), so the title-dup bug leaks into
conversation. The dying identity is `brain/symbolic/analogy_engine.py:251`'s
literal return format — `f"[analogy/{intent}] Similar situation (score=…)"` —
passed as the resolved `answer` by
`brain/symbolic/reasoning_router.py:170-176` with no prose layer; the converter
that would fix it exists (`brain/symbolic/symbolic_fluency.py:202`) but this
path bypasses it.

---

## 5. Plumbing / telemetry (DATA_FILE_AUDIT items)

| Problem | Why |
|---|---|
| 116 ledger rows `goal_id: null` **and** `cycle: 0` | `brain/symbolic/crystallization.py:225` and `brain/symbolic/causal_graph.py:124` call `record_symbolic_effect` **without** `context=` — so `bound_goal` is never consulted (`brain/symbolic/symbolic_effects.py:34-40`) and `_cycle_from(None, None)` returns 0 (`brain/agency/effect_ledger.py:330-343`). One omitted kwarg, two audit findings. |
| `failures.jsonl` 0 bytes | Category error: that file belongs to the *exception* counter (`brain/utils/failure_counter.py`), while goal failures (deadline, fast-fail) are outcomes recorded only in activity-log prose — no machine-readable goal-failure writer exists. And the v2 runner swallows handler exceptions into `step.last_error` without calling `record_failure` (`goals/runner.py:272-275`), so even the 9 research crashes never reached it. |
| `health_state` 2,014 of 10,071 cycles | By design — the health check runs every 5th cycle (`brain/loop/finalize.py:214`); the field name over-promises. |
| `final_thoughts_written: false` at death | The flag is set in `lifespan.json` (`brain/cognition/runtime_lifetime.py:403-404`), but the audit read `runtime_lifetime.json`'s own snapshot block, written independently — two records of one fact, last-write-wins at shutdown. |
| `rss_cache.json` `{}` despite 9 picks | Every real execution path writes the cache, even fetch-failure (`brain/cognition/rss_reader.py:61-62`) — so the 9 "picks" never reached the function body. The only silent early-return is the 30-min throttle (`rss_reader.py:47-48`): picks were selected but throttled/never dispatched; the EMA counts picks, not executions. |
| `stagnation_signal_log.json` empty | *(Corrected after implementation pass:)* a writer DOES exist — `brain/cognition/seek_novelty.py:263` — but it logs seek_novelty *actions taken on stagnation*, not stagnation signals, and seek_novelty was rarely picked while the rest scream owned ignition. The name over-promises; not a fossil. |
| `events.jsonl` DECISION-only | `emit_event` has two call sites; the ACTION_START one lives in `brain/behavior/tools/tool_executor.py`, which no module imports — one live emitter remains (`brain/think/think_utils/finalize.py:567`). |
| `habituation.json` unbounded (15,469 keys) | Eviction exists but only removes entries **older than 30 days** with count < 3 (`brain/cognition/habituation.py:190-214`) — nothing in a 9-hour life qualifies; no size cap. |
| `allostatic_load` 0.000 all life | Load accrues only when `resource_deficit > 0.60` (`brain/cognition/cost_prediction.py:247`); the run peaked at 0.216 because executive steps cost 0.0006 each (`brain/cognition/planning/executive.py:43`) and deliberate cycles ~0.002 — the arming threshold is unreachable under normal operation. Inert by arithmetic, not by bug. |
| `ground_truth.jsonl` stopped 56 min early | Its sole writer is `action_gate._stamp_outcome` (`brain/think/think_utils/action_gate_helpers.py:106-113`), which fires only for conscious gated *actions* — consistent with the final stretch being rest-scream ignitions plus the executive-lane stuck loop, neither of which passes the action gate. |
| `trace.jsonl` at 37.6 MB | The writer (`brain/think/loop_helpers.py`) embeds full emotion/committed snapshots per row; `cap_jsonl` bounds rows, not bytes. |
| Fossils (`proposed_goals`, `symbolic_plans`, `map_territory_audit_state`) | `proposed_goals.json` still has a writer (`brain/behavior/behavior_generation.py:230`) that only re-seeds an empty list — the proposal flow moved elsewhere; `symbolic_plans.json` (`brain/symbolic/temporal_planner.py:35`) and the map-territory audit have writers that never fired this run (both live behind organs starved after 10:30). |

---

## 6. Cheapest fixes with the biggest blast radius (in order)

1. **Rest-drive decay/discharge** — a leak term in `Demand.tick()` or a real
   discharge behavior; unjams the 74% ignition monopoly that sits behind the
   organ blackout, the completion drought, and part of S6's thin sample.
2. **`ctx["web_search"]` in `main.py:465`** — one line; unblocks AR2
   end-to-end.
3. **`context=` on the two symbolic effect callers**
   (`crystallization.py:225`, `causal_graph.py:124`) — kills the 116-row
   `goal_id: null` / `cycle: 0` blind spot and feeds both S6 crediting and the
   satiety-close effect gate.
4. **Point the production counter at the ledger** instead of the hand-fed
   `_effect_rows_this_cycle` list — closes S7 for every lane at once.

Then: the `serves`/`driven_by` stamp + ledger→aspiration bridge (S6), the
failed-dependency cascade in `_maybe_finalize_goal`, `_strip_goal_scaffold` in
`spawn_frontier_subtask` (title-dup), and a person-model write on interaction.

*Generated 2026-07-02, root-cause pass over the run's doc set + codebase.
Analysis only; no code changed by this write. Companions:
`2026-07-02_run_analysis.md` (§8 verdict), `2026-07-02_deeper_pass.md`
(behavioral connections), `DATA_FILE_AUDIT_2026-07-02.md` (plumbing).*
