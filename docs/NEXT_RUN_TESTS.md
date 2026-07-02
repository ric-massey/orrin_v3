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
