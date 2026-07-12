# Run 6 deeper pass — loop forensics, exemplar autopsy, new organs

Companion to `2026-07-11_run_analysis.md`. Four deep dives the gate tables can't hold.

## 1. Anatomy of the QuadRF loop (cycle-level)

The life's defining artifact is a Jeff Geerling blog post about an SDR board. Chain:

1. **Selection**: `research_topic`/`fetch_and_read` legitimately score high (EMA 0.585 /
   0.642 — they *are* his best-rewarded real actions).
2. **Source pick**: `_pick_url` tier 2 returns the first http link of the top RSS item
   — deterministically the QuadRF post, every call, all life. (Per-URL visited cache
   now written — `FETCH_REREAD_LOOP_FIX_2026-07-11.md` — but post-mortem, uncommitted,
   never ran in this life.)
3. **Memo write**: `_write_research_memo` re-renders the same scrape, appending
   `source: fetch_and_read · <timestamp>` — **the timestamp makes every rewrite hash
   unique**, so the ledger's content-hash dedupe (which the fix doc assumed was
   swallowing the duplicates) actually credited **387 of 403** rewrites. Only novelty
   scoring saw the truth (0.002) — and novelty doesn't gate credit.
4. **Spread**: the memo was written under **10+ different goal folders**
   (aspiration-self_understanding, g_095343…, g_52037d…, g_6132…, g_696f…, g_9afd…,
   g_a11f…, g_a35d…, g_54ea…, g_f774…, ltc_…_232) — whichever goal held the driver slot
   at write time got a copy. Artifact identity is per-goal-path, so cross-goal dedup
   never triggers either.
5. **Payoff**: each credited write pays significance 0.314 into the committed goal's
   value EMA → the commitment monopoly (goals audit §2).

Flat rate all life: ~40 file_writes per 1k cycles from cycle 3,000 → 12,000; last one
41 s before death. Three dedup layers (ledger hash, artifact path, URL history) and
each had a hole the loop threaded exactly.

**Fixes this implies beyond the URL cache**: hash normalized content (strip volatile
footers); per-path repeat-credit decay; novelty < ε should gate *credit*, not just
score.

## 2. `write_exemplar` autopsy (the run's oldest wound)

- 12 failures, `PermissionError [Errno 13]` on
  `tests/fixtures/quality_golden/exemplars/research-memo-quadrf-can-spot-drones-and-see-wif-ef5f019d.md`
  at 21:01Z, 21:07, 22:06, 22:33, 22:44, 22:52, 22:55, 22:59 (day 1), 01:59, 05:00,
  08:00, 11:00 (day 2) — **first at minute 13 of life**, then roughly every retry epoch.
- The gate code (`quality_standard/gate.py::_apply_promotions`) is correct-by-shape:
  predicate → near-dup check → `QUALITY_EXEMPLARS_DIR.mkdir` → `write_text`, EACCES
  caught and recorded. The target dir **is owner-writable post-mortem** (probe
  confirmed); no chflags, no code-side deny path exists. Cause unresolved — candidates:
  transient FS state during the run, something environmental about how the process was
  launched. **Action**: record `errno`, `os.access` and `stat` in `record_failure`
  for OSError sites, and add a boot-time writability probe for QUALITY_EXEMPLARS_DIR
  so a dead promotion path screams on cycle 1, not minute 13 in a log nobody reads.
- Note what it tried to canonize: *the looped memo* was the "demonstrated-good"
  promotion candidate. Had the write succeeded, the quality golden set would have
  pinned the loop's output as the standard. Two bugs mutually contained each other.
- Behavior around the failure is the run's best news *and* its most instructive
  failure: the **problem-refocus organ ran twelve full episodes in the wild**,
  starting at minute 13. Detection and parking were correct every time — but the
  first nine episodes ended in an evidence-free *"is working again — resuming"*
  (the recovery check never re-attempts the failed op), the "transient" hypothesis
  was never updated across twelve recurrences, and one repair attempt literally
  **web-searched his own internal bug** (`[web_research] Researching topic: 'Figure
  out why quality_standard.gate.write_exemplar isn't working'`). Only from 05:00
  local did episodes end honestly ("couldn't fix it myself — working around it").
  Right choreography; missing verification, cross-episode memory, and an inward
  toolset. Full audit: `2026-07-11_self_awareness_audit.md` §2.

## 3. Companion & Presence — staged verification (the e4abfe7 build)

| Claim | Evidence | Verdict |
|---|---|---|
| Presence notifications ignition-gated, rare | `presence_notifications.json`: **3 events in 15.5 h** (birth, +48 min, +2.75 h) | ✅ rarity holds |
| Typed person-facing speech | `speech_log.json` `response_type`: share_finding 31 / express_state 21 / uncertainty 16 / acknowledge 3 / answer 2 / greet_return 1 / name_shared_situation 1 | ✅ typing live |
| R-rooms / theory-of-mind peers | `relationships.json`: `peer_observer`, `peer_reward_auditor`, `peer_goal_auditor`, `peer_signal_historian`, `peer_architect` all populated | ✅ ran |
| Speech content grounded | replies truncate mid-referent ("QuadRF can s What do you think?"); early Wikipedia-disambiguation junk | 🔴 content quality still the gap |

No crash, no telemetry regression attributable to the new phases: the build survives
its staging life. Remaining risk is quality, not stability.

## 4. Memory & introspection

- **Estate**: 2,001 long-memory entries, 89 % working-memory summaries (Run 5: 91 %).
  The F17/F18 instrumentation-share target (< 40 %) is not in sight. Everything else
  about memory is healthy: 100 % graph endpoint resolution, live-compaction actively
  dropping orphan edges (visible in the runtime log to the final minute).
- **Delayed reward**: grounded resolutions 12 % (was 8 %), mean resolved reward 0.166
  (was 0.107) — the channel improves run-over-run but still evaporates 88 % of
  decisions.
- **Map-territory audit** (introspective frontier goals): ran every ~75 min, found a
  *real* defect — `cognition/language/acquisition.py:49` `_NARRATE_MIN_INTERVAL_S=90.0`
  vs a comment promising 10 s — and then found the **same defect every pass** for the
  rest of the life. The introspection organ works and has its own re-read loop: no
  "already reported" memory. Same disease as `fetch_and_read`, different organ. A
  finding-dedup cache is the obvious small fix (and the acquisition.py comment should
  just be corrected).
- **Thought flood**: private_thoughts rotated every ~18 min from 23:51 local — the
  back-half rumination signature from Run 5 reproduced almost exactly (it starts when
  the treadmill has fully owned the committed slot).

## 5. Failure inventory (38 rows — the taxonomy is maturing)

| n | failure | reading |
|---|---|---|
| 12 | `PermissionError` exemplar write | §2 — structural, all life |
| 9 | `ValueError: no URLs to fetch` | down from 20 in Run 5; one research goal FAILED honestly on it (no FAILED→DONE bridge-override observed this run) |
| 6 | `steps_unreachable` (3-attempt cap) | the durable step_attempts fix (F-series) doing its job |
| 4 | `objective unmet after 2 attempts` | honest acceptance failures |
| 4 | `FileNotFoundError: brain/data/self_code/manifest.json` | self-code writer looks for a manifest that lives at `brain/agency/manifest.json.migrated` — path drift, needs a look |
| 3 | plan/step misc | |

Legitimate-failure signal (S4): comfortably nonzero, and increasingly *diagnostic*
rather than noise.
