# Benchmark Realignment — fit the suite to the dual-process, multi-goal architecture

**Status:** ✅ IMPLEMENTED (2026-06-10) — F1–F5 all landed; see the
*Implementation record* at the bottom. Originally proposed (design + file:line),
verified against the live tree and a running LLM-off benchmark instance.
**Problem:** the benchmark harness (`brain/benchmarks/__init__.py`) was written against an
implicit **single-goal, single-lane** model. Orrin's architecture is **dual-process**
(a single conscious/deliberate slot + a background Executive lane) and **multi-goal** (a
committed-goals queue advanced round-robin). Several benchmarks therefore measure the wrong
surface or never trigger at all. This doc lists each misalignment with evidence and the fix.

---

## The architecture the benchmarks must match

- **Two lanes run concurrently.** The conscious loop picks **one** function per cycle
  (`ORRIN_loop.py:142` publishes it as the only `active_fn`, `lane="deliberate"`). The
  Executive daemon (`executive.py:_daemon_loop`, ~7 s) advances a goal **step** via
  `pursue_committed_goal`; the function it runs is computed as `summary["active_fn"]`
  (`executive.py:152`) but **never sampled**.
- **Goals are planned/pursued only when *committed*.** `committed_goal` is the head of
  `committed_goals = goal_io.committed_goals_v1(api, limit=3)` (`ORRIN_loop.py:1264`);
  decomposition (`decompose_goal`, `goals.py:481`) and pursuit only happen for committed
  goals. A merely-`active` seeded goal is never planned.
- **Multiple goals are time-sliced, not parallel.** The Executive advances **one** queued
  goal's step per tick, round-robin (`executive.py` `_build_queue` ≤ `_DEFAULT_QUEUE_K=3`,
  rotating index `_exec_rr`).

---

## Misalignments (with live evidence)

### M1 — Lane blindness: the sampler sees only the conscious lane
`record_sample` logs `context["last_function_chosen"]` — the **deliberate** pick only. The
Executive lane's goal-step functions (often the *real* goal work) are invisible.
- **Affects B2** (affect-driven switching): novelty-seeking that happens in the Executive
  lane isn't counted, biasing the correlation and the "novelty-when-bored" fraction.
- **Affects B3** (offline planning): the plan is executed in the Executive lane via
  `pursue_committed_goal`, so the action sequence B3 wants to observe is mostly off-sample.

### M2 — Scenario goals are seeded but never committed → never planned
`seed_scenario` appends the goal with `status:"active"` (`benchmarks/__init__.py`), but
planning/pursuit only touch the **committed** goal. **Live proof:** after 130+ cycles the
B3 goal still has **0 plan steps** and `status:"active"`, while the *actually committed*
goal ("Write a cognitive function…") has a real 3-step plan. So B3/B4/B5 measure a goal the
system never works on.

### M3 — Single-goal timing assumption vs the round-robin queue
B3's success criterion is "mean **cycles** to completion < 200." But the Executive shares
ticks round-robin across ≤3 committed goals, so wall-clock cycles for one goal are diluted
by the others. The metric should be **pursuit-ticks spent on that goal**, or the trial
should pin the benchmark goal as the sole committed goal.

### M4 — B3 goal text hits the wrong decomposition template
With the LLM off, `decompose_goal` → `_rule_based_decompose` (`goals.py:412`) routes by
keyword. "**Find** the word 'reaper'…" matches none of research/write/fix/connect/reflect →
falls to the **generic** template (*gather context → identify next action → execute/log*),
which doesn't map to the intended *search → grep → summarize* sequence. B3 can't fairly
test symbolic planning if the seed never yields a search-shaped plan.

---

## The fixes

### F1 — Sample both lanes (resolves M1)
1. Publish the Executive lane's `active_fn` to telemetry (this is also UI Fix 1 in
   `ui_fixes.md`); or, simpler for benchmarking, have `record_sample` read the last
   executive summary directly.
2. Record a **per-lane** sample each cycle: `{cycle, stag, fn_deliberate, fn_executive}`.
3. **B2**: count a cycle as "novelty-seeking" if **either** lane ran a `NOVELTY_FN`; compute
   the correlation against the combined behavior.
4. **B3**: track the action sequence from **both** lanes (the plan runs in the Executive).

### F2 — `seed_scenario` must commit the goal (resolves M2)
Give the scenario goal what `committed_goals_v1` ranks on (priority/recency) so it becomes
the committed head — or expose a `commit=True` that writes it into `context["committed_goal"]`
/ bumps its priority. Without this the goal is never planned and the benchmark is vacuous.
Add a guard to the evaluator: if a scenario goal has been `active` with `0` plan steps for
> N cycles, report `not_committed` (a distinct, honest state) rather than `pending`.

### F3 — Measure per-goal pursuit, not wall-clock cycles (resolves M3)
Count B3's "cycles to completion" as the number of Executive ticks that actually targeted
that goal (the round-robin already swaps it into `committed_goal` for its pursue call), or
run B3 with the queue pinned to one goal. Record both for transparency.

### F4 — Align the B3 seed with a real plan shape (resolves M4)
Reword the B3 scenario goal to hit a search/summarize template (e.g. *"Research where the
word 'reaper' appears in the brain files and write a one-line summary"* → research/write
branch), **or** extend `_rule_based_decompose` with a `search/find` template that yields
`search_own_files → grep_files → save_note`. Document which, so B3 measures planning, not
template luck.

### F5 — Add a multi-goal benchmark (forward-looking)
Once multi-goal pursuit lands (`docs/multi_goal_pursuit.md`), add **B6 — concurrent goal
progress**: seed K goals, confirm all K advance within a window while one conscious focus is
maintained. This benchmarks the property the architecture actually has, instead of pretending
there's one goal.

---

## Per-benchmark impact summary
| Benchmark | Misaligned? | Fix |
|---|---|---|
| B1 Memory boundedness | No (passive, lane-agnostic) | — |
| B2 Affect switching | **Yes (M1)** | F1 (count both lanes) |
| B3 Offline planning | **Yes (M1,M2,M3,M4)** | F1+F2+F3+F4 |
| B4 Satiety closure | **Yes (M2)** | F2 (commit the goal) |
| B5 Self-repair | **Yes (M2)** | F2 (commit the stuck goal) |
| B6 Concurrent goals | new | F5 (after multi-goal lands) |

## Order & risk
1. **F2** (commit scenario goals) — without it B3/B4/B5 are vacuous; highest priority. Low risk.
2. **F1** (sample both lanes) — depends on publishing the Executive `active_fn` (shared with
   `ui_fixes.md` Fix 1). Low risk.
3. **F4** (B3 seed/template) — trivial wording or one template branch.
4. **F3** (per-goal timing) — bookkeeping refinement.
5. **F5** (B6) — after multi-goal pursuit ships.

**Files:** `brain/benchmarks/__init__.py` (sampler both lanes, `seed_scenario` commit,
evaluators), `brain/cognition/planning/executive.py` (expose/publish `active_fn` — shared
with UI Fix 1), optionally `brain/cognition/planning/goals.py` (`_rule_based_decompose`
search template).

---

## Implementation record (2026-06-10)

- **F1 — both lanes sampled.** `record_sample` now records `fx` (the functions
  the Executive lane ran this cycle) and `gx` (the goal ids it advanced), read
  from the executive summary's `advanced` list (multi-goal) with a single-fn
  fallback. `_eval_b2` counts a cycle as novelty-seeking when **either** lane
  ran a `NOVELTY_FN` and reports `lanes: "both"`. (Daemon-mode samples still
  only see the interleaved summary — the documented default path is covered.)
- **F2 — scenario goals are committed.** `seed_scenario(tag, commit=True)`
  (default) also creates the goal through the **GoalsAPI** at `CRITICAL`
  priority — `committed_goals_v1` sorts by `-priority`, so the goal ranks into
  the committed head and actually gets planned/pursued. The goals_mem.json
  record reuses the **API goal's id**, so pursuit progress merges into the same
  record the evaluators read (no split-brain). Records carry `seeded_at_cycle`;
  evaluators (`_commitment_state`) report the distinct, honest **`not_committed`**
  state when a goal has sat `active` with no plan for >50 cycles. Legacy
  fallback (API unavailable) keeps the old behavior.
- **F3 — per-goal pursuit timing.** `_pursuit_ticks(goal_id, samples)` counts
  the sampled cycles whose Executive lane advanced that goal; `_eval_b3`
  reports **both** `pursuit_ticks` (the fair criterion under queue sharing) and
  `wall_clock_cycles_since_seed`, and checks the <200 criterion against ticks.
- **F4 — search-shaped plans (template option chosen, seed text unchanged).**
  Both plan generators gained a file-search template guarded by file/string
  cues: `_symbolic_plan` (pursue_goal.py — the one that drives execution) and
  `_rule_based_decompose` (goals.py). B3's goal now yields
  `search_own_files → grep_files → leave_note` (verified through
  `recognise_step_action`; `grep_files` added to `_KNOWN_FN_NAMES` so the
  literal name wins). Research-style "find out about X" goals still hit the
  research branch.
- **F5 — B6 added.** New passive benchmark **B6 — concurrent goal progress**
  (multi-goal pursuit landed first, see `multi_goal_pursuit.md`): pass when ≥2
  distinct goals advance within a ≤10-cycle window (the multi-goal Executive
  typically advances them within ONE tick — reported as
  `max_goals_single_tick`), while the deliberate lane stays singular.
  Wired into `evaluate_all` + `report`.

**Tests:** `tests/brain/test_benchmark_realignment.py` (15) — B2 both-lane
counting, not_committed guard, pursuit ticks, B6 pass/fail/insufficient, F4
template routing + recognizer mapping + research-template regression,
seed_scenario shared-id commit + idempotence + API-less fallback.
