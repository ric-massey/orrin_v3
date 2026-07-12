# Run 6 goals-system audit — the commitment machinery after Fix 2

The Run 6 build gave commitment a score (`commitment_value.py`: value EMA, staleness,
avoidance, incumbent hysteresis) and rotation. This pass audits what that machinery
actually did across the life, from `commitment_signals.json`, `production_loop.jsonl`,
`evaluator_wal.jsonl`, `goals_mem.json`, and the metacog/thought streams.

## 1. The committed-goal ledger (whole life, per-cycle truth)

From `production_loop.jsonl` (13,341 rows, one per cycle):

| committed goal | cycles | share |
|---|---|---|
| `aspiration-self_understanding` | **12,274** | **92.0 %** |
| `g_696f8771833c` (philosophy of time) | 244 | 1.8 % |
| `g_6132820139c9` (history of written language) | 205 | 1.5 % |
| `g_095343dfeec6` (research child) | 147 | 1.1 % |
| `g_52037d5c0a53` (research child) | 141 | 1.1 % |
| `ltc_aspiration-self_understa_1` | 65 | 0.5 % |
| `g_a35d9ec92fd9` (quantum mechanics) | 52 | 0.4 % |
| `g_9afd79e32dc3` (history) + others | ~213 | 1.6 % |

**Rotation is real** — eight-plus goals held the driver slot for 35–244-cycle
stretches, vs Run 5's single owner at 99.9 %. And it lost anyway: 92 % is still a
monopoly by the ~60 % gate, and the death snapshot's committed goal is the life-owner.

## 2. Why the incumbent won: the value pump

`commitment_signals.json` at death:

| goal | value_ema | avoid_streak | note |
|---|---|---|---|
| `aspiration-self_understanding` | **0.8142** | **18.8** | highest value in the store *and* the most avoided |
| `g_6132820139c9` | 0.8024 | 6.2 | real memo work |
| `g_696f8771833c` | 0.7917 | 2.5 | real memo work |
| `g_54ea2c5e7a2f` | 0.7172 | 1.3 | |
| (typical others) | 0.50–0.64 | 0–5 | |

The incumbent's `value_ema` was fed by **457 of the 546 credited ledger rows**, of
which **403 are one memo rewritten** (`memo_quadrf-…`, novelty ~0.002, credited because
a fresh timestamp footer defeats the content-hash dedup). Fix 2's score did exactly
what it was built to do — commit to the highest-value goal. The value was counterfeit.

Run 5's monopoly mechanism: a static tier+priority stable-sort no outcome could touch.
Run 6's: a learned value no *honest* outcome could outbid. That is progress in
architecture and a regression in exploitability: **the monopoly relocated into the
learning signal itself** (Run 4: candidate generator → Run 5: commit sort → Run 6:
value EMA).

## 3. The avoidance channel: local success, global orbit

- Whole-life: avoidance on `Understand my own mind and how I work` is effectively
  continuous — 140 of the last 200 metacog entries, thousands of thought-stream echoes.
- **Max consecutive streak 27** (Run 5: 68; gate ~20). Fix 3's release does fire and
  break streaks.
- But `commitment_signals` shows `avoid_streak 18.8` *coexisting with* `value_ema
  0.8142`: the avoidance penalty and the pumped value fight inside one score, and value
  wins the re-commit every time. **Avoid → release → same goal wins the next sort →
  avoid.** A release must carry a re-commit cooldown (temporal exclusion), not just a
  score penalty, or a pumped incumbent snaps straight back.

## 4. Credit and commitment still don't speak the same key (R-D)

- Aspiration `contribution_count` at death: self_understanding **2**, world_knowledge
  **0**, genuine_contact **0**, output_producing **7**.
- Ledger credit at death: self_understanding **457**, everything else ≤ 18.
- The paradox: the QuadRF memo is *world knowledge* by content, credited to
  `self_understanding` because **credit keys off the committed goal at write time**.
  So: the aspiration whose content dominated the life earned 0; the committed one
  absorbed everything; and `mark_objective_contribution` (a different path) paid
  `output_producing` most. Three credit ledgers, three different winners.
- Fix 4 (credit→commitment convergence) is wired and working — over mis-keyed input.
  Until credit is assigned by **content alignment** (what is this artifact about /
  which aspiration's success criteria does it move), convergence amplifies the bug.

## 5. `genuine_contact`: 0 for the second straight run

Never committed, 0 contributions, absent from the committed-goal ledger entirely.
75 speech rows exist (typed intents — the F19 fix landed), so contact *behavior*
happened; it just never routes to the aspiration. Same key problem as §4: nothing
maps a `share_finding` reply to `genuine_contact` credit.

## 6. The `ltc_` children

Only two `ltc_aspiration-self_understa_*` ids appear in the final context (`_1`, 65
committed cycles, and `_232`, 18 cycles + an artifact folder). The numbering implies
~232 long-term-commitment children were minted and pruned across the life — a churn
worth instrumenting (each mint is allocation work; 2 of ~232 ever drove).

## 7. Daemon-side view (root `data/goals`)

Clean this run: 18 state rows, all born in-life; 14 DONE / 2 FAILED / 1 READY /
1 WAITING; the two `intrinsic-*` research pipelines both produced `research_memo.md`
(one goal FAILED honestly on `no URLs to fetch` after producing docs). No resurrection,
no orphan-RUNNING, `store_desyncs_repaired` 0 — **S8 holds for the second consecutive
run**; the Run 3 escalation (GOAL_STORE_UNIFICATION) stays closed.

## 8. What the next fix round must do (goals side)

1. **Anti-pump on credit**: decay repeated credit per artifact path/hash (n-th write of
   the same target pays ~0); normalize volatile footers out of the ledger content hash.
2. **Content-keyed credit** (the real R-D fix): route ledger credit to the aspiration
   whose domain the artifact serves, not whoever holds the driver slot.
3. **Re-commit cooldown on avoidance release**: a released goal is ineligible for the
   driver slot for N cycles, hysteresis be damned.
4. **Value-EMA sanity bound**: a goal whose credited rows are ≥ X % one content family
   gets its value contribution capped (diversity-weighted value).
5. Commit + stage the `fetch_and_read` URL-dedup fix (upstream valve of the pump).
