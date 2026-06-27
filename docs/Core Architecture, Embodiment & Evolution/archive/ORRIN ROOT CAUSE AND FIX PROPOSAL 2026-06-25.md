# Orrin — Root-Cause & Fix Proposal

**Date:** 2026-06-25
**Status:** Proposed — for review and work-splitting
**Run under analysis:** Life of 2026-06-23 23:37 → 2026-06-25 00:41 EDT (17,352 cycles, clean stop)
**Companion:** The signal-by-signal Wiring Map is folded in as **Appendix A** — read it alongside §2 (the open-loop argument) and §5 (the workstreams it inventories).
**Author note:** This consolidates a fresh code/data pass with the prior forensic pass. Provenance is marked per claim (`[verified this pass]` = traced in source/data here; `[prior pass]` = from the earlier run-analysis / data-audit docs, re-cited for completeness). Everything tagged `[prior pass]` should be independently re-confirmed before work starts — that's part of why this doc exists.

---

## 1. Executive summary

The run did **not** fail because "goals are broken." Goals are where the failure is loudest, but they are a *symptom*. The run failed because of a single structural pattern that shows up in a dozen places:

> **Orrin is afferent-rich and efferent-poor: it senses, feels, and models almost everything, and routes almost none of that back into what it does next. It is an open-loop system wearing closed-loop clothing — and it has no authority to act on its own evidence without a human.**

This pattern is the *generator* of the individual bugs, and it is why prior lives keep landing in the same place. Each life added a better *component*; the deficit was never components — it was the **closing edges between them**, which are invisible to component-level testing. Every part passes its own unit test; the system fails at integration, in the same spot, every life.

The fix is therefore **not** another round of component polish. It is a change in the *unit of work*: from "ship a better X" to "wire and prove one complete loop, end to end, on real evidence." This document names the generator, gives the evidence, proposes the fix, and splits the work into six ownership-ready workstreams with loop-level acceptance tests.

---

## 2. The generator, stated precisely

Two intertwined faults produce nearly all observed pathology.

### 2.1 Open feedback loops — "computed, never read"

Outcomes are produced but the edge that would let an outcome change the next decision is missing or open. The same shape, repeated:

| Signal / outcome produced | Edge that should consume it | State |
|---|---|---|
| `allostatic_load` (stress readout) | telemetry / behavior | read by telemetry only; mistuned `[verified]` |
| `vitality` (felt aliveness) | any rest/fatigue decision | **read by nothing** `[verified]` |
| `action_reward_ema` (learned action value) | action selector | not a selector input `[prior pass]` |
| per-action satiety | action selector | not a selector input `[prior pass]` |
| PLANNING prediction error (0.999) | rule retirement | rules keep firing at full priority `[prior pass]` |
| v2 goal execution outcome | v1 node closure | `v2_id=None`, can't reconcile `[prior pass]` |
| 37 proposed rule revisions | rule store | all `pending`, never applied `[prior pass]` |
| goal "DONE" flag | satisfaction check | 0/256 actually met their definition `[prior pass]` |

Every row is the same defect: **a loop that doesn't close.**

### 2.2 No evidence-based corrective authority

The system accumulates but will not prune on outcome, and nothing is allowed to act on evidence without a human:

- A rule wrong 893/893 times keeps firing 1000+ times. `[prior pass]`
- A goal failed 64 times keeps re-committing. `[prior pass]`
- Revisions queue forever instead of applying or being rejected. `[prior pass]`
- Closure rubber-stamps "DONE" instead of checking satisfaction. `[prior pass]`

Sensing without corrective authority is a detailed way of staying the same.

### 2.3 Why this explains "stuck across lives"

Component testing cannot catch a missing-edge problem — each component is individually green. Integration is the only place it surfaces, and **closure is the integration test of the whole mind**: it is the one operation that touches perception, affect, memory, planning, action, and self-model at once. That is also why the user's instinct is right — *legitimate hierarchical goal closure is harder than any single subsystem because it uses all of them.* The difficulty is real, but it is **interface correctness**, not component weakness — which makes it tractable without "fixing the whole mind first."

---

## 3. What is actually solid (so we don't re-fix it)

Confirmed healthy this pass — **do not** spend effort here:

- **Affect coherence** `[verified]`. End-of-life core vector is differentiated, not pinned (stdev 0.358 across 12 signals; positive_valence 0.90 coexisting with contentment 0.006 and impasse 0.746). The opponent-process per-call decay fix (Solomon & Corbit) worked; the old "everything maxed at once" incoherence is gone.
- **Interoception allostatic regulator** (`_allostatic_load`) `[verified]`. Genuinely sophisticated: predictive recovery target τ, asymmetric load (builds +0.02 / recovers −0.04), mandatory-rest override at load>0.5, dream-scaled recovery. This is the *correct* allostatic system — see §5 WS-5.
- **Causal self-model** `[verified]`. 398 edges; high-evidence ones correctly signed (`assess_goal_progress` → impasse/uncertainty/stagnation fall; `look_outward` → positive_valence rises), learned from intervention evidence.
- **Experiential learning substrate** `[verified]`. 314 semantic action→outcome facts with counts/confidence; 18 crystallized skills; native LM at 22.1M tokens (3.2× prior life).
- **Ops & persistence** `[prior pass + spot-verified]`. 5 graceful restarts, 0 crashes, swap fix held, no RSS leak, clean shutdown, all JSON/JSONL parse intact, locks released.

The foundational layers are sound. The broken parts are in the **middle layers** (prediction, closure, selection, social, and several lying instruments) — the parts closure depends on and exposes.

---

## 4. Fix strategy (the part that prevents getting stuck again)

Four operating rules, in priority order. These govern *how* the workstreams in §5 are executed.

1. **Change the unit of work from component to loop.** Do not ship "a better X." Pick one complete loop, wire every edge, prove it closes on real evidence, then move. Add nothing new until the current loop is green.
2. **Put the acceptance test at the loop, not the component.** The capstone red test: *a goal born from a felt need closes because it satisfied that need, with evidence, and the spawning drive then drops.* Keep it red until the whole loop is green. (This is exactly the need-satisfaction handshake already designed in the autonomic/felt-goal proposal — that primitive is the right one.)
3. **Run a standing open-edge audit.** Any signal computed-and-written but never read is a missing wire or dead weight. Any learning signal that is not a selector input is decorative. This turns "the wiring is wrong" from a vibe into a finite checklist (see WS-5).
4. **Sequence bottom-up by dependency, not by what's satisfying to build.** Fix PLANNING and the v1↔v2 binding *before* production polish; closure and production sit downstream of them.

---

## 5. Workstreams (ownership-ready)

Each workstream lists: problem, fix, evidence, loop-level acceptance test, dependencies. Priorities: **P0** = foundational/blocking, **P1** = high, **P2** = medium, **P3** = isolated/parallelizable.

### WS-1 — Goal closure core (P0) — *capstone loop*
**Problem.** Executable goals run and fail in v2 but cannot close in v1; closures are hollow.
**Fix.**
- Write the v2 id back onto the v1 node at projection time so completion/failure reconciles.
- Require a **satisfaction handshake** for felt-origin goals: `DONE` must carry `satisfied_need` + evidence; no evidence → not done.
- On satisfaction, **relax the spawning drive/need** (close the loop back to affect).
**Evidence.** `comp_goals.json`: `v2_id=None` on all 13 v1 ledger entries; `origin=None` on all 1,576 v2 records; "quantum mechanics" goal marked failed 64× then re-committed `[prior pass]`. 0/256 DONE met any definition-of-done `[prior pass]`.
**Acceptance test (loop).** A goal spawned from a felt need reaches DONE *only* with satisfaction evidence; the originating drive measurably drops after closure; the 64×-style re-commit loop cannot occur.
**Depends on:** WS-3 for trustworthy foresight (soft dependency — can start in parallel, must integrate after).

### WS-2 — Selector wiring (P1)
**Problem.** The action selector ignores its own learning signals.
**Fix.** Feed `action_reward_ema` (elevating) and per-action satiety (suppressing) into the selection score.
**Evidence.** `run_forgetting_cycle` is the highest-reward action (EMA 0.755) yet selected 2×; `look_outward` reached satiety 1.0 yet was selected most (5,082) `[prior pass]`. Terminal goal-lens is also near-dead — `goal_lens_top_signal_relevance = 0.0` in 381/400 final cycles `[verified this pass]`, suggesting the committed goal exerts almost no pull on attention; worth confirming whether the lens is a third decoupled selector input.
**Acceptance test (loop).** A high-reward, low-satiety action's selection frequency rises measurably vs baseline; a fully-satiated action's frequency falls.
**Depends on:** none.

### WS-3 — Prediction & learning authority (P0)
**Problem.** PLANNING predictor is wrong essentially every time but keeps firing; revisions never apply; one instrument lies about it.
**Fix.**
- Outcome-based **rule authority**: a rule's firing priority decays automatically with sustained prediction error; wrong-100% rules lose the floor.
- **Drain the revision queue**: revisions apply or are rejected, never sit `pending`.
- Fix the `accuracy` field so it reflects `correct/total` (see WS-5).
**Evidence.** `prediction_domain_stats.PLANNING`: total 893, correct 0, reliability 0.0011, `prediction_error 0.9989`, still heavily used `[prior pass]`. `accuracy` field stuck at 0.5 prior while true is 0.0 `[prior pass]`. `rule_revisions.json`: 37 entries, all `pending` `[prior pass]`.
**Acceptance test (loop).** A rule that mispredicts N times in a row loses priority without human action; a proposed revision reaches applied/rejected within a bounded window.
**Depends on:** none. **Blocks:** WS-1 quality (closure relies on planning foresight).

### WS-4 — Survival / maintenance subsystem (P1)
**Problem.** Chronic-deficit recruiting spams; the remedy can't remedy; autonomic maintenance leaks into conscious goals.
**Fix.**
- Dedup recruits on the **deficit key**, not the entry-count-bearing title.
- **Fix the remedy**: `run_forgetting_cycle` pruned 0 on every run — a restoration goal whose action can't restore is a guaranteed perpetual recruit.
- Land the **autonomic-vs-felt boundary** (separate maintenance proposal) so file-size/WAL/cache work never becomes a conscious goal.
- Allow tier-closure on the satiety predicate independent of the objective gate.
**Evidence.** 627 recruits, all `long_memory_growth` → 233 distinct goals (title defeats dedup); remedy named 627×, selected 2×, pruned 0× (`forgetting_log.json`) `[prior pass]`. `satiety=0` all life; satiety-close blocked by "objective not met" `[prior pass]`.
**Acceptance test (loop).** One sustained deficit produces one live restoration goal; its remedy demonstrably reduces the deficit; the goal closes on satiety; no conscious goal title ever contains a raw file/entry count.
**Depends on:** WS-1 (shares the satisfaction/satiety closure machinery).

### WS-5 — Signal hygiene & observability (P1, high-leverage)
**Problem.** Several instruments lie, which sends debugging to the wrong room (this is *how* the user lost time on allostatic_load).
**Fix.**
- **Unify allostatic load.** Retire `homeostasis.update_allostatic_load` (the mistuned, exploration-drive-keyed, monotonic, telemetry-only one) and point telemetry + life-capsule at the correct `_allostatic_load`. *Root cause:* it integrates raw `exploration_drive` deviation from baseline 0.25; resting curiosity ~0.84 → deviation ~0.59, above the 0.5 crossover, so load only ever climbs and saturates to 1.0 in ~540 cycles, then pins for 25 h. The `_EXPLORATION_DEV_WEIGHT = 0.15` that exists *precisely* to neutralize this is applied in a sibling function but not here.
- **Decide vitality's fate.** It is write-only (6 occurrences, all `health_monitor.py`) with baseline 0.0 → decays to ~0 and is read by nothing. Either give it a non-zero healthy baseline + a real consumer (e.g. the "rest when vitality low" trigger) or delete it.
- **Open-edge audit (standing task).** Grep every computed-and-persisted signal for readers; each with none is a missing wire or dead weight. Each learning signal that isn't a selector input is decorative — list them.
**Evidence `[verified this pass]`.** `homeostasis.py:107–117` (integrator), `:74` (`_EXPLORATION_DEV_WEIGHT`), `:98` (weight applied here, not in the integrator); `setpoints.py` `CORE_BASELINES["exploration_drive"]=0.25`; `interoception.py:245–247,300` (`_allostatic_load`, recovers); consumers of the pinned one: `telemetry.py:197`, `life_capsule_ingest.py:330` only; correct one consumed by interoception τ + `dream_cycle.py:532`. Data: `affect_state.json` `allostatic_load=1.0` while `resource_deficit=0.0099`, `exploration_drive=0.8418`, `vitality=1.09e-07`. Note: `boosts.py:257`'s "stress impairs executive function" reads `_stress_streak` (`:231`), **not** allostatic load — a misleading comment, not a behavioral consumer.
**Acceptance test.** Telemetry `allostatic_load` tracks the behaviorally-active recovery variable and falls when the body recovers; no signal in the persisted state has zero readers without a documented reason.
**Depends on:** none. Mostly parallelizable, low-risk, high-trust-recovery.

### WS-6 — Isolated component faults (P3, parallelizable)
These are *not* open-edge bugs; fix them as ordinary defects.
- Narrative interval > lifetime: `narrative_pressure.json` `next_min_interval_s ≈ 95,219 s (26.4 h)` > 25 h life → Chapter 2 mechanically unreachable. Scale to lifespan / advance on life-events `[prior pass]`.
- `final_thoughts_written: false` on graceful stop — emit final reflection on operator stop, not only modeled death `[prior pass]`.
- `proposed_goals.json` is 0 bytes (invalid JSON) — writer should emit `[]` / readers guard `[prior pass]`.
- `chat_log.json` FileNotFound in telemetry chat-history router — seed file or tolerate absence `[prior pass]`.
- Unbounded per-cycle JSONL (`production_loop`, `telemetry_archive`, `memory_graph`, goals WAL) — add rotation/compaction before multi-day runs `[prior pass]`.
**Depends on:** none.

### Also flagged, needs an owner
- **SOCIAL domain has 0 learned rules** despite `connection` being a core drive (0.63) and the endorsed volition being connection `[prior pass]`. This is a learning gap, not a wiring bug — assign to whoever owns rule acquisition (overlaps WS-3).

---

## 6. Suggested sequencing

```
Phase A (parallel, foundational):   WS-3 (prediction authority)   WS-1 (closure binding + handshake)
Phase B (after A integrates):       WS-2 (selector wiring)        WS-4 (survival + autonomic boundary)
Standing / any time:                WS-5 (signal hygiene, open-edge audit)   WS-6 (isolated faults)
```

Rationale: WS-3 and WS-1 are the load-bearing loop and the layer it depends on. WS-2 and WS-4 sharpen selection and stop the churn that starves production, but only matter once goals can close. WS-5 runs continuously because every instrument it fixes prevents the next person from debugging the wrong room. WS-6 is independent cleanup.

**Do not** begin production-output polish until WS-1 + WS-3 are green — production sits downstream of both, and polishing it first repeats the exact pattern this proposal is trying to break.

---

## 7. Risks & honesty caveats

- **Not every bug is an open edge.** The forgetting remedy (prunes 0) and the narrative interval are genuine component faults; treat them as such. Don't force every fault into the open-loop story.
- **Provenance.** All `[prior pass]` claims should be re-confirmed against the raw data before assigning effort; this doc deliberately separates first-hand verification from inherited findings.
- **The meta-risk.** The most likely failure mode of *this very plan* is the same shape as Orrin's pathology — sense richly, close nothing, keep polishing solid substrate. The discipline that fixes Orrin (close one loop, prove it, then move) is the discipline required to execute this plan. Apply rule §4.1 to ourselves: no new workstream until the current loop's acceptance test is green.

---

## 8. One-line for the higher-up

The substrate is sound; the failure is a system-wide pattern of **open loops with no corrective authority**, concentrated in prediction and goal-closure. Fix it by switching the unit of work from components to **one fully-wired loop at a time**, tested at the loop, sequenced bottom-up — starting with v1↔v2 closure binding and PLANNING rule authority.

---

## Appendix A — Wiring Map (signal-by-signal companion)

*This is the plain-language map that the §2 "open loops" argument is built on. Every feeling, drive, and learned signal I could check, sorted by whether it actually changes what Orrin does. Each item has a confidence level and a fix. Read it alongside §5 (the workstreams) — the dead/half wires below are the concrete inventory those workstreams close.*

**How to read the verdicts:**
- ✅ **Wired & working** — a decision-making part reads it; it steers behavior.
- 🟡 **Half-wired** — one end is connected, the other isn't. Real, sneaky, worth fixing.
- ⚪ **Felt but goes nowhere** — Orrin computes it, but no decision reads it. Dead wire.
- 🔧 **Broken part, not a wire** — it's connected fine, the logic inside is wrong.

**Confidence:** `high` = I traced the code/data directly. `med` = strong evidence, one path unconfirmed. `inherited` = from the earlier analysis, re-cite before acting.

**One honest caveat:** a signal can reach behavior through a weak "weighting" path (`signal_router`) where it nudges attention *in proportion to its size*. A signal pinned near zero flows through that path but contributes ~nothing. I've marked where that applies, because "technically reachable" and "actually does something" are different things.

### The feelings (23 core signals)

#### ✅ Wired & working
These are read directly by selection/planning and routinely non-zero, so they steer behavior.

- **impasse_signal** (feeling stuck) — `high`
- **uncertainty** (not sure what's true) — `high`
- **motivation** (drive to act) — `high`
- **confidence** (belief it'll go well) — `high`
- **exploration_drive** (curiosity) — `high`
- **stagnation_signal** (nothing's changing) — `high`
- **expected_gain** (this looks worth it) — `high`
- **risk_estimate** (this might go badly) — `high`
- **threat_level / negative_valence** (something's wrong/bad) — `high`
- **wonder** (open curiosity) — `med`
- **social_deficit** (need contact) — `med`

These are the ones doing real work. Good.

#### ⚪ Felt but goes nowhere
Computed every cycle, no decision reads them. They flow through the weak weighting path but sit near zero, so they contribute nothing.

- **contentment** (at peace / satisfied) — `high`. **Special and important.** The slow drain toward zero is *correct by design* — it's the hunger that should make Orrin act. The bug is that nothing reads the drain, so the hunger drives nothing. The engine is built; the wire from it to behavior is missing. **This is probably the single most valuable wire to connect**, because the whole "act → feel satisfied → satisfaction fades → act again" loop runs through it.
- **vitality** (feeling alive/energized) — `high`. Read by nothing, anywhere. Also has no resting value, so it just sits at zero. Either wire it (e.g. "rest when vitality is low") or delete it.

#### 🟡 Weakly wired (nudge only, no real steering)
These reach behavior *only* through the weighting path, and only if incoming info happens to be tagged with them. They can mildly tilt attention but don't drive any specific action. Treat as "barely connected."

- **surprise** — `med`
- **compassion** — `med`
- **analytical** — `med`
- **reflective** — `med`
- **jealousy** — `med`
- **melancholy** — `med`
- **positive_valence** (general good feeling) — `med`. *Note:* this one was sitting at 0.90, **above its own ceiling of 0.85** — a small sign that something is pumping it past the limit the clawback is supposed to enforce. Worth a glance.

**Needs-checking flag on this whole group:** I confirmed they don't steer the *decision* parts (selection/planning/goals). I have **not** ruled out that they feed Orrin's *language* (what it says) or its *learning*. So: "doesn't drive actions" is confirmed; "completely useless" is not. Quick follow-up: check whether speech/LM paths read them.

### The drives (the deeper motivations)

- **Drives as a group** (curiosity-mastery, connection, autonomy, competence, novelty) — 🟡 **half-wired**, `inherited`. They do influence things, but **all the "credit" for satisfying a drive flows to only one of four life-aspirations** ("understand the world"). The other three aspirations ("make things," "be useful," "understand self") never get fed, so they sat at 0% all life. So: drives are connected, but the reward routing behind them is pinched down to one channel. **Fix:** spread drive-credit across all four aspirations, not one. *(See the Aspiration Coverage proposal.)*

### The learned signals (things Orrin figures out from experience)

- **action reward** (which actions have paid off) — 🟡 **half-wired**, `high`. This is subtle and worth understanding. The selector reads the *uncertainty* half of this signal (how unpredictable an action's payoff is, used to encourage trying under-explored actions) — but it does **not** read the *value* half (how rewarding an action actually is, which should encourage repeating what works). So the action Orrin learned pays best (the memory-cleanup action) got no boost and was picked twice all day. **One end of this wire is connected, the other is cut.** Fix: feed the reward *level* into the score as a "do more of what works" term, not just the reward *uncertainty*. *(WS-2.)*

- **satiety** (how sick of an action Orrin is) — ⚪ **goes nowhere (for selection)**, `inherited`. An action hit "completely satiated" and kept getting picked the most. The signal exists; selection doesn't read it. Fix: let satiety suppress an action's score. *(WS-2.)*

- **causal self-model** (what causes what) — ✅ **working**, `high`. It correctly learned things like "checking my progress lowers my stuck-feeling." This one's healthy.

- **semantic facts** (action → outcome memory) — ✅ **working**, `high`. 314 learned action/outcome stats with confidence. Healthy.

- **prediction accuracy** (was my guess right?) — 🔧 **broken part**, `inherited`. The planning predictor guessed wrong 893/893 times and the rules kept firing at full strength — the wire that should let "I keep being wrong" retire a rule is missing, *and* the part itself is bad. Also one status field reports it as 50% right when it's 0% right (a lying gauge). Fix: wrong-repeatedly rules auto-lose priority; fix the status field. *(WS-3.)*

### The body / health signals

- **energy** (= 1 − tiredness) — ✅ **working**, `high`.
- **_allostatic_load** (real stress/wear meter, the good one) — ✅ **working**, `high`. Properly wired into rest and dream-recovery.
- **allostatic_load** (the *other* stress meter, no underscore) — 🔧 **broken + mis-shown**, `high`. Pinned at max all life because it's accidentally tied to curiosity (always high), and it's the one the dashboard shows instead of the good one. Fix: delete it, show the good one. *(WS-5.)*
- **health_score** (am I running well) — ✅ **working**, `high`.

### The goal machinery (the capstone)

- **goal closure** (finishing a goal) — 🔧 **broken wire**, `inherited` + `high`. The "doer" half does the work but never tags the result with the "planner" half's ID, so results can't be matched back — one goal failed 64 times in a row this way. This is a **wrong/missing wire inside the goal system**, and it's the headline goal bug. Fix: write the ID back; require real proof before "done." *(This is the one the open-edge sweep does NOT find for you — it came from reading the goal code directly. WS-1.)*
- **need → goal → satisfaction handshake** — ⚪ **not built yet**, `high`. Goals currently open and close without ever touching the feelings they're supposed to serve. This is where the contentment wire (above) plugs in. Fix: goals close on *satisfaction evidence*, and that satisfaction lowers the need that spawned them. *(WS-1.)*

### The checklist (what to actually do, grouped)

**Connect dead wires (the search-found ones):**
1. ☐ Wire **contentment** into the goal/need loop (highest value).
2. ☐ Wire or delete **vitality**.
3. ☐ Wire **satiety** into action selection.
4. ☐ Decide the fate of the weakly-wired feelings (surprise, compassion, analytical, reflective, jealousy) — after checking if they feed speech/learning.

**Fix half-wires (one end connected):**
5. ☐ Feed action **reward-value** (not just reward-uncertainty) into selection.
6. ☐ Spread **drive-credit** across all four aspirations, not one.

**Fix broken parts (logic wrong, not wiring):**
7. ☐ **Goal closure**: write the ID back + require proof of done. *(the main goal fix)*
8. ☐ **Prediction**: auto-retire repeatedly-wrong rules; fix the lying accuracy field.
9. ☐ **allostatic_load**: delete the broken meter, show the good one.
10. ☐ **forgetting cleanup**: make it actually free things (it freed zero).

**Build the missing piece:**
11. ☐ The **satisfaction handshake** — goals close because a need was met, and the need then drops.

### Honest limits of this map

- "No decision reads it" is confirmed for the ✅/⚪ items marked `high`. For the 🟡 weakly-wired feelings, I confirmed they don't steer *actions* but did not check *speech/learning* — that's the one open question on this map.
- Items marked `inherited` come from the earlier analysis; re-confirm against raw data before assigning effort.
- The run data here was a partial snapshot, so this map is built mostly from the **source code** (reliable for wiring) plus the end-of-run state. Behavioral/timing questions would need the full data + the moment-by-moment telemetry log.

**Bottom line:** the map confirms the pattern — a real chunk of Orrin's inner life is felt and then ignored — but it's a *finite, listed* set of wires, not a vague fog. Eleven items. Most are connections, a few are repairs. That's a workable plan, not a rebuild.
