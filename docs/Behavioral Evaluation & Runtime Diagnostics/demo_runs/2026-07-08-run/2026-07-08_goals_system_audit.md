# Goals-system deep dive — 2026-07-08 run

Ric flagged "there are issues in the goals system." There are five, and they compound.
Ordered by blast radius. All reproducible from the captured `data/` and `goals_daemon/`.

## G1 — Committed-goal monopoly (the dominant one)

**Finding:** the committed goal was `aspiration-self_understanding` on **essentially every
cycle of the life** — sampled every 500 cycles from birth to death, 24/25 samples are
`self_understanding` and the odd one is `None`. It was frozen from cycle 0, not a late
drift. That one goal collected **131 of 152** credited effect-ledger rows (86 %).

**Why it matters:** commitment is the pivot everything keys off — the goal lens hydrates for
it, `assess_goal_progress`/`attend_goal`/`thread_continue` (together ~43 % of all selections)
operate on it, and effect credit is attributed to it. When one aspiration owns commitment for
the whole life, the other three starve:

| aspiration | contribution_count | scoreboard generated / attempted / completed |
|---|---|---|
| output_producing | 6 | 2 / 2 / 6 |
| world_knowledge | 2 | 80 / 10 / 2 |
| self_understanding | 1 | 5 / 2 / 1 |
| **genuine_contact** | **0** | **0 / 0 / 0 — never even generated** |

Note the cruel irony: `self_understanding` **owns commitment** but is credited only **1**
contribution, while `output_producing` is credited **6** despite rarely being committed —
because *contribution* credit is attributed by the completed task-goal's `driven_by` tag,
whereas *commitment* is a separate selection. **The two halves of the aspiration system don't
talk to each other.** The committed goal isn't the one getting credit, and the credited
aspiration isn't the one being pursued.

**Root cause to chase:** whatever picks `committed_goal` never rotates off an aspiration once
latched. This is the Runs 2–4 "jammed horn" relocated from the ignition layer to the
commitment layer — the same failure mode (one channel monopolizes) one level up. Fixing
ignition diversity didn't help because commitment sits above ignition.

## G2 — FAILED→DONE bridge lets failed research goals "complete"

**Finding:** four research goals had their fetch step throw `ValueError: no URLs to fetch`.
Their WAL lifecycles then diverge:

- `g_77d3d3db35` (history): steps FAILED → goal **FAILED** in `state.jsonl`, but
  **`comp_goals.json` lists it as `completed`.** Genuine cross-store disagreement.
- `g_c857c1d16b` (biology): FAILED → then **DONE** in the WAL (`FAILED … DONE` back-to-back).
- `g_a9cc879243` (evo biology): `FAILED (no URLs) … DONE … DONE (no URLs)` — the DONE record
  even carries the failure string.
- `g_da938db928` (written language): FAILED in `state.jsonl`, yet a `research_memo.md` was
  produced for it anyway.

**Why it matters:** a research goal whose search found **zero sources** should not be able to
book a completed artifact. The synthesis child runs on the offline fallback (stitching *prior*
memos), so it produces a memo with no new sources and the parent flips to DONE. This is how
`median_seconds_to_complete` collapsed to 42 s (S2) and how the "no URLs" capability hole
(20/32 failures) gets laundered into completions. The daemon's own `store_desyncs_repaired`
reads 0 because this isn't a v1↔v2 mirror desync — it's a *legitimate* status write from the
failure path being overridden by the completion path. The reconciler can't see it.

**Root cause to chase:** the completion bridge (synthesis child → parent DONE) doesn't check
whether the parent's own steps failed. Failure should be terminal for the parent even if a
child artifact exists, or the child should refuse to synthesize from zero new sources.

## G3 — The "understand X" research goal has a broken search capability

**Finding:** 20 of 32 failure rows are `ValueError: no URLs to fetch`. The research plan is
always `search → fetch sources → synthesize findings`; when `search` returns no URLs, `fetch`
raises. This is the same class as the 07-02 `ctx.web_search` gap — the search step is not
reliably producing URLs for offline/degraded operation.

**Why it matters:** research is the main goal shape Orrin generates (the whole "Understand X
more deeply" family). If its first step routinely yields nothing, every research goal either
fails or gets G2-laundered into a hollow completion. Combined with G2, the failure is invisible
in the headline completion count.

**Root cause to chase:** `search` step implementation / `ctx.web_search` wiring for the
research plan; add a guard so a 0-URL search fails the *goal cleanly* (not a fetch exception),
and so synthesis refuses to run on 0 new sources.

## G4 — Satiety close works but isn't metered (and defers a lot)

**Finding:** `satiety_closures` metric = 0, but the logs show **7** real
`Goal '…' closed (satiety:…)` events and **9** `satiety close deferred … only N/M plan steps
done, no milestone met` refusals. The F3 machinery is working — `"Wrote a 'what I learned'
note … satiety close can now complete legitimately"` fires and then the close succeeds — but:

1. the acceptance meter (`outcome_metrics.satiety_closures`) is not wired to the close path
   (S3 reads 0 when the real answer is 7), and
2. the deferral gate refuses ~as often as it closes (9 deferred vs 7 closed), so understanding
   goals still frequently can't close on quenched drive without a plan-step/milestone.

**Root cause to chase:** wire the counter; and revisit whether the "N/M plan steps done" gate
is the right close condition for a *satiety* (drive-quenched) close, which by definition
shouldn't require plan completion.

## G5 — Goal model almost never hydrates

**Finding:** `goal_model_hydrated` is true on **29 of 12,330 cycles (0.2 %)** while
`goal_lens_active` is true on 12,327. The lens (cheap retrieval) is always on; the model (the
richer hydrated representation the production path is supposed to use) is essentially never
populated.

**Why it matters:** if the production/commitment machinery is meant to reason over a hydrated
goal model but that model is absent 99.8 % of the time, decisions fall back to the lens's
retrieval mean — which may be part of why commitment latches (G1) and never re-evaluates.

**Root cause to chase:** what gates `goal_model_hydrated`? It may be a cheap fix (a hydration
call skipped on the hot path) with outsized effect on G1.

## What's healthy in the goals system (keep it)

- **Identity coverage is 100 %** — every goal and every ledger row has a stable id (F14).
- **Aspirations survive** — all four present at death, 0 aspiration failure rows (F2 solid).
- **No daemon desync** — `store_desyncs_repaired` 0; the v1/v2 bridge that plagued Run 3 held.
- **Reuse arc is real** — memos cite prior memos by path; `mark_reused` fires (8 rows). The
  produce-then-reference loop the plan wanted exists.
- **Durable step-attempt cap fires** — 1 `steps_unreachable: 3 steps abandoned at the
  3-attempt cap` proves F1b's `step_attempts.json` replaced the tick-reset in-dict counter.
- **Retirement is orderly** — 14 `Retired N terminal/invalid goal(s)` maintenance passes, 18
  retired total, no orphan RUNNING goals.

## Suggested Run 6 goal-system gate

1. **Break the commitment monopoly (G1):** committed goal must rotate; no single aspiration
   > ~50 % of committed cycles; `genuine_contact` must get > 0 contributions. **And** reconcile
   the two aspiration halves so the credited aspiration is the committed one.
2. **Close the FAILED→DONE bridge (G2):** a goal with failed steps cannot complete; synthesis
   refuses 0-new-source input. `comp_goals` and `state.jsonl` must agree on every goal.
3. **Fix or fence the search step (G3):** 0-URL search fails the goal cleanly, not via a fetch
   exception; ideally restore real URL production.
4. **Wire the satiety meter (G4)** and reconsider the plan-step deferral gate.
5. **Investigate hydration (G5):** find why `goal_model_hydrated` is 0.2 %.
