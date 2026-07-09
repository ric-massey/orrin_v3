# Run 5 — forensic analysis + the eleven §6 read-side checks

Companion to `DEMO_RUN_2026-07-08.md`. All numbers reproducible from the captured
`data/` snapshot. Reading discipline per `NEXT_RUN_TESTS.md` §6: report the honest
denominators, never the flattering cumulative fields.

## Timeline

| Time (local) | Cycle | Event |
|---|---|---|
| 08:42:58 | 0 | launch #0, single-instance lock pid 99882 |
| 08:43 | ~10 | 4 aspirations + `Immediate Actions` seeded; boot invariant held (F2) |
| ~08:46–14:26 | 0–~2,000 | the productive stretch: research memos + syntheses written, most reuse rows land |
| ~15:00 → death | ~4,000→12,330 | committed goal freezes on `aspiration-self_understanding`; `private_thoughts` rotates every ~11 min (20 rotations); production tapers to dedupe churn |
| 20:22 (00:22Z) | 12,330 | operator SIGTERM → graceful shutdown, clean |

The two halves are stark: **~3 h of real making, ~8 h of treadmill** on one frozen
commitment. The last ledger rows (cycle 12309) are `note_novel … novelty 0.0 … dedupe
true` — re-noting the same thing.

## The eleven §6 read-side checks

**1 — Production reset-safe totals.** No relaunch, so `production_loop.jsonl` is one
clean segment: 12,330 rows, one per cycle. Boolean sums (the honest totals):
`production_attempt` **185**, `production_success` **104**, `committed_goal_present`
12,328, `goal_lens_active` 12,327, **`goal_model_hydrated` only 29**. The tail cumulative
fields (`production_attempt_count` etc.) read 0 at death — do not trust them; the booleans
are the truth.

**2 — Funnel wiring.** `production_funnel.json` has **82 events, all `stage:"candidate"`** —
still candidate-only. No `staged`/`handoff`/`produced` stages were ever written. The funnel
tells you what was *considered*, never what shipped. Top candidates are the "Understand X"
and "Open question:" goals.

**3 — Goal identity coverage.** **100 %** — 0 of 200 effect-ledger rows are id-less; every
`comp_goals` row and daemon goal carries a stable id. F14 holds. (The `ltc_…` synthetic id
on one completed row is stable, just synthetic.)

**4 — Material class counts (the big one).** Of **152 credited** ledger rows:

| kind | n | is it prose material? |
|---|---|---|
| `symbolic_artifact` | **116** | ❌ every one is `"[causal edge established] cause: … effect: …"` — self-model graph bookkeeping, *not* a made artifact |
| `file_write` | 21 | ✅ real (501–14,939 chars) |
| `note_novel` | 5 | ✅ real (1,166–1,659 chars) |
| `reuse` | 8 | ⚠️ tier-3 back-ref markers, char_len 0 |
| `tool_run_effect` | 2 | ✅ operational |

So **only ~26 rows (17 %) are readable made material**; **76 % of "production" is causal
edges.** This inflates S5 (significance) and the production counters. The causal-edge rows
should be a separate ledger class excluded from the production denominator.

**5 — Material availability + transformation.** 106 sidecar files; **114/152 credited rows
resolve to a sidecar body** (the 116 causal-edge rows are short and mostly deduped against
each other, which is why not all resolve). Transformation **is** demonstrated: the biology
`research_memo.md` cites `Builds on: data/goals/artifacts/g_77d3d3db35/research_memo.md`
(the history memo), and syntheses cite prior memos by path — a genuine produce-then-reference
arc. The defect: the **offline fallback stitches prior memos *verbatim and recursively***, so
each memo embeds the full text of the one before it, growing degenerate.

**6 — Memory composition (fails badly).** `long_memory.json` = 2,001 entries, **1,825 (91 %)
are `📝 Working memory summary`.** Real content (world-model notes, unanswered questions,
failures, aspirations) is <10 % of the estate. Instrumentation isn't *tagged* as
instrumentation (so a keyword filter reads "1 %"), but by content it is a flood. The
memory graph is healthier: 10,276 edges, **1,905/1,905 endpoints (100 %) resolve to live
long-memory ids** — no orphans. So the graph is fine; the node estate it points into is
swamped by working-memory snapshots.

**7 — Delayed reward by source (F15 partially landed, but the channel is thin).**
`evaluator_wal.jsonl` = 1,001 decisions. `resolved_by`: **`None` 501 (50 %), `pruned` 421
(42 %), `goal_B_grounded` 72 (7.2 %), `retrieval_A` 7 (0.7 %)**. So it is **no longer 100 %
flat goal_B** — F15's variety landed — but **92 % of decisions resolve to nothing usable**
(unresolved or pruned before resolution), and only ~8 % become a grounded learning signal.
Worse, the 500 rows that *did* resolve carry **mean reward 0.107** — the delayed-reward
channel is both thin and low-value. And `committed_goal_id` here is **97.5 %
`self_understanding`-related** (902 + 73 + 23 of 1,001) — the monopoly (R1/G1) cross-confirmed
in a third independent store. This is R-A upstream: even the outcome signal that *should* teach
selection mostly evaporates before it can.

**8 — Cooldown truth.** `decision_stats.json` shows recognized-vs-ran separation exists;
`assess_goal_progress` selected 14,995× and `research_topic` 8,914× across the life (these
are cumulative all-selection counts, ~63.8k total, not per-cycle). Production attempts (185)
correspond to real producer runs (104 successes), so the cooldown accounting is honest here.

**9 — Classifier agreement.** Artifact-gated goals (research, `requires_artifact:true`),
make-shaped goals, production handoffs (0 in the funnel), and making-aspiration credit
(6 to output_producing) do **not** line up: production_handoff_count stayed 0 while 104
production successes were booked — the success path books through the effect ledger, not the
funnel handoff stage, so the two disagree by construction.

**10 — Speech grounding (weak).** Only 24 speech rows; the `intent` field exists but is
effectively untyped, and the replies are ungrounded Wikipedia-disambiguation junk:
*"I learned something: Growth: Growth may refer to:!"*, *"consciousness and subjective
experience: Wikiped Am I off on that?"*. No `share_artifact` / `share_finding` typed intents
in evidence. F19's grounded-speech intent did not visibly take.

**11 — Writeback pressure.** `workspace_writeback.jsonl` = **8,653 rows, 702 /1k cycles**
(binding writes back on ~70 % of cycles — better than 07-05's 9,299/9,300 but still very
high). **3,823 rows (44 %) touch motivation.** Source is 100 % `binding`. The
writeback-derived prior is a structural background pressure on nearly every cycle.

## Cross-cutting root problems (new or deepened this run)

### R1 — The committed-goal monopoly (new dominant pathology)
99.9 % of the last 3,000 `DECISION` events carry `committed_goal = aspiration-self_understanding`.
That one goal collected **131 of 152** credited ledger rows. The Runs 2–4 "jammed horn" was
at *ignition* (which function fires); Run 5 moved it up to *commitment* (which goal owns the
cycle). Because credit, attention, and the goal-lens all key off the committed goal, a single
aspiration starves the other three. `genuine_contact` got **0** contributions and never even
appears in `aspiration_scoreboard.json`. Full mechanism in the goals-system audit.

### R2 — Production credit is mostly self-model bookkeeping
The 116 causal-edge `symbolic_artifact` rows (§6.4) are the engine "learning about itself"
being counted as "making things." Real for the world-model, wrong for the production gate.
Until they're split out, S5/S7 numbers overstate the making organ by ~4×.

### R3 — S9: learned value still has no authority
`corr(EMA, selection-share) = −0.17`. The worst-rewarded major action (`look_outward`,
avg reward 0.228, EMA 0.361) is still picked 4,899× (#6). The dying decision snapshot shows
why: `weights = {emo 0.312, goal 0.297, band 0.25, dir 0.22, drive 0.15, novel 0.11}` — the
A4 multiplicative (0.5+EMA) scaler is a rounding error next to affect. The EMA→selection link
the plan requires is still not live.

### R4 — The "no URLs to fetch" capability hole
20 of 32 failures are `ValueError: no URLs to fetch` — the search step returns zero URLs, so
the fetch step throws. Then (S8 asterisk) the goal is bridged **FAILED→DONE** by its synthesis
child, so a search that found nothing still books a "completed research goal." This is both a
capability gap (search/`ctx.web_search`) and a status-integrity gap (failure overridden).

### R5 — Goal model almost never hydrates
`goal_model_hydrated` true on **29 of 12,330 cycles (0.2 %)**. The goal *lens* is active
(12,327) but the goal *model* it's supposed to hydrate is essentially never populated — the
production path runs on the lens's cheap retrieval, not a hydrated model. Worth a look at why
hydration is gated shut.

### R6 — Meter/mechanism drift (S3)
7 real `closed (satiety:…)` events, `satiety_closures` metric = 0. The F3 machinery works
(satiety closes now legitimately complete after a learned-note is written) but the acceptance
meter isn't wired to the close path, so the signal reads as a failure it isn't.

## Reproduction

```bash
cd docs/"Behavioral Evaluation & Runtime Diagnostics"/demo_runs/2026-07-08-run/data
# material classes
python3 -c "import json,collections;print(collections.Counter(json.loads(l)['kind'] for l in open('effect_ledger.jsonl') if not json.loads(l).get('dedupe')))"
# committed-goal monopoly
python3 -c "import json,collections;print(collections.Counter(json.loads(l)['payload'].get('goal',{}).get('id') for l in open('events.jsonl')).most_common(3))"
# long-memory spam share
gzcat long_memory.json.gz | python3 -c "import json,sys;m=json.load(sys.stdin);print(sum('Working memory summary' in str(x.get('content','')) for x in m),'/',len(m))"
# S9 correlation → run the block in the analysis session
```
