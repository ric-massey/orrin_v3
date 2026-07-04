# Run 4 Fix Plan (2026-07-04)

Implementation plan for `RUN4_ISSUES_AND_IMPROVEMENTS_2026-07-04.md`, grounded
in a code read of every failure site. Each fix names the exact file/function,
the mechanism that broke in the 2026-07-03 run, the change, its test, and what
Run 4 must show. Build order is §Rounds at the bottom.

**One diagnosis correction against the issues doc** (found in code, changes
fix 2.1 — see A3): the daemon is *not* failing to schedule `generic` goals.
`GenericHandler.plan()` deliberately parks non-daemon-executable generic goals
as a `WAITING` placeholder — *"the cognitive loop pursues this goal, not the
daemon"* (`goals/handlers/generic.py:54-63`, the 2026-07-02 fast-fail fix).
The synthesis goal starved because the **conscious lane never picked it up**
— the same lane `social_presence` monopolized 84% of. Fixing "the daemon's
runnable-kind selection" would re-introduce the exact fake-completion bug
that fix removed.

---

## Round A — gate blockers (S7 reuse, S8, S9, first product)

### A1. Close the v1 mirror at the v2 completion event (issue 1.2, S8)

**How it broke (confirmed in code):** research goals complete daemon-side in
v2 (`goals/goals_daemon.py::_finalize_goals`). The only brain-side listener,
`goal_io._on_event` (`brain/goal_io.py:475`), reacts **only to `failed`**
events — a v2 `DONE` never touches the v1 mirror, which
`_reconcile_open_v2_into_v1` had earlier absorbed as `in_progress`
(`goal_io.py:327`). The mirror stays live until the 200-cycle reconciler
logs `resurrection repaired` (`goal_reconcile.py:124`). 12 repairs ≈ 12
completions, 1:1, exactly as the run data shows.

**Fix:**
1. Extract the v1-close logic from `goal_reconcile.py:114-125` into a shared
   helper `close_v1_mirror(goal_id, title, v2_status)` (find node by id, fall
   back to title; set `completed`/`failed`; append a
   `closed_from_v2_event` history entry; save).
2. In `_on_event`, handle **all terminal statuses** (`done`, `failed`,
   `cancelled`), not just `failed`: enqueue for the failed-goal drain as
   today, *and* call `close_v1_mirror`. The event bus fires synchronously on
   `api.update_goal`, so this is the transactional chokepoint the issues doc
   asked for. Idempotence is free: v1-initiated closes already call
   `close_goal_v2`, whose event finds the v1 node already terminal.
3. Keep the 200-cycle reconciler unchanged — it stays the *instrument*: any
   nonzero `store_desyncs_repaired` in Run 4 is now a genuine unknown seam.

**Escalation rule:** if after this the counter still tracks completions,
GOAL_STORE_UNIFICATION is formally triggered (§8's own rule) — do not patch a
third time.

**Test:** unit — create v2 goal mirrored into v1, complete it in v2, assert
the v1 node is terminal *before* any reconciler pass, and that a subsequent
reconciler pass makes 0 repairs.
**Run 4 shows:** `store_desyncs_repaired` ~0 **with** ≥10 completions.

### A2. Wire `mark_reused` into real read paths + production handoff (issue 1.1, S7)

**How it broke:** `effect_ledger.mark_reused` (`effect_ledger.py:572`) and
`note_artifact_use` (`:643`, named tools only) exist, but nothing that *reads*
ever calls them, and nothing ever resolves an artifact **path** back to its
content hash. `pending_production_action` is only *read* by
`production_telemetry.py:95`; no organ stages it.

**Fix:**
1. **Path→hash index in the ledger.** At `record_effect` time for
   `file_write`-shaped effects, store `path → content_hash` (persist beside
   the existing `_artifact_names` map). Expose
   `hash_for_path(path) -> Optional[str]` (normalize; only paths under
   `data/goals/artifacts/` need to resolve). Without this, no read path can
   ever credit reuse — this is the missing primitive, do it first.
2. **Read-path call sites** (each is 3–5 lines once #1 exists):
   - `fetch_and_read` / `read_a_book`: if the opened path resolves via
     `hash_for_path`, call `mark_reused`.
   - Research handler (`goals/handlers/research.py`): before writing a new
     memo, scan the artifacts dir for a same/overlapping-topic memo; if found,
     read it, cite it in the new memo ("builds on: <path>"), `mark_reused` it.
     This is the "build on prior memo" step — the cheapest genuine reuse arc.
   - Goal planning: when a new goal's spec references a prior goal's artifact
     dir, `mark_reused` on bind.
3. **Production handoff.** In the deliberate pick path (where the winning
   intention maps to an act — `step_execution.py`'s intention→act table is
   the chokepoint), when the pick is make-shaped **and** a committed
   make-goal exists, stage `context["pending_production_action"]` so the
   funnel counts a handoff. Keep it honest: stage only on a real act
   dispatch, not on selection alone.

**Test:** unit — write artifact via ledger, re-open it through
`hash_for_path` + `mark_reused`, assert a `reuse` row and the owning goal's
significance lift; research-handler test that a second same-topic memo cites
and credits the first.
**Run 4 shows:** ≥1 ledger `reuse` row; `production_handoff_count` > 0.

### A3. Get the synthesis goal actually pursued (issue 2.1 — corrected)

**How it broke (see header):** the goal sat `READY` in v2 with a `WAITING`
external-pursuit placeholder, by design. Its pursuit lane — the conscious
loop via `committed_goals_v1` (`goal_io.py:350`) — never worked it for 8 h.
Two candidate causes, both cheap to address:
(a) commitment ranking: `_committable_from_v1_tree` sorts by tier-then-
priority (`goal_io.py:281-284`); a refocus-born `generic` goal with no tier
may never crack the 3-goal committed set against research goals;
(b) even when committed, the lane was starved by the ignition monopoly (B1).

**Fix (both halves):**
1. **Diagnostic first** (30 min): replay `goals_mem.json` +
   `comp_goals.json` from `demo_runs/2026-07-03-run/data/` through
   `_committable_from_v1_tree` and answer: was the synthesis goal ever in the
   committed 3? Record the answer in the run folder.
2. **Give make-goals a daemon-executable lane**: add a `synthesize` directive
   to `_DAEMON_EXECUTABLE_KEYS` in `GenericHandler`
   (`goals/handlers/generic.py:44`): spec `{"synthesize": "<topic>",
   "from_artifacts": true}` → tick reads prior memos on the topic from
   `data/goals/artifacts/` (calling `mark_reused` on each — pairs with A2),
   composes a synthesis via the handler's `_llm_call`, and writes it as a
   real artifact through the same effect-ledger path research memos use.
   Problem-refocus (`problem_refocus.py`) sets this key when it births a
   "turn what I know into a written synthesis" goal.
3. If the diagnostic shows the goal never committed, also boost refocus-born
   make-goals' commit rank (stamp `priority: HIGH` at birth) — one line in
   `problem_refocus.py`.

**Test:** unit — a `generic` goal with `synthesize` spec plans a READY step,
produces an artifact file, ledger records it, prior memos get reuse rows.
**Run 4 shows:** that goal (or successor) DONE or honestly FAILED; ≥1
non-research artifact in `data/goals/artifacts/`; `making_backlog` no longer
required to be empty for S6's make-credit (pairs with B4).

### A4. Give the reward EMA real authority in selection (issue 1.3, S9)

**How it broke (confirmed):** in `score_actions.py:221` the EMA enters as
`s_exploit = 0.25 × max(0, expected − default)` — one additive term among
~25; max contribution ≈ 0.12 on totals that reach 1.1+. Meanwhile the learned
`exploration_drive→look_outward` coupling hit 0.706 (all others ~0.195), so
affect routing outvotes value structurally.

**Fix (the "smallest honest version"):**
1. **Multiplicative modulator**: after the `total` sum
   (`score_actions.py:244`), for actions with ≥8 scored observations
   (`_stats[name]["count"]` — same maturity gate `s_curio` uses), apply
   `total *= (0.5 + ema)` where `ema = get_expected(context, name)` (neutral
   0.5 → factor 1.0; look_outward's 0.150 → ×0.65; research_topic's 0.674 →
   ×1.17). Immature actions keep factor 1.0 — exploration stays the additive
   `s_explore` term's job. Remove `s_exploit` from the sum (no
   double-counting).
2. **Cap coupling growth** in the signal→function map (writer of
   `signal_function_map.json`): cap any single coupling at 0.5 **or**
   L1-normalize per signal so one association can't be 3.6× all others.
3. **Write the intended authority into `NEXT_RUN_TESTS.md` §8 S9** so it is
   falsifiable: "a mature action's final score scales by (0.5 + EMA); expected
   observable: corr(EMA, share-delta) > 0 and look_outward share falls while
   its EMA stays < 0.3."

**Test:** unit — two equal-prior actions, EMA 0.2 vs 0.7 with n≥8, assert the
high-EMA one outranks; an n<8 action is unaffected. Re-run the §3 selection
subset for regressions.
**Run 4 shows:** positive EMA↔share-delta correlation; `look_outward` share
falls while its EMA stays low.

---

## Round B — the environment the gate is measured in

### B1. Ignition habituation — the jammed-horn law (issue 1.4)

**How it broke (confirmed):** `deliberation_gate.should_think` trigger 3
(`deliberation_gate.py:67-73`) fires on any raw signal ≥ 0.60 and
short-circuits every lower trigger. An unchanged `social_presence@1.00`
therefore wins ignition every cycle forever — emotion (trigger 4) and
prediction-error (5) never get a turn after the horn saturates. Three lives,
three horns (`action_debt` → `drive_rest` → `social_presence`).

**Fix (one mechanism at the gate, not a fourth per-drive patch):**
1. Keep a rolling window in context: `_ignition_recent`, a deque of the last
   M=50 firing reasons as `(source, round(strength, 1))` keys, appended
   whenever trigger 3 wins.
2. Before trigger 3's comparison, compute each signal's **effective**
   strength: `eff = raw / (1 + k × n_identical)` where `n_identical` is the
   count of that exact `(source, quantized value)` key in the window and
   k ≈ 0.25 (identical signal that won 12 of the last 50 → ×0.25). The
   moment the value *changes* the key changes and full strength returns —
   habituation to sameness, not to the source.
3. When habituation demotes a signal below 0.60, the gate **falls through**
   to triggers 4–14 — that alone restores the emotion/prediction diet.
4. Log attenuated wins (`strong_signal_habituated(...)`) so the run analysis
   can census them.

**Test:** unit — feed the gate an unchanged 1.0 signal for 60 synthetic
cycles: assert its win-share drops below 40% and lower triggers fire; then
change the value and assert it wins immediately again.
**Run 4 shows:** no single source > ~40% of ignitions while alone;
emotion/prediction-check ignitions still present in hour 6.

### B2. Timer-protect the consolidation organs (issue 2.2)

**How it broke:** every ignition-gated integrative organ (idle consolidation,
crystallization, rule firing, world-model audit, symbolic concepts) went dark
by hour 3 under the monopoly; the 3-hour **dream timer never missed (5/5)**.
The existence proof is in this run's own data.

**Fix (interim, until SL1–SL5):** give each of
`idle_consolidation/consolidation_cycle.py`, `symbolic/crystallization.py`,
rule-firing, world-model audit a last-ran timestamp and a timer fallback on
the same scheduling path dreams use: if not run via ignition in the last
60–90 min, run once in a protected slot. Copy the dream cadence pattern
verbatim rather than inventing a second scheduler.

**Test:** unit — simulate 2 h of cycles with ignition always taken; assert
each organ still ran via its timer.
**Run 4 shows:** `crystallized_skills`, `rule_firings.jsonl`,
`world_model_stats` mtimes in the back half of the run; dreams still 5/5.

### B3. Unblock satiety closures (issue 2.3, S3 — red since Run 1)

**How it broke (confirmed):** `goal_outcomes.py:138-145` refuses a satiety
close when the goal has **no qualifying ledger effect** — correct
anti-hollow-completion behavior. But a read-heavy "understand X" goal
records nothing, so it can *never* satiety-close: sated → refused → stays
open → 19 refusals, 0 closures, three runs.

**Fix (make the refusal productive instead of terminal):** on a satiety
refusal, enqueue one micro-step on the goal: *"write down what I learned"* —
a produce-and-check note into the goal's artifact dir through the normal
effect-ledger path. The note **is** the qualifying effect; the next satiety
pass closes the goal legitimately, and the note is exactly the kind of
artifact A2's read paths can later reuse. If the goal genuinely learned
nothing, the note step fails honestly and the refusal stands.

**Test:** unit — sated no-effect goal: first pass refuses + stages the note
step; after the note lands, second pass closes; assert one closure counted.
**Run 4 shows:** ≥1 satiety closure (or, if this is judged wrong, an explicit
S3 re-scope note in `NEXT_RUN_TESTS.md` — decide, don't carry a fourth run).

### B4. Tighten aspiration credit + candidate quota (issue 2.4)

Two small changes where credit and candidates are minted:
1. `output_producing` credit requires the crediting effect to be
   `file_write`/`tool_run` **on a goal whose own kind is make-shaped**
   (`generic` with synthesize/make spec, `coding`, `code_edit`) — research
   memos stop wearing the making hat.
2. Enforce AR5's per-aspiration quota **at the candidate stage** (158/162
   targeted one aspiration last run): cap any single aspiration's share of
   generated candidates per window at ~50%.

**Run 4 shows:** S6 still no-zeros, with ≥1 credit from a genuine make-goal
(A3 supplies the goal).

---

## Round C — housekeeping sweep (issues 3.1–3.11, one pass)

| # | Fix | Where |
|---|---|---|
| 3.1 | Register `social_penalty` in the emotion buffer vocabulary (the gate already treats it as spike-worthy, `deliberation_gate.py:76`) | emotion buffer vocab / `brain/data/vocab_weights.json` writer |
| 3.2 | Set `final_thoughts_written` in the same write as `final_thoughts.json` itself (move the flag into that file or write-then-fsync-then-flag in one place), replacing the lifespan-file read-modify-write | `runtime_lifetime.py:403-427` |
| 3.3 | Floor `attention_value_weights` channels at 0.01 (same class as drive-pinning, opposite direction) | attention weights updater |
| 3.4 | Apply items.jsonl's gz rotation to root `data/memory/wal/events.jsonl` (15 MB) | WAL writer |
| 3.5 | Slim `trace.jsonl` rows (drop full emotion+committed snapshot; keep deltas/ids) | trace writer |
| 3.6 | Rotate/cap `workspace_writeback.jsonl` (~1 MB/run) | writeback appender |
| 3.7 | Seven fossil files: per file, retire it + its readers **or** wire the writer — no third option | `proposed_goals`, `symbolic_plans`, `map_territory_audit_state`, `concepts`, `consolidation_queue`, `learned_phrases`, `failure_summary`, `model_failures.txt`, `vocabulary.json` |
| 3.8 | Stock `language/library/` with a few public-domain texts (else retire `read_a_book`) — note: a stocked shelf also feeds A2's read-path reuse | `brain/cognition/language/library.py` |
| 3.9 | Teach §8 tooling to sum `outcome_metrics` rows across a midnight straddle | run-analysis tooling |
| 3.10 | Decay/re-test high-confidence semantic facts whose source lane changed (`produce_and_check` neutral, n=228, conf 0.979 — learned from the removed stuck loop) | semantic fact store |
| 3.11 | Populate `long_memory` tags at write time or drop the field | `long_memory` writer |

## Do not touch (§4 of the issues doc)

Allostatic arming line, identity/mouth surface (blocked on P2 roadmap),
speech self-evaluation (reply-dependent), stuck-step residual (absorbed by
A2/A3). The 2026-07-04 social tone-down (§5) is **verify-only**: no person
record until someone speaks, `drive_social` ~0.66, `social_presence` a
minority source. If a *different* signal monopolizes Run 4, that is B1's law
demonstrating itself — priority evidence, not a new bug.

## Build order and gates

1. **Round A** (A1 → A2 → A3 → A4; A2.1's path→hash index before A2.2/A3.2).
   Each lands with its unit test; `make verify` green after each.
2. **Round B** — B1 first (every §8 number is measured through the ignition
   diet), then B2, B3, B4.
3. **Round C** — one sweep, one commit.
4. Pre-run: `make verify` green, §3 subset green, clean reset, baseline copies
   of `outcome_metrics` + `action_reward_ema`, single instance, ~10k+ cycles.
5. Score against the Run 4 checklist in
   `RUN4_ISSUES_AND_IMPROVEMENTS_2026-07-04.md` §7.

If time allows only Round A plus one thing: **B1** — the issues doc is right
that Run 4's numbers are only as trustworthy as its ignition diet.

---

## Implementation status (2026-07-04)

**Built & tested (`make verify` Python gate green: ruff + mypy + 1373 tests):**

- **Round A** — A1 (v1 mirror closes at the v2 terminal event; reconciler is now
  a pure instrument), A2 (path→hash index `hash_for_path` + read-path reuse in
  `fetch_and_read` / `read_a_book` / research "builds-on" / goal-bind + production
  handoff staged in `step_execution`), A3 (daemon-executable `synthesize` lane in
  `GenericHandler`; make-goals born HIGH-priority with a synthesize spec; commit
  diagnostic recorded in `A3_COMMIT_DIAGNOSTIC_2026-07-04.md` — the goals ranked
  #4/#5, never committed), A4 (reward EMA is a multiplicative modulator
  `total *= 0.5+EMA` for mature actions; `s_exploit` dropped from the sum;
  per-signal couplings L1-normalized + capped at 0.5; §8 S9 authority written).
- **Round B** — B1 (ignition habituation at the gate: `eff = raw/(1+k·n_identical)`,
  falls through when a jammed horn demotes below 0.60), B2 (`organ_timers`: world-
  model audit / symbolic prediction / symbolic consolidation get a 75-min timer
  fallback on the dream's protected slot), B3 (a satiety refusal writes a "what I
  learned" note through the ledger — the note is the qualifying effect), B4
  (making credit requires a make-shaped goal via shared `goal_is_make_shaped`;
  candidate pool capped at 50% per aspiration).
- **Round C** — 3.1 (`social_penalty`/`loss_signal` seeded into `CORE_BASELINES`
  so the emotion buffer stops dropping them), 3.2 (final-thoughts flag set last +
  verify-retry), 3.3 (attention weights floored at 0.01), 3.5 (trace rows slimmed
  to top-5 signals + goal id), 3.6 (writeback cap tightened to 8000), 3.8
  (bundled public-domain offline library starter), 3.9 (`window_summary` sums a
  midnight-straddling run), 3.10 (semantic facts decay when not re-observed).
  3.4 already satisfied (the WAL gz-rotates both streams at 16 MB — `events.jsonl`
  at 15 MB simply hadn't crossed it). 3.11 no-op (no `tags` field exists on
  long-memory entries to populate or drop).

**Deliberately deferred:**

- **3.7 (seven fossil files)** — retiring a reader/writer without a live
  integration run to confirm nothing breaks is exactly the destabilizing,
  hard-to-verify change to keep out of a behavioural-fix commit. Most candidates
  showed BOTH a writer and a reader on inspection (not simple dead files), so the
  correct call per file needs a dedicated pass with a run behind it. Flagged, not
  done.

*Compiled 2026-07-04 from a code read of `goal_io.py`, `goal_reconcile.py`,
`goals/goals_daemon.py`, `goals/policy.py`, `goals/handlers/generic.py`,
`effect_ledger.py`, `deliberation_gate.py`,
`selection/score_actions.py`, `goal_outcomes.py`, against
`RUN4_ISSUES_AND_IMPROVEMENTS_2026-07-04.md` and the
`demo_runs/2026-07-03-run/` forensics.*
