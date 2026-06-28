# Auditing Orrin by Signal→Action, Not by Artifact Output

*Verification report — 2026-06-18. Question posed: "is it true that judging Orrin
by 'every N cycles must produce an artifact' is wrong, and that the right test is
whether internal pressure eventually crosses into appropriate action?" This
document checks that claim against the actual code in `brain/`, separates what is
true from what is a strawman, and names the one issue that is genuinely
actionable.*

---

## TL;DR

The critique is **directionally right but partly aimed at a standard Orrin never
had**, and the "better test" it proposes is **already implemented**. The real,
code-verified gap is narrower and worth fixing:

1. **"Every 25 cycles → an artifact" is not a rule in Orrin.** There is no such
   cadence anywhere in `brain/`. It was a proposed *diagnostic*, never a built
   behavior. Critiquing it as un-human-like is correct, but it is not describing
   an Orrin defect.

2. **The proposed "right test" — internal signal → changed attention → changed
   selection → changed behavior → changed future state — is already built.**
   `brain/cognition/behavioral_adaptation.py` is exactly this loop, citing Carver
   & Scheier (1982), Bandura (1977), and Powers (1973). The architecture already
   agrees with the thesis.

3. **What is genuinely missing / broken (the actionable part):**
   - **(A) Observability gap.** The action-class taxonomy the critique proposes
     (reflex / regulatory / orienting / communicative / productive / maintenance /
     failed-blocked) does **not** exist as an audit lens. We cannot currently ask
     "after signal X, did the right action class rise *and did signal X then
     fall?*" The closest record, `behavior_changes.json`, logs that a correction
     was **armed**, not whether it **landed**.
   - **(B) Closed loop defeated in practice.** In the logged 2026-06-14 run the
     corrective chain *fired* (goal_avoidance flagged 212× consecutively) but was
     **preempted every cycle** by survival/threat systems, with a release valve
     that produced nothing. Designed as a closed loop, it executed as an open one.
     This is precisely the "internal pressure that never crosses into action"
     failure the critique correctly says we should test for.

So: the philosophy is sound, but the headline fix is **not** "make Orrin produce
more." It is **"instrument and protect the signal→action chain that already
exists."**

---

## 1. Claim-by-claim verification

### 1.1 "Every 25 cycles must produce an artifact" — NOT in the code

`grep` across `brain/` for any cycle-count → artifact obligation returns nothing.
There is no scheduler, no metacog rule, and no audit gate that demands output on a
cadence. The phrase originates as an *external diagnostic suggestion*, and the
source critique itself concedes this ("my … suggestion is not human-like. It is an
engineering diagnostic, not a cognitive model").

**Verdict: TRUE as a principle, but it corrects a proposal, not an Orrin behavior.**
Orrin is *not* currently punished by his own machinery for quiet stretches.

### 1.2 "The right test is signal → selection → behavior → future state" — ALREADY BUILT

`brain/cognition/behavioral_adaptation.py` closes exactly this loop. Called from
`metacog_flush()` immediately after `metacog_analyze()`, it classifies each
metacog observation and applies a targeted mutation to the selection context:

| Signal (metacog observation) | Corrective mutation | Effect on next selection |
|---|---|---|
| `rut` / `oscillation` | `_novelty_pressure += 0.25` | exploration fns scored higher |
| `goal_avoidance` | `_goal_pressure_amplified`, conditionally `_force_action_next` + `_suppress_goal_deliberation` | goal-pursuit fns boosted; reflection locked out |
| `reflection_imbalance` | `_force_action_next = True` | active fns prioritized |
| `emotional_stagnation` | `_novelty_pressure += 0.15` | novelty-seeking boosted |

The module's docstring cites the exact literature the critique appeals to —
Carver & Scheier's control-systems discrepancy→corrective-output, Bandura's
self-observation→self-reaction, Powers' perceptual control. It also already
records each rewrite as a before→after→because row in `behavior_changes.json`
(cap 250).

**Verdict: TRUE as the right standard — and the system was designed to that
standard, not to an artifact-cadence standard.**

### 1.3 "Orrin does reactive/regulatory actions but weakly demonstrates productive ones" — TRUE

Confirmed by `ORRIN_ACTIVITY_REPORT.md` (the 2026-06-14 run, ~700 cycles):
- **Regulatory/orienting present:** `attempt_regulation`, `dream_cycle`,
  `metacog_analyze`, novelty pressure rising after rut events.
- **Communicative present but inert:** 21 `express_state` entries, all unsolicited,
  *no human ever replied* (`chat_log.json` empty) — he was talking to no one.
- **Productive weak:** ~100 notes, but most near-duplicate
  (*"I'm feeling impasse_signal while working on…"*); no tool executions of
  consequence; no external artifact that changed the world.

**Verdict: TRUE.** Reactive/regulatory machinery is alive; productive output is
thin and largely redundant.

### 1.4 The proposed action-class taxonomy — DOES NOT EXIST as an audit lens

The critique proposes classifying every event into **reflex / regulatory /
orienting / communicative / productive / maintenance / failed-blocked**, then
asking whether the right class rises after each signal.

What actually exists in code is a *different* taxonomy, used for a *different*
purpose — score-boosting at **selection time**, not auditing after the fact:
- `brain/think/think_utils/select_function.py` defines outward-presence tiers:
  `_OUTWARD_HIGH` (`outward_artifact`: leave_note, write_tool, …),
  `_OUTWARD_MED` (`outward_explore`: look_outward, research_topic, …),
  `_OUTWARD_LOW` (`outward_sense`: survey_environment, check_user_presence, …).
- Stray `maintenance` and `reflex` tags appear in `setpoint_regulation.py` and
  `drive.py`, but there is no unified mapping and no post-hoc classifier.

Critically, **no instrument measures follow-through**: "signal X appeared → did
the matching action class increase in the next K cycles → did X subsequently
decrease?" `behavior_changes.json` records that a corrective was *armed*; nothing
records whether the next selection actually changed or whether the originating
signal relaxed.

**Verdict: this is the real observability gap.**

---

## 2. The real failure mode: a closed loop running open

The most important finding is not philosophical. In the logged run the chain in
§1.2 **fired and was then defeated**, every cycle, by two interacting systems:

1. **Survival preemption.** `brain/cognition/planning/pursue_goal.py`
   (`_survival_critical`) yields goal pursuit whenever `resource_deficit > 0.85`.
   In the run, `resource_deficit` was pinned at **0.95**, so pursuit of his
   central goal ("Write a structured account of what's stuck and why") yielded
   on essentially every cycle:
   > `[pursue_goal] survival preemption (resource_deficit>0.85) — yielding pursuit … (resumable).`

2. **Threat-driven retreat.** The action arbiter
   (`select_function.py`, `[action_arbiter] threat-vote → dream_cycle`) kept
   electing `dream_cycle` as a low-cost retreat under the 0.85 threat spike.

3. **A release valve that released nothing.** Those dream passes ran
   **LLM-free / symbolic-only** and mostly *"produced no insights (symbolic below
   threshold, LLM tool unavailable)."*

Net loop, per cycle:

```
impasse felt
  → goal_avoidance flagged → corrective chain ARMS action pressure   (§1.2 fires)
  → resource_deficit 0.95 > 0.85 → pursuit YIELDS                    (preempt wins)
  → threat 0.85 → action_arbiter votes dream_cycle                  (retreat wins)
  → dream produces nothing (no LLM)                                 (valve dead)
  → impasse unrelieved → next cycle identical
```

So the system *did* generate corrective output (the critique's "right test"
passed in spirit) but the output **never crossed into action** because two
higher-priority subsystems overrode it and the only escape hatch was inert. The
metacog log proves the agent *knew*: 212 consecutive cycles of "thinking but not
doing," correctly self-diagnosed, never escaped.

**This is the genuine, narrow, actionable issue** — and it is exactly the failure
the critique points at, stated mechanically: *internal pressure that does not
become outward behavior when the agent's own state says action is needed.*

---

## 3. Recommendations (ranked)

**R1 — Build the signal→action follow-through audit (closes §1.4).**
Add a post-hoc classifier that tags each executed function with an action class
(reflex / regulatory / orienting / communicative / productive / maintenance /
failed-blocked) and an audit that, for each signal (rut, goal_avoidance,
stagnation, threat, user-input, host-distress, uncertainty), measures over the
following K cycles:
- did the *expected* action class rise? (e.g. goal_avoidance → productive/goal-
  progress; rut → orienting/novelty; user-input → communicative)
- did the **originating signal subsequently fall**? (the relief test)

This is the difference between "the corrective was armed" and "the corrective
worked." It reuses the existing `outward_*` tag tiers as a starting partition and
extends `behavior_changes.json` with an `outcome` field (signal_delta over the
next K cycles).

**R2 — Detect and break "closed loop running open" (closes §2).**
When the corrective chain arms action pressure but a survival/threat preemption
overrides it for N consecutive cycles, that is a *distinct* state from healthy
regulation and should be surfaced and escalated (raise the preemption threshold
temporarily, force a minimal grounded action, or demand help) rather than left to
loop. The data to detect it already exists (`_force_action_next` armed +
`survival preemption` log + flat signal).

**R3 — Never ship a release valve that can't release.**
`dream_cycle` as the threat-retreat target must have a working low-cost effect
when the LLM tool is unavailable, or the arbiter must not route to it under
sustained impasse. A retreat that produces nothing is indistinguishable from
freezing.

**R4 — Do NOT add an artifact-cadence rule.**
Explicitly: the fix is not "force output every N cycles." That would re-introduce
the un-human-like standard §1.1 correctly rejects. Judge the chain, not the
cadence.

---

## 4. Bottom line

- The artifact-cadence critique is **right in principle but not describing an
  existing Orrin behavior** — no such rule is in the code.
- The proposed signal→action standard is **correct and already the design intent**
  (`behavioral_adaptation.py`).
- The **real issues are two and concrete**: (A) we cannot yet *audit* whether the
  signal→action chain follows through and relieves the signal, and (B) in the one
  logged long run, the chain fired but was *defeated* by survival/threat
  preemption with a dead release valve — a closed loop executing open.
- Fix those by **instrumenting and protecting the existing loop**, not by demanding
  scheduled artifacts.

---

## 5. Resolution (status) — ALL RECOMMENDATIONS ADDRESSED

- **R1 — signal→action follow-through audit: DONE 2026-06-28.**
  `brain/cognition/signal_action_audit.py` adds (1) `classify_action()` — the
  seven-class taxonomy (reflex/regulatory/orienting/communicative/productive/
  maintenance/failed-blocked), built on the existing `_OUTWARD_*` selection tiers;
  and (2) a deferred follow-through audit: when `behavioral_adaptation` arms a
  corrective it stamps an `_audit_id` + pending `outcome`, and K cycles later the
  audit writes back whether the **expected class rose** (vs the K cycles before)
  **and the originating signal fell** (the relief test) — i.e. *did it land?*, not
  *was it armed?*. Surfaced on the Learning page (`OutcomeRow` in `Learning.tsx`)
  and aggregable via `audit_summary()`. Tests: `tests/brain/test_signal_action_audit.py`.
- **R2 — break "closed loop running open": DONE 2026-06-28.**
  `goal_closure._closed_loop_break` (wired in `goal_execution.py`): a sustained
  armed-but-preempted streak forces one grounded pursuit (cooldown-bounded,
  `ORRIN_CLOSED_LOOP_BREAK`).
- **R3 — never ship a release valve that can't release: DONE 2026-06-28.**
  `consolidation_cycle._submit_retreat_discharge`: the threat-retreat now
  discharges the elevated threat/impasse that elected it.
- **R4 — do NOT add an artifact-cadence rule:** honoured — no cadence rule added.

This audit's actionable findings are fully discharged; archive when convenient.

---

*Code consulted: `brain/cognition/behavioral_adaptation.py`,
`brain/cognition/planning/pursue_goal.py` (`_survival_critical`),
`brain/think/think_utils/select_function.py` (outward tiers, action_arbiter
threat-vote), `brain/cognition/metacog.py`, `brain/embodiment/setpoint_regulation.py`,
`brain/motivation/drive.py`. Run evidence: `ORRIN_ACTIVITY_REPORT.md` (2026-06-14,
~700 cycles).*
