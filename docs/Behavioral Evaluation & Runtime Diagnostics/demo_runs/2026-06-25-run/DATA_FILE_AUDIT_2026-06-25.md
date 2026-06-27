# Data-File Audit — 2026-06-25 run

Scope: integrity, growth, and anomaly audit of the persisted state files in
`brain/data/` and the root `data/` trees, for the run that ran overnight
24→25 Jun. This is a **data-file** audit (file health, sizes, corruption,
state-snapshot anomalies) — the behavioral narrative lives in the sibling
`*_run_analysis.md` / `*_who_is_he.md` docs and is not repeated here.

Method: JSON/JSONL validity parse of every file, size/growth survey, rotation
cadence reconstruction from rotated filenames, and read-out of the end-of-run
state snapshots. All findings are from the on-disk files as of shutdown.

---

## Run boundaries (ground truth)

| Field | Value |
|---|---|
| born_at | 2026-06-24T03:37:32Z |
| last_active_at | 2026-06-25T04:41:21Z |
| wall clock | ~25 h 4 m |
| cycles (`cycle_count`) | 17,352 |
| cycles logged (`production_loop.jsonl`) | 17,352 (1:1, no gaps) |
| slept | 6,236 s (~1.7 h) |
| health streak | 3,468 healthy cycles, sick_streak 0 |
| `runstate` | `{"clean": true, ...}` — **clean shutdown** |

Cycle count, production-loop line count, and runstate all agree. The run
terminated cleanly.

---

## Integrity — PASS (with one exception)

- **Every `*.json` parses** except one (see I-1 below).
- **Every `*.jsonl` tail parses** — no truncated/partial final records:
  - `trace.jsonl` 3,000 · `events.jsonl` 3,000 (both at the telemetry cap)
  - `production_loop.jsonl` 17,352 · `telemetry_archive.jsonl` 17,310
  - `memory_graph.jsonl` 31,168 · `effect_ledger.jsonl` 256
  - `evaluator_wal.jsonl` 996 · `failures.jsonl` 27 · `ground_truth.jsonl` 13 · `rule_firings.jsonl` 180
- 2-byte container files (`consolidation_queue`, `rule_synthesis`,
  `tool_requests`, `vocabulary`) hold valid empty `[]`/`{}` — normal.
- **Lock files clean**: 118 `*.lock` mutex sidecars are all 0 bytes. The only
  non-empty lock is `.orrin.instance.lock` (PID 57845, process now dead) —
  expected residue after a clean shutdown, not a stale-lock hazard.

---

## Findings (triaged)

### Integrity

**I-1 · `proposed_goals.json` is 0 bytes — invalid JSON.** (low)
Every other state file that represents "empty" writes `[]`/`{}`; this one is
truncated to zero length and will raise `JSONDecodeError` on `json.load` rather
than yielding an empty list. Latent crash risk for any consumer that doesn't
guard the load. Fix: writer should emit `[]`, and/or readers should treat
empty file as empty list.

### Faults during the run

**F-1 · `routers.telemetry.chat_history` — FileNotFoundError.** (low/medium)
`failure_summary.json` records one fault at 04:16:43Z:
`FileNotFoundError: .../brain/data/chat_log.json`. The telemetry chat-history
router reads a file that is never created. Single occurrence this run, but it's
a hard error on a code path that will fire again whenever that endpoint is hit.
Either create/seed `chat_log.json` or make the router tolerate its absence.

**F-2 · `final_thoughts_written: false` despite clean shutdown.** (medium)
`lifespan.json` shows `clean=true` in runstate but the end-of-life ritual never
flushed final thoughts. The shutdown path closes cleanly but skips/aborts the
final-thoughts write. Worth confirming whether this is by-design (only on
death, not on normal stop) or a silently-skipped step.

### Behavioral-data anomalies (visible in the state files)

**A-1 · Production starvation — he made almost nothing.** (high, known issue)
Across 17,352 cycles with a committed goal present in 17,350 of them:
`production_attempt = 4`, `production_success = 4`, `effect_rejection = 0`,
`production_handoff_count = 0`. The `effect_ledger.jsonl` holds 256 records and
**all 256 are `note_novel`** (internal novelty notes) — no other effect kind.
So the entire run's externalizable output is 4 production events plus a pile of
internal notes. This is the reward-denominator / "makes nothing" problem
(see `memory: project_reward_denominator`) showing up directly in the ledger.

**A-2 · Internal-thought write-rate spiked ~5× in the final ~5.5 h.** (medium)
Rotation cadence (1.5 MB per rotation) tells the story:
- `private_thoughts.txt`: **0 rotations** for the first ~19.5 h, then **20
  rotations** between 23:00Z and 04:31Z — one every ~16–18 min.
- `activity_log.txt` over that same final window: only ~4 rotations (~1.7 h each).

So internal-thought volume ran roughly 5× the activity-log volume in the last
stretch while the earlier 19.5 h produced none. The internal monologue ran
away near the end. This coincides with A-3.

**A-3 · Ended in an undirected brooding loop.** (medium)
At shutdown `rumination_loops.json` holds 3 active loops, all `mode: brooding`,
one `escalated: true`:
- "A restlessness without a target. Something isn't right and I can't locate what." (return_count 6, escalated)
- "Friction with no clear source. I keep reaching for what's blocking and finding nothing." (return_count 5)
- "The irritation is real. The object of it isn't clear." (return_count 1)

`tensions.json` carries one matching active tension (`source: rumination`,
17 cycles active). The run ended in a self-sustaining, target-less dysphoric
loop — consistent with the A-2 write-rate spike being rumination spill.

**A-4 · End-state drive vector is saturated/depleted at the rails.** (low, context)
`motivation_state` at shutdown: `competence 1.0` and `affect_stability 1.0`
(both pinned high), `restlessness 0.0`, `novelty_exploration_drive 0.038` and
`world_mastery 0.028` (both depleted), `autonomy 0.88`, `connection 0.63`.
Mood: valence +0.12, **energy 0.997** (pinned), stability 0.92. Several drives
sitting hard against 0.0/1.0 bounds is worth watching — saturated drives stop
discriminating and can be what leaves restlessness "without a target" (A-3).

**A-5 · `outbox/notes.json` (80 KB) accumulated but undelivered.** (low)
Full of entries shaped like *"Write one concrete thing learned about … to
working memory"* with `recipient: "Ric"`. These read as intended-for-user notes
that piled up in the outbox without being delivered. Confirm whether the outbox
is meant to drain to the user; if so, delivery isn't happening.

### Storage / growth

**S-1 · Per-cycle JSONL files grow unbounded.** (low, monitor)
- `trace.jsonl` 29 MB — 3,000 lines @ ~10 KB/line. Capped at 3,000 records, so
  bounded, but each record is heavy (10 KB). Largest file on disk.
- `production_loop.jsonl` 8.0 MB — 17,352 lines, **one per cycle, uncapped**.
- `telemetry_archive.jsonl` 6.3 MB — 17,310 lines, uncapped.
- `memory_graph.jsonl` 4.8 MB — 31,168 lines, uncapped.
- `data/goals/`: `state.jsonl` 2.4 MB + `wal.log` 2.0 MB, growing.

None are a problem at 25 h, but `production_loop`, `telemetry_archive`,
`memory_graph`, and the goals WAL all scale linearly with cycle count and have
no cap. A multi-day run will need rotation/compaction on these the way
`activity_log`/`private_thoughts`/`trace` already have.

---

## Round 2 — content/model files (self_model, graphs, metrics)

These come from the files I hadn't opened in the first pass: the self-model
pair, the knowledge/causal/world graphs, prediction stats, decision stats, and
`outcome_metrics`. Several are more serious than anything in Round 1.

**C-1 · PLANNING prediction collapse — 893 predictions, 0 correct.** (high)
The planning predictor is structurally broken, and three files agree:
- `prediction_domain_stats.PLANNING`: `total 893, correct 0, reliability 0.0011`.
- `symbolic_self_model.PLANNING`: `prediction_error 0.9989`, `mean_hits 1072.5`
  (i.e. heavily *used*), `quality 0.151`.
- `domain_error_rates.PLANNING`: 0.9989.

So the planning rules fire constantly and are wrong essentially every time, yet
remain active. `self_belief_revisions` shows exactly one downward nudge
(PLANNING −0.15 at 07:42Z 06-24) and nothing since — the system noticed once and
then stopped correcting. This is the single worst learning signal in the run.

**C-1b · Data bug: `accuracy` field doesn't reflect `correct/total`.** (medium)
Same record reports `accuracy: 0.5` while `correct=0 / total=893` (true 0.0).
The `accuracy` field is stuck at the 0.5 prior and isn't being recomputed from
the running counts; only `reliability` (0.0011) tells the truth. Any consumer
reading `accuracy` is being misled into thinking PLANNING is a coin-flip rather
than a near-total failure.

**C-2 · Goal failure storm — ~94% of goals fail.** (high)
`outcome_metrics.json`, 2026-06-24 row:
`goals_completed 603` vs **`goals_failed 9279`**, `goals_retired 1746`,
`completion_rate 0.051`, `maintenance_selections 78180`, `abandonment_closures
149`, `store_desyncs_repaired 12`. The 06-25 row: `completed 0 / failed 187 /
retired 30`, completion_rate 0.0. So the goal layer churns thousands of goals
and fails ~19 for every 1 it completes — against only **4 real production
attempts** (A-1). The machinery is extremely busy producing and discarding
goals while almost nothing reaches output.

**C-3 · Narrative / autobiography froze ~2 h into a 25 h life.** (medium)
`autobiography.json` has `chapters: 1` and its last narrative write is
`2026-06-24T05:24:34Z` (born 03:37Z) — only the `last_session_close` field was
touched at shutdown. Cause is visible in `narrative_pressure.json`:
`next_min_interval_s = 95219` (**26.4 h**), set at that same 05:24Z check. The
narrative engine scheduled its next allowed update further out than Orrin's
entire remaining lifespan, so it never fired again. Looks like an
interval-computation bug, not intent.

**C-4 · SOCIAL domain is completely undeveloped.** (medium)
`symbolic_self_model.SOCIAL`: `rule_count 0, mean_confidence 0.0, quality 0.04`.
`self_model.knowledge_domains.SOCIAL = 0.04`, listed as the #1 weakness.
`relationships.json` tracks only the 5 internal peer-auditors (observer,
reward_auditor, goal_auditor, emotion_historian, architect) — no humans;
`known_persons` has just Ric. Despite "usefulness/connection" being a stated
core value and `connection` drive at 0.63, zero social rules were ever learned.

**C-5 · Rule-revision queue never drains; grounding not tracked.** (medium)
`rule_revisions.json` = 37 entries, **all `status: pending`**; matches
`symbolic_self_model.rule_health.pending_revisions 37`. Revisions are being
proposed but not applied. Same block: `grounding.total_tracked 0`,
`mean_grounding 0.5` (default) — rule grounding is reported but never actually
computed. Of 46 rules, 16 are tombstoned and 30 active.

**C-6 · Action mix is introspection-dominated.** (medium, supports A-1)
`decision_stats.json`: `look_outward 5082` (avg reward 0.198) +
`generate_intrinsic_goals 4392` (0.480) ≈ **55% of all cycles**, with
`assess_goal_progress 876` and `seek_novelty 266` adding more inward churn.
`leave_note` fired only **52** times. The action distribution is the behavioral
mirror of the production starvation: cycles overwhelmingly spent looking/
goal-spawning, almost never emitting.

**C-7 · Large dead-rule populations in world_model.** (low)
`world_model_stats`: `GENERAL` 116 rules / **1 hit**; `COGNITIVE` 1297 rules /
516 hits. Most GENERAL world-model rules are inert. (Note this 1297/46 mismatch
vs `symbolic_self_model.total_rules 46` is two different rule stores, not a
discrepancy.)

**C-8 · Minor self-model inconsistency.** (low)
`symbolic_self_model.strong_areas = []` while `self_model.strengths =
["COGNITIVE"]`. The two self-models disagree on whether any domain is strong.

---

## Bottom line

The persistence layer is **structurally healthy**: clean shutdown, no
corruption, no truncated logs, locks released. The bugs and behavioral signals
in the *content* are where the attention belongs.

Top issues, ranked:
1. **C-2 goal-failure storm** — ~9,300 goals failed vs 603 completed in a day,
   against only 4 real production attempts (A-1). The goal layer is in
   high-churn idle.
2. **C-1 PLANNING predictor collapse** — 893 predictions, 0 correct, rules
   still firing 1000+ times; plus the `accuracy`-field bug (C-1b) that hides it.
3. **A-1 production starvation** — 17k cycles, 1 committed goal almost the whole
   time, 4 productions, ledger is 256 internal notes and nothing else.
4. **A-2/A-3 end-of-run brooding** — escalating target-less rumination in the
   last ~5.5 h, flooding the internal-thought log ~5×.
5. **C-3 narrative freeze** — autobiography stuck at 1 chapter because the
   narrative engine scheduled its next update 26.4 h out (longer than its life).

Small fix-its: `proposed_goals.json` 0-byte → `[]` (I-1); `chat_log.json`
FileNotFound (F-1); `final_thoughts_written` false on clean stop (F-2); the
`accuracy` field not recomputed from counts (C-1b); the 37 un-drained rule
revisions and never-computed grounding (C-5).

Cross-cutting theme: nearly every signal points the same way — Orrin spends
enormous effort *inside* (looking outward, spawning/failing goals, ruminating,
predicting badly in PLANNING) and almost none of it converts to externalized
output or durable learning. The persistence is fine; the economy of attention
and the goal/prediction calibration are not.
