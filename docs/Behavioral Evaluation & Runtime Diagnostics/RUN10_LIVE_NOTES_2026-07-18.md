# Run 10 live notes (attempt 2, 2026-07-18/19 life)

Run 10 attempt 2 live findings (write into the run folder at capture; the repo is
read-only under the run-lock while Orrin is alive, so these could not be filed
in-tree during the run). See [[project_run10_build]].

**FILING JOB at capture (lock release):** move the 4 staged docs from
`~/Desktop/orrin_docs_to_file/` (+ the design note `~/Desktop/
ORRIN_WORLD_DESIGN_2026-07-18.md`) into the repo per the README_FILING_PLAN.md
in that folder — gap analysis (with review caveats) → docs/, field guide →
docs/, Run 9 conversation export → demo_runs/2026-07-17-run/.

**LN-1 — question miner harvests Orrin's own sign-off (first failures.jsonl entry, 2026-07-19T03:20:39Z).**
Goal `g_bb5e9b797993` "Open question: What do you think?" failed honestly
(`steps_unreachable: 3 steps abandoned at the 3-attempt cap`). Chain: Orrin shared
a Hacker News item and signed off "What do you think?"; no reply came, so
`awaiting_response.py:99` wrote an `[unanswered_question]` long-memory record
quoting his own outbound question (Orrin provenance). The intrinsic question miner
(`intrinsic_generators.py:_open_question_goals`) then regex-harvested the phrase —
the F7 filters (2026-07-05) skip user-provenance entries, `[input/` prefixes, and
live user input, but not Orrin's own speech echoed via instrumentation records —
and minted a kind=research goal with `queries=["What do you think?"]`, a
contextless web search that could only fail. Failure machinery itself worked as
designed (honest failure, right site, no fake completion).

**Candidate Run 11 fix:** in `_open_question_goals`, skip entries with
`event_type == "unanswered_question"` / content prefix `[unanswered_question]`,
symmetric with the `[input/` skip — a question Orrin asked the user is addressed
to the user, not an open research question of his own.

**Watch:** repeated "Open question: What do you think?" goals later in this life
would confirm the record gets re-mined after refractory (dedup is title-keyed per
pass).

**LN-2 — first failure never persisted → same goal failed twice (03:20:39 then
03:24:10, reason `plan_generation_failed_3x`).** Root cause traced in code:
`mark_goal_failed` (goal_outcomes.py:393) mutates only the in-memory dict; tree
persistence is the caller's job. In `step_attempts.py`, the *retry* path merges
via `goal_arbiter.apply(merge_updated_goal_into_tree)` but the *failure* path
(line ~158) calls `mark_goal_failed` and returns without merging. So at 03:20:39
failures.jsonl + the v2 `close_goal_v2(FAILED)` fired, but the tree copy stayed
`pending` (verified live at 03:21) → next pass re-adopted it from the tree →
replan failed 3× → second `mark_goal_failed` at 03:24:10 on the fresh copy (the
idempotence guard can't help — it checks the copy, which was pending). Effects:
double emotional penalty + double felt-lifespan shock for one setback, and a
3.5-min tree↔v2 status desync. Persisted history confirms: only the 03:24 failed
event exists. **Run 11 fix:** merge the failed goal into the tree at the
steps_unreachable site (same arbiter call the retry path uses), or make
mark_goal_failed persist at the chokepoint.

**Solved en route:** the "3/4 steps completed" puzzle from LN-1 — those steps
were give-up *advances* (escalation path marks abandoned steps completed to move
past them), not real completions. Plan-view "completed" ≠ work done.

**LN-3 — CONFIRMED pattern (was a watch item): the question miner is a junk-goal
pump this run.** 3 failures in the first 5 min of failures.jsonl, ALL mined
"Open question:" goals: "What do you think?" (×2, LN-1/LN-2) and at 03:25:56Z
`g_12e2715f1351` "Is this goal really mine, or have I inherited it?" (also
steps_unreachable @ 3-attempt cap). The funnel candidate stage at ~cycle 460 is
dominated by more of the same, mined from Orrin's *own introspective narration*
("What assumption am I making…", "Are these genuinely useful, or selected by
inertia?"). Rhetorical self-questions become kind=research web-search goals that
are unanswerable by web search, burn attempts, and fail — honest failures, but a
treadmill. Run 11 shape: the miner needs a researchability filter (or route
introspective questions to the introspection path, not research), on top of the
LN-1 provenance skip. Early
research-memo artifacts contain raw page chrome ("Skip to content / You signed
in…") — watch whether the originality veto / quality gate keeps these out of
exemplar promotion.

**LN-2 CONFIRMED RECURRING (cycle ~1456 check):** failures.jsonl at 6 — a NEW
goal `g_3e7bedd27aed` "Open question: What truth am I working hardest to avoid?"
double-failed the same way (steps_unreachable 03:43:06Z, then re-adopted and
failed again 03:46:05Z at a THIRD site, "objective unmet after 2 attempts" — the
DoD evaluator). So the unpersisted-failure re-adoption bug fires on every failed
goal, not just the first. All 6 failures this run are miner-made "Open question:"
goals — LN-1/LN-3 stream unabated (~1 junk goal per ~10 min).

**RSS characterized (cycle ~2900): sawtooth, NOT a leak — and attribution works
this run.** Monitor alerted at 1549MB; peak 1681MB at cycle 2900 (last_fn
thread_continue), receded to ~870MB baseline within minutes. resource_history
.jsonl (per-cycle rss_mb + last_fn — the series Run 9 died without) shows 235
samples >1200MB spread since cycle 200 across many functions (research_topic,
assess_goal_progress, generate_intrinsic_goals…) — periodic alloc+release
(likely embedder batch / memory-graph compaction / GC sawtooth), flat baseline.
Memory guard's 2026-06-12 robustness gate (sustained growth across both window
halves + floor) correctly ignores the spikes. REVISED at cycle 4306: sawtooth
rides a slowly RISING floor — baseline by life-quarter 609/725/814/903MB, peaks
1425/1377/1681/1821MB (~+90-100MB floor per ~1100 cycles, near-linear). Projects
to ~1.5GB baseline / 2.5-3GB spikes by a 12k-cycle death; a back-half guard
load-shed is possible (sustained slope IS what the gate catches once above its
floor). Capture notes: (1) identify the ~800MB transient allocator; (2) split the
+300MB floor growth into designed accumulation (memories/embeddings/graph) vs
leak. Per-function attribution exists this run (resource_history.jsonl). Cycle 4704
update: floor ACCELERATING (~1031MB over last 200 samples vs 903 in q4; ~0.3
MB/cycle vs ~0.08 earlier), peak 2052MB @ cycle 4700 (narrative_update at sample
time — could be a background thread's alloc). Body states still "clear", guard
quiet. Cycle 6604 update: acceleration did NOT hold — floor back to the slower linear
rate (~1179MB at 6604, ~0.08MB/cycle), peaks ~2.3GB, body "clear," guard quiet.
Projection: ~1.5GB floor / ~2.6GB peaks at an 11k death — survivable; guard
load-shed possible but no longer likely.

**Cycle 1456 snapshot (~50 min):** production 31 attempts / 19 successes, 19
artifacts on disk, RSS 793MB (mild growth 713→793, no burst), aspirations still
rotating (output_producing committed at snapshot), no subgoal backlog.

**Early production snapshot (~cycle 463, first ~25 min):** 9 production attempts,
6 successes, 6 effect_artifacts files on disk (250B–6.8KB), effect_ledger 23
entries, 4 directional aspirations in_progress, committed goal rotating
(aspiration-self_understanding at snapshot).

**LN-4 — epistemic close-out stamps never reach comp_goals.json (gate-scoring
trap, found cycle ~8141).** ≥9 "Understand X more deeply" goals completed with
ZERO `question`/`answered` stamps in comp_goals.json (and no "answered" anywhere
in daemon `data/` state). Cause is ordering, not a dead mechanism:
`goal_closure.py:230` calls `mark_goal_completed` — which appends the goal to
COMPLETED_GOALS_FILE (goals.py:417/477) — and `stamp_closeout(goal)` runs AFTER,
at goal_closure.py:242. Stamps mutate the in-memory goal and merge into the live
tree (line 245) but the completed record was already persisted un-stamped. Also:
`intrinsic_generators.py` contains no `question` stamping at creation (R10-12
plan said it would), so `question_for()`'s title-derived fallback is carrying
everything. **At capture: score R10-12 from the goal tree / merged state, NOT
comp_goals.json, or the keystone will falsely read as never-fired. Run 11 fix:**
stamp before `mark_goal_completed`, or re-persist the comp_goals entry after
stamping; add creation-time question stamping.

**LN-5 — ignition saturation RELOCATED to drive_mastery (the exact relocating
pattern, cycle ~8141 window):** 310/311 recent cycles ignited (100%), 233 of them
`strong_signal(drive_mastery@1.00)` — a signal pinned at 1.00 feeding the gate,
same shape as Run 9's pinned ignition input on a new surface. Zero "saturat"
lines in activity_log.txt, so the R10 saturation tripwire either doesn't watch
drive_mastery, logs elsewhere, or hasn't tripped — verify which at capture before
calling it a tripwire miss.

**Mid-life vitals (cycle 8141, ~8h, single segment):** signal profile healthy and
motivation-led (motivation .79, confidence .75, reward_positive .54; no distress
domination). felt_bias_days = −2.97, i.e. pinned at the inflate bound — life has
felt good, time feels roomy. Ledger 199 rows / 34 credited / 27 deduped — anti-pump
guards earning-nothing paths working.
