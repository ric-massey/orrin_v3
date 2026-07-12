# Run 7 Fix Plan — make credit un-pumpable (2026-07-11)

**Status:** PROPOSED. Written after the Run 6 (2026-07-10/11) life analysis in
`demo_runs/2026-07-11-run/`, grounded in a fresh code read of the ledger, memo,
commitment, quality-gate, refocus, and speech paths. Every diagnosis below was
re-verified against the source before a fix was accepted (§2).

Run 6's thesis ("make learning steer behavior") worked: value authority killed
`look_outward` (4,899 → 88 picks), rotation fired, avoidance release fired. And
the life still ended in a 92 % committed-goal monopoly, because the learned
value signal itself was poisoned: one RSS item re-fetched all life, each memo
rewrite hash-fresh via a timestamp footer, **387 credited rewrites** pumping
`self_understanding.value_ema` to 0.8142. The monopoly has relocated one layer
up each run (Run 4 candidate generator → Run 5 static commit sort → Run 6 the
value EMA). Run 7's job is to make the *credit substrate* honest, so there is
no next layer to relocate into.

---

## 1. Verification — the findings' diagnoses checked against code

Every load-bearing claim was confirmed at a specific site:

| Claim (findings) | Verified at | Verdict |
|---|---|---|
| Timestamp footer defeats content-hash dedup | `web_research.py:65-67` — `source: {source} · %Y-%m-%d %H:%MZ` is inside the hashed content; minute resolution explains 30 of 403 writes deduping (same-minute) and 373 crediting | ✅ confirmed |
| Novelty doesn't gate credit | `effect_ledger.py:444-448` — `sig = 0.0 if nov <= 0.0 else _structural_significance(...)`; near-dup novelty 0.002 (> 0) passes, `dedupe` only when `nov <= 0.0`. `NEAR_DUP_RESIDUAL = 0.15` keeps near-dups on a credit-eligible slope by design | ✅ confirmed |
| Credit pumps commitment | `effect_ledger.py:548` → `commitment_value.note_goal_credit`: value EMA converges to `0.5 + sig` (0.5 + 0.314 ≈ **0.8142**, the exact observed value), **and zeroes `stale_cycles` and halves `avoid_streak` on every credited effect** — the pump kept the incumbent permanently fresh | ✅ confirmed, worse than reported |
| sig 0.314 despite goal-alignment gating | `effect_ledger.py:463-478` — file_write base sig 0.4; `sig *= 0.75 + 0.25·alignment` → alignment ≈ 0.14 was *detected* but the 0.75 floor kept 78.5 % of sig | ✅ mechanism located |
| Avoid→release→re-commit orbit | `commitment_value.py` — no temporal exclusion exists anywhere; avoidance is only a score penalty (max −15) that `note_driver_selected` decays ×0.9/pull once the slot is lost, so a pumped incumbent (+3.1 value, +2 incumbent) re-wins as soon as the streak decays | ✅ confirmed |
| Credit keys off committed goal | `_write_research_memo` (`web_research.py:58-71`): `goal_id = bound_goal(ctx)` — whoever holds the driver slot at write time; aspiration `contribution_count` moves only via completion-path `mark_objective_contribution(driven_by)` / rollup | ✅ confirmed |
| Footer poisoned 4 stores | ledger credit, commitment value, S5 sig stream, + `quality_standard_revisions.json` (189/200 rows the same memo under fresh hashes; near-dup check runs at *apply* time only — `gate.py:153`, nothing at proposal time in `proposer.py`) | ✅ confirmed |
| `write_exemplar` EACCES cause | `gate.py:159-171` correct-by-shape; `QUALITY_EXEMPLARS_DIR` = repo-tree `tests/fixtures/quality_golden/exemplars` (`paths.py:191-192`), owner-writable post-mortem | ❓ unresolved — diagnostics-first is the right move |

**Two corrections to the findings:**

1. **`FileNotFoundError: brain/data/self_code/manifest.json` is NOT path
   drift.** The deeper-pass guess ("looks for a manifest that lives at
   `brain/agency/manifest.json.migrated`") is wrong: migration ran correctly
   (that's why `.migrated` exists). The real bug is `self_code.load_manifest`
   (`self_code.py:254-261`) reading `MANIFEST_FILE` unconditionally and
   recording the miss as a failure — on a fresh life the file legitimately
   doesn't exist until the first `save_manifest`. Fix is an existence check,
   not a path change.
2. **`acquisition.py:49` is not a code/comment divergence.** The comment reads
   "min seconds between narrations, so the fast (~10s) cognitive cycle can't
   flood the corpus" — the ~10 s describes the *cycle*, not a promised
   interval. Orrin's map-territory organ misread it (and then re-reported the
   misreading every ~75 min all life). The fix that matters is the organ's
   missing finding-dedup (F8b), plus an optional comment reword so it can't be
   misparsed again.

---

## 2. The fixes

Ordered by leverage. F1–F4 are the Run 7 gate; F5–F8 ride along.

### F1 — Commit the fetch-loop valve (already built, uncommitted)

The per-URL visited cache in `web_research.py` (`_url_cache`, `_pick_url`
skips, mark-before-fetch) + `tests/brain/test_web_research_url_dedup.py` sit
uncommitted in the working tree and never ran in the Run 6 life
(`FETCH_REREAD_LOOP_FIX_2026-07-11.md`). Commit as-is; it is the upstream
valve of the pump.

### F2 — Anti-pump credit at the ledger (one fix, four poisoned stores)

All in `brain/agency/effect_ledger.py` + `web_research.py`:

- **F2a — de-volatilize the hash.** Producer side: drop the timestamp from the
  memo footer (`web_research.py:66-67`) — keep `source: fetch_and_read`; the
  file's mtime already carries the time. Ledger side (defense for every other
  producer): strip ISO-date/time-shaped tokens
  (`\b\d{4}-\d{2}-\d{2}[ t]?\d{0,2}:?\d{0,2}z?\b`) in `_normalize` before
  hashing, so no volatile stamp can mint a fresh hash again. An identical body
  then exact-dups regardless of which goal folder it lands in — this also
  closes the cross-goal spread (the memo under 10+ goal dirs).
- **F2b — novelty gates credit.** In `record_effect`: computed novelty below a
  floor (`NOVELTY_CREDIT_FLOOR = 0.05`) → treated as dedupe (recorded,
  uncredited); novelty in `[0.05, 0.30)` → `sig *= nov / 0.30` (a ramp, so the
  intentional near-dup slope survives but pays proportionally). Run 6's
  0.002-novelty rows would have paid ~0 instead of 0.314 × 387.
- **F2c — per-path repeat-credit decay.** New `_path_credit_counts`
  (normalized path → credited-write count, rebuilt in `_hydrate` from row
  metadata): n-th credited write of the same path scales sig ×1 / ×0.5 / ×0.25,
  and n ≥ 3 → no credit. Matches the gate observable ("same artifact path
  credited ≤ ~3× per life") exactly.

### F3 — Content-keyed credit (the real R-D fix) + `genuine_contact` seam

- **F3a — value EMA weighted by alignment.** `record_effect` already computes
  `goal_alignment` (`effect_ledger.py:472`); pass it through to
  `note_goal_credit` and weight the EMA sample by it
  (`sample = 0.5 + sig·alignment` instead of `0.5 + sig`). A 0.14-aligned memo
  then nudges the committed goal's value toward ~0.54, not 0.81. Keep the
  staleness reset (the goal *did* act) but make the avoid-streak halving
  require alignment ≥ 0.3 — unrelated output is not counter-evidence to
  avoidance.
- **F3b — route aspiration credit by content.** New small router in
  `intrinsic_objectives`: classify a credited artifact against the four
  aspiration domains (reuse `goal_lens.relevance` against each aspiration's
  description lens); the argmax aspiration above a floor receives the drive
  credit that today goes solely to the committed goal's `driven_by`. The
  QuadRF memo then pays `world_knowledge`, whatever goal held the slot.
- **F3c — `genuine_contact` finally earns.** At the one door
  (`express_to_user.py:287` emission success): a person-facing reply typed
  `share_finding` / `answer` / `name_shared_situation`, with a person present
  and evaluator `quality_score` ≥ 0.5, calls
  `mark_objective_contribution("genuine_contact")` — rate-capped (≤ 1/hour) so
  this can't become the next pump. Two straight runs at 0 contributions with
  75 real speech rows is a missing wire, not missing behavior.

### F4 — Re-commit cooldown on avoidance release

`commitment_value.py`: in `note_driver_selected`, when the previous driver
loses the slot *while* its `avoid_streak ≥ 15` (¾ of `_AVOID_FULL` — i.e. it
was displaced by avoidance, not ordinary rotation), stamp
`recommit_block_pulls = 300` on its row, decremented per pull. In
`order_committable`, a directional whose block is active is **ineligible for
the driver slot** (stays a signpost; the next-best directional drives).
Explicitly: `note_goal_credit` does NOT clear the block, and `_W_INCUMBENT`
does not apply to a blocked goal — the block is temporal and unconditional,
"hysteresis be damned" (goals audit §3). This turns release from a rubber band
into an actual exit.

### F5 — Value-EMA diversity weighting (belt-and-braces on F2)

`note_goal_credit` gains the effect's `content_hash`; each signals row keeps a
short deque of its last 20 credited hashes, and the EMA sample is weighted by
the distinct-hash share. With F2 live this should rarely bind — it exists so
the *next* undiscovered volatile-token trick still can't buy a monopoly from a
single content family. (Goals audit §8 item 4.)

### F6 — `write_exemplar`: instrument, probe, and unclog the queue

- **F6a — capture the evidence.** At the `gate.py:168` OSError site, record
  `errno`, `os.access(dir, W_OK)`, and `stat` of the dir + parent alongside
  the exception. Twelve identical failures taught us nothing because
  `record_failure` kept only the message.
- **F6b — boot writability probe.** At startup, touch + unlink a probe file in
  `QUALITY_EXEMPLARS_DIR`; on failure, raise a real problem event (so
  problem-refocus starts with data, not a mystery) and log loudly. A dead
  promotion path must scream on cycle 1, not minute 13 in a log nobody reads.
- **F6c — proposal-time near-dup check (wiring item C8).** `proposer.py`
  re-nominated the same memo 189× because `_is_near_duplicate` runs only at
  apply time against a golden set that stayed empty. Run the same check
  against *pending revisions' artifact texts* before enqueueing. (F2a also
  collapses the flood at the hash level; this is cheap insurance.)

### F7 — Problem-refocus: verify, count, look inward (wiring C1–C3)

The organ's choreography was the run's best moment; three surgical wires make
it a diagnostician:

- **C2 — no evidence-free recovery.** The recovery check must *re-attempt the
  failed operation* (or a side-effect-free probe of it, e.g. the F6b
  writability probe for write failures) before declaring "working again."
  Nine of twelve episodes ended in a false recovery ~3 s after parking.
- **C3 — recurrence counter.** Per failure-key episode count, persisted; at
  ≥ 3 recurrences the "transient" hypothesis is refuted and the episode
  escalates (workaround/park, honest wording). Run 6 called it transient
  twelve times over fifteen hours.
- **C1 — internal failures route inward.** A failure key shaped like an
  internal module path (`quality_standard.gate.write_exemplar`) routes repair
  to the map-territory/self-code introspection organ, not `web_research`.
  Episode 11 literally web-searched his own internal bug.

### F8 — Small verified fixes

- **F8a** — `self_code.load_manifest`: `if not MANIFEST_FILE.exists(): return []`
  before the read (see correction §1.1) — kills 4 spurious failure rows/life.
- **F8b** — map-territory audit finding-dedup: cache reported finding keys
  (file + finding hash) so a standing observation is reported once, not every
  ~75 min forever. Same disease as fetch_and_read, different organ. Optionally
  reword the `acquisition.py:49` comment (§1.2) so it can't be misparsed.
- **F8c** — speech mid-referent truncation: `speech_content.py:137`
  (`text[:140]` → "QuadRF can s") and siblings cut at a word/sentence boundary
  instead of a raw slice.
- **F8d** — surface the F16 `cooldown_skipped` observable where run analysis
  can find it (decision-stats snapshot), still missing per §6 check 8.

---

## 3. Explicitly deferred (tracked, not this round)

- **C4–C7, C9–C11** from the self-awareness wiring list (correction
  persistence, monitor authority, mantra-edge corroboration, forward-model
  cost, volition-over-commitments, tension coverage, WM merge threshold) —
  real, but each is its own design; C6/C7 get partial coverage free from
  F2/F3 (relief-only edges stop out-earning task outcomes).
- **Memory composition** (89 % wm-summary flood; F17/F18 target < 40 %) —
  failed twice unchanged; needs its own plan, not a rider.
- **S1 repeat-family cap** ("Strengthen … symbolic reasoning" = 8/17
  completions) and **R5 consolidation pressure** — watch first: both are
  plausibly downstream of the treadmill owning the slot; F1–F4 must run a life
  before adding more mechanism.
- **`ltc_` child churn** (~232 minted, 2 ever drove) — instrument only if it
  survives Run 7.

## 4. Test plan

- Unit: footer-stripped hash equality (same body ± timestamp footer → same
  hash); novelty floor + ramp arithmetic; per-path decay schedule (1/0.5/0.25/0);
  alignment-weighted EMA sample; recommit block set/decrement/driver-skip
  (incl. credit does NOT clear it); router argmax on the four aspiration
  domains; `genuine_contact` rate cap; recovery-check requires re-attempt;
  recurrence escalation at 3; manifest existence check; word-boundary cut.
- Characterization: replay a QuadRF-shaped sequence (same body, fresh
  footers, one committed goal) through `record_effect` → assert total credit
  ≤ 3 rows and `value_ema` < 0.6.
- `make verify` green before staging; venv mypy/ruff upgraded to CI's unpinned
  latest first (2026-07-09 incident).

## 5. Run 7 gate (already written into `NEXT_RUN_TESTS.md`)

No committed goal > 60 % · reuse ≥ 8 · `genuine_contact` > 0 · same artifact
path credited ≤ ~3× per life — plus (new observables from this plan): zero
credited rows with novelty < 0.05, `write_exemplar` either works or fails with
a captured errno + boot-probe alarm, and no false-recovery line without a
verified re-attempt.
