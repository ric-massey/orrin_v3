# Data-file audit — 2026-07-03 run (plumbing pass)

A file-by-file health check of both data trees after the 11,333-cycle life, in
the style of `DATA_FILE_AUDIT_2026-07-02.md`. Method: mtime census against the
run window (birth 22:04 EDT / 02:04:14Z, death 12:15 EDT / 16:15:51Z), row/cap
verification, and cross-file consistency checks. **207 files were touched in
the final minute** — the write path was healthy to the end, shutdown clean
(`[run] clean exit`, single instance, zero `.corrupt` files, pre-reset snapshot
archived at 21:55). This audit doubles as the re-check of the 07-02 audit's
8-item fix list, since fix-round items 3/9/11 targeted it directly.

---

## 1. The 07-02 fix list, re-checked at the file layer

| 07-02 audit item | 07-03 state | Verdict |
|---|---|---|
| 1. `ctx.web_search` hook for the research runner | 11 `research_memo.md` + per-goal `doc_*.txt` corpora + step artifacts in `data/goals/artifacts/`; zero hook errors | ✅ **fixed** |
| 2. `cycle` plumbed into ledger + health_state | ledger `cycle: 0` rows **2 of 171** (Run 2: 119/150; the 2 are boot-second housekeeping writes); `health_state.cycle` **11,330** (was 0) | ✅ **fixed** |
| 3. Failed keystone step ⇒ goal FAILED | 3 research goals FAILED in `state.jsonl` with cascade records (Run 2: stuck READY) | ✅ **fixed** |
| 4. Failure writers → `failures.jsonl` | **94 rows**, ts/site/goal_id/title/reason, spanning the whole run (was 0 bytes) | ✅ **fixed** |
| 5. `final_thoughts_written` set after write lands | **still `False`** at death while `final_thoughts.json` is fully written at 16:15:51Z | 🔴 **NOT fixed** — the read-modify-write did not close the race |
| 6. Attribute symbolic effects to committed goal | `goal_id: null` **0 of 171** (was 116/150); 15 distinct goal ids | ✅ **fixed** |
| 7. Habituation eviction; slim trace rows | `habituation.json` **5,047 keys** (cap 5,000 working; was 15,469 in 9 h) ✅ · `trace.jsonl` still 3,000 rows × **~9.4 KB avg = 28.3 MB** 🟡 (down from 12.5 KB avg but still the fattest file per row) | 🟡 **half** |
| 8. Retire/rewire fossils | `rss_cache.json` now populates (8.8 KB — `read_rss` 7 picks cached ✅); `stagnation_signal_log.json` wrote (398 B ✅); still `{}` at birth-mtime: `proposed_goals`, `symbolic_plans`, `map_territory_audit_state`, `concepts`, `consolidation_queue`, `learned_phrases`, `failure_summary` (+ `model_failures.txt` 0 B) | 🟡 **two revived, seven still fossils** |

## 2. Dead or early-stopped organs (the blackout's file shadow)

All timestamps EDT. The ignition-starved integrative organs (see
`2026-07-03_deeper_pass.md` §2):

```
21:56  neutral_reflection_count.json  (pre-boot state, never touched)
22:09  idle_consolidation_log.json    (1 event all life)
22:10  crystallized_skills.json       (1 skill; 07-02: 3)
00:31  rule_firings.jsonl             (12 rows; 07-02: 97)
00:35  world_model_stats.json
01:11  symbolic_concepts.json         (5 concepts)
07:36  capability_descriptions.json
```

Counter-case proving it's ignition starvation, not module death: the dream
pass (timer-driven) wrote on schedule five times, 22:09→10:10, and
`ground_truth.jsonl` (263 rows) wrote to the death minute — 07-02's early-quit
grounding writer did **not** recur.

## 3. Caps, growth, and silting

**Caps verified holding** (no runaway files):

```
long_memory.json     2,001 entries      trace.jsonl            3,000 rows
events.jsonl         3,000 rows         evaluator_wal.jsonl      669 rows
attention_history      500              cognition_history        500
telemetry_history      240              reward_trace              50
announcements           50              monitor_verdicts         300 (cap hit — again all stuck_step)
prediction_metrics.jsonl 2,502 rows (AR6 capped file working)
telemetry_archive.jsonl 11,325 rows (durable archive — correct)
speech_log.json        150 entries
```

**Growth candidates to watch** (fine at 14 h, questionable at multi-day):

- `trace.jsonl` — 28.3 MB for 3,000 rows. Row slimming remains undone.
- `memory_graph.jsonl` — **36,531 rows / 5.8 MB**, append-only, up from
  33,825 in a shorter life. No compaction story yet.
- `production_loop.jsonl` — 11,333 rows / 5.2 MB, one row per cycle,
  append-only across lives unless rotated.
- Rotation healthy: 12 activity-log rotations (~70 min each), 20
  private-thoughts rotations (~1.5 MB each). Both working as designed.

## 4. State desyncs and honesty gaps

- **`final_thoughts_written: false`** at death — the one carried desync
  (item 5 above), third run in a row.
- **12 v1↔v2 resurrection repairs** in the WAL/logs — systematic leak at the
  completion bridge, §8 S8 escalation triggered (`run_analysis.md`).
- **Two `generic`-kind v2 goals stuck READY** all run (`NEW→READY`, then
  nothing) — a *scheduling* coverage gap, distinct from Run 2's status-honesty
  gap, which is fixed.
- `outcome_metrics.json` — the run straddles midnight and lands in **two daily
  rows**; naive single-row reads under-report every counter. Flag for any
  future §8 tooling.
- New: `[emotion_buffer] dropped delta for unknown emotion 'social_penalty'`
  ×37 — an emitter naming an emotion the buffer doesn't know; the penalty
  silently no-ops.

## 5. Funnels (cross-file arithmetic)

- **Aspiration funnel:** scoreboard **162 generated → 14 attempted → 14
  completed** (07-02: 87 → 2 → 0). The middle of the funnel is alive. Skew
  note: 158 of 162 generated candidates target one aspiration
  (world-knowledge); diversity exists only at the credit layer.
- **Effect attribution:** 171 rows, 0 anonymous, 102 nonzero-significance;
  dedupe marked on 40 rows, rate-cap on 26 — the honesty gates leave visible
  fingerprints now.
- **Production funnel:** attempts 163 = ledger rows drained; successes 102 =
  nonzero-significance rows exactly; rejections classified (33 dup / 28
  low-sig); handoffs 0 (no conscious staging path — behavioral, not plumbing).
- **Announcement channel:** still 50/50 template felt-state (2 distinct
  bodies); the expressed-note channel: 662 sends, ~5 distinct bodies, of which
  2 are the first-ever *"something I actually found out"* payloads.

## 6. Two-tree split and infrastructure — healthy

- `brain/data/` vs root `data/` behaved; `data/goals/` WAL (393 rows) and
  `state.jsonl` (60 goals) consistent, compacted at shutdown; artifacts tree
  holds real content for 11 research goals + housekeeping receipts.
- Locks: per-file `.lock` files present and empty; single instance all run;
  no stale instance lock left behind.
- Archives: 3 pre-reset snapshots in `_archive/`; rotated logs complete.
- Spine counts agree end-to-end: `cycle_count.json` 11,333 =
  `production_loop.jsonl` rows = calibration n (Brier 0.0346, bias +0.0601);
  telemetry archive 11,325 (8 boot cycles pre-telemetry — normal).

## Fix list from this audit (smallest first)

1. Register (or stop emitting) the `social_penalty` emotion — 37 silent no-ops.
2. Set `final_thoughts_written` transactionally with the write — third strike.
3. Schedule `generic`-kind v2 goals (unblocks the synthesis make-goal).
4. Slim `trace.jsonl` rows; compaction story for `memory_graph.jsonl`.
5. Retire or rewire the seven remaining fossils (`proposed_goals`,
   `symbolic_plans`, `map_territory_audit_state`, `concepts`,
   `consolidation_queue`, `learned_phrases`, `failure_summary`).
6. Teach §8 tooling to sum `outcome_metrics` rows when a run crosses midnight.
7. The big two filed in `run_analysis.md`: v1/v2 completion bridge (S8) and
   `mark_reused` call sites (S7).

*Generated 2026-07-03, plumbing pass over both data trees. Analysis only; no
code changed by this write. Companion: `2026-07-03_deeper_pass.md` (behavioral
connections).*
