# Data-file audit — 2026-07-02 run (plumbing pass)

A file-by-file health check of both data trees after the 10,071-cycle life,
in the style of `DATA_FILE_AUDIT_2026-06-25.md`. Method: mtime census against the
run window (birth 07:18 EDT / 11:18:58Z, death 16:31 EDT / 20:31:07Z), row/cap
verification, and cross-file consistency checks. 58 files were alive at the death
second, 21 within the final minute — the write path was healthy to the end, and
the shutdown was clean (`[run] clean exit — not restarting`, single instance,
lock file present, pre-reset snapshot archived).

---

## 1. Dead at birth — 17 files never written all run

| File | State | Assessment |
|---|---|---|
| `failures.jsonl` | **0 bytes** | 🔴 **Broken seam.** Nine goal failures this run (6 deadline + 3 fast-fail) and the failures log recorded none of them. `failure_summary.json` is also `{}` and `model_failures.txt` 0 bytes. Failure telemetry lives only in `activity_log` prose — nothing machine-readable survived. (`failure_review_state.json` was last touched 07:24.) |
| `known_persons.json` | mtime = birth second | 🔴 The person-model finding from the first pass, confirmed at the file layer: two real chat sessions, zero writes. |
| `rss_cache.json` | `{}` | 🟡 `read_rss` was picked 9× yet the cache never wrote — either every fetch failed silently or the cache path is disconnected. |
| `proposed_goals.json` | `{}` | 🟡 Goal proposals evidently flow elsewhere now (production_funnel/intrinsic spawns); file is a fossil — retire or rewire. |
| `learned_phrases.json` | `{}` | 🟡 The mouth's phrase-learning store never populated — consistent with speech self-evaluation barely running (§5). |
| `stagnation_signal_log.json` | `{}` | 🟡 A life with a 1.7 h stuck loop and a 74% rest scream logged zero stagnation signals. Either thresholds are wrong or the writer is dead. |
| `symbolic_plans.json`, `map_territory_audit_state.json`, `concepts.json`, `consolidation_queue.json` | `{}`/empty | 🟡 Empty organs; concepts/consolidation may be by design (coherent-but-adult — no concept promotion), the other two look like fossils. |
| `quality_standard_revisions.json` | `{}` | 🟢 Correct by design — revisions are human-ratified only; none occurred. |
| `behavioral_functions_list.json`, `cognitive_functions.json`, `control_signals_model.json`, `schema_version.json` | seeded at birth | 🟢 Static definition files; expected. |

## 2. Early-stoppers — organs that wrote only in the first hours

All timestamps EDT. These are the file-layer shadow of the rest-drive ignition
monopoly (`2026-07-02_deeper_pass.md` §2):

```
07:36  capability_descriptions.json      10:25  crystallized_skills.json
08:41  demand_objective_credit.json      10:25  symbolic_concepts.json
10:24  idle_consolidation_log.json       10:36  neutral_reflection_count.json
                                         10:40  rule_firings.jsonl (97 rows)
                                         10:45  world_model_stats.json
```

Every consolidation/abstraction organ stopped inside 07:18–10:45 and never wrote
again in the following ~5.75 h. One outlier worth its own look:
`ground_truth.jsonl` (643 rows) stopped at **15:35**, ~56 min before death — the
grounding-truth writer quit early while its consumers kept running.

## 3. The `cycle` field is not plumbed everywhere

A cross-cutting bug: several consumers record `cycle: 0` because the cycle count
never reaches them.

- `effect_ledger.jsonl`: **119 of 150 rows have `cycle: 0`** — every AR1
  `symbolic_artifact` and runner `file_write`; only the conscious-lane
  `note_novel` rows carry real cycles. Any future "when was this effect made"
  analysis (e.g. S5 over time) is blind for the new kinds.
- `health_state.json`: `cycle: 0`, and `total_healthy_cycles` = **2,014** of
  10,071 — the health checker either runs on a 1-in-5 cadence or misses cycles;
  worth deciding which before trusting its streaks.
- `production_loop.jsonl` carries cycles correctly (1…10,071) — the pattern is
  per-writer, so the fix is at each writer's callsite, not global.

## 4. State desyncs (small but real)

- `runtime_lifetime.json` ends with **`final_thoughts_written: false`** while
  `final_thoughts.json` was fully written at 20:31:07Z. Whichever writer owns the
  flag lost the race at shutdown. Harmless today; a resurrection-guard reading
  that flag would be misled.
- Research goals whose keystone step FAILED terminally remain **READY** in the v2
  store (WAL shows `NEW→READY→READY`, step `FAILED att 3`, no goal transition) —
  status honesty gap, filed in the deeper pass §5.
- `comp_goals.json` status-at-copy ("in_progress" entry skipping
  `credit_objectives`) — known, part of the S6 chain.

## 5. Caps, growth, and silting

**Caps verified working** (no runaway files):

```
long_memory.json        2,001 entries (cap ~2k)   trace.jsonl            3,000 rows
events.jsonl            3,000 rows (DECISION only) evaluator_wal.jsonl   1,001 rows
attention_history        500  cognition_history 500  telemetry_history    240
reward_trace              50  monitor_verdicts  300  announcements         50
telemetry_archive.jsonl 10,065 rows (the durable archive — correct)
```

**Growth candidates to watch** (fine at 9 h, questionable at 25 h+):

- `trace.jsonl` — 3,000 rows but **12.5 KB average row** (37.6 MB file). The cap
  holds the row count, not the bytes; each row carries a full emotion/committed
  snapshot. Consider trimming the row schema.
- `habituation.json` — **15,469 `wm:<hash>` keys in 9.2 h** (~1,700/h) with no
  visible eviction. At the 06-25 run's length this is a ~40k-key dict loaded per
  access.
- `memory_graph.jsonl` — 33,825 rows / 5.4 MB, append-only.
- `activity_log` rotation works (9 rotations to `rotated/`, ~55 min each);
  `private_thoughts` rotated twice near 958 KB. Both healthy.

**Odd caps:** `events.jsonl` contains **only `DECISION` events** — either the
name over-promises or other event types lost their writer. `speech_log.json`:
344 entries, only **15 evaluated / 9 ever retrieved** — the speech-quality
feedback loop barely engages its own data.

## 6. Funnels that narrow to zero (cross-file arithmetic)

- **Aspiration funnel:** `aspiration_scoreboard` = **87 generated → 2 attempted →
  0 credited**. The S6 failure isn't just broken crediting links — the middle of
  the funnel (attempts) is already near-empty.
- **Effect attribution:** 116 of 150 ledger rows have `goal_id: null` (all
  symbolic artifacts). AR1 records the *what* but usually not the *for-whom*;
  aspiration crediting can't work on anonymous effects. The 31 attributed
  `ltc_aspiration-*` rows are the exception, and they hit the S6 dead-end.
- **Announcement channel:** 50/50 entries are the same felt-state template from
  `system_presence` — the person-facing channel carries no findings, plans, or
  questions. Matches the notes pathology (94/100 template).

## 7. Two-tree split and infrastructure — healthy

- `brain/data/` vs root `data/` split behaved; no path-split casualties found
  this run. `data/goals/wal.log` last writes at 15:40 (the final goal step) with
  `state.jsonl` compacted at shutdown — consistent, not a stall.
- Locks: per-file `.lock` files present and empty (held-and-released);
  `.orrin.instance.lock` single instance all run.
- Archives: `_archive/` holds both pre-reset snapshots + rotated logs;
  `data/goals/artifacts/` holds only the 3 housekeeping `_ok.txt` stubs (the
  artifact channel's honest, thin truth).
- `calibration_state.json` (Brier 0.0181, n=10,071) and `cycle_count.json`
  (10,071) agree with the run log's final cycle — the spine counts are
  consistent end to end.

## Fix list from this audit (smallest first)

1. `ctx.web_search` hook for the research runner (one line of wiring, unblocks
   AR2 end-to-end). *(from deeper pass, filed here for completeness)*
2. Pass the real cycle into `symbolic_effects` / runner effect records and
   `health_state`.
3. Failed-keystone-step ⇒ goal FAILED (or explicit retry state) in the v2 store.
4. Point the failure writers at `failures.jsonl` (or delete the file and its
   readers — one or the other).
5. Set `final_thoughts_written` after the write actually lands.
6. Attribute symbolic-artifact effects to the committed goal when one exists
   (kills the 116-row `goal_id: null` blind spot; feeds S6).
7. Eviction policy for `habituation.json`; slim `trace.jsonl` rows.
8. Retire or rewire the fossil files (`proposed_goals`, `symbolic_plans`,
   `map_territory_audit_state`, `rss_cache` if read_rss stays).

*Generated 2026-07-02, plumbing pass over both data trees. Analysis only; no code
changed by this write. Companion: `2026-07-02_deeper_pass.md` (behavioral
connections).*
