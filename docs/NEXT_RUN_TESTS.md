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
