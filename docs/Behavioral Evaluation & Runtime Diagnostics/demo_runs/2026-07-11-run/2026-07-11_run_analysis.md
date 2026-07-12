# Run 6 — forensic analysis + the eleven §6 read-side checks

Companion to `DEMO_RUN_2026-07-11.md`. All numbers reproducible from the captured
`data/` snapshot. Reading discipline per `NEXT_RUN_TESTS.md` §6: honest denominators,
never the flattering cumulative fields.

## Timeline

| Time (local MDT) | Cycle | Event |
|---|---|---|
| 14:48:27 | 0 | launch #0, single-instance lock pid 59935, clean reset (habituation cleared — first run where that's true) |
| 14:48–14:57 | ~0–100 | 4 aspirations seeded; both reuse rows of the whole life land (2 intrinsic research pipelines: packet capture, evolutionary biology) |
| **15:01** | ~190 | **first `write_exemplar` EACCES** — the quality-standard promotion path is already dead, 13 minutes into life |
| 14:54–16:24 | ~100–2,300 | the productive stretch: ~14 distinct research memos ("Understand X more deeply" arcs), 2 pipeline `research_memo.md`, doc scrapes, 2 "Builds on:" citations |
| ~15:00 onward | ~200+ | `fetch_and_read` pins on the QuadRF blog post (top RSS item); the memo-rewrite loop begins and **never stops** — file_writes run at a flat ~40/1k cycles from cycle 3,000 to 12,000 |
| 23:51 → death | ~7,900+ | private_thoughts rotates every ~18 min (20 rotations) — back-half thought flood, same signature as Run 5 |
| 15:01 → 05:00 | ~190 on | problem-refocus runs **12 episodes** on the exemplar failure, starting minute 13 — the first nine end in a *false recovery* ("working again — resuming", no evidence); from 05:00 local it runs repair attempts and honestly concludes "couldn't fix it myself — working around it" (full record: self-awareness audit §2) |
| 06:15:19 | 13,334 | last ledger row: the QuadRF memo, again (`novelty 0.002, sig 0.314`) — 41 s before death |
| 06:16:06 | 13,341 | operator stop → graceful shutdown, `clean_shutdown: true` |

Same two-halves shape as Run 5 — a real making stretch, then a treadmill — but the
treadmill is different in kind: Run 5 re-*noted* the same reflection; Run 6 re-*made*
the same artifact and got **paid for it 387 times**.

## The eleven §6 read-side checks

**1 — Production reset-safe totals.** No relaunch; `production_loop.jsonl` = 13,341
rows, one per cycle, cycle counter strictly increasing. Boolean sums:
`production_attempt` **443**, `production_success` **384** (Run 5: 185/104),
`committed_goal_present` 13,331, `goal_lens_active` 13,330, `goal_model_hydrated`
**893 (6.7 %** — 30× Run 5's 29, still low). This run the tail cumulative fields
(443/384) **match** the boolean sums — with no relaunch there's no seam, and the Run 5
zeroed-tail defect did not reproduce. The honest caveat moved elsewhere: **the 384
"successes" are ~93 % one memo rewritten** (check 4).

**2 — Funnel wiring.** `production_funnel.json`: **81 events, all `stage:"candidate"`**.
Identical to Run 5. No staged/handoff/produced stage has ever fired;
`production_handoff_count` 0 all life. Still candidate-only.

**3 — Goal identity coverage.** **100 %** — 0 of 593 ledger rows id-less; every daemon
goal and comp_goals row carries a stable id. F14 continues to hold.

**4 — Material class counts (the honest denominator).** Of **546 credited** rows:

| kind | n | reading |
|---|---|---|
| `file_write` | 387 | **403 writes of ONE memo** (`memo_quadrf-…jeff-g.md`, 30 deduped, 373 credited) + ~24 writes of 17 distinct real docs |
| `bookkeeping` | 146 | ✅ **Fix 5 live** — causal-edge rows now a separate class (`symbolic_artifact` fell 116 → 4) |
| `note_novel` | 4 | real |
| `symbolic_artifact` | 4 | real |
| `tool_run_effect` | 3 | operational |
| `reuse` | 2 | tier-3 markers, both < 70 min into life |

Distinct readable made-material ≈ **17 documents**. The Fix-5 split worked exactly as
designed — and immediately exposed that the remaining inflation lives in `file_write`:
**the ledger's dedup is content-hash based, and each memo rewrite embeds a fresh
`source: fetch_and_read · <timestamp>` footer, so every rewrite hashes new.** Novelty
scoring saw through it (0.002) but credit and significance (0.314) were paid anyway.
This is the mechanism that poisoned the commitment value (goals audit).

**5 — Material availability + transformation.** 385 sidecar bodies; **382/395 (97 %)**
of credited readable rows resolve to a sidecar. Transformation exists but is thin:
**2 "Builds on:" citations** (history→packet-capture memo, evolutionary-biology memo)
vs Run 5's memo-chains + 3 syntheses. **Syntheses this run: 0.** The produce-then-
reference arc regressed — everything after cycle ~2,300 was the loop.

**6 — Memory composition (fails again).** `long_memory.json` = 2,001 entries,
**1,795 (89 %) `📝 Working memory summary`** (Run 5: 91 %). F17/F18's < 40 % target is
not close. The graph stays healthy: 10,673 live edges after continuous live-compaction,
**21,346/21,346 (100 %) edge endpoints resolve** to live memories. Same verdict as
Run 5: the graph is fine; the node estate is a wm-snapshot flood.

**7 — Delayed reward by source.** `evaluator_wal.jsonl` = 1,001 decisions.
`resolved_by`: **None 501 (50 %), pruned 380 (38 %), goal_B_grounded 106 (10.6 %),
retrieval_A 14 (1.4 %)**. Grounded share ~12 % (Run 5: ~8 %); mean resolved reward
**0.166** (Run 5: 0.107). Direction is right, channel still thin: **88 % of decisions
evaporate** before becoming a learning signal. `committed_goal_id` ~64 % raw
`self_understanding` (+ its child goals beyond that) — the monopoly cross-confirmed.

**8 — Cooldown truth.** `decision_stats` totals **13,341 = exactly one per cycle** —
per-cycle chosen actions, an honest denominator at last (Run 5's were ~63.8k cumulative
all-selection counts). Production attempts (443) correspond to producer runs (384
successes). No `cooldown_skipped` field surfaced anywhere in the snapshot — the F16
observable is still not being emitted where an analysis can find it.

**9 — Classifier agreement.** Still disagree by construction: 384 ledger
production-successes vs 0 funnel handoffs vs 7 making-aspiration contributions vs 81
candidate-only funnel rows. Four counters, four answers.

**10 — Speech grounding (typed intents landed; content still weak).** 75 rows, and
`response_type` is now real: **share_finding 31 (41 %), express_state 21,
uncertainty 16, acknowledge 3, answer 2, greet_return 1, name_shared_situation 1** —
F19's typing took (Run 5: effectively untyped). Quality did not: replies truncate
mid-referent (*"I learned something: QuadRF can s What do you think?"*), and early ones
are disambiguation junk (*"Growth: Growth may refer to:"*). `quality_score` mean 0.651
over the 13 evaluated rows. Grounded *type* ✅, grounded *content* 🔴.

**11 — Writeback pressure.** `workspace_writeback.jsonl` = **9,282 rows, 696/1k
cycles** (Run 5: 702/1k — unchanged), **43 % motivation-touching** (Run 5: 44 %),
source 9,281/9,282 `binding`. The decaying-only writeback remains a near-every-cycle
background pressure; no movement.

## Cross-cutting root problems

### R1 — The value-pump loop (new, and the run's defining failure)
Chain, each link verified in the snapshot: `_pick_url` tier-2 pins the top RSS item →
same URL re-fetched all life (fix now written, uncommitted, post-mortem) → memo
rewritten with fresh timestamp footer → ledger content-hash dedup defeated → **387
credited file_writes** at sig 0.314 → `record_effect` credit feeds Fix 2/4 →
`self_understanding.value_ema` = **0.8142**, highest in `commitment_signals.json` →
commitment score keeps the incumbent → goal lens keeps selecting research/fetch → loop.
The Run 6 plan's thesis was "make learning steer behavior." It now does. **The
monopoly relocated one layer up again: Run 4 candidate-generator → Run 5 static
commitment sort → Run 6 the learned value signal itself.**

### R2 — `write_exemplar` structurally dead (quality standard cannot grow)
12× `PermissionError` writing
`tests/fixtures/quality_golden/exemplars/research-memo-quadrf-…-ef5f019d.md`, first at
**minute 13**, recurring every 1–3 h. The dir is owner-writable post-mortem; the errno
path is unexplained (needs `errno` + `os.access` capture in `record_failure` and a boot
writability probe). Two ironies: (a) the artifact the gate kept trying to canonize as
demonstrated-good was *the looped memo*; (b) this was the recurring "Problem hit"
that dominated the life narrative and drove the problem-refocus engagement.

### R3 — Credit mis-keying (R-D survives Fix 4)
Ledger credit keys off the **committed goal**, not the content. A world-knowledge blog
memo paid `self_understanding` 403×; `world_knowledge` (whose content it was) earned
**0** contributions; `genuine_contact` stayed at 0 a second run. Fix 4 then faithfully
converged commitment toward the mis-keyed winner.

### R4 — Avoid→release→re-commit orbit
Avoidance ran continuously on `Understand my own mind and how I work` (140 of the last
200 metacog entries; thousands of thought-stream echoes). Fix 3 works locally — max
streak fell 68 → **27** (still > the ~20 gate) — but every release is followed by the
same goal winning the next commit sort on its pumped value. Release without a
re-commit cooldown is a rubber band, not an exit.

### R5 — Consolidation starved again
Reuse 2 (both < 70 min), syntheses 0, funnel handoff never fired, `look_outward`'s
collapse shows selection *can* now kill a channel — but nothing upstream generates
consolidation pressure once the treadmill owns the committed slot.

### R6 — S1 mutated: repeat *family*
"Strengthen COGNITIVE/GENERAL/EMOTIONAL symbolic reasoning" = 8 of 17 completions.
Under the per-title cap (max 4× / 13.3k cycles) but a single template family is half
the completion ledger. Median completion 46–118 s also deserves scrutiny — closes are
real but cheap.

## Reproduction

```bash
cd docs/"Behavioral Evaluation & Runtime Diagnostics"/demo_runs/2026-07-11-run/data
# material classes (credited)
python3 -c "import json,collections;print(collections.Counter(json.loads(l)['kind'] for l in open('effect_ledger.jsonl') if not json.loads(l).get('dedupe')))"
# the one-memo loop
python3 -c "import json,collections,os;print(collections.Counter(os.path.basename((json.loads(l).get('metadata') or {}).get('path','?')) for l in open('effect_ledger.jsonl') if json.loads(l).get('kind')=='file_write').most_common(3))"
# committed-goal monopoly (whole life)
gzcat production_loop.jsonl.gz | python3 -c "import json,sys,collections;print(collections.Counter(json.loads(l).get('committed_goal_id') for l in sys.stdin).most_common(5))"
# S9 numbers
python3 -c "
import json,math
ema=json.load(open('action_reward_ema.json')); ds=json.load(open('decision_stats.json'))
tot=sum(v['count'] for v in ds.values())
pairs=[(ema[k] if isinstance(ema[k],(int,float)) else ema[k].get('ema'), v['count']/tot) for k,v in ds.items() if k in ema and v['count']>=8]
xs,ys=zip(*[(a,b) for a,b in pairs if a is not None])
ma,mb=sum(xs)/len(xs),sum(ys)/len(ys)
print('corr',sum((x-ma)*(y-mb) for x,y in zip(xs,ys))/math.sqrt(sum((x-ma)**2 for x in xs)*sum((y-mb)**2 for y in ys)))"
# exemplar failures
python3 -c "import json;print(*[json.loads(l)['ts'][:16] for l in open('failures.jsonl') if 'write_exemplar' in l],sep='\n')"
```
