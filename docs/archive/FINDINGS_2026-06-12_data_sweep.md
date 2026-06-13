# Findings — data-tree sweep for bugs NOT in FINDINGS_2026-06-12_goals_curiosity_errors
**Date:** 2026-06-12 · **Scope:** `brain/data/`, `data/`, all 34 rotated activity logs (full 6.5 h run, 04:23Z–10:57Z). Everything below is *additional* to the earlier findings doc.

---

## 1. Long-memory store is re-sorted score-descending by pruning — breaks dedup and "recent" reads (root cause of the duplicate floods)

`prune_long_memory` sorts the entire store `reverse=True` by score and saves it
back in that order (`brain/cog_memory/long_memory.py:394`, `save_json` at `:439`).
Evidence: in `long_memory.json`, **1,993 of 2,000 adjacent pairs are
timestamp-descending** even though `update_long_memory` appends chronologically.

Consequences:
- The dedup check scans `memories[-window:]` assuming the tail is "most recent".
  After every prune the tail is the *lowest-scored* entries, so identical new
  entries sail past even the wide 200-entry repetitive window. Observed result:
  the same `[research] Housekeeping…` text stored **127 times** (median gap
  between copies: **1 entry** — adjacent duplicates the dedup should trivially
  catch).
- Every other reader that does `long_memory[-N:]` for "recent memories"
  (autobiography pressure scan, reflection selectors) gets score-sorted, not
  recent, entries after a prune.
- `prune_long_memory` does load→sort→save with plain `save_json`, **outside the
  `modify_json` lock** that `update_long_memory` uses — concurrent appends
  between the prune's read and write are silently lost (the exact lost-update
  race the writer's own comment says it guards against).

**Fix direction:** prune should compute `kept` then re-sort it by timestamp
ascending before saving, and do the whole read-modify-write inside
`modify_json`. (Or store score separately and never reorder the file.)

## 2. ~28 % of long-term memory is pollution from one goal, and it outcompetes real memories

570 of 2,001 entries mention the housekeeping goal. The 127 research copies are
stored at `importance=6`, so under the prune's score ranking the *duplicates
survive every prune* while ordinary importance-1 memories get evicted
(cap `MAX_LONG_MEMORY=2000` was hit all run). Pollution is self-entrenching.
Also stored 148× : "…'Housekeeping: daily snapshot (2026-06-12)'. I'm thinking
but not doing."

## 3. web_research researches the literal goal title → stores an irrelevant Wikipedia hit on loop

161× `Researching topic: 'Housekeeping: daily snapshot (2026-06-12)'`,
135× HTTP 404 on the summary endpoint, then the search fallback fuzzy-matched
**"Daily Harvest" — an American frozen meal-kit company** — and stored it as
research **159 times** ("Stored research … (114 chars)"). Problems, in order:
1. Research topic is derived verbatim from an internal goal title (dates,
   colons and all) — internal housekeeping goals should never become web topics.
2. No negative-result cache: the identical 404 lookup was retried 135 times.
3. No relevance check on the search fallback before storing.
4. `decision_stats.json`: `research_topic` count=330, **avg_reward=0.642 — the
   best-paid frequently-chosen action**. The reward system actively paid for
   this loop, which is why the selector kept picking it.

## 4. Speech died 1 h into the run and never came back (talk gate keyed to the wrong signal)

All 70 speech entries are from 04:23Z–05:18Z; **zero speech for the remaining
5.6 h** while the loop ran until 10:57Z. Mechanism:
- `talk_policy_allows` (`brain/think/think_utils/talk_policy.py:105`) permits
  unprompted speech only when `stagnation_signal ≥ 0.65`.
- Final affect state: `stagnation_signal = 0.012` … while `impasse_signal = 0.851`,
  `positive_valence = 0.862`, `motivation = 0.864`.
The reward pumping documented in the earlier findings keeps `stagnation_signal`
near zero, so the gate never opens — even though the *impasse* signal (the
correct "I'm stuck" indicator, sustained at 0.85–1.0) was screaming. The talk
gate should consider `impasse_signal` (or max of the two), not stagnation alone.

## 5. Narrative-pressure deadlock: autobiography can never fire in tool-only mode, pressure accumulates unboundedly

`narrative_pressure.json: running_total = 379.1` against a fire threshold of
**1.0**. The chain: pressure crosses 1.0 → autobiography fires →
`gated_generate` returns a symbolic (non-JSON) string with the LLM disabled →
`extract_json` → None → `ValueError` → early return (`autobiography.py:408-411`)
→ `_reset_pressure()` at `:455` is never reached. 15× "[autobiography]
LLM/parse error: expected dict, got NoneType" in the logs; the autobiography
never updated all run and pressure grows forever. Needs a symbolic fallback (or
reset/decay on failure).

## 6. v2 goal store "completes" goals instantly via noop steps; loop pursues a DONE goal for 6.5 h

`data/goals/state.jsonl`: all three goals were created **and marked DONE with
`progress 100 %` within ~2 s** (04:23:28→04:23:30), via steps named `noop`
with empty `action: {}` and `attempts: 0` even when DONE. Meanwhile the
cognitive loop pursued 'Housekeeping: daily snapshot' until **10:57Z** —
6.5 hours of work on a goal the canonical store had already closed. This is the
other half of the split-brain documented earlier: not only does v1 progress
never reach v2; v2 "completion" is fake (noop) and never reaches the loop.
Also: step `attempts` is never incremented anywhere.

## 7. action_debt counter exceeds total lifetime cycles

Metacog logged "Goal avoidance: **5,724** consecutive cycles without taking
action" but `cycle_count.json` says the whole run was **4,193** cycles. Either
`action_debt` increments more than once per counted cycle or the two counters
use different tick sources; either way "consecutive cycles" is inflated and the
memories/rules formed from it are quantitatively wrong. Related: with the LLM
off, symbolic plan steps are thought-steps, `_executed` is never true, so
`__acted_this_tick__` is never set (`pursue_goal.py:941`) and debt can only
grow while the agent is, from its own point of view, working the goal every cycle.

## 8. Emotion-regulation thrash: 1,072 reappraisal attempts, "success" changes nothing

921 succeeded + 151 failed reappraisal attempts for `impasse_signal` in 6.5 h
(~1 per 20 s). Despite an 86 % "success" rate, `impasse_signal` stayed at
0.85–1.0 — success doesn't durably move the signal because the upstream cause
(the goal loop) immediately re-raises it, so regulation burns cycles forever.
Also `regulation_log.json` retains only ~6 history entries, so no analysis of
strategy effectiveness is possible from disk.

## 9. Corrupt-text quarantine fires continuously — producer never fixed

155× "[crystallization] Quarantined corrupt source text", 147 of them from
`symbolic_reflection/meta`, roughly once a minute all run. The quarantine
(crystallization.py:176) correctly blocks rule-minting, but the same corrupt
text (truncation slicing through `[EXTERNAL/UNTRUSTED …]` wrappers, e.g.
`"[EXTERNAL/UNTRUSTED source=https more deeply —…"` in working memory) keeps
flowing into working memory, long memory (367 wrapper occurrences), private
thoughts, and — as the earlier doc found — a goal title. The sanitizer needs to
run where chunks are *truncated/merged*, not only at crystallization.

## 10. Unbounded growth / hygiene

- `brain/data/rotated/`: **49 MB in 6.5 h** (34 files); `_maybe_rotate`
  (`utils/log.py`) archives every 1.5 MB segment with no retention cap →
  ~180 MB/day.
- `data/memory/wal/items.jsonl` (20,098) and `events.jsonl` (13,024) — no
  rotation observed (goals WAL has `wal-rotated/`; memory WAL does not).
- `brain/data/proposed_goals.json` is **0 bytes** (not `[]`) — readers relying
  on `load_json` defaults survive, but any strict parse fails.
- 3 orphaned locks: `final_thoughts_archive_2026-06-{06,08,10}.json.lock`
  exist with no corresponding data file; 121 `.lock` files total in
  `brain/data/`.
- `[speak] stripped leaked telemetry prefix(es)` fired 5× (`[regulation]`,
  `[housekeeping/NORMAL]`) — the stripper works, but telemetry prefixes are
  reaching the speech composer's input in the first place, and one leaked into
  `leave_note` output unstripped.
- `wikipedia_search` was called with a raw internal prompt as the lookup term:
  `direct lookup failed '🌓 Shadow question: What truth am I working hardest to
  avoid…'` — same class as §3 (internal strings used as external queries).

## 11. Reward economy contradicts the metacognitive objective

From `decision_stats.json`: `look_outward` is the **worst-paid action in the
table** (avg 0.181, n=92) and `search_own_files` (0.345, n=753),
`update_affect_state` (0.350, n=683) dominate selection counts — while metacog
spent the whole run writing "Goal avoidance / I'm thinking but not doing"
observations and the outward-debt machinery exists specifically to push outward
action. The incentive gradient points exactly opposite the stated objective;
no amount of metacog suppression (which was active: `search_own_files` muted at
escalation levels 2–7 for 1,800+ cycles) wins against a standing reward gap.

---

### Cross-check notes
- `eb88ac7` (the code that ran) already contained the wide repetitive-dedup
  window — the dupes in §1 are explained by the prune re-sort, not by a missing
  dedup feature, so HEAD's dedup will *still* leak until the sort bug is fixed.
- No NaN/Inf anywhere in JSON state; all `.json`/`.jsonl` files parse except
  the empty `proposed_goals.json`. `error_log.txt`/`failures.jsonl` empty, as
  the earlier doc said — everything above is behavioral, found in
  activity/rotated logs and the stores themselves.
