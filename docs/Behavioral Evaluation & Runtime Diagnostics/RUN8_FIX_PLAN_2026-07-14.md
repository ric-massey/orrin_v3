# Run 8 Fix Plan — an absolute release for the commitment monopoly (2026-07-14)

**Status:** BUILT 2026-07-14 (`make verify` green, 1511 tests). F1 + F2 landed in
`brain/cognition/planning/commitment_value.py`; tests in
`tests/brain/test_run8_stale_refractory.py`. Written after the Run 7 (2026-07-12)
capture in `demo_runs/2026-07-12-run/RUN_CAPTURE_2026-07-12.md`, grounded in a
fresh read of `brain/cognition/planning/commitment_value.py` and
`brain/goal_io.py`. Every diagnosis below is verified at a specific line (§1).

**One deviation from the letter of the plan (F2).** F2's "one line at
`commitment_value.py:310-311`" is necessary but **not sufficient** on its own: an
aspiration carrying only `_aspiration` (no `directional`/`never_complete`) never
reaches `order_committable` at all, because `goal_io._committable_from_v1_tree`'s
`committable_tier` gate (`goal_io.py:272-274`) admits a `long_term` goal only when
it is flagged `directional`/`never_complete`, and `promote_one_directional`
(`long_term_driver.py:81-100`) flags exactly one long-term goal and strips the
flags from the rest. So the three non-promoted aspirations were filtered out
upstream. The build therefore adds `or n.get("_aspiration")` to that
`committable_tier` gate as well — the two changes together are what actually
admit all four directions to the pool. Safe: `mark_goal_completed`
(`goal_outcomes.py:95-96`) already blocks any `long_term`-tier goal from filing
DONE, so committable aspirations still never terminate. The tests' headline
scenario also revealed that **four *equal* directions rotate on the relative
penalty alone** (yield at `stale ≈ 42`, well below F1's 250) — so F1's absolute
release is only exercised by a *dominant* incumbent no rival can displace (Run 7's
actual condition). The headline test reproduces that dominant-incumbent case; the
equal-strength population is used for the producer/anti-thrash guard.

Run 7's thesis ("make credit un-pumpable") **worked**: the memo loop is gone
(most-rewritten file 2×, was 403×), `self_understanding.value_ema` fell from the
pumped 0.8142 to **0.5196**, false production attempts dropped 443 → 38. And the
life *still* ended in a **90.9 % committed-goal monopoly** (10,052 / 11,060
cycles), with `stale_cycles = 10,291` and `avoid_streak = 6,852` on the
incumbent.

That is the tell. The monopoly no longer needs a reward pump. It survives on a
structural gap: **every anti-monopoly lever Orrin has is *relative* — it lowers
the incumbent's score so a *rival* can overtake it. When no rival is within
range, a saturated penalty just sits there.** Run 8's job is to add the one lever
that is missing: an **absolute** release that yields the driver slot on evidence
of non-progress *regardless of whether anything can beat it*.

This is **not** a new temporal-regulation subsystem. **F1** re-triggers a block
that **already exists** in the file (`recommit_block_pulls`, Run 7's F4) on a
second, absolute condition (~25 lines). **F2** (added from the Run 7 verdict, §2b)
admits all four aspirations to the directional pool so F1's release hands the slot
to another *direction*, not to an ordinary chore — because Run 7 proved only
`self_understanding` was ever flagged directional.

---

## 1. Verification — the diagnosis checked against code

| Claim | Verified at | Verdict |
|---|---|---|
| All commitment authority is relative, max ≈ −30 | `commitment_value.py:240-266` — `commit_score = 100·tier + 10·priority + 10·(value−0.5) − 15·stale_norm − 15·avoid_norm (+2 incumbent)`. Downward authority caps at `_W_STALE + _W_AVOID = 30`. | ✅ confirmed |
| Both penalties saturate early, then do nothing | `commitment_value.py:52,56` — `stale_norm` saturates at `_STALE_FULL_CYCLES = 120`, `avoid_norm` at `_AVOID_FULL = 20`. Past those the penalty is a **constant −30** no matter how high the counters climb. Run 7 rode stale 120 → 10,291 with **zero** additional pressure. | ✅ confirmed, this is the gap |
| Nothing releases an un-displaced holder | `commitment_value.py:113-153` `note_driver_selected` — the **only** absolute lever (`recommit_block_pulls`, lines 136-140) arms **iff** `prev != chosen AND prev.avoid_streak ≥ 15` (displaced *by* avoidance). In Run 7 the holder was never displaced (no rival in range) → `prev == chosen` every pull → the block never armed. | ✅ confirmed — the smoking gun |
| The tier floor makes a lower-tier goal unreachable | `commitment_value.py:41` `W_TIER = 100`; a stale directional at `long_term` tier cannot be crossed by a −30 penalty from any lower-tier rival — by Part I design. So "rotation" only ever happens *between same-tier directionals*; with one dominant directional there is nothing to rotate to. | ✅ confirmed |
| `stale_cycles` is a clean "no credit while holding" signal | `commitment_value.py:212` — `note_goal_credit` sets `stale_cycles = 0.0` on every credited effect. So `stale_cycles` high ⟺ the holder produced **nothing creditable** for that many cycles. It is exactly "occupancy without information gain." | ✅ confirmed — this is what we trigger on |
| The block is a true eligibility gate, not a penalty | `commitment_value.py:296-316` — `order_committable` drops any directional whose `recommit_block_pulls > 0` from the driver slot (`_gid(g) in blocked`); `commit_score:263` also withholds the incumbent bonus. Unconditional, temporal, credit does not clear it. | ✅ confirmed — reuse it verbatim |
| Driver selection is the single call site | `goal_io.py:288-289` — `order_committable(found, …)` is the one path that assigns the committed/driver slot; it calls `note_driver_selected` internally. F1 lands entirely inside `commitment_value.py`. | ✅ confirmed |
| The directional pool is single-member (F2's target) | `intrinsic_objectives.py:255-263` — all four aspirations are created with `_aspiration: True` / `tier: long_term` but **no** `directional` or `never_complete` key. The `is_directional` gate at `commitment_value.py:310-311` (`tier == "long_term" and bool(g.get("directional") or g.get("never_complete"))`) is therefore False for all four *at creation*; only `self_understanding` acquires the flag later via causal-frontier promotion → the "rotate among directionals" cap governs a one-member pool. | ✅ confirmed — this is why F1 alone is insufficient |

**The one-sentence root cause:** Orrin can *recognize* a rut (`stale_cycles`
10,291, `avoid_streak` 6,852) but the only machinery that can *leave* one is
competitive, and Run 7 had no competitor — so recognition never converted to a
mode change. See the standing hypothesis this operationalizes:
"recognition ≠ authority."

---

## 2. The fix — F1: absolute staleness refractory (arm the dormant block)

**One change, in `brain/cognition/planning/commitment_value.py`.** Add a second
arming condition to `note_driver_selected`: when the *current holder* has occupied
the driver slot for `_STALE_REFRACTORY_CYCLES` with **zero** credited effect, it
arms **its own** `recommit_block_pulls` and yields the slot next pull — regardless
of whether any rival can beat it. `order_committable` already makes a blocked
directional ineligible, so the next-best directional (or, if none, ordinary goals)
takes the slot even at a lower score. That is the absolute release the relative
penalties never provided.

**Why `stale_cycles` alone is the right trigger (not a new fatigue variable):**
credit zeroes `stale_cycles` (line 212). A goal that is genuinely producing
therefore *cannot* reach the ceiling — the trigger can only ever fire on a holder
that has produced nothing creditable for `_STALE_REFRACTORY_CYCLES` straight. This
encodes the load-bearing distinction directly: **persistence *under progress* is
protected; persistence *without information gain* loses the slot.** No `F[k]`
table, no phase oscillator, no global-pressure variable — those are deferred (§6).

### 2.1 Constants (near line 71, after the F4 block)

```python
import os  # add to the import block at the top of the file

# F1 (RUN8_FIX_PLAN_2026-07-14): absolute staleness refractory — the missing
# ABSOLUTE release. Every other lever in commit_score is relative and caps at
# −30; with no rival in range it did nothing while Run 7's holder rode
# stale_cycles 120 → 10,291. A driver that holds the slot this many cycles with
# ZERO credited effect (credit zeroes stale_cycles, so this can only trip on
# genuine non-production) arms its OWN F4 block and yields — no rival required.
_STALE_REFRACTORY_CYCLES = 250   # ~130 cycles past the −15 stale saturation:
                                 # the relative machinery gets first refusal,
                                 # then the absolute lever forces the yield.
_STALE_REFRACTORY_ENABLED = os.environ.get("ORRIN_STALE_REFRACTORY", "1") != "0"
```

Occupancy math: a goal that keeps going stale cycles out at roughly
`250 / (250 + 300) ≈ 45 %` — under the 60 % gate — while a goal that keeps
*producing* resets `stale_cycles` and holds as long as it earns it.

### 2.2 Arm it in `note_driver_selected` (after `row["last_ts"] = now`, ~line 143)

```python
            row["stale_cycles"] = float(row.get("stale_cycles", 0.0)) + 1.0
            row["last_ts"] = now
            # F1 (Run 8): absolute refractory release. The holder has occupied the
            # driver slot for _STALE_REFRACTORY_CYCLES with no credited effect
            # (credit zeroes stale_cycles); the −30 relative penalty saturated
            # long ago and no rival displaced it. Arm its own block so
            # order_committable makes it ineligible next pull — the slot yields
            # even if nothing outscores it. Logged for the Run 8 gate.
            if (_STALE_REFRACTORY_ENABLED
                    and float(row.get("stale_cycles", 0.0)) >= _STALE_REFRACTORY_CYCLES
                    and float(row.get("recommit_block_pulls", 0.0) or 0.0) <= 0.0):
                row["recommit_block_pulls"] = float(_RECOMMIT_BLOCK_PULLS)
                ev = d.get("refractory_events")
                if not isinstance(ev, list):
                    ev = []
                d["refractory_events"] = (ev + [{
                    "goal": chosen,
                    "ts": now,
                    "stale_cycles": float(row.get("stale_cycles", 0.0)),
                    "avoid_streak": float(row.get("avoid_streak", 0.0)),
                }])[-200:]
```

The holder still "wins" this pull (`commit_score` already ran); the block takes
effect on the **next** `order_committable` — one-pull latency, harmless. While
blocked and not holding, its `stale_cycles`/`avoid_streak` decay ×0.90/pull
(existing lines 149-150), so after the 300-pull block it re-enters *fresh* (stale
≈ 0) and gets a real second chance — if it produces, it holds; if it goes stale
again, it cycles out again. This is genuine re-entry, not permanent suppression
(hypothesis Invariant 3).

### 2.3 Telemetry accessor (for the Run 8 capture)

```python
def refractory_events() -> List[Dict[str, Any]]:
    """Run-analysis: every absolute-staleness refractory release this life
    (F1). Empty list = the release never fired — read alongside the max
    stale_cycles at death to decide whether Run 8's fix did anything."""
    ev = _load_signals().get("refractory_events", [])
    return ev if isinstance(ev, list) else []
```

`refractory_events` rides inside `commitment_signals.json`, which the run capture
already reads — so it is captured with zero new wiring.

---

## 2b. The fix — F2: admit all four aspirations to the directional pool

Surfaced by the Run 7 verdict (`demo_runs/2026-07-12-run/DEMO_RUN_2026-07-12.md`
§4.2), not the original hypothesis. F1 gives the incumbent an absolute release —
but **the release only means something if there is another *direction* to hand the
slot to.** In Run 7 there was not: of the four HIGH `long_term` aspirations, only
`self_understanding` carried the `directional` / `never_complete` flags, so
`order_committable`'s directional cap governed a **single-member pool** and the
"rotate among directionals" logic was a no-op.

```
self_understanding   directional=True  never_complete=True   ← the only "direction"
world_knowledge      directional=None  never_complete=None
genuine_contact      directional=None  never_complete=None
output_producing      directional=None  never_complete=None
```

This is a downstream effect of the causal-frontier-introspection reframing (the
causal graph is ~100 % self-model, so the frontier generator only ever promoted a
`self_understanding` frontier). Verified above (§1): the four aspirations are born
at `intrinsic_objectives.py:255-263` **without** the `directional`/`never_complete`
keys, so the `is_directional` gate is False for all of them until one is promoted.

**The fix — one line at `commitment_value.py:310-311`.** Relax `is_directional` to
treat any long-term aspiration as a direction, rather than seeding the flags at
creation (which would leave already-persisted aspiration rows in existing goal
stores un-flagged and need a migration — a one-line predicate needs none):

```python
        is_directional = tier == "long_term" and bool(
            g.get("directional") or g.get("never_complete") or g.get("_aspiration"))
```

`_aspiration: True` is set on exactly the four enduring directions (and nothing
else), so this admits all four to the directional pool and no ordinary goal. The
driver slot then rotates among **four real directions** on value/staleness, and
F1's release hands off to a genuine direction rather than an ordinary research
chore. No new flag, no env switch (F2 is a definitional correction, not a tunable);
`ORRIN_STALE_REFRACTORY=0` still isolates F1, and the ablation arm runs F2 alone.

**Sequencing:** F1 is the load-bearing change; F2 is what makes F1's outcome
*good* rather than merely *not-monopolized*. Build both for Run 8. With F1 + F2,
G1 (no goal > 60 %) should pass by rotation among four directions, not by starving
the incumbent. Guard against the opposite failure — four directions round-robining
regardless of progress — with the same `stale_cycles`/credit evidence F1 uses (a
direction that is producing holds; one that is not yields). Add a test: with four
directional aspirations and one going stale, the driver rotates to a *different
aspiration*, not to an ordinary goal.

---

## 3. Why this and not the bigger proposal

The standing hypothesis proposes a three-variable temporal-regulation layer
(endogenous phase `C`, global pressure `S`, attractor fatigue `F[k]`). Run 7
justifies **only** the fatigue-→-eligibility slice, and even that is already
half-built:

- **`F[k]` is largely already computed** — per-goal `stale_cycles` and
  `avoid_streak` live in `commitment_signals.json`. We don't need a new table; we
  need to give the existing counter *absolute* authority.
- **The eligibility mechanism already exists** — `recommit_block_pulls`. We arm it
  on a new condition; we do not build a new gate.
- **`C` and `S` have zero Run-7 evidence.** A phase oscillator interrupts a
  monopoly only to hand it straight back when the phase turns (hypothesis
  Prediction 2); `S` duplicates `resource_deficit` / allostatic load. Both are
  deferred to §6 behind their own flags, to be considered *only if* F1 proves
  insufficient.
- **Raising `_W_STALE` is the trap we are avoiding.** A bigger relative penalty is
  still relative — it fails identically the moment the score gap to the nearest
  rival exceeds it. The monopoly has relocated one layer up every run precisely
  because each fix stayed inside the same additive-score topology (candidate gen →
  static sort → value EMA → now incumbency). An absolute eligibility gate changes
  the topology; another 0.05 does not.

---

## 4. Tests — `tests/brain/test_run8_stale_refractory.py` (green before the run)

The isolated unit checks below are necessary but not sufficient: they exercise F1
against one or two goals and never test the thing Run 8 actually depends on — **F1
and F2 together**, a driver slot rotating among *four* directional aspirations
while ordinary goals compete for it. So the file leads with a **life-simulation
harness** that drives a realistic multi-goal population through many pulls and
asserts the whole set of gate-aligned properties *at once* on the resulting
occupancy trace, then keeps the sharp single-condition guards to localize any
failure the simulation surfaces.

### 4.1 `_simulate_life(...)` — one harness, many assertions

A helper that mirrors the run's driver loop in-process:

```python
def _simulate_life(goals, *, pulls, credit_earner=None, credit_every=0,
                   credit_gain=0.4, env=None):
    """Drive note_driver_selected/order_committable for `pulls` cycles over a
    fixed goal population; return the occupancy trace + per-goal signal rows.

    goals: list of (gid, tier, priority, directional) — build 4 directional
        long_term aspirations + ≥2 ordinary goals so BOTH pools are populated.
    credit_earner/credit_every: optionally feed note_goal_credit to ONE goal on
        a fixed cadence, so 'persistence under progress' is exercised inside the
        same run, not a separate toy case.
    Returns: dict(occupancy={gid: share}, drivers=[gid per pull],
                  refractory=refractory_events(), rows={gid: signal row}).
    """
```

Two scenarios run through it and each asserts several gate properties together:

1. **`test_monopoly_breaks_and_rotates` (F1 × F2, the headline).** Population = 4
   directional `long_term` aspirations (`self_understanding`, `world_knowledge`,
   `genuine_contact`, `output_producing`) + 2 ordinary goals; **no** goal earns
   credit (the Run 7 condition). Over `pulls` ≈ 3× a full stale+block cycle,
   assert on the single trace:
   - **G1:** no single `gid` exceeds ~60 % of `drivers` (Run 7 was 90.9 % on one).
   - **F1 fired:** `refractory` non-empty, and it contains a release of whichever
     aspiration led early.
   - **F2 handoff is to a *direction*:** each post-release driver change lands on
     another **directional aspiration**, not on one of the two ordinary goals —
     this is the assertion the old single-`g2` case could not make.
   - **Bounded staleness:** `max(row.stale_cycles) < _STALE_REFRACTORY_CYCLES +
     _RECOMMIT_BLOCK_PULLS` (~550) — hundreds, not thousands (G2/G3).
   - **Re-entry:** the first-released aspiration appears **again** as driver later
     in the trace (block decayed, not permanent suppression).

2. **`test_producer_holds_without_thrash` (G4 anti-thrash, in the same world).**
   Same population, but one aspiration earns credit every `credit_every` pulls.
   Assert together:
   - **No release ever fires on the credit-earner:** no `refractory` entry names
     it, and its `stale_cycles` never reaches the ceiling (credit zeroes it).
   - **It legitimately holds more of the slot** than any non-producer — G1 met by
     *contribution*, not by starving the producer (the Decision-rule case).
   - The **non-producing** aspirations still rotate via F1 among themselves — the
     producer's protection does not re-freeze the rest.

### 4.2 Focused guards (retained, one condition each — for fast triage)

3. **Arms on absolute staleness.** `note_driver_selected(g, [g])` ×
   `_STALE_REFRACTORY_CYCLES` with no credit → `row.recommit_block_pulls ==
   _RECOMMIT_BLOCK_PULLS`, `refractory_events()` has one entry for `g`.
4. **Yields the slot.** With `g` blocked, `order_committable([g, g2], …)` (both
   directional `long_term`) returns `g2` even when `g` out-scores it.
5. **Ablation.** With `ORRIN_STALE_REFRACTORY=0`, guard (3) produces **no** block —
   Run-7 behavior is reproducible for the ablation arm, isolating F1 as the cause.

The two §4.1 scenarios are the behavioral proof; the §4.2 guards exist so a red
simulation points at *which* mechanism broke (arming, eligibility, or the flag)
without re-reading the trace. Plus `make verify` stays green (mypy/ruff path).

---

## 5. Run 8 acceptance gate

The pass/fail criteria live in **`docs/NEXT_RUN_TESTS.md` → "Run 8 re-test gate"**
(added alongside this plan) so the next life is graded against them. Headline:
**no committed goal > 60 % of cycles** (Run 7: 90.9 %), **`refractory_events`
non-empty**, **max `stale_cycles` at death in the hundreds, not thousands**, and —
the anti-thrash guard — **no release fires on a goal that is earning credit**, and
production/contribution does not collapse (breaking the monopoly by making Orrin
idle is a **failure**, not a pass).

---

## 6. Deferred (do not build for Run 8 — parked behind flags)

Only if F1 lands but the gate still misses:

- **Credit-override of the block (Invariant 4).** Let a genuinely significant new
  event re-admit a blocked goal early. Moot for the *arming* path (a producing
  goal can't reach the stale ceiling), so it only matters for a goal blocked *then*
  handed strong new evidence — rare; defer until observed.
- **Global pressure `S` → protected consolidation.** Extend `resource_deficit` /
  allostatic load (do **not** add a duplicate fatigue variable) to gate a
  consolidation entry that reduces pressure *only on cycle completion*.
- **Endogenous phase `C`.** Phase-dependent budgets. Lowest priority; no Run-7
  evidence.

Each stays a shadow-loggable idea, not a build, until Run 8 says F1 alone is
insufficient.

---

## 7. Invariants preserved

- **User communication is never gated** — F1 touches only the committed-goal
  driver slot, not reply/EVC paths.
- **Phase alters conditions, not content** — the block changes *eligibility*, never
  what Orrin concludes.
- **No permanent suppression** — the block decays 1/pull and the goal re-enters
  fresh (§2.2).
- **Recovery cannot award success** — F1 awards nothing; it only withholds a slot.
- **Inspectable & ablatable** — `refractory_events()` telemetry +
  `ORRIN_STALE_REFRACTORY=0` master switch.

---

## Appendix A — the standing hypothesis this narrows ("Global Temporal Regulation")

The plan above cites this hypothesis by number (Invariant 3, Invariant 4,
Prediction 2) and by variable (`C`, `S`, `F[k]`). It was not written down anywhere
else in the repo, so it is stated here in full — F1/F2 implement exactly the one
slice marked **[BUILD: Run 8]**; everything else is the parked context that
justifies *not* building more (§3, §6).

**Premise — "recognition ≠ authority."** Orrin can already *recognise* that it is
stuck (`stale_cycles`, `avoid_streak` climb without bound) but has no mechanism
that *converts that recognition into a mode change* unless a rival goal happens to
be in scoring range. Every regulator it owns is **relative**. The hypothesis is
that a long-running cognitive agent needs at least one **absolute** temporal
regulator — one that acts on elapsed non-progress itself, not on comparison.

**The proposed three-variable layer (full form — mostly deferred):**

- **`F[k]` — per-attractor fatigue.** A goal (attractor `k`) that holds attention
  without producing information gain accrues fatigue that *lowers its own
  eligibility*, independent of rivals. **[BUILD: Run 8]** — F1 is precisely this,
  reusing the existing `stale_cycles` counter as `F[k]` and `recommit_block_pulls`
  as the eligibility gate. The full hypothesis' continuous `F[k]` is narrowed to a
  single threshold + block.
- **`S` — global pressure.** A whole-system allostatic load that, when high, favours
  a consolidation/recovery mode over new acquisition. *Deferred* (§6) — must extend
  the existing `resource_deficit`, never add a duplicate fatigue variable. No Run-7
  evidence yet.
- **`C` — endogenous phase.** A slow internal oscillator that shifts budgets between
  exploration and consolidation on a clock. *Deferred, lowest priority* (§6) — see
  Prediction 2 for why a clock alone is dangerous.

**Invariants (what any temporal regulator must preserve):**

1. **Phase alters conditions, not content** — regulation may change *which* goal is
   eligible, never *what* Orrin concludes or says.
2. **User communication is never gated** — reply/EVC paths are outside the regulated
   slot entirely.
3. **No permanent suppression** — every block must decay and the goal must re-enter
   *fresh*, on equal footing; a regulator may not kill an attractor, only yield its
   turn. (F1 satisfies this via the 1/pull decay + fresh re-entry, §2.2.)
4. **Credit can re-admit** — genuine new information gain should be able to clear a
   block early; recovery/regulation must never *prevent* a goal that has started
   producing again. (Moot for F1's arming path — a producer can't reach the stale
   ceiling — so the early-re-admit half is deferred, §6.)
5. **Recovery cannot award success** — yielding a slot awards no reward; it only
   withholds eligibility. Otherwise the regulator becomes a new thing to pump.

**Predictions:**

1. Adding an absolute fatigue release breaks a monopoly that no relative penalty
   could (Run 8's G1 tests this directly).
2. **A phase oscillator (`C`) alone is insufficient and can be harmful** — it
   interrupts a monopoly only to hand it straight back when the phase turns, so a
   naive clock produces *thrash*, not rotation. This is why Run 8 triggers on
   *evidence of non-progress* (`stale_cycles` with zero credit), not on a clock, and
   why `C` is the lowest-priority deferred item.
3. With multiple genuine attractors available (F2's four directions), an absolute
   release yields *rotation among directions*; with only one attractor it yields to
   ordinary goals — so F2 is a precondition for the release to produce *good*
   behaviour, not merely non-monopoly.

**What Run 8 settles:** whether Prediction 1 holds with `F[k]` alone. If G1 passes
with G2∧G4 clean, the `S`/`C` layer stays parked indefinitely (§6). If F1 fires
cleanly yet G1 still misses, that is the evidence that promotes `S` (protected
consolidation) from hypothesis to build — and only then.

---

*Created 2026-07-14. Companion to `docs/NEXT_RUN_TESTS.md` (Run 8 gate). Appendix A
is the self-contained statement of the "Global Temporal Regulation" hypothesis this
plan narrows to one shippable lever (F1) — previously referenced but undocumented.*
