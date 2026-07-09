# Run 4 — every open issue and how to improve, consolidated (2026-07-04)

One place for everything found across the 2026-07-03 run analysis (7 docs +
2 data audits in `demo_runs/2026-07-03-run/`), ordered by what it buys the
next demo run. Each issue: evidence, root cause, the fix, and what Run 4
should show if it landed. Issues already fixed on 2026-07-04 are in §5 so
they get *verified*, not re-fixed.

**The one-paragraph state of the organism:** he completes goals steadily,
makes real artifacts (11 research memos), credits all four aspirations,
remembers the person who talks to him, fails honestly and machine-readably,
and regulates through 54 flagship failures without spiraling. What's left is
circulation and attention: nothing he makes is ever used again, one saturated
signal owns his workspace every life, his learned values don't steer
selection, and the v1/v2 goal seam leaks resurrections under every
completion.

---

## 1. Critical — these gate Run 4 (§8 re-test: 7-reuse, 8, 9 must move; 5, 6 hold)

### 1.1 Nothing he makes is ever used again (S7's failing half)
- **Evidence:** 11 memos written, 0 ever read back; `mark_reused` has **zero
  call sites** in behaviour; `production_handoff_count` 0 all 11,333 cycles
  (`pending_production_action` never set).
- **Root cause:** the reuse machinery exists in `effect_ledger.py`
  (tier-3 credit, "the only ungameable significance signal") but no organ
  calls it, and the conscious lane has no path that stages a production
  action for the funnel.
- **Fix:** (a) wire `mark_reused(content_hash)` into the real read paths —
  when research retrieves/quotes a prior memo, when `read_a_book`/
  `fetch_and_read` opens an own-artifact path, when a goal builds on a prior
  goal's artifact dir; (b) give the research generator a "build on prior
  memo" step when a same-topic memo exists (cheapest genuine reuse arc);
  (c) let the conscious lane stage `pending_production_action` when a
  make-intent wins the pick.
- **Run 4 shows:** ≥1 ledger `reuse` row; handoff_count > 0.

### 1.2 The v2→v1 completion bridge leaks resurrections (S8 regression)
- **Evidence:** `store_desyncs_repaired` **12** (Run 2: 0); every repair is
  `[goal_reconcile] resurrection repaired: … re-closed in v1`, tracking
  research/housekeeping completions ~1:1.
- **Root cause:** a goal completing in the v2 store leaves/reopens a live v1
  mirror; invisible until this run because research goals never completed
  before. The reconciler (200-cycle pass) is masking a systematic seam.
- **Fix:** close the v1 mirror in the same transaction as the v2 completion
  (the completion-record chokepoint already stamps `serves`/`driven_by` — do
  the v1 close there too). If the bridge can't be made transactional, this
  run formally triggered §8's escalation: execute GOAL_STORE_UNIFICATION.
- **Run 4 shows:** `store_desyncs_repaired` back to ~0 *with* ≥10 completions
  (zero-completions-zero-desyncs doesn't count — that was Run 2's illusion).

### 1.3 Learned value doesn't steer selection (S9 unfalsifiable as phrased)
- **Evidence:** corr(EMA, pick-share change) ≈ **−0.15**; `look_outward`
  (lowest major EMA, 0.150; avg reward 0.216 over 3,961 scored picks) *gained*
  share; `signal_function_map.json` holds a learned
  `exploration_drive→look_outward` coupling of **0.706** — affect routing
  outvotes value; `outward_satiety` had `look_outward` at 1.0 (maximally
  sated) and it kept winning. The four meta-controller arms learned nothing
  (0.40–0.42 after 11k pulls).
- **Root cause:** the multi-factor ranker weights (`emo 0.312 / goal 0.297 /
  band 0.25 / dir 0.22 / drive 0.15 / novel 0.12`) fold the reward EMA in as a
  fraction of one term. Run 2's apparent EMA→selection link was partly the
  stuck-loop self-payment that fix #10 removed.
- **Fix (decide, then implement — smallest honest version):** make the EMA a
  *multiplicative* modulator on the final score (e.g. `score × (0.5 + ema)`)
  or give satiety/value a veto tier above affect routing. Also floor the
  `signal_function_map` couplings' growth so one association can't reach 0.71
  while all others sit at 0.195. Whatever is chosen, write the intended
  authority into the §8 S9 row so the signal is testable.
- **Run 4 shows:** a positive EMA↔share-delta correlation, and `look_outward`
  share falling while its EMA stays low.

### 1.4 One saturated signal owns every life (the jammed-horn law)
- **Evidence:** three consecutive lives monopolized by one undischargeable
  signal — phantom `action_debt` (06-17), `drive_rest@1.00` (~74%, 07-02),
  `social_presence@1.00` (**84%**, 07-03). Each starves the consolidation
  organs (07-03: 1 crystallized skill, 12 rule firings, everything dark by
  01:11 EDT).
- **Root cause:** ignition has no habituation — an *unchanged* signal at an
  unchanged value competes at full strength forever. Any signal that can
  reach 1.0 with no discharging behavior eventually wins every cycle.
- **Fix:** ignition-layer habituation: attenuate a signal's effective
  strength when (source, quantized value) is identical to what already
  ignited N of the last M cycles; full strength returns the moment the value
  *changes*. This is one mechanism instead of a fourth per-drive patch. The
  2026-07-04 social tone-down (§5) treats the current horn; this fixes the
  pattern.
- **Run 4 shows:** no single source above ~40% of ignitions while alone;
  emotion/prediction-check ignitions still present in hour 6 (07-03: they
  never reappeared after hour 1).

## 2. High — big behaviour wins, not gate-blocking

### 2.1 `generic`-kind v2 goals are never scheduled (the starved make-goal)
*"Turn what I know about evolutionary biology into a written synthesis"* —
born from problem-refocus at 08:16Z, `NEW→READY` in one second, never ran in
8 hours while 11 research goals were scheduled around it; the flagship
aspiration meanwhile failed 54× on `no_artifact_by_deadline`, and
`making_backlog.json` has never held an item. Fix the daemon's runnable-kind
selection to cover `generic` (likely small — it demonstrably schedules
`research` and `housekeeping`). **This is the cheapest path to his first real
product.** Run 4: that goal (or its successor) DONE or honestly FAILED, and
≥1 non-research artifact in `data/goals/artifacts/`.

### 2.2 Consolidation must survive a busy workspace
The blackout replicated under a different monopoly, so it isn't rest-specific.
The existence proof is in this run's data: the 3-hour dream timer never missed
(5/5) while every ignition-gated integrative organ died in hour 3. Interim
fix: move crystallization / rule-firing / world-model audit to timers or
protected slots the way dreams already are. Real fix: SL1–SL5. Run 4:
`crystallized_skills`, `rule_firings.jsonl`, `world_model_stats` all have
mtimes in the back half of the run.

### 2.3 Satiety closures still 0 (S3 — red since Run 1)
19 "Refusing satiety close" honesty refusals, 0 closures, three runs running.
Either the quench threshold is unreachable (audit what the gate demands vs.
what a satisfied understanding goal actually looks like in the stores) or the
path has a dead precondition. Run 4: ≥1 satiety closure, or a documented
decision that the gate's S3 expectation is wrong.

### 2.4 Aspiration credit quality (protect S6 before it's load-bearing)
S6 passed, but the making aspiration's 2 credits are research goals
(artifact partial-credit path), and 158 of 162 generated candidates targeted
one aspiration. Tighten: `output_producing` credit requires a
`file_write`/`tool_run` effect on a goal whose *own* kind is make-shaped; keep
AR5's quota honest at the candidate stage. Run 4: S6 still no-zeros with at
least one credit from a genuine make-goal (pairs with 2.1).

## 3. Medium — bugs and hygiene (one housekeeping round)

| # | Issue | Evidence | Fix |
|---|---|---|---|
| 3.1 | `social_penalty` emotion unknown | 37 dropped deltas during the one conversation — the speech-block penalty silently no-ops | register the emotion in the buffer's vocabulary, or emit an existing one |
| 3.2 | `final_thoughts_written` still `False` at death | third run in a row; the 07-02 read-modify-write didn't close the race | set the flag in the same write (or after fsync) of `final_thoughts.json` itself, not via the lifespan file |
| 3.3 | `attention_value_weights` underflow | `system`/`long_memory`/`internal`/`fs_perception` at ~1e-25 — dead channels that can never multiply back | floor at ~0.01; same class as drive-pinning, opposite direction |
| 3.4 | Root `data/memory/wal/events.jsonl` unrotated | **15.0 MB**, the only WAL without rotation (items.jsonl rotates fine) | apply the same gz rotation as items |
| 3.5 | `trace.jsonl` rows still fat | 3,000 rows = 28.3 MB (~9.4 KB/row, full emotion+committed snapshot per row) | slim the row schema |
| 3.6 | `workspace_writeback.jsonl` unbounded | ~1 MB/run append; the loop itself is healthy (validated this run) | rotate or cap |
| 3.7 | Seven fossil files | `proposed_goals`, `symbolic_plans`, `map_territory_audit_state`, `concepts`, `consolidation_queue`, `learned_phrases`, `failure_summary` all `{}` at birth-mtime (+ `model_failures.txt` 0 B, `vocabulary.json` {} beside a live `symbolic_dictionary`) | retire the file + its readers, or wire the writer — per file, one or the other |
| 3.8 | Empty library | `read_a_book` picked 73× against an empty `language/library/`; `book_reads.json` `{}` | stock the shelf (drop a few public-domain texts in) or retire the shelf path |
| 3.9 | Midnight-straddle metrics | the run crossed midnight → two `outcome_metrics` rows; naive reads under-report | teach §8 tooling to sum rows in the run window |
| 3.10 | Poisoned semantic fact | `produce_and_check → neutral, n=228, conf 0.979` — learned from the stuck loop; wrong once the lane bridge lands | decay or re-test high-confidence facts whose source lane changed |
| 3.11 | `long_memory` tags never populated | 2,001 entries, zero tags | populate at write time or drop the field |

## 4. Known-and-accepted (do not re-litigate for Run 4)

- **Allostatic layer inert** (`allostatic_load` 0.000 every life; arming line
  0.60 unreachable, active EMA ~0.44) — standing invariant since 06-29;
  behavioural tuning decision, not a bug.
- **Identity/mouth surface** — the dying self-story is still bracket-tag
  salad and 658/662 expressed notes are the "hard to name" template; the
  narration pairs feeding the native LM carry the same monotone. Blocked on
  the P2 felt-surface vocabulary + speech-feedback roadmap, not hotfixable.
  (Two "something I actually found out" notes escaped this run — the channel
  exists.)
- **Speech self-evaluation idle** (12/150 evaluated) — structurally
  reply-dependent; nothing to fix until there is more conversation.
- **Stuck-step loop behaviour** — its pay exploit is closed and its output
  metered; the residual step-name→`produce_and_check` matching at sim=0.35
  gets absorbed by 1.3/2.1 rather than its own fix.

## 5. Already fixed 2026-07-04 — verify, don't re-fix

Social tone-down (response to the 84% monopoly; suite green 1,331/5 skipped):

1. **Stale-input boot bug** — `social_presence.py` seeds `_last_input_mtime`
   with the file's boot mtime; leftover `user_input.txt` content (this run:
   `"i wonder why."`) can no longer mint a phantom visitor at birth.
2. **Presence signal** — threshold 0.40→0.50, ×1.1 amplifier removed,
   strength capped **0.85**.
3. **Distant-user easing** — >1 h silence caps pressure at **0.60** instead
   of climbing to 0.95.
4. **Social drive leak** — `demand_engine.py` `leak_per_tick=0.005` →
   equilibrium ≈ **0.66**, signal ≈ 0.79 (was pinned 1.0 → 1.00).

**Run 4 verifies:** no person record until someone actually speaks;
`social_presence` a minority ignition source while alone; `drive_social`
cruising ~0.66. If a *different* signal monopolizes instead, that is the
jammed-horn law (1.4) demonstrating itself a fourth time — treat it as
priority evidence, not a new per-signal bug.

## 6. Suggested build order before Run 4

Two rounds, test-gated (`make verify` green before the run; §3 subset green
before and after):

1. **Round A — the gate:** 1.2 (completion bridge), 1.1 (reuse call sites +
   handoff), 2.1 (generic scheduling — cheap, high payoff), 1.3 (EMA
   authority decision + implementation).
2. **Round B — the environment the gate is measured in:** 1.4 (ignition
   habituation), 2.2 (timer-ize consolidation), then the §3 table as one
   housekeeping sweep (3.1–3.11 are each small).

If time allows only one thing beyond Round A, pick **1.4** — every §8 number
so far has been measured through a jammed horn, and Run 4's numbers are only
as trustworthy as its ignition diet.

## 7. Run 4 checklist (pin next to the §8 gate)

- [ ] Preconditions: clean reset, single instance, tests green, baseline
      copies of `outcome_metrics` + `action_reward_ema`, ~10k+ cycles.
- [ ] S5 holds (mean significance ≳ 1.1) and S6 holds (no aspiration at 0,
      ≥1 credit from a genuine make-goal).
- [ ] S7: ≥1 `reuse` ledger row, handoffs > 0, ≥1 non-research artifact.
- [ ] S8: desyncs ~0 **with** double-digit completions.
- [ ] S9: positive EMA↔share correlation; `look_outward` share falls.
- [ ] Ignition: no source >40% while alone; consolidation organs writing in
      the back half; dreams still 5/5.
- [ ] Social: no phantom person at boot; `drive_social` ~0.66; if someone
      talks — ToM updates, person record moves, and check whether the mouth
      can now say anything it knows (e.g. "did you sleep?" → yes).
- [ ] Honesty spine unchanged: failures machine-readable, satiety refusals
      logged (closures >0 or S3 re-scoped), zero crashes, clean death.

*Compiled 2026-07-04 from `demo_runs/2026-07-03-run/` (run_analysis,
did_the_fixes_land, what_did_he_make, who_is_he, deeper_pass, both data
audits) and `NEXT_RUN_TESTS.md`. The social tone-down in §5 is the only code
change made since the run.*
