# Multi-Goal Pursuit — let Orrin chase several goals at once

**Status:** ✅ IMPLEMENTED (2026-06-10) — Options **A + B** landed in
`brain/cognition/planning/executive.py`; Option C (worker threads) deliberately
deferred per the recommended path ("only if step latency proves to be the
bottleneck"). See the *Implementation record* at the bottom.
**Question:** can Orrin pursue **multiple goals concurrently**, and if not fully, how do we
get there without breaking the dual-process design?
**Short answer:** he already *tracks* multiple goals and *time-slices* them, but he does not
*advance them in parallel*. This doc lays out what exists, the design principle to preserve,
and three concrete ways to make pursuit genuinely concurrent — with safety invariants.

---

## What exists today (verified)

- **A committed-goals queue (≤ 3).** Each cycle the loop sets
  `context["committed_goals"] = goal_io.committed_goals_v1(api, limit=3)`
  (`ORRIN_loop.py:1264`), priority-ordered, and seeds the single conscious focus
  `committed_goal = committed_goals[0]` (`:1268`).
- **One conscious focus.** `think()`/the Global Workspace operate on the single
  `committed_goal` — one "theatre" (Baars). This is intentional (I2 stable focus).
- **The Executive advances ONE goal per tick, round-robin.** `executive.py` builds a queue
  ≤ `_DEFAULT_QUEUE_K=3` (`_build_queue`), then advances **one** goal's next step per tick
  using a rotating index (`_exec_rr`), swapping that goal into `committed_goal` only for the
  `pursue_committed_goal` call and restoring the deliberate focus afterward
  (`executive.py:96–168`). The daemon ticks every ~7 s (`_DAEMON_INTERVAL_S`).

**So "multiple goals at once" today = time-sliced, not parallel:** three goals can be *in
flight*, but only one step on one goal advances per ~7 s tick. With three goals each gets a
step roughly every ~21 s. There is no simultaneous progress.

---

## The design principle to preserve

The dual-process split is the thing to protect:

- **Consciousness is singular by design** — one Global-Workspace winner, one deliberate
  focus. *Do not* parallelize the conscious slot; that would break the "one theatre" model
  and the Monitor/Workspace invariants. Humans attend to one thing at a time too.
- **Procedural pursuit is where parallelism belongs.** The Executive/background lane is
  already decoupled, symbolic-only, procedural-only, and reversible-only. Concurrency added
  *there* is brain-accurate ("you pursue many goals, attend to one") and architecturally safe.

So the goal is: **keep one conscious focus; make the Executive lane advance multiple goals
per unit time.**

---

## Three ways to get there (in increasing power / risk)

### Option A — Batch round-robin: advance *all* K queued goals per tick **[recommended first]**
Change `executive_tick` from "advance one rotating goal" to "advance the next pending step
of **each** of the ≤K committed goals this tick."
- **Change:** loop over the queue, run `pursue_committed_goal` once per goal (swap each into
  `committed_goal` for its call, restore after — the swap machinery already exists at
  `executive.py:157–168`). Optionally cap steps/tick to bound latency.
- **Effect:** all K goals progress every tick instead of 1/K of the time. Single thread, so
  **no new concurrency hazards** beyond what one tick already does.
- **Tradeoff:** a tick now does up to K steps → longer tick. Mitigate with a per-tick budget
  and the existing tier weighting (6.3) so higher-tier goals get more steps when capped.
- **Risk:** Low. Smallest change that delivers real concurrent progress.

### Option B — Tier/drive-weighted parallel rotation
Build on A: instead of one step each, allocate a **budget of N steps/tick across the K
goals**, weighted by tier/priority/drive (reuse the 6.3 `_TIER_W` weighting already in
`executive.py:134`). A `core` goal might get 2 steps while a `minor` one gets 0–1.
- **Effect:** concurrent *and* prioritized — attention-like resource allocation across goals.
- **Risk:** Low–Medium (tuning the budget/weights).

### Option C — Parallel Executive worker lanes (true threads)
Run a small **worker pool** (e.g. K `orrin-executive-i` threads), each owning one queued
goal's step execution, instead of a single daemon.
- **Effect:** genuine wall-clock parallelism (useful if steps block on I/O — file reads,
  tool calls).
- **Cost/Risk:** **Medium–High** on an 8 GB M1: thread contention, and the affect-fidelity
  path must harvest each lane independently. Only worth it if step latency (not tick cadence)
  is the bottleneck. Defer unless A/B prove insufficient.

---

## Safety invariants (must hold for any option)

These already exist for the single daemon and must be honored per concurrent goal:
1. **All goal writes go through the `GoalArbiter`** (one in-process lock) — serializes the
   tree mutation even when K goals advance (`executive.py` header guarantee).
2. **Disk writes are flock + atomic temp/rename** (`utils/json_utils`) — goals / WM /
   long-memory never tear.
3. **Per-goal-id finalize idempotency** (`_FINALIZED_IDS`, `pursue_goal.py`) — prevents
   double-completion/double-reward when the same goal appears as several dicts.
4. **Procedural-only + reversible-only discipline** (`_procedural_only`/`_symbolic_only` on
   the Executive context) — concurrent lanes must not run irreversible/outward/self-modifying
   steps; those defer to the conscious thread (I10). Two lanes must never both fire an
   irreversible action.
5. **Affect via the thread-safe inbox** (`_harvest_daemon_affect` → `submit_affect(None,…)`)
   — each goal's step affect routes to the arbiter inbox and is committed by the main loop,
   so K lanes don't race the affect file.
6. **Bound K** (`_DEFAULT_QUEUE_K`, configurable) — concurrency is capped so a backlog can't
   spike CPU/latency.

---

## How it connects to the rest

- **UI (`ui_fixes.md`):** the dual-process visualization generalizes from "two lights" to
  "**1 conscious + K executive lights**." Each concurrently-advancing goal is its own
  procedural light on the Cognitive Sphere; the queue + per-goal step shows in the
  Consciousness panel's Executive section.
- **Benchmarks (`benchmark_realignment.md`):** unlocks **B6 — concurrent goal progress**
  (seed K goals, assert all K advance within a window while one conscious focus holds).
- **Closure (RECONCILED plan):** more goals in flight raises the importance of the
  deterministic retirement/fade/satiety maintenance tier — concurrency without closure would
  regrow the unbounded-goal problem, so multi-goal must ship *with* the closure tier active.

---

## Recommended path
1. **Option A** (batch round-robin + per-tick step budget) — the minimal, low-risk change
   that delivers real concurrent progress while keeping one conscious focus.
2. **Option B** (tier/drive-weighted budget) — layer on prioritization once A is stable.
3. **Option C** (worker threads) — only if step **latency** (not tick cadence) proves to be
   the bottleneck; gate behind a flag and the safety invariants above.
4. Ship alongside the closure maintenance tier; add **B6** to measure it; extend the UI to
   K executive lights.

**Files (Option A):** `brain/cognition/planning/executive.py` (`executive_tick` /
`_daemon_loop` — advance all queued goals per tick with a step budget),
`brain/ORRIN_loop.py` (unchanged commitment path; it already supplies `committed_goals`),
optionally `brain/cognition/planning/goals.py` (GoalArbiter is already the write path).
**Risk:** Low for A, scaling with the option chosen.

---

## Implementation record (2026-06-10)

**Options A + B landed together** in `executive.py`:

- `executive_tick` now advances **every** queued goal per tick (Option A) under a
  per-tick step budget. The budget defaults to `len(queue)` (one step each — the
  Option A guarantee) and is tunable via `ORRIN_EXEC_STEP_BUDGET`; a higher value
  hands the extra steps to higher-tier goals first (Option B), capped per goal at
  its tier weight (`_TIER_TURNS`: core/existential 3, identity/growth 2, else 1).
- `_allocate_steps(queue, rr, budget)` does the weighted allocation: pass 1 gives
  one step to each goal in tier order (the old `_exec_rr` rotation now breaks
  ties between equal tiers so scarce budget rotates fairly); pass 2 distributes
  the remainder by weight.
- A step that does **not** take hold (`retry`/`blocked`/`stalled`/`error`/skip)
  forfeits that goal's remaining same-tick budget — no same-tick retries against
  a wall; the 3-attempt cross-tick cap in `pursue_goal` still governs.
- The per-goal swap/restore of `committed_goal` (the existing machinery) wraps
  every pursue call, so **one conscious focus** is preserved exactly as before
  (I2); the deliberate slot is restored after the tick even when a non-focus
  goal completes mid-tick.
- The executive summary gained `advanced: [{goal_id, goal_title, step, fn,
  status}]` — the per-tick record of every goal that moved. `active_fn` (the
  Sphere's second light) tracks the most recent real act of the tick, so the
  existing UI contract is unchanged; the `advanced` list is the data source for
  the future "K executive lights" rendering.
- Each advanced step charges `_EXEC_STEP_DEFICIT` and submits its outcome reward
  through the RewardEngine (per-action EMA), and emits `lane="executive"`
  telemetry + history per step — so all six safety invariants hold (GoalArbiter
  writes, atomic disk, finalize idempotency, procedural-only discipline,
  affect via the inbox in daemon mode, bounded K × bounded budget).

**Tests:** `tests/brain/test_multi_goal_executive.py` (10) — allocation
weighting/caps/rotation, all-K-advance-in-one-tick, focus restoration, blocked
goals not burning budget, outcome-reward mapping. Full `tests/brain` suite green.

**B6 (concurrent goal progress)** is added with the benchmark realignment — see
`benchmark_realignment.md` F5.
