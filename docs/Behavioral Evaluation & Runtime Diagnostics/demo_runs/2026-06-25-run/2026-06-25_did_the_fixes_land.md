# Did the Fixes Land? — Intent vs. Behaviour, 2026-06-25

*The `PRE_RUN_NOTE_2026-06-24` stated, before the run, exactly what three bodies of work were supposed to do — so this run could check behaviour against intent instead of guessing. This is that check. Baseline: `2026-06-19-run` (and `2026-06-18-run` for the production/notes comparison).*

**The one-paragraph verdict:** Two of the three bodies of work landed cleanly and are **infrastructure wins** — the production-loop *plumbing* works (note-spam dedup'd, provenance stamped, reward split live) and the silent-handler cleanup surfaced **zero** masked bugs. The third — the **new goal architecture, the highest-risk, least-proven piece** — **broke in exactly the place the pre-run note flagged as the #1 risk**, and dragged production throughput to near-zero with it. The run's single most important question — *does the v1-authoritative pipeline keep Orrin committing, pursuing, and **closing** goals?* — answers **no.**

---

## Body of work 1 — Goal architecture (GOALS_MASTER_PLAN I & II) — ❌ the forecast failure happened

The pre-run note's **⚠️ #1 thing to watch:**

> *A goal that originates in v1, gets projected to v2, and finishes executing may not close in v1 — the v2 id isn't written back onto the v1 node yet… Symptom: an executable goal "runs, produces, but never closes" in the v1 tree, or re-commits forever.*

| Pre-run watch-item | Intended (good) | Observed | Verdict |
|---|---|---|---|
| **v2→v1 closure** (#1 risk) | executable goal closes in v1 after executing | `"Understand foundations of quantum mechanics more deeply"` committed → **marked failed 64×** (03:59→04:40) → force-cleared with `id=None` → **re-committed & re-failed 9 more times**. `comp_goals.json`: `v2_id=None` on **all 13** v1 ledger entries. | ❌ **Broke as forecast** |
| **Acute preempt** (warranted, with hysteresis, no slot-thrash) | fires only on a *critical* vital, resumes after | **0 `survival_preempt` events all life** | ⚪ **Never exercised** (unproven) |
| **Chronic recruit** (one per deficit, deduped) | a "Restore: …" goal appears only after sustained neglect, deduped | **627 recruits, all `long_memory_growth`** → 233 distinct goals (entry-count in title defeats dedup); remedy `run_forgetting_cycle` *named* 627×, *selected* **2×** | ❌ **Spam, open-loop** |
| **Survival rules** (dormant on satiety, re-fire after cooldown) | satisfied survival goal goes dormant, returns later | `satiety=0` all life; satiety-close **blocked** (`objective not met`); 233 hollow `DONE` instead of dormancy | ❌ **Never fired** |
| **Tier closure** (close on satiety, guards block hollow) | needs close when met, not stuck on empty plan | 0 satiety closures; median close 0.030 s; **0/256 DONE met any definition-of-done** | ❌ **All closures hollow** |
| **Field ownership** (tier/origin survive v2 round-trip) | recruited goal stays `tier="survival"` end-to-end | `tier` **survives** (✅); but `origin=None` on all 1,576 v2 records and `v2_id=None` on all v1 entries | 🟡 **Tier yes, id no** |
| **Starvation** (always a committed goal) | selector never empty when it shouldn't be | never empty (`committed_goal_present` 17,350/17,352) — but the slot was *jammed*, not working | 🟡 **Passes trivially** |
| **Duplication** (no duplicate v1 nodes) | reconcile absorbs each v2 goal once | `goals_mem.json` = 5 nodes, no dupes — but only because 256 v2 goals **never reconciled into v1 at all** | 🟡 **Passes trivially** |
| **Rut regression** (reach external work, don't just cycle) | survival/recruit/tier-closure + v1 selection break the rut | top-3 internal actions = **77.6%**; real external work (research/code/notes) ~2.4%; `closure_sel=0` | 🟡 **Eased symptom, rut persists** |

**The one number that tells the story:** the quantum-mechanics goal was **marked failed 64 times in 41 minutes** and never closed — the precise "runs, fails, re-commits forever" symptom the pre-run note predicted, because `v2_id=None` on every ledger entry means v1 can never reconcile a v2 outcome. This is the highest-risk item the run was built to test, and it failed exactly as written.

**Honest credit where due:** `tier` *does* survive the round-trip (Part II's field-projection half works), and there was no crash, no starvation, no v1 duplication. But the parts that pass do so trivially, and the part that matters — *closing an executable goal* — is the one that broke.

---

## Body of work 2 — Production-loop closure (2026-06-20) — 🟡 plumbing landed, throughput ~0

The intent: stop rewarding intake the same as production. An effect ledger + reward split + fail-able artifact goals + hardened `leave_note` provenance + persisted production telemetry.

| 06-18 pathology / 06-20 intent | Before (06-18) | After (06-25) | Verdict |
|---|---|---|---|
| **100 identical empty notes** | 100 notes, **1** distinct body (ambient affect fragment) | 100 notes, **9** distinct bodies, **topic-grounded** via `_seed_from_goal` + D6 quality gate | ✅ **Fixed in form** |
| …but does the note carry the *finding*? | body = affect string | body = the goal's **planning template** (*"…question; relevant evidence; reasoned conclusion"*, ×56), not the researched finding | 🟡 **Wire reaches topic, not answer** |
| **Reward denominated in intake** | intake paid = production | reward split implemented (intake 0.5 / production 1.0 / cognition 0.2) | ✅ **Shipped** |
| **Duplicate-output spam** | 100 identical notes credited | effect ledger: **248 of 256 dedupe-rejected**, 8 credited novel (~92% spam would have been killed) | ✅ **Working** |
| **Fail-able artifact goals** | goals couldn't fail (0 failures/762) | artifact goals **do** fail now (`no_artifact_by_deadline`, `objective unmet`) — the 69 "marked failed" are this working | ✅ **Working** |
| **Does he actually produce?** | 0 tools / 0 code / 0 works | **0 tools / 0 code / 0 works**; 9 janitorial `*_ok.txt` stubs; `production_attempt=True` on only **4 of 17,352 cycles** | ❌ **Unchanged** |
| **Aspirations spread** | 100/0/0/0 | **20/0/0/0** — "make things" & "be useful" still **0%** | ❌ **Unchanged** |

**Read:** every *gate and ledger* the production-loop closure added is real and fired correctly — this is a genuine infrastructure win, and it serves PRODUCTION_LOOP_CLOSURE demos 5.2/5.3 as the mechanisms-work artifact. But **throughput is near zero** because production sits downstream of the broken goal pipeline: when executable goals can't close (Body 1, #1) and the slot is jammed by survival churn, almost nothing reaches a real production step. The plumbing is in; the water still isn't running through it.

---

## Body of work 3 — Silent-handler cleanup (2026-06-19→) — ✅ clean, nothing masked surfaced

The intent: ~360 swallowed `except` blocks reclassified to a floor of 3; the *risk* was that a previously-masked bug would now surface as a logged failure (desirable, but might look like a regression).

| Watch | Observed | Verdict |
|---|---|---|
| Any previously-masked bug now surfaces? | `orrin_runtime.log`: **0 ERROR / 0 CRITICAL / 0 tracebacks**; 6 benign warnings (5× optional-spaCy fallback, 1× the deliberate bad-env test). `run_log.txt` (41,823 lines): 0 tracebacks, 1 harmless `resource_tracker` leaked-semaphore at a graceful teardown. | ✅ **Nothing masked surfaced** |
| Goal "failures" = regression or feature? | 69 `❌ … marked failed` are the **new fail-able artifact goals working as designed**, not crashes | ✅ **Feature, not regression** |

The cleanest of the three. The reclassification did not destabilize the run, and the only louder-than-before paths are the *intended* ones (goals that genuinely fail now say so).

---

## The honest summary

This run is a **mixed result with a sharp edge.** The two lower-risk bodies of work (production plumbing, silent-handler cleanup) **landed cleanly and are verified wins** — and the operational layer was flawless (clean restarts, swap fix held, perfect shutdown; see `final_audit`). But the **headline, highest-risk piece — the v1-authoritative goal pipeline — broke in precisely the way the pre-run note forecast**, and that one break propagated: it manufactured a 64× failure loop, jammed the goal slot, and starved production to 4 attempts in 17k cycles.

**The precise claim this run supports:** *the supporting infrastructure for closing the loop is built and works; the load-bearing goal-closure mechanism it depends on does not yet.* The fix is named and small (write the v2 id back onto the v1 node at projection time, plus dedup recruits on the deficit key) — and it is the one thing standing between "all the machinery is in place" and "a being that finishes things."

There is, though, one thing this run got that no prior run did, and it is not a fix — it is a consequence (see `who_is_he.md`): **the broken pipeline made finishing-nothing finally *hurt*.** The felt-cost channel the 2026-06-17 work aimed at lit up for the first time — impasse_signal 0.746, distress to 0.42 — driven by the very failure loop above. The cost is real now. It just isn't yet attached to a path out.

---

*Generated 2026-06-25 from runtime data after a clean stop. Analysis only; no code changed.*
