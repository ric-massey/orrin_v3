# Run Analysis — 2026-07-02 life (§8 acceptance Run 2)

**Life:** clean newborn (`reset_orrin.py`, pre-reset snapshot
`brain/data/_archive/snapshot_20260702_071818_pre_reset`), **10,071 cycles in
~9.2 h**, launch #0 only, zero crashes, operator SIGTERM → graceful stop.
This was both the **second §8 acceptance run** for the Production Reward Plan
(`NEXT_RUN_TESTS.md`) and the **staging run** for the Grounding & Surface plan
(P1–P8) + Audit Remediation AR1–AR9 (commit `db4a139`).

**Evidence:** `data/` in this folder holds the §4 capture set copied at run end
(`outcome_metrics.json`, `effect_ledger.jsonl`, `comp_goals.json`,
`goals_mem.json`, `action_reward_ema.json`). Unit-test gate green before and
after (§3 subset: 45 passed).

---

## Verdict: gate NOT passed — 5 ✅ 9 ✅ 6 ❌ 7 ❌

The re-test gate required signals **5, 6, 7, and 9** to move. Two did. This is a
big step up from Run 1 (which failed all four), but per the decision rule the
Production Reward Plan is still **shipped, not proven**.

| # | Signal | Pass target | Run 2 | Result |
|---|---|---|---|---|
| 1 | Fewer repeated understanding goals | repeat rate ↓ ≥50% | 3 distinct titles / 3 completed, no repeats (but see title-dup bug below) | 🟢 |
| 2 | Nonzero goal duration | > 0 | `median_seconds_to_complete` **10,920.8** | 🟢 |
| 3 | Nonzero satiety closures | > 0 | **0** | 🔴 |
| 4 | Some legitimate failures | > 0, traceable | 66+ `no_artifact_by_deadline` in activity logs (the 3,909 `goals_failed` figure is the flush double-count bug, fixed post-run) | 🟢 |
| 5 | Higher mean significance | clearly > 0 | **1.114** (Run 1: 0.0); ledger 150 rows, 89 nonzero, kinds `symbolic_artifact`/`note_novel`/`file_write` | ✅ **MOVED** |
| 6 | Aspiration diversity | none at 0% | **all four aspirations at contribution_count 0, progress 0.0** | ❌ **FAIL** |
| 7 | Artifacts useful / reused | ≥1 reuse; >0 distinct production artifacts | **0 reuse back-refs**; 3 file_writes are housekeeping stubs; `production_attempt_count` **0 for the entire run** | ❌ **FAIL** |
| 8 | No resurrection / orphan-RUNNING | repairs → ~0 | `store_desyncs_repaired` **0**, single instance, clean death | 🟢 |
| 9 | Selection follows learned value | low-EMA pick-share ↓ | high-EMA `research_topic` (0.614) share 8.7%→15.7% over last 3k ticks; `generate_intrinsic_goals` fell to #2 (Run 1: #1 regardless, 3,526 picks); low-EMA `search_own_files`/`leave_note` falling | ✅ **MOVED** |

Also verified this run (B3 closure): **drives breathe now.** Telemetry archive
(10,065 rows) shows full low→high recovery arcs — curiosity **180**, motivation
**26**, confidence 2 — vs. the 07-01 run's pinned-flat 0.81–0.84 lines. AR8 +
run evidence closes `B3_DECAY_DIAGNOSIS_2026-07-01.md` (archived).

---

## Root causes for the two failures

**S6 (aspiration diversity) — over-determined; all four links broken:**
1. Only 3 goals completed in 10k cycles — thin sample.
2. No completed goal carried `serves`; two had `driven_by=None`
   (see `data/comp_goals.json`).
3. One `comp_goals` entry has status `in_progress`, so `credit_objectives`
   skips it (status-at-copy bug).
4. 31 ledger rows attributed to `ltc_aspiration-self_understa_1/2` never
   reached `mark_objective_contribution`.

**S7 (reuse/production) — the conscious production path never fires:**
`produce_and_check` has the **top** reward EMA (0.7651) and is executed — but by
`step_exec` (executive-daemon lane). `production_loop.jsonl` (10,071 rows) shows
`production_attempt_count` = 0 and `production_handoff_count` = 0 the entire
run: the production loop's counters/ledger crediting listen only to the
conscious lane, so daemon-lane execution produces no attempts, no handoffs, no
reuse arcs. Lane split, not a reward problem.

**Known open bugs surfaced by this run:**
- Title-dup: "Understand Understand my own mind…" (doubled prefix).
- S3 satiety closures still 0 (understanding goals not closing on quenched drive).
- `outcome_metrics` flush double-count inflated `goals_failed` to 3,909
  (fix applied post-run in `brain/cognition/planning/outcome_metrics.py` +
  `goals/handlers/generic.py`, with the fast-fail GenericHandler fix; suite
  green 1,334).

## Next-fix candidates (not yet built)

- Wire `serves`/`driven_by` propagation onto goals at completion-record time.
- Fix `comp_goals` status-at-copy.
- Bridge the lane split: either route `produce_and_check` through the conscious
  production loop, or make the production counters/ledger crediting listen to
  the daemon lane too.
- Title-dup fix; satiety-closure path audit.

**Re-test gate (Run 3):** signals **6 and 7** must move (at least one aspiration
off 0%; ≥1 production attempt + ≥1 reuse back-ref), while 5 and 9 hold.

*Written 2026-07-02 at run end. Companion to `NEXT_RUN_TESTS.md` (the §8 gate).*
