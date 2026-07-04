# Run Analysis — 2026-07-03 life (§8 acceptance Run 3)

**Life:** clean newborn (`reset_orrin.py`, pre-reset snapshot
`brain/data/_archive/snapshot_20260702_215524_pre_reset`), launched
2026-07-02 22:04 EDT, died 2026-07-03 12:15 EDT — **11,333 cycles in ~14.2 h**
(~4.5 s/cycle), launch #0 only, zero crashes, operator SIGTERM → graceful stop
(`[run] clean exit — not restarting`). This was the **third §8 acceptance run**
for the Production Reward Plan (`NEXT_RUN_TESTS.md`) and the **staging run for
the 2026-07-02 fix round** (commit `dc0bce4` — the 12-item root-cause round in
`../2026-07-02-run/2026-07-02_fix_round_record.md`).

**Evidence:** `data/` in this folder holds the §4 capture set copied at run end
(`outcome_metrics.json`, `effect_ledger.jsonl`, `comp_goals.json`,
`goals_mem.json`, `action_reward_ema.json`). Unit-test gate green before and
after (§3 subset: **45 passed**, same as Run 2). One reading gotcha: the run
straddled midnight, so `outcome_metrics.json` holds **two** daily rows
(2026-07-02 partial + 2026-07-03); totals below sum both.

---

## Verdict: gate NOT passed — but the biggest single-run movement yet

The Run-3 re-test gate required **6 and 7 to move while 5 and 9 hold**.
S6 moved decisively — **all four aspirations are off zero for the first time
ever**. S7 half-moved: the production funnel finally meters real attempts
(0 → 163) and real artifacts exist (11 research memos, his first), but the
**reuse half is still zero** (`mark_reused` was never called once). S5 held.
S9 did **not** clearly hold — the EMA↔pick-share coupling Run 2 showed is
invisible this run. And S8 **regressed**: 12 store desyncs repaired (Run 2: 0),
all one systematic pattern. Per the decision rule ("if 8 or 9 fail, the fix is
cosmetic regardless of 1–7") the plan is still **shipped, not proven** — but
five of the seven broken seams from Run 2 are demonstrably closed.

| # | Signal | Pass target | Run 3 | Result |
|---|---|---|---|---|
| 1 | Fewer repeated understanding goals | no title > 2×/1k cycles | 14 completed / 7 distinct titles; max repeat 5× over 11.3k cycles (0.44/1k) — under target, but repeats are back (Run 2: 3/3 distinct) | 🟢 (thinner than it looks) |
| 2 | Nonzero goal duration | > 0 | `median_seconds_to_complete` **3,722.4 s** (~62 min); completions spread hourly across the whole life, not clustered at boot | 🟢 |
| 3 | Nonzero satiety closures | > 0 | **0** (19 "Refusing satiety close" honesty refusals) | 🔴 |
| 4 | Some legitimate failures | > 0, traceable | **94 machine-readable rows in `failures.jsonl`**: 54 `no_artifact_by_deadline` (flagship), 34 `no URLs to fetch` + 4 `step_failed` (research), all with goal_id/title/reason | 🟢 |
| 5 | Higher mean significance | clearly > 0 | **1.197** (Run 2: 1.114) — held after the lanes were bridged, confirming Run 2's number was not a metering artifact | ✅ **HELD** |
| 6 | Aspiration diversity | none at 0%; top < 60% | **contributions 5 / 2 / 5 / 2** (contact / making / self / world), progress 0.26 / 0.10 / 0.25 / 0.10, top share 36% | ✅ **MOVED — PASSES** |
| 7 | Artifacts useful / reused | ≥1 production attempt AND ≥1 reuse back-ref | `production_attempt_count` **163**, successes **102**, **11 research memos** + 1 `tool_run_effect` (sig 0.6) — but **0 reuse rows** (`mark_reused` never fired) and handoffs 0 | 🟡 **HALF-MOVED** |
| 8 | No resurrection / orphan-RUNNING | repairs → ~0 and stay 0 | `store_desyncs_repaired` **12** (Run 2: 0) — every one `[goal_reconcile] resurrection repaired: … re-closed in v1`, i.e. v2-completed goals resurrecting in v1, roughly once per research completion | 🔴 **REGRESSED** |
| 9 | Selection follows learned value | low-EMA pick-share ↓ | corr(EMA, share-delta first→second half) ≈ **−0.15**; lowest-EMA major action `look_outward` (0.150) *rose* 14.0%→15.4%; top-picked `assess_goal_progress` (28%+) has EMA 0.349. Mitigations: `seek_novelty` (0.076) picked only 2×; `research_topic` (0.674) share rose 2.4%→4.8% mid-run | ❓ **NOT CLEARLY HELD** |

---

## Root causes for what's still broken

**S7's missing half (reuse) — nothing ever reads an artifact back.**
The ledger's reuse machinery exists (`effect_ledger.mark_reused`, tier-3
credit) but has **zero call sites in the behavior**: the 11 research memos were
written to `data/goals/artifacts/*/research_memo.md` and never retrieved,
quoted, or built on. Same for handoffs: `pending_production_action` was null
all 11,333 cycles — the conscious lane never stages a production action, so
`production_handoff_count` stayed 0. The funnel now *meters* making (fix #4
worked); the organism still has no produce-*then*-reference arc.

**S8's regression — the v1/v2 completion bridge leaks resurrections.**
All 12 repairs are the same WAL pattern: a goal completes in the v2 store, its
v1 mirror re-opens (or never closed), and the 200-cycle reconciler re-closes it
(`re-closed in v1 (DONE)` ×11, `(FAILED)` ×1). It tracks research-goal
completions almost 1:1 — this seam was invisible in Run 2 **because research
goals never completed at all**. The reconciler is doing its job (that part of
P6 is proven), but §8's own escalation rule applies: persistently >0 repairs =
real desync source → **escalate to GOAL_STORE_UNIFICATION**.

**S9's murk — the EMA is a minority shareholder in selection.**
The dying decision snapshot shows the multi-factor ranker: weights
`dir 0.22 / goal 0.297 / emo 0.312 / novel 0.124 / band 0.25 / drive 0.15`,
where the reward EMA enters as one term among many. `look_outward` won the
final cycle at 1.1188 with the *lowest* EMA of any major action (0.150) because
exploration affect and workspace priors carried it. Run 2's clean S9 signal may
have been partly the stuck-loop EMA inflation that fix #10 removed —
`produce_and_check` no longer even has a conscious EMA row this run (0 conscious
picks). Before Run 4, decide what authority the EMA is *supposed* to have;
right now "selection follows learned value" is structurally diluted.

**Known open bugs surfaced by this run** (detail in the companion docs):
- `social_presence` ignition monopoly — **9,544 of 11,332 ignitions (84%)**,
  ~90% after hour one (`2026-07-03_deeper_pass.md` §1). The rest-drive fix
  worked; the jam moved one organ over.
- Two generic make-goals stuck READY all run, incl. *"Turn what I know about
  evolutionary biology into a written synthesis"* — his first genuine
  make-goal, never scheduled while 11 research goals ran (`deeper_pass.md` §4).
- `final_thoughts_written` still `False` at death despite the fix-round
  read-modify-write (fix #11 did not close it).
- `emotion_buffer` dropped 37 deltas for unknown emotion `social_penalty`
  during the conversation — the speech-block penalty never lands.
- S3 satiety closures still 0 (19 refusals; carried since Run 1).

## Next-fix candidates (not yet built)

1. **Wire `mark_reused` into real read-paths** (memo retrieval, artifact
   fetch, research building on prior memos) and give the conscious lane a
   production handoff — closes S7's remaining half.
2. **Root-fix the v2→v1 completion bridge** (or execute GOAL_STORE_UNIFICATION)
   — closes S8.
3. **Decide the EMA's authority in the multi-factor ranker** — makes S9
   testable instead of drowned.
4. **Presence-silence habituation** so `social_presence` can't monopolize
   ignition while a session sits open silently.
5. Scheduler coverage for non-research v2 kinds (the stuck-READY make-goals).

**Re-test gate (Run 4):** signals **7 (reuse half), 8, and 9** must move —
≥1 `mark_reused`/tier-3 row, desync repairs back to ~0, and a demonstrable
EMA→share link — while 5 and 6 hold.

*Written 2026-07-03 at run end. Companion to `NEXT_RUN_TESTS.md` (the §8 gate).*
