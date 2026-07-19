# Next-Run Verification — Production Reward Plan

*What to test on the next clean-instance life run, and how to decide pass/fail.*

This is the **§8 acceptance gate** for `docs/Behavioral Evaluation & Runtime
Diagnostics/ORRIN_PRODUCTION_REWARD_PLAN_2026-06-18.md`. The code for that plan
(§7 + P0–P8 + Guards) is **implemented and unit-tested as of 2026-06-19**; what is
**not** yet done is confirming the behavior actually changed in a real run. Until
the signals below move, the fix is "shipped" but not "proven" — `looks better` is
not a result. A run that doesn't move these is a **failed fix, not a matter of
interpretation**.

> **2026-07-01:** the AR1–AR4 work in `docs/Behavioral Evaluation & Runtime
> Diagnostics/IMPLEMENTATION_PLAN_AUDIT_REMEDIATION_2026-07-01.md` is what should
> move signals 5/6/7/9 on the next run.

---

## Run 6 re-test gate (2026-07-09 — from `RUN6_FIX_PLAN_2026-07-08.md` §4)

Run 4 (07-05) and Run 5 (07-08) results live in their run folders
(`demo_runs/2026-07-05-run/`, `demo_runs/2026-07-08-run/`); Run 5's verdict:
gate NOT passed, S6/S9 fail, and the recurring monopoly relocated to the
*committed goal* (`self_understanding`, **99.9 %** of cycles). The Run 6 build
(selection value authority + commitment score/rotation + avoidance-release +
credit/commitment loop + ledger hygiene) targets the root: **learned outcomes
now have authority over both selection and commitment.**

**Run 6 passes iff all of the following hold:**

- **S9 passes:** `corr(action_reward_ema, selection-share) > 0`; `look_outward`
  share **falls** while its EMA stays < 0.3; no mature action (≥8 observations)
  with realized reward < 0.3 sits in the top-3 selected.
- **NEW S10 — anti-monopoly:** no single channel exceeds **~60 % of its layer**
  for the life, at *every* layer the monopoly has relocated through: ignition
  source (Runs 2–3), candidate-generator flavor (Run 4), and committed goal
  (Run 5). For commitment specifically: no committed goal > ~60 % of cycles;
  `genuine_contact` (0 in Run 5) gets committed and earns > 0 contributions;
  the death snapshot's committed goal is not the one that owned the whole life.
- **Avoidance releases commitment:** goal-avoidance events per life fall
  sharply (Run 5: 240, all on one goal); no avoidance streak exceeds ~20 cycles
  without a commitment change.
- **Credit/commitment convergence:** by end of life the most-committed
  aspiration and the top-credited aspiration are the same; no aspiration is
  both "committed most" and "credited least".
- **HOLDS:** S7 reuse ≥ Run 5 (8 reuse rows), S8 desyncs stay 0, all four
  aspirations survive the whole life (F2), S5 mean significance > 0 — now
  computed over readable-body material only (`bookkeeping` causal-edge rows are
  a separate ledger class and excluded from production/significance counts;
  read `bookkeeping_count` in `production_loop.jsonl` separately).
- **Meters trusted:** `satiety_closures` now wired to the pursuit-path satiety
  close (S3 read 0 in Run 5 while 7 real closes happened), and `reset_orrin.py`
  clears `habituation.json` (91 % survived the Run-5 "clean" reset) — confirm a
  fresh reset zeroes it before trusting S3 or any exploration-share number.

New instrumentation to read: `brain/data/commitment_signals.json` (per-goal
value EMA / staleness / avoidance the commitment score sorts on) and the
per-candidate `value` component in the selection reason payload.

---

## Run 9 re-test gate (2026-07-16 — from `RUN9_DEEP_ANALYSIS_2026-07-15.md`)

The Run 9 build landed 2026-07-16 (clean reset done the same day): **R9-F1**
in-flight step guard (daemon skips queued/running step ids), **R9-F2** workers
re-read the step fresh + never run a step of a terminal goal (zombie kill),
**R9-F3** stage-suffix artifact loading in research.py, **R9-F4** attempts
capped at max + goal `last_error` taken from the FAILED step, **R9-F5**
title-scaffold stoplist in `_find_prior_memo`, **R9-F6** `mark_reused` stamps
real cycle + owning path, plus the two owed items (invoke.py keyword-only
regression test; **cycle-stall tripwire** keyed on `production_loop` cycle
stamps, `supervisor/cycle_stall.py`, default 900 s / `ORRIN_CYCLE_STALL_S`).
Also found+fixed while wiring: `watchdog_setup.build()` kwargs had drifted from
`start_watchdogs` (vital_*/resource_on_* spellings), so every prior life ran on
the bare-fallback watchdogs with NO resource providers — the fallback now
prints a DEGRADED warning instead of swallowing the TypeError.

**G2 is rescored (Finding 5):** F1's refractory is unreachable in any life
where F2 rotation works (Run 8 max stale 8.8 vs the 250 trip — 28× margin), so
the release is proven by the **forced-fire harness**
`tests/brain/test_refractory_harness.py` (280 uncredited pulls → exactly one
`refractory_events` release at stale=250, block counts down 1/pull, blocked
holder yields the directional slot, credit resets accrual). G2 = that test
green, not a life observable. The ablation life is deleted from the plan; F1
stays as a zero-cost backstop.

**Run 9′ is a verification life. It passes iff:**

- **S4 honest failures:** research goals whose artifacts exist on disk are not
  marked FAILED; no step's `attempts` exceeds `max_attempts` in the WAL; no
  DONE→FAILED flapping on a single step; failed goals carry the failing step's
  real `last_error` (never `None`, never the zombie's).
- **S7 reuse is topical:** every `reuse` row carries a real `cycle` and
  `metadata.path`, and cited memos share subject tokens with the citing goal
  (no cross-topic boilerplate matches). Reuse ≥ 8 stands as the target now that
  failures can't manufacture/mask it — but do not raise the target past 8
  before checking topicality (Finding 3's caveat).
- **Exemplar promotion fires** on this first life with a writable dir (watch
  for the boot probe; if EACCES recurs, the backup/sync lock re-applied).
- **HOLDS:** S8 desyncs 0, S10/G1 occupancy < 60 % via F2 rotation, value
  anti-pump intact, all four aspirations survive, production does not collapse.
- **Capture `data/goals/` (WAL + state + artifacts)** into the run folder —
  the Run 8 capture lost it and the diagnosis had to mine the live WAL.

**Out of scope for Run 9′ (Ric's product decisions, Finding 2 + Finding 6):**
`genuine_contact` stays structurally unscoreable unattended — options are (a)
scripted-interaction arm, (b) headless outbox with post-life reply credit,
(c) score S6-contact only on attended lives; recommendation (b)+(c). R9-F8
(move runtime exemplars out of `tests/fixtures/quality_golden/`) needs sign-off
because the golden/promoted split must survive the relocation. Finding 7 (the
difficulty ladder) is the post-gate axis, target Run 11 planning.

---

## Run 9′ result — 2026-07-17 life: **NOT PASSED as written** (S7 count 1 < 8) — but every Run 9 mechanism proven (S4 🟡 · S7 🔴count/🟢quality · exemplars 🟢 first ever · S8 🟡 · G1 🟢 40.5 % best ever)

Ninth acceptance run (build R9-F1..F7, **10,278 cycles**, **two segments**:
7.3 h to a `HARD:memory_leak_slope` supervisor kill at rss 1,898 MB, then a
relaunch + 1.6 h to a clean operator stop; cycle counter contiguous across the
seam, boundary ≈ cycle 8,710). Full analysis:
`docs/Behavioral Evaluation & Runtime Diagnostics/demo_runs/2026-07-17-run/DEMO_RUN_2026-07-17.md`.

**First life with live resource watchdogs** (kwargs-drift fix) — and the
memory guard fired for real, completing the first end-to-end supervision arc
(detect → graceful window → kill → relaunch → rebirth with `final_thoughts`).
The 726 MB/60 s burst that tripped it is **unattributed** (no RSS series is
kept; only the last value survives) on top of a real ~2–3 MB/min estate climb
(segment 2 died at 805 MB @ 1.6 h vs segment 1's 1,898 MB @ 7.3 h).

- **S4** 🟡 — the runner race is dead: 0 steps past `max_attempts`, 0
  DONE→FAILED flaps, 0 daemon FAILED goals, all failure reasons real cap-outs.
  Caveats: one goal double-failed 5 min apart (second reason is placeholder
  junk `['?', '?']`), and a drive-by `fetch_and_read` intake memo (off-topic
  PLOS scrape) was filed into that failing goal's artifact dir — letter
  violation of "artifacts ⇒ not FAILED", but not the goal's own work.
- **S7** 🔴 on count / 🟢 on integrity — exactly **1** reuse row, but it's the
  first fully honest one: real cycle (8,803), real path, topical
  (evolutionary-biology goal citing the evolutionary-biology memo), citing
  goal went DONE (Run 8's reuse↔failure time-lock gone), hash matches a
  promoted exemplar. Mechanics proven; volume regressed (Run 8: 2).
- **Exemplar promotion** 🟢 — **fired for the first time in nine lives** (3
  promoted at 07:56Z). But the segment-1 boot probe DID catch EACCES (launch
  lock re-applied; writable later; segment-2 probe clean), and one promoted
  exemplar is ~90 % pasted abstract — the bar can't tell scrape from
  synthesis.
- **HOLDS:** G1/S10 🟢 **40.5 %** top occupancy (best ever; all four
  aspirations drove; max stale 6.5 so F1 stayed untouched, per the G2
  harness rescoring) · anti-pump 🟢 (`value_ema` 0.5196, max path credit 3×) ·
  aspirations 🟢 all four survive · production 🟢 37 attempts / 17 successes
  (Run 8: 37/21) · **S8 🟡 regression in letter** — 2 desyncs, both the same
  twin-id research goal re-closing in v1 in the first 11 minutes, then 0 for
  ~9 h. Root cause: the same question was created as **two goal ids in two
  stores** (daemon DONE in 6 s; brain-side twin failed at the cap) — one seam
  behind the desyncs, the double-failure, and the S4 ambiguity.
- **Capture** 🟢 — full `data/goals/` daemon tree in the run folder (Run 8's
  gap closed). `genuine_contact` 0 at every stage and funnel candidate-only,
  both out of scope as declared.

**Re-test gate (Run 10)** (detail in the run doc §Run 10 fix list): (a) RSS
time series into telemetry + attribute the estate growth; (b) one question =
one goal id (unify creation across stores); (c) intake memos filed by
provenance, not slot; (d) ~~originality check before exemplar promotion~~
**BUILT 2026-07-18** (`quality_standard/originality.py` veto + scrape exemplar
purged; see run doc §item 6); (e) confirm the run-lock script fix at launch;
(f) check the daemon's 1.5 h
silence in segment 2 (R9-F1 over-suppression?); (g) reuse ≥ 8 stands; reset
should clear stale `data/goals/artifacts/` leftovers.

> **Run 10 attempt 1 (2026-07-18): ABORTED, gate untested.** 2,671 cycles
> (~1.7 h) on `b175ed2`, killed externally — terminal close tripped
> `BrokenPipeError` in `graceful_shutdown` (`runtime/lifecycle.py:132`) which
> also skipped run-lock cleanup. Capture in `demo_runs/2026-07-18-run-aborted/`;
> shutdown prints made pipe-safe; this gate rolls over unchanged to the relaunch.

**Added 2026-07-18 from the whole-system skeptic pass** (run doc §items
10–14, with per-item observables): (h) **reward sees impossibility** — a
gate-blocked action (this life: `decide_to_write_code`, blocked 369/369,
EMA #2 at 0.618) writes zero-with-prejudice and leaves the selectable set
while blocked; (i) **signal-saturation tripwire** — ignition fired
10,278/10,278 cycles on `drive_mastery` pinned at 1.00; any signal flat at a
bound ~500+ cycles → forced recalibration; **verdicts must again score every
historical monopoly layer** (ignition source, generator flavor, commitment,
value) — the saturation went unseen because ignition stopped being scored
after Run 3; (j) **knowledge-formation refractory** — one reinforcement per
rule per cycle (goal_avoidance rule hit 66,087 times ≈ 6×/cycle);
(k) **first outward causal edge** — the graph is 241/241 interoceptive;
(l) **epistemic close-out on understanding goals** — close on an answered
question derived at creation, not on satiety alone (difficulty-ladder rung 1,
B18 in embryo). This is the **keystone (rung 0)** of the value-grounding design
`Core Architecture, Embodiment & Evolution/QUALITY_GROUNDING_DESIGN_2026-07-18.md`
— the one "source of good" Orrin structurally lacks (grounded consequences),
without which the quality stack only measures itself. Also declared: **LLM mode is a run variable, not an ambient
accident** — every verdict states `mode: symbolic-only` or `mode: LLM-assisted`
up front (this run: symbolic-only; the promoted exemplars are offline
scrape-stitches, hence gate item (d)).

---

## Run 8 re-test gate (2026-07-14 — from `RUN8_FIX_PLAN_2026-07-14.md`)

Run 7 (2026-07-12 life, `demo_runs/2026-07-12-run/`) proved the Run-7 anti-pump
worked *and* that it was not enough: the committed-goal monopoly survived at
**90.9 %** (10,052 / 11,060 cycles) with `stale_cycles = 10,291` /
`avoid_streak = 6,852` on `self_understanding` and **no** pumped value
(`value_ema 0.5196`). Diagnosis (verified in `RUN8_FIX_PLAN` §1): every
anti-monopoly lever in `commit_score` is *relative* and saturates at −30; with no
rival in range it did nothing for ~10k cycles. Run 8 adds the missing **absolute**
lever (F1): a holder that occupies the driver slot for `_STALE_REFRACTORY_CYCLES`
(250) with **zero** credited effect arms its own `recommit_block_pulls` and yields
the slot regardless of rivals — reusing Run 7's F4 block machinery.

**This is a single-lever fix. The run must show it fired *and* that it did not
just replace one pathology (monopoly) with another (forced churn / idleness).**

**Run 8 passes iff all of the following hold** (read
`brain/data/commitment_signals.json`: per-goal `stale_cycles`/`avoid_streak`/
`recommit_block_pulls` + the new `refractory_events` list; committed-goal
occupancy from the driver-slot share the run capture already computes):

- **G1 — monopoly broken (headline):** no committed goal exceeds **~60 %** of
  life cycles (Run 7: 90.9 %). This is the number the last six runs never moved.
- **G2 — the release actually fired:** `refractory_events` is **non-empty** and
  contains ≥ 1 release of the goal that would otherwise have monopolized; **max
  `stale_cycles` at death is in the hundreds, not thousands** (target < ~550 =
  `_STALE_REFRACTORY_CYCLES + _RECOMMIT_BLOCK_PULLS`). If `refractory_events` is
  empty, F1 never triggered → **failed fix, not interpretation** (check the trip
  condition / flag, don't reinterpret).
- **G3 — release latency collapses:** cycles from a holder crossing the stale
  ceiling to a durable driver change ≤ ~300 (one block), not 10,000; no
  `avoid_streak` climbs into the thousands.
- **G4 — persistence-under-progress preserved (anti-thrash guard):** **no
  refractory event fires on a goal that is earning credit** — releases correlate
  with `stale_cycles` (no credit), never with punishing productive work. A
  directional that keeps producing may still hold the slot > 60 % *if its
  contributions are real* — in that case G1 is met by contribution diversity, not
  by starving it. Driver changes must track evidence, not a clock.
- **G5 — HOLDS (no regression, and not idle):** value anti-pump holds
  (`value_ema` not re-pumped, no memo loop); S8 desyncs stay 0; all four
  aspirations survive; S7 reuse ≥ Run 7; and **production/contribution does not
  collapse** — `self_understanding` should still *contribute* (Run 7:
  `contribution_count` 1), just not *own* the slot. Breaking the monopoly by
  making Orrin do nothing is a **failure**.

**Decision rule:** **G1 is the headline, but G1 without G4 is a regression** —
periodic switching regardless of evidence is the exact naive-regulator pathology
the fix is designed to avoid. **Pass = G1 ∧ G2 ∧ G4, with G5 showing no
regression.** Optional ablation arm: a second life with
`ORRIN_STALE_REFRACTORY=0` should reproduce Run-7-shaped occupancy, isolating F1
as the cause of any improvement.

**If G1 misses but G2 fired** (releases happened, monopoly persisted): the block
is too short or the ceiling too high → lower `_STALE_REFRACTORY_CYCLES` (250 →
150) and/or raise `_RECOMMIT_BLOCK_PULLS`; do **not** re-architect. **If G4
misses** (thrash): raise `_STALE_REFRACTORY_CYCLES` so productive holders get more
rope. Only if F1 fires cleanly (G2, G4) yet G1 still misses does the deferred
work in `RUN8_FIX_PLAN` §6 (global pressure / phase) become warranted.

---

## Run 8 result — 2026-07-15 life: **NOT PASSED as written, but the monopoly finally broke** (G1 ✅ · G2 ❌ · G4 ✅ · G5 🟡 · S10 ✅ · S6/S7 🔴)

Eighth acceptance run (build `fc2b635` F1+F2, **9,785 cycles**, **two runtime
segments split by a mid-life crash**). Full analysis:
`docs/Behavioral Evaluation & Runtime Diagnostics/demo_runs/2026-07-15-run/DEMO_RUN_2026-07-15.md`.

**Verdict: objective achieved, formal gate not passed.** The ≥6-run
committed-goal monopoly moved **90.9 % → 42.6 %** (S10 ✅ / G1 ✅) — all four
aspirations drove the slot, `genuine_contact` committed for the first time,
holds in both segments (54 % / 44 %, both < 60 %). **But F1 never fired**:
`refractory_events` is empty, all `recommit_block_pulls` = 0, max `stale_cycles`
= 8.8. **F2 (aspiration rotation) is the load-bearing lever** — it kept the slot
turning so staleness never accumulated to F1's 250-cycle trip. So `G2` (release
must fire) is unmet and `G5` regressed on reuse (2 < 4). `Pass = G1 ∧ G2 ∧ G4`
→ **NOT passed**, but by prevention, not failure.

**Two events dominate the engineering read:** (1) a real crash — uncaught
`TypeError: make_candidate() missing … keyword-only arguments 'kind','direction'`
at `invoke.py:108`, killed the brain thread mid-cycle **4418** (the exact cycle
missing at the `production_loop` seam; the "~4253" in `crash.log` is stale
block-buffered stdout); the dispatchability guard ignored required
`KEYWORD_ONLY` params. Fixed mid-life; fix committed in `e70ac98`; segment 2 ran
clean. (2) the watchdog took 6.5 h to notice the dead cognitive loop
(pulse-based liveness, not cycle-advance).

**Second-pass audit findings (verdict §4b):** both reuse rows resolve to
concrete referents via `content_hash` — one is a synthesis citing the prior
written-language memo by filename — so "referent-less reuse" is retracted; but
**both reuse events are time-locked ≤ 250 ms before goal failures** (the goals
doing the reuse are the ones recorded as failed). `genuine_contact`'s hole is at
goal *generation* (zero scoreboard events at any stage), not completion. Only 3
of 7 failures are traceable in the capture ("emotional response triggered" is
the loop's reaction, not a cause; the `goals_daemon/` tree wasn't captured).

> **Superseded in part by the no-run diagnosis pass:**
> `docs/Behavioral Evaluation & Runtime Diagnostics/RUN9_DEEP_ANALYSIS_2026-07-15.md`
> root-caused every remaining red without a life — the research-goal failures
> are a daemon runner race (all three "failed" goals' work succeeded on disk),
> `genuine_contact` is structurally unscoreable unattended, `_find_prior_memo`
> matches on title boilerplate, and the F1 ablation life is replaced by a
> forced-fire harness test (R9-F7). Items (a)–(e) below stand where not
> contradicted; the R9-F1..F8 fix list in that doc is the Run 9 build. Its
> Finding 7 also scopes what this gate does and does not prove: passing it
> twice = the goals system is *stable* (regulatory learning), not *growing* —
> no difficulty ladder exists yet (quality ratchet has 0 live hours, reuse
> compounding broken, outcome labels race-noised). The ladder is the post-gate
> axis (target: Run 11 planning).

**Re-test gate (Run 9):** (a) **`ORRIN_STALE_REFRACTORY=0` ablation** — confirm
occupancy stays < 60 % with F1 off (proves F2 is the lever; decide F1's fate —
note max stale was 8.8 vs the 250 trip, a 28× margin: with F2 on, F1's code path
is unreachable in life); (b) ~~commit `invoke.py` fix~~ *(done, `e70ac98`)* +
**regression test** (required-keyword-only fn is skipped, not dispatched);
(c) cycle-stall tripwire in the watchdog, keyed on `production_loop` cycle
stamps (the only crash-accurate counter — heartbeat lagged 18 cycles, stdout
~160); (d) ~~clear the `uchg`/`0o500` lock~~ *(done post-capture 2026-07-15,
repo-wide)* → **confirm exemplar promotion fires** on its first life with a
writable dir, and watch for the lock re-applying (backup/sync suspected);
(e) contribution layer — reuse ≥ 8 *and* understand the reuse↔failure
time-lock before optimizing either; `genuine_contact` generation > 0 (fix
belongs in the contact→goal-generation path); capture the `goals_daemon/` tree
so failures are traceable; stamp real `cycle`/path in `mark_reused` rows.

---

## Run 7 result — 2026-07-12 life: **FAILED** (gate 1/4 · S10 🔴 · S6 🔴 · S7 🔴 · S9 🟡 · S1–S5/S8 ✅) — but the cause is isolated

Seventh acceptance run (clean reset incl. habituation, commits `a63b160` +
`bb3685a`, **11,060 cycles in ~8h 03m**, single segment, zero crashes, operator
stop → clean death). Full analysis:
`docs/Behavioral Evaluation & Runtime Diagnostics/demo_runs/2026-07-12-run/DEMO_RUN_2026-07-12.md`.

**Verdict: gate NOT passed — but Run 7 is the run that proved the monopoly is
structural, not a reward artifact.** Every Run 7 credit fix landed and is visible
in the data: the value pump is dead (`self_understanding.value_ema` **0.5196** vs
Run 6's 0.8142), the memo loop is gone (max single-file rewrite **2×** vs 403×),
the ledger rejected junk (8 `duplicate` + 4 `low_significance`), and content-keyed
credit **decoupled the slot-holder from reward** — the incumbent earned **1**
contribution while holding 90.9 % of life, the actual producer (`output_producing`)
earned **7**. And the committed-goal monopoly **survived at 90.9 %** anyway
(`aspiration-self_understanding`, 10,052 / 11,060 cycles, `stale_cycles` 10,291 /
`avoid_streak` 6,852). Kill the pump, the monopoly stays → it was never the pump.

**Run 7 re-test gate (from Run 6): 1 of 4.** no committed goal > 60 % → **90.9 %**
❌ · reuse ≥ 8 → **4** (null referents) ❌ · `genuine_contact` > 0 → **0** (3rd
run) ❌ · same artifact ≤ ~3× → **2×** ✅.

- **S10** 🔴 — commitment 90.9 % on one goal; 106 driver transitions but **none
  durable** (longest non-incumbent hold 324 cycles; one ~500-cycle research
  interlude near cycle 5,300, then reclaimed for ~5,273 cycles to death).
- **S6** 🔴 — contributions **1 / 3 / 0 / 7**; top share 63.6 %, `genuine_contact`
  0. Note: the *contribution* layer is diverse (3 of 4 earned) — only the
  *commitment* layer monopolizes. Content-keyed credit is why.
- **S7** 🔴 — reuse **4** (Run 6: 2, doubled) but `path`/`ref` null; funnel still
  candidate-only (72 events, no later stage).
- **S9** 🟡 — `look_outward` demoted (EMA 0.22, avg reward 0.284); holds as Run 6.
- **HOLDS** ✅ — S1 13 completed / **13 distinct** (0 repeats); S5 `mean_significance`
  **1.205**; S8 desyncs **0** (3rd clean run); S3 satiety **12**; S4 failures **55**
  real. Bonus: the Run-6 map-territory misread loop is **fixed** (6 audits, empty
  findings); **first `synthesis.md`** produced (quality still poor).

**Root cause (two reinforcing structural causes, detail in the verdict §4):**
(1) every lever in `commit_score` is *relative* and saturates at −30, so with no
rival within 30 pts it did nothing while the incumbent's counters climbed into
five figures; (2) **the directional rotation pool has exactly one member** —
only `self_understanding` carries the `directional`/`never_complete` flags (a
downstream effect of the causal-frontier-introspection reframing), so "rotate
among directionals" is a no-op and the one directional slot has a permanent
occupant.

**Re-test gate (Run 8):** built as `RUN8_FIX_PLAN_2026-07-14.md` + the **Run 8
re-test gate** above. **F1** = absolute staleness refractory (arm the dormant
`recommit_block_pulls` on stale-with-no-credit) for cause (1); the verdict adds
**F2** = admit all four aspirations to the directional pool for cause (2) —
without it F1 breaks the monopoly but leaves three of Orrin's four directions
unable to ever drive. Pass = G1 (no goal > 60 %) ∧ G2 (release fired) ∧ G4
(no thrash), G5 no regression.

---

## Run 6 result — 2026-07-10/11 life: **FAILED** (S10 🔴 avoidance 🔴 convergence 🔴 S7 🔴 · S9 🟡 · S8/meters/aspirations ✅)

Sixth acceptance run (clean reset incl. habituation, commit `e4abfe7`,
**13,341 cycles in ~15.5 h**, launch #0 only, zero crashes, operator stop →
graceful death). Full analysis + captured data:
`docs/Behavioral Evaluation & Runtime Diagnostics/demo_runs/2026-07-11-run/`.

**Verdict: gate NOT passed — but the failure changed species.** Every Run-6 fix
is mechanically alive: value authority demoted `look_outward` from 4,899 picks to
**88 (0.66 %, EMA 0.212)** — the first visible learned-value kill in six runs;
commitment rotation fired (8+ goals held the driver slot; Run 5: one at 99.9 %);
the `bookkeeping` ledger class landed (146 rows, `symbolic_artifact` 116 → 4);
both meter bugs are fixed (`satiety_closures` **17**, habituation cleared at
reset). And the life still ended in a **92 % committed-goal monopoly**
(`self_understanding`), because a new pathology fed the new machinery poisoned
reward: `fetch_and_read` re-read one RSS item all life, each re-written memo's
fresh timestamp footer defeated the ledger's content-hash dedup, and **387
credited rewrites of one memo** pumped the incumbent's commitment `value_ema` to
0.8142 — the monopoly relocated *into the learned value signal itself* (Run 4:
candidate generator → Run 5: static commit sort → Run 6: value EMA).

- **S9** 🟡 — 2 of 3 observables pass (`look_outward` collapse; no mature
  <0.3-reward action in top-3); `corr(EMA, share)` = **−0.03**, still not > 0.
- **S10** 🔴 — selection layer diverse (top action 18.1 %), commitment layer 92 %;
  `genuine_contact` never committed, **0 contributions** (2nd run at 0).
- **Avoidance release** 🔴 — max streak 68 → **27** (release fires), but the
  released goal wins the next commit sort on its pumped value: an
  avoid→release→re-commit orbit. Needs a re-commit cooldown.
- **Credit convergence** 🔴 — most-committed (`self_understanding`, 2) ≠
  top-credited (`output_producing`, 7); credit keys off the committed goal, not
  content — a *world-knowledge* memo paid `self_understanding` 403× while
  `world_knowledge` earned 0.
- **Holds:** S8 desyncs **0** (2nd consecutive clean run) ✅; all 4 aspirations
  survived ✅; S5 readable-only 0.309 ✅ (caveat: the looped memo); **S7 reuse 2
  (< 8) 🔴 REGRESSED**, syntheses 0, funnel still candidate-only.

**Re-test gate (Run 7):** (a) commit + stage the `fetch_and_read` URL-dedup fix
(`FETCH_REREAD_LOOP_FIX_2026-07-11.md` — built post-mortem, did not run in this
life); (b) **anti-pump credit**: normalize volatile footers out of the ledger
content hash and decay repeat-credit per artifact path (novelty < ε must gate
credit, not just score); (c) **content-keyed credit** so an artifact pays the
aspiration whose domain it serves; (d) **re-commit cooldown** on avoidance
release; (e) fix or explain `write_exemplar` — **12× EACCES on the quality-golden
exemplars dir from minute 13 of life** (writable post-mortem; add errno capture +
a boot writability probe) — until then the quality standard cannot grow. Pass =
no committed goal > 60 %, reuse ≥ 8 again, `genuine_contact` > 0, and the same
artifact path credited ≤ ~3× per life.

---

## Run 3 result — 2026-07-03 life: **FAILED** (6 ✅ 5 ✅ 7 🟡 8 🔴 9 ❓ — re-test required)

Third acceptance run (clean newborn via `reset_orrin.py` at 21:55 EDT,
**11,333 cycles in ~14.2 h**, launch #0 only, zero crashes, operator SIGTERM →
graceful stop). This was also the staging run for the 2026-07-02 fix round
(commit `dc0bce4` — 12 items, S6/S7 seams + rest drive + AR2 hooks). Full
per-signal analysis + captured data:
`docs/Behavioral Evaluation & Runtime Diagnostics/demo_runs/2026-07-03-run/`.
Reading note: the run straddled midnight — `outcome_metrics.json` holds two
daily rows; totals below sum both.

**Verdict: gate NOT passed — but the biggest single-run movement yet.** The
Run-3 gate required 6 and 7 to move while 5 and 9 held. S6 moved decisively
(passes its target outright); S7 half-moved (attempts and artifacts real, reuse
still zero); S5 held; S9 no longer shows a visible EMA→selection link once fix
#10 removed the stuck-loop self-payment; and S8 regressed with a newly exposed
systematic desync. Per the decision rule ("if 8 or 9 fail, the fix is cosmetic
regardless of 1–7"), still shipped, not proven.

| # | Signal | Run 3 | Result |
|---|---|---|---|
| 1 | Fewer repeated understanding goals | 14 completed / 7 distinct; max repeat 5× over 11.3k cycles (0.44/1k, under target — but repeats returned; Run 2: 3/3 distinct) | 🟢 |
| 2 | Nonzero goal duration | median 3,722.4 s; completions spread hourly across the whole life | 🟢 |
| 3 | Nonzero satiety closures | **0** (19 "Refusing satiety close" refusals) | 🔴 |
| 4 | Some legitimate failures | **94 machine-readable rows in `failures.jsonl`** (54 flagship `no_artifact_by_deadline`, 34 research `no URLs to fetch`) | 🟢 |
| 5 | Higher mean significance | **1.197** (Run 2: 1.114) — held after the lanes were bridged; Run 2's number was not a metering artifact | ✅ **HELD** |
| 6 | Aspiration diversity | **contributions 5/2/5/2, all four off 0, top share 36%** (was 0/0/0/0) | ✅ **MOVED — PASSES** |
| 7 | Artifacts useful / reused | attempts 0→**163**, successes **102**, **11 research memos** (first ever) + 1 tool-validated effect — but **0 reuse back-refs** (`mark_reused` has no call sites) and handoffs 0 | 🟡 **HALF-MOVED** |
| 8 | No resurrection / orphan-RUNNING | `store_desyncs_repaired` **12** (Run 2: 0) — all `resurrection repaired … re-closed in v1`, tracking v2 completions ~1:1; invisible before because nothing completed | 🔴 **REGRESSED — escalation rule triggered** |
| 9 | Selection follows learned value | corr(EMA, share-delta) ≈ **−0.15**; lowest-EMA major (`look_outward` 0.150) share *rose*; the EMA is a minority term in the multi-factor ranker — Run 2's link was partly the now-removed loop self-payment | ❓ **NOT CLEARLY HELD** |

**Root causes (detail in the run analysis):** S7's reuse half has *zero call
sites* — memos are written and never read back, and the conscious lane never
stages a production action (handoff 0). S8 is a **v2→v1 completion-bridge
leak**: every v2 completion resurrects its v1 mirror, which the 200-cycle
reconciler re-closes — per this doc's own rule, persistent repairs = real
desync source → **escalate to GOAL_STORE_UNIFICATION**. S9 is structurally
diluted: the dying decision snapshot shows the EMA folded into a multi-factor
rank (`emo 0.312 / goal 0.297 / band 0.25 / dir 0.22 …`) where affect outvotes
learned value; decide the EMA's intended authority before Run 4 or the signal
stays untestable. Also relevant: the ignition monopoly relocated
(`social_presence` 84% of ignitions — third jammed horn in three lives) and
starved the consolidation organs again; the fix belongs at the ignition layer.

**Re-test gate (Run 4):** signals **7 (reuse half), 8, and 9 must move**
(≥1 `mark_reused`/tier-3 row; desync repairs back to ~0 or the bridge
unified; a demonstrable EMA→share link) while **5 and 6 hold**. Until then
this doc and its companions stay live.

### S9 — the EMA's intended authority (decided for Run 4, fix A4)

The reward EMA now has **multiplicative** authority over selection, not one
additive term among ~25. In `score_actions.py`, after the multi-factor sum, a
**mature** action (≥8 scored observations — the same maturity gate `s_curio`
uses) has its whole positive score scaled by **(0.5 + EMA)**:

- neutral EMA 0.5 → ×1.0 (no change),
- `look_outward` at EMA 0.150 → ×0.65 (demoted),
- `research_topic` at EMA 0.674 → ×1.17 (promoted),
- an immature action (n < 8) keeps ×1.0 — exploration stays the additive
  `s_explore`/`s_curio` term's job.

The old additive `s_exploit` term is **removed from the sum** (kept only for
telemetry) so the modulator is not double-counted. In parallel, per-signal
affect couplings are **L1-normalized and capped at 0.5 share**
(`signal_learning._bound_coupling_shares`) so no single coupling (2026-07-03:
`exploration_drive→look_outward` at 0.706) can structurally outvote value.

**S9 passes in Run 4 iff:** a mature action's final score scales by (0.5 + EMA);
**expected observable:** `corr(EMA, share-delta) > 0` **and** `look_outward`
share *falls* while its EMA stays **< 0.3**.

> **Run 4 prep:** every open issue + build order + pre-run checklist is
> consolidated in `docs/Behavioral Evaluation & Runtime Diagnostics/`
> `RUN4_ISSUES_AND_IMPROVEMENTS_2026-07-04.md`.

---

## Run 2 result — 2026-07-02 life: **FAILED** (5 ✅ 9 ✅ 6 ❌ 7 ❌ — re-test required)

Second acceptance run (clean newborn via `reset_orrin.py`, **10,071 cycles in
~9.2 h**, launch #0 only, zero crashes, operator SIGTERM → graceful stop). This
was also the staging run for Grounding & Surface P1–P8 + Audit Remediation
AR1–AR9 (commit `db4a139`). Full per-signal analysis + captured data:
`docs/Behavioral Evaluation & Runtime Diagnostics/demo_runs/2026-07-02-run/`.

**Verdict: gate NOT passed.** The Run-2 gate required 5, 6, 7, and 9 to move;
two did — a big step up from Run 1 (which failed all four), but still shipped,
not proven.

| # | Signal | Run 2 | Result |
|---|---|---|---|
| 1 | Fewer repeated understanding goals | 3 distinct / 3 completed, no repeats | 🟢 |
| 2 | Nonzero goal duration | median 10,920.8 s | 🟢 |
| 3 | Nonzero satiety closures | 0 | 🔴 |
| 4 | Some legitimate failures | 66+ `no_artifact_by_deadline` (activity logs) | 🟢 |
| 5 | Higher mean significance | **1.114** (was 0.0); 150 ledger rows, 89 nonzero | ✅ **MOVED** |
| 6 | Aspiration diversity | all four aspirations at 0 contributions | ❌ **FAIL** |
| 7 | Artifacts useful / reused | 0 reuse; `production_attempt_count` 0 all run | ❌ **FAIL** |
| 8 | No resurrection / orphan-RUNNING | desyncs repaired 0, clean death | 🟢 |
| 9 | Selection follows learned value | high-EMA `research_topic` share 8.7%→15.7%; `generate_intrinsic_goals` off #1 | ✅ **MOVED** |

**Root causes (detail in the run analysis):** S6 is over-determined — completed
goals carry no `serves`, two had `driven_by=None`, a `comp_goals` status-at-copy
bug makes `credit_objectives` skip one, and 31 aspiration-attributed ledger rows
never reach `mark_objective_contribution`. S7 is a **lane split** —
`produce_and_check` has the *top* reward EMA (0.7651) but runs in the
executive-daemon lane (`step_exec`), and the production loop's attempt/handoff
counters + ledger crediting listen only to the conscious lane, so production
attempts stayed 0 for the entire run.

**Re-test gate (Run 3):** signals **6 and 7 must move** (≥1 aspiration off 0%;
≥1 production attempt and ≥1 reuse back-ref) while 5 and 9 hold. Until then this
doc and its companions stay live.

---

## Run 1 result — 2026-06-19 life: **FAILED** (re-test required)

The first acceptance run happened (born 2026-06-19 22:17 UTC, stopped at cycle
**11,633**, ~13.9 h, single clean instance, clean graceful death). Evidence:
`docs/Behavioral Evaluation & Runtime Diagnostics/demo_runs/2026-06-19-run/`.

**Verdict: failed the gate — the fix is shipped, not proven.** The new machinery
(`binding.py` / `goal_lens.py` / `goal_comprehension.py` / `compose_section.py`)
ran **crashless for 14 h and died clean** — the fail-closed plumbing is proven in
the wild — but the **production end is fed garbage, so the gate correctly paid
zero**. The keystone number is **146 → 0**: 146 effect records, every one
`note_novel` with `novelty 0.0` *and* `significance 0.0`. Note bodies are scraped
noise (`.lock`/`data` filename fragments + raw prediction-error strings), not a
comprehended target.

| # | Signal | Pass target | Run 1 | Result |
|---|---|---|---|---|
| 1 | Fewer repeated understanding goals | repeats ↓ ≥50% | lean store (9 live goals), different shape | 🟡 indeterminate |
| 2 | Nonzero goal duration | > 0 | not surfaced | ❓ unverified |
| 3 | Nonzero satiety closures | > 0 | not reported | ❓ unverified |
| 4 | Some legitimate failures | > 0 | not reported | ❓ unverified |
| 5 | Higher mean significance | clearly > 0 | **0.0** (all 146 effects) | 🔴 **FAIL** |
| 6 | Aspiration diversity | none at 0%, top < 60% | **all four 0%** | 🔴 **FAIL** |
| 7 | Artifacts useful / reused | ≥1 reused, > 0 distinct | **0 credited, 0 tools, notes junk** | 🔴 **FAIL** |
| 8 | No resurrection / orphan-RUNNING | repairs → ~0 | single clean instance, clean death | 🟢 likely held |
| 9 | Selection follows learned value | low-EMA pick-share ↓ | `generate_intrinsic_goals` picked 3,526× (#1) regardless | 🔴 **FAIL** |

Per the decision rule below, **5/6/7/9 failing makes this a failed fix, not a
matter of interpretation** — even though 8 (the structural fix) held.

**Root cause is upstream of the retune levers in §2.** The content isn't merely
"too short" (so dropping `MIN_ARTIFACT_CHARS` won't help) — the *source* is noise.
The fix is to make `compose_section` + `goal_comprehension` feed note/artifact
bodies from a **comprehended goal target** (what "done" looks like, grounded),
not from `search_own_files` filename hits or the ambient affect string. Until that
lands, a re-run will reproduce 146 → 0.

**Re-test gate (Run 2):** signals **5, 6, 7, and 9 must move** (first non-zero
`effect_ledger` row; at least one aspiration off 0%; a low-EMA action's pick-share
visibly falling). Until then this doc and its three companions stay live.

---

## 0. Before you start — run preconditions

These must all hold or the numbers can't be trusted:

- [ ] **Single clean instance.** Exactly one `main.py` against `brain/data/`.
  Now enforced by the lock (`main.py` `_acquire_single_instance_lock` → `flock` →
  `sys.exit(3)`); `run_orrin.sh` will not re-spawn on SIGKILL (137) or lock
  refusal (3). Confirm boot log shows `single-instance lock acquired (pid …)` and
  there is no second python process on the data dir.
- [ ] **Clean shutdown of any prior run.** No stale `.orrin.instance.lock`
  (start_orrin.command clears a stale one automatically), no leftover `.corrupt`
  files accumulating.
- [ ] **Unit tests green first** (see §3). Don't start a 9-hour run on red code.
- [ ] **Capture a baseline.** Copy the *current* `brain/data/outcome_metrics.json`
  and `brain/data/action_reward_ema.json` aside as the "before" so the before→after
  is real, not remembered.
- [ ] **Decide LLM availability up front.** The production path needs real
  artifacts. If running offline/native-LM, the making generator falls back to
  offline-producible artifacts (Guard) — that's fine, but note it, because signal
  #7 (reuse) and #5 (significance tier-2 validation) lean on it.

---

## 1. How long the run needs to be

Think in **cycles, not hours** — every mechanism is cycle-gated, and the binding
constant is the 200-cycle deadline/reconcile epoch (`PRODUCTION_DEADLINE_CYCLES`).

| Goal | Cycles | ≈ Wall-clock @ ~3.3 s/cycle | What it proves |
|---|---|---|---|
| **Smoke read** | ~500–1,000 | ~0.5–1 h | Working at all: production % rises, first ledger artifacts, making/contact goals firing, probably first deadline failure. Catches a regression; does **not** pass §8. |
| **Full §8 acceptance** | **~10,000** | **~9–10 h (overnight)** | All nine signals settle — matches the ~10,300-cycle run the targets were derived from, so it's a true apples-to-apples before/after. |

The three slowest signals set the floor:
- **#4 failures** — first one can't appear before ~400 cycles (generate → live 200 →
  caught on next `%200` pass).
- **#8 desync trend** — reconciler runs every 200 cycles; "stays 0" needs ~8+ passes
  (~1,500 cycles).
- **#9 EMA→selection** + **#7 reuse** — EMAs are slow and reuse needs a
  produce-*then*-reference arc; both want a few thousand cycles.

**To go faster:** lower `ORRIN_CYCLE_SLEEP` to raise throughput — the 200-cycle
constants are in *cycles*, so acceptance logic is unaffected. Don't drop it so far
that LLM/web calls get starved, or the production path won't get a fair chance.

---

## 2. The nine acceptance signals (the real test)

Read off the **same stores the diagnosis used**, primarily
`brain/data/outcome_metrics.json` (rolling daily snapshots; the run's row is the
one to read), plus `comp_goals.json`, `action_reward_ema.json`, and the new
`brain/data/effect_ledger.jsonl`. Every signal needs **measurable movement**.

| # | Signal | Metric / source | Current (bad run) | Pass target |
|---|---|---|---|---|
| 1 | Fewer repeated understanding goals | distinct-title ratio among completed goals (`comp_goals.json` + goals WAL); max repeats of one title | ~a dozen titles, 3–4× each | repeat rate down ≥ 50%; no title completed > 2× per 1k cycles |
| 2 | Nonzero goal duration | `outcome_metrics.median_seconds_to_complete` | **0.0** | > 0 (real elapsed work, not instant self-report) |
| 3 | Nonzero satiety closures | `outcome_metrics.satiety_closures` | **0** | > 0 (understanding goals close on *quenched drive*, not one fact) |
| 4 | Some legitimate failures | `outcome_metrics.goals_failed` from `deadline`/acceptance (reason `no_artifact_by_deadline`), not no-handler | **0** | > 0, traceable to a real unmet artifact gate |
| 5 | Higher mean significance | `outcome_metrics.mean_significance` (tier-weighted, P8) | **0.0** | clearly > 0, driven by tier-2/3 (validation/re-use), not self-assert |
| 6 | Meaningful aspiration diversity | per-aspiration share of *effect-backed* contributions (aspiration rows in `goals_mem.json`: `contribution_count`) | 100 / 0 / 0 / 0 | no aspiration at 0%; top share < ~60% |
| 7 | Production artifacts useful / reused | `effect_ledger.jsonl` rows with a tier-3 `reuse` back-reference; tools invoked; replies answered | 0 tools, notes all dup | ≥ 1 artifact re-used/validated; > 0 distinct production artifacts |
| 8 | No resurrection / orphan-RUNNING | `outcome_metrics.store_desyncs_repaired` (P6 reconciler) trend | unmeasured | repairs → ~0 and **stay** 0 (persistently >0 = real desync source — escalate to GOAL_STORE_UNIFICATION) |
| 9 | Selection changes when learned value changes | correlation of `action_reward_ema[fn]` ↓ with that fn's pick-share ↓ | EMA 0.39 yet picked #1 | a low-EMA action's pick-share visibly falls (EMA→selection link is live) |

**Decision rule:** Signals **1–7** say the behavior changed; **8** says the
structural fix held; **9** says learning now has authority. **If 8 or 9 fail, the
fix is cosmetic regardless of 1–7.** Capture the run as a Life Capsule (or at least
archive the data files above) so the numbers are reproducible, not asserted.

**Retune levers if a signal misses** (don't re-architect — adjust the named
constant):
- #4 still 0 → halve `PRODUCTION_DEADLINE_CYCLES` 200 → 100 (`goals.py`).
- #5/#7 syntheses real but rejected as too short → drop `MIN_ARTIFACT_CHARS`
  120 → ~80 (`effect_ledger.py`).
- #1 repeat-rate still high → check the laddering (`note_intake_completed` →
  `_making_goals` drain) is actually firing in the activity log.
- #6 an aspiration still 0% → confirm `aspiration_pressure` is biasing the pick and
  `_contact_goals`/`_making_goals` are entering the pool.

---

## 3. Unit tests to run (must be green before *and* after the run)

```bash
python3 -m pytest \
  tests/brain/test_effect_ledger.py \
  tests/brain/test_goal_store_reconcile.py \
  tests/brain/test_intrinsic_goal_zones.py \
  tests/brain/test_multi_goal_executive.py \
  tests/brain/test_reward_engine.py \
  tests/brain/test_set_goal_plan_regression.py \
  tests/brain/test_subgoal_adaptation.py -q
```

Last green: **41 passed (2026-06-19).** These cover the ledger (dedup, novelty,
significance, artifact gate), the P6 reconciler (resurrection / orphan-RUNNING /
double-home), and the surrounding goal/reward machinery so the plan changes didn't
regress them.

**Gaps worth adding before the run (optional but recommended):**
- A **bridge-invariant regression** (P6) asserting the new production path cannot
  (a) resurrect a v2-closed goal into v1, or (b) leave a v1-closed goal RUNNING in
  v2 — the two exact failures `goal_io.py` records. (Reconcile test covers the
  repair; an invariant test would assert the *prevention*.)
- A **finalize reward-tier test**: production → 1.0, intake → 0.5 (floored 0.35),
  cognition-only → 0.2, keyed on `_production_effect_this_cycle`.
- A **commitment-competition test** (P7): an artifact-gated production goal under
  high aspiration pressure can win `committed_goal` over a cheap intake goal.

---

## 4. What to capture from the run

So the result is reproducible, not anecdotal:

- [ ] `brain/data/outcome_metrics.json` — the run's snapshot row (signals 2–6, 8).
- [ ] `brain/data/effect_ledger.jsonl` — every recorded effect (signals 5, 7;
  inspect `novelty`, `significance`, `dedupe`, `reuse` rows).
- [ ] `brain/data/comp_goals.json` + goals WAL — completed-goal titles (signal 1).
- [ ] `brain/data/goals_mem.json` — aspiration rows `contribution_count` (signal 6).
- [ ] `brain/data/action_reward_ema.json` — EMA vs. pick-share (signal 9; diff
  against the baseline copy).
- [ ] `activity_log.txt` (+ `rotated/`) — confirm `[goal_reconcile]`,
  `[goals] Failed … past deadline`, making/contact goal commits, and grounded
  `leave_note` payloads actually appear.
- [ ] **Ideally:** seal a **Life Capsule** (`ORRIN_LIFE_CAPSULE_PLAN_2026-06-18.md`)
  if that builder lands — one self-describing evidence file beats a pile of logs.

---

## 5. Pass = archive

When signals 1–7 move toward target **and** 8 stays ~0 **and** 9 shows the EMA→
selection link live, the Production Reward Plan is **proven**, and it (plus the
three companion docs) can move to `archive/`. Until then, keep them live — the code
is in, the verdict is pending.

*Created 2026-06-19. Companion to `ORRIN_PRODUCTION_REWARD_PLAN_2026-06-18.md` §8.*

---

## 6. Run 5 read-side analysis checks (2026-07-08 addendum)

Not organ fixes — reporting the Run 5 analysis MUST include so the §8 gate can't
be satisfied by partial truths (from the four 07-05 audit passes; built alongside
F10–F22 in `RUN5_FIX_IMPLEMENTATION_2026-07-07.md`):

1. **Production reset-safe totals** — sum `production_loop.jsonl` booleans across
   counter resets; never trust the tail cumulative fields (they reset at relaunch;
   the 07-05 tail was segment-2 only).
2. **Funnel wiring** — verify `production_funnel.json` has stages beyond
   `candidate`, or state explicitly that it's candidate-only.
3. **Goal identity coverage** — % of live / failed / completed / effect rows with
   stable ids (F14's observable; target ≥ 95%, no active artifact-gated goal
   id-less).
4. **Material class counts** — ledger rows split into readable body vs structural
   graph effect (causal edges are *not* prose material) vs operational check vs
   file write; only readable bodies count as synthesis material.
5. **Material availability + transformation** — credited prose rows whose sidecar
   body resolves; later artifacts that cite prior hashes / memo paths.
6. **Memory composition** — instrumentation share of long memory and of the
   memory graph (F17/F18 observables; instrumentation < 40% of the estate,
   ≥ ~70% of graph endpoints resolve to live memories).
7. **Delayed reward by source** — split resolved WAL rows by `resolved_by`:
   retrieval_A / goal_B_grounded / pruned / pruned_overflow / apply_failed (F15
   observable; never again 100% flat goal_B).
8. **Cooldown truth** — recognized executive actions counted separately from
   actions that actually ran (`cooldown_skipped` in the executive summary; F16
   observable). Production attempts must correspond to producer runs.
9. **Classifier agreement** — artifact-gated vs make-shaped vs production handoff
   vs making-aspiration credit, reported separately (they overlap but don't mean
   the same thing).
10. **Speech grounding** — % of replies with a concrete referent (typed intents
    share_artifact / share_finding / state_blocker / ask_grounded_question vs
    express_state in the speech log), not just non-duplicate wording (F19).
11. **Writeback pressure** — writeback rows/1k cycles, source share, % targeting
    `motivation`, top actions when the writeback-derived prior > 0.10 (07-05:
    binding wrote back on 9,299/9,300 cycles).

*Added 2026-07-08 alongside the F10–F22 build.*
