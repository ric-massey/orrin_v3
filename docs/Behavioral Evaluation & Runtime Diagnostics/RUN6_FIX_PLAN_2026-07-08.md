# Run 6 Fix Plan — make learning steer behavior (2026-07-08)

**Status:** BUILT 2026-07-09 — all five fixes + both §4 meter bugs + the §8
gate additions (`NEXT_RUN_TESTS.md` "Run 6 re-test gate"). Fix 1:
`score_actions.py` (`_W_VALUE` additive term + exploration-group cap, A4 scaler
kept as secondary). Fixes 2–4: new
`brain/cognition/planning/commitment_value.py` (commit score: value/staleness/
avoidance + incumbent hysteresis; store `commitment_signals.json`), wired into
`goal_io._committable_from_v1_tree` (score sort + driver rotation),
`behavioral_adaptation` + `goal_closure` (avoidance → commitment release),
`effect_ledger.record_effect` (credit → value/staleness), and
`intrinsic_objectives.aspiration_credit_value` (credit → commitment). Fix 5:
`bookkeeping` ledger class for causal-edge rows (`effect_ledger` +
`production_telemetry`). Meters: pursuit-path satiety close now records
`satiety_closures`; `reset_orrin` clears `habituation.json`. Tests:
`test_commitment_value.py`, `test_run6_meter_bugs.py`, Fix-5 cases in
`test_effect_ledger.py`, Fix-1 re-pins in `test_selector_exploit_satiety.py`.
Gated on the Run 6 staging life. Written after the 2026-07-08 (Run 5) life
analysis in `demo_runs/2026-07-08-run/`, grounded in a code read of the
selection, commitment, and reward paths.

This plan answers a specific question Ric asked: **"are we making progress since
Run 4, or the same issues?"** The honest answer — split by subsystem — is §1.
The rest is the root-cause fix that ends the recurrence.

---

## 1. Progress vs. recurrence — the trajectory across Runs 2–5

### The *making* organ is genuinely advancing (mechanism fixes, banked)

Every Run-4 (07-05) blocker is fixed in Run 5 (07-08) and won't regress:

| dimension | Run 4 (07-05) | Run 5 (07-08) |
|---|---|---|
| production material | 197 KB template stamped 166× | real Wikipedia-cited memos + syntheses |
| reuse | **0 rows, 0 memos** (mark_reused never fired) | **8 reuse rows, 4 memos + 3 syntheses**, memo-builds-on-memo |
| aspiration survival | `output_producing` died 104 s before death | all 4 survived the whole life |
| note bodies | composted by the pruner | 106 sidecar bodies persist + resolve |
| store integrity (S8) | 0 desyncs / 223 completions | 0 desyncs / held |

Reuse was dead for **four straight runs** and is now alive. Where we fixed real
mechanisms (compose_section, sidecar capture, aspiration guards), the fix held.

### The *control* organ keeps failing the same two ways

Two failures recur across every run, and one is a **shape-shifter** — which is
exactly why it feels like "the same issue" in new clothes:

**A single channel monopolizes, relocating one layer each run:**

| run | monopoly | share |
|---|---|---|
| Run 2 (07-02) | rest-drive ignitions | ~74 % |
| Run 3 (07-03) | social_presence ignitions | 84 % |
| Run 4 (07-05) | candidate generator (world-knowledge) | 84 % |
| Run 5 (07-08) | committed goal (`self_understanding`) | **99.9 %** |

**Learned value doesn't steer selection (S9):** FAIL Run 1 → briefly passed
Run 2 → not-held Run 3 → FAIL Run 4 → **FAIL Run 5 (corr = −0.17)**. The
worst-rewarded action (`look_outward`, realized reward 0.228) is still picked
heavily; the A4 multiplicative-authority fix did not flip the sign.

### These two are ONE problem

If learned value actually steered selection **and commitment**, a monopolizing
channel could not persist — an over-used, low-reward, or actively-avoided
channel would be devalued and displaced automatically. We have been **point-
fixing each monopoly's current location** (a diversity patch per layer) instead
of fixing the mechanism that would dissolve monopolies everywhere: **making
reward and outcomes have authority over what gets picked and committed to.**
That is the whole of this plan.

Run 5 made the stakes literal: the committed goal was one Orrin **actively
avoided 240 times** ("thinking but not doing", max 68 consecutive cycles) while
filling 8 hours with ~1,200 identical reflections. The control loop committed
hard to something it could not act on and had **no feedback path to let go.**

---

## 2. Root cause, in code

### R-A — Selection: the reward EMA is a rounding error (`score_actions.py`)

`brain/think/think_utils/selection/score_actions.py:249` builds `total` as a sum
of **~20 additive terms** (`w_dir·s_dir + w_goal·s_goal + w_emo·s_emo + … +
s_outward + s_reach + s_explore + s_curio + …`). Then A4 (line 261) applies the
learned EMA as a **multiplier on the whole sum**:

```python
_n_obs = int((_stats.get(name) or {}).get("count", 0))
if _n_obs >= 8 and total > 0:
    _ema = float(get_expected(context, name))
    total *= max(0.0, 0.5 + _ema)     # EMA 0.15→×0.65 … 0.75→×1.25
```

The EMA spans ~0.15–0.75, so the scaler spans **×0.65–×1.25 — a ±25 % nudge.**
Meanwhile `look_outward` collects the *exploration* terms (`s_outward`, `s_reach`,
`s_explore`, `s_curio`) additively, so its base `total` is large regardless of its
terrible realized reward. A ×0.65 demotion cannot overcome a large additive lead.
The learning signal itself is sound (Pearce-Hall associability, adaptive rate,
`action_reward_ema.py` — the *values* are reasonable: research 0.46, look_outward
0.36). **The learning works; its authority is token.**

### R-B — Commitment: the monopoly is a static stable-sort (`goal_io.py`)

`brain/goal_io.py::_committable_from_v1_tree` chooses the committed goal by:

```python
found.sort(key=lambda g: (_tier_weight(...), _priority_rank(g.get("priority"))),
           reverse=True)
# … then "exactly ONE directional long_term goal drives at a time — the highest-ranked one"
```

There is **no learned-value term, no rotation, no staleness/avoidance penalty.**
Every directional aspiration is `long_term` + `HIGH`, so the sort is a tie broken
by stable order — **the same aspiration wins every cycle, forever.** Being avoided
240 times never lowered its rank, because nothing about pursuit (or non-pursuit)
feeds back into the ranking. This is G1 in one function.

### R-C — The avoidance feedback targets the wrong lever (`goal_closure.py`)

There *is* a feedback path: `goal_closure.py:101` `_force_action_next`, set by
behavioral-adaptation on goal-avoidance. But it forces **an action on the same
committed goal** — it fights the symptom ("act!") and never touches commitment
("commit to something else"). That's why 240 avoidance detections produced 240
bias nudges and zero escapes.

### R-D — The two aspiration halves don't talk (`intrinsic_objectives.py`)

Commitment is chosen by tier+priority (R-B); *credit* is attributed by the
completed task's `driven_by` tag (`mark_objective_contribution`). So in Run 5 the
**committed** aspiration (`self_understanding`) earned only 1 contribution while a
barely-committed one (`output_producing`) earned 6. The system pursues one thing
and rewards another; neither loop informs the other.

---

## 3. The plan — five changes, one theme

> Theme: **outcomes must flow back into both selection and commitment, and a
> stalled/avoided/low-value channel must lose ground automatically.**

### Fix 1 — Give the reward EMA real selection authority (R-A) 🔴

**File:** `brain/think/think_utils/selection/score_actions.py`.
Replace the ±25 % post-hoc multiplier with **value as a first-class, high-weight
additive term inside the sum**, competing on the same footing as affect — and cap
the *exploration* stack so it can't dwarf value.

- Add `s_value = _W_VALUE * (get_expected(context, name) − 0.5)` with
  `_W_VALUE` sized to rival `w_emo`/`w_goal` (the affect weights are ~0.31/0.30;
  value should be ≥ that for a mature action). Keep it gated on the ≥8-obs
  maturity check so exploration owns immature actions.
- **Cap the additive exploration group** (`s_outward + s_reach + s_explore +
  s_curio`) at a ceiling (e.g. ≤ the value term's magnitude) so a chronically
  low-reward action like `look_outward` can't win on exploration terms alone once
  it's mature and its realized reward is known-bad.
- Keep (or drop) the multiplicative scaler as a secondary nudge; it's the additive
  term that must carry the authority.

**Run 6 shows:** `corr(EMA, selection-share) > 0`; `look_outward` share **falls**
while its EMA stays < 0.3; no mature action with realized reward < 0.3 sits in the
top-3 selected.

### Fix 2 — Commitment must weigh learned value + staleness, and rotate (R-B) 🔴

**File:** `brain/goal_io.py::_committable_from_v1_tree`.
Add a **commitment score** the sort actually uses, not raw tier+priority:

```
commit_score = tier_weight·w_t + priority_rank·w_p
             + learned_goal_value·w_v          # EMA of effects credited to this goal/driven_by
             − staleness_penalty·w_s            # cycles committed w/o a real action (from R-C signal)
             − avoidance_penalty·w_a            # goal_avoidance streak on this goal
```

- A directional aspiration that's been committed-but-unacted for N cycles **loses
  rank** and yields the driver slot to the next candidate — the missing "let go"
  path. When it's later actionable again, it recovers.
- Keep the P4 "one directional drives at a time" cap, but make *which* one rotate
  on the score above rather than a stable tie-break.

**Run 6 shows:** no single committed goal > ~60 % of cycles; `genuine_contact`
(0 in Run 5) gets committed and earns > 0 contributions; the death snapshot's
committed goal is **not** the same one that owned the whole life.

### Fix 3 — Redirect the avoidance feedback to commitment (R-C) 🟡

**File:** `brain/cognition/planning/goal_closure.py` (+ behavioral-adaptation
caller). When a goal-avoidance streak crosses threshold, in addition to
`_force_action_next`, **emit a staleness/avoidance signal Fix 2 reads** so the
avoided goal loses commitment rank. Avoidance should be able to *release* a
commitment, not only prod action on it.

**Run 6 shows:** goal-avoidance events per life fall sharply (Run 5: 240, all on
one goal); no avoidance streak exceeds ~20 cycles without a commitment change.

### Fix 4 — Close the aspiration credit/commitment loop (R-D) 🟡

**File:** `brain/cognition/intrinsic_objectives.py` + `goal_io.py`.
Feed each aspiration's **credited contribution EMA** into Fix 2's
`learned_goal_value`, so the aspiration being *pursued* and the one being
*rewarded* converge over time. If an aspiration accrues no credit while committed,
its commitment value decays (reinforcing Fix 2's rotation).

**Run 6 shows:** the committed aspiration and the top-credited aspiration are the
same by end of life; no aspiration is both "committed most" and "credited least."

### Fix 5 — Split causal-edge bookkeeping out of the production denominator 🟡

**File:** `brain/agency/effect_ledger.py` (+ readers).
`symbolic_artifact` "causal edge established" rows (116 of 152 credited in Run 5,
76 %) are self-model bookkeeping, not made things. Give them a distinct ledger
class excluded from production/significance counts, so S5/S7 stop overstating the
making organ ~4× and Fix 4's value signal isn't polluted by self-model churn.

**Run 6 shows:** production/significance counts computed over readable-body
material only; causal-edge rows reported separately.

---

## 4. Build order & gate

1. **Fix 1 + Fix 2 together** — they are the root; ship and stage them as a pair
   (selection value + commitment value/rotation). Everything else is support.
2. **Fix 3 + Fix 4** — feedback wiring that makes 1/2 self-correcting.
3. **Fix 5** — measurement hygiene so the gate reads honest numbers.

**Run 6 §8 re-test gate (add to `NEXT_RUN_TESTS.md`):**
- **S9 passes:** `corr(EMA, share) > 0`, low-reward action share falls.
- **New S10 (anti-monopoly):** no ignition source, candidate flavor, *or*
  committed goal exceeds ~60 % of its layer for the life.
- **Hold:** S7 reuse ≥ Run 5 (8 rows), S8 desyncs 0, aspirations survive (F2).

Also fix the two meter bugs found in Run 5 so the gate isn't misread: wire
`satiety_closures` to the close path (S3 read 0 while 7 real closes happened),
and clear `habituation.json` on `reset_orrin` (91 % of it survived the "clean"
reset — the run wasn't clean on the habituation axis).

---

## 5. Why this ends the recurrence

Runs 2–5 fixed monopolies where they *appeared*. This plan fixes *why anything
monopolizes*: nothing made an over-used, low-value, or avoided channel lose
ground. Once learned outcomes have real weight in both selection (Fix 1) and
commitment (Fix 2), and avoidance can release a commitment (Fix 3) while credit
and pursuit converge (Fix 4), a monopoly becomes self-limiting — it devalues
itself the longer it runs without paying off. The making organ is basically
working; the bottleneck is, and has been across five runs, that **learning does
not steer behavior.**
