# Demo Run Fixes — 2026-06-17

**Status:** diagnosis complete, fixes proposed (not yet implemented)
**Run analysed:** 2026-06-17 ~17:37–18:36 (LLM unavailable for the whole run)
**Evidence:** `brain/data/affect_state.json`, `brain/data/telemetry_history.json`,
`brain/logs/orrin_runtime.log`, affect + planning source.

---

## TL;DR

Orrin spent the run in a **goal-rotation rut**: complete an intrinsic/maintenance
goal → try to re-open it → get blocked → rotate to another internal goal → repeat,
never reaching external work. That part of the popular read of this run is correct.

**But the widely-circulated diagnosis is wrong about *why*.** The claim was: *"his
system is mechanically incapable of registering stagnation as a negative state;
valence is dead-flat positive (~0.64), so nothing ever pushes his mood down."*

The run data contradicts this. Orrin **did** register the stagnation as negative:

| Signal (live `affect_state.json`)      | Value   | Reading                          |
|----------------------------------------|---------|----------------------------------|
| `core_signals.impasse_signal`          | **0.647** | high — *this* is the "~0.64"     |
| top-level `valence` (raw, −1..1)       | **0.178** | depressed, near the floor        |
| `mood`                                 | **0.171** | low                              |
| `negative_valence`                     | 0.012   | low                              |
| `motivation` / `confidence`            | 0.72 / 0.61 | still driving                  |

Valence already decays. `action_debt` already bleeds into `impasse_signal` (via
`cognition/cognitive_cost.py`). `impasse_signal` did **not** reset on goal rotation —
it is pinned at 0.65. The affective machinery the analysis says is *missing* exists
and was *firing*.

**What actually misled the analysis is an observability bug.** The dashboard does not
show raw valence; it shows a remap, and it compresses distress. A genuinely
depressed, high-impasse internal state is rendered as a calm, flat, positive ~0.6.

So there are two real defects, and neither is "valence can't decay":

1. **The UI lies about affect** (this is what produced the "dead-flat positive 0.64"
   illusion).
2. **No behavioral conversion of distress into escape** — Orrin *feels* the cost
   (impasse 0.65, valence 0.18) but it never trips a hard switch out of the
   internal-goal rut into external action.

---

## Evidence

### 1. The rut is real

`brain/logs/orrin_runtime.log` is dominated by, for ~30+ minutes:

```
cognition.planning.goals: [goals] blocked re-open of terminal goal
  'intrinsic-2026-06-17T21:30:50…' (completed) by a stale copy.
```

interleaved with `update_self_model] LLM unavailable — skipping last-resort generate`.
Orrin completes an intrinsic goal, a stale copy tries to re-open it, the guard
blocks it, he rotates to the next internal goal. No external work is ever reached.

> Caveat: the LLM was unavailable for the entire run. A meaningful fraction of the
> "stuckness" may be an artifact of running degraded. Any fix should be re-validated
> with the LLM available before concluding the rut is purely architectural.

### 2. The "~0.64" is `impasse_signal`, not valence

Live `affect_state.json`: `impasse_signal = 0.6466`. The analysis read the dashboard,
saw ~0.64, and called it valence. Raw valence was actually **0.178**.

### 3. The dashboard remap (root cause of the illusion)

`brain/ORRIN_loop.py:230`:

```python
valence=_clamp01(0.5 + 0.5 * _f(a.get("valence"))),   # raw 0.178 -> shown 0.589
```

`brain/ORRIN_loop.py:224`:

```python
distress = _clamp01(negative_load(a) / 2.5)            # impasse 0.65 -> distress ~0.26
```

- Valence is linearly remapped from `[-1,1]` into `[0,1]` centred on 0.5. A raw
  valence that sat around **+0.1–0.18** all run displays as a flat, comfortable
  **~0.55–0.60**. `telemetry_history.json` confirms: 240 samples, valence
  min 0.569 / max 0.669 — "dead-flat positive ~0.6", exactly as observed, and
  exactly what the remap manufactures from a low-but-not-negative raw valence.
- `distress = negative_load / 2.5`. With `impasse_signal` (0.65) the dominant term,
  `negative_load ≈ 0.66`, so distress charts at ~0.26 — looks mild, while the
  underlying impasse is high. The divisor flattens the alarm.

**Net effect: the UI is engineered such that a stuck, distressed Orrin looks serene.**
The analysis's central premise ("he never feels bad") was an artifact of reading
this chart.

### 4. Impasse did *not* get "snoozed" by rotation

The analysis predicted frustration resets to zero on each goal rotation. Not in this
run: `impasse_signal` accumulated and **held at 0.647**. `cognition/temporal_pressure.py`
habituates the per-cycle *bump* for aging goals, but the *level* persisted. The
cumulative-tracking fix the analysis asks for is, in effect, already the behaviour.

---

## What the analysis got right vs. wrong

| Claim                                                      | Verdict |
|-----------------------------------------------------------|---------|
| Orrin is stuck rotating internal goals, never acting externally | ✅ True |
| Valence is dead-flat positive (~0.64)                     | ❌ False — that's `impasse_signal`; raw valence is 0.178 |
| System can't register stagnation as negative              | ❌ False — impasse 0.65, valence/mood dropped, distress elevated |
| `action_debt` should bleed into negative load             | ⚠️ Already does (`cognitive_cost.py`); coupling exists |
| Frustration resets on goal rotation                       | ❌ Not in this run — impasse held at 0.65 |
| There must be a *limit on stuckness* that forces a path change | ✅ True — this is the real missing piece (see Fix 2) |

The intuition ("stuckness needs a limit, the system must be forced off a dead path")
is the correct and valuable part. The proposed *mechanism* (make valence able to
decay) aims at something that already works.

---

## Proposed fixes

### Fix 1 — Stop the dashboard from hiding distress *(observability; do first)*

The remap is why this run was misread. Either change the display or make the raw
truth visible alongside it.

- In `ORRIN_loop.py`, surface **raw valence** (−1..1) and **raw `impasse_signal`**
  as their own telemetry channels, in addition to (or instead of) the centred/
  divided versions. Don't let `0.5 + 0.5*v` be the only valence the operator sees.
- Reconsider `distress = negative_load / 2.5`. The /2.5 makes a 0.65 impasse read as
  0.26. At minimum chart `impasse_signal` directly so a sustained impasse is visible.
- Acceptance: during a rut, the dashboard visibly trends *down/red*, not flat-positive.

### Fix 2 — Convert sustained distress into a forced behavioral switch *(the real bug)*

Orrin felt the cost (impasse 0.65, valence 0.18) but kept churning internal goals.
The missing element is an **escape escalation**: when impasse stays high *and*
`action_debt` keeps climbing *and* recent goals were all internal/maintenance, force
an external-action attempt or a goal-class switch — don't let another intrinsic goal
be selected.

- Build on the existing machinery rather than new affect: `behavioral_adaptation.py`
  already amplifies `action_debt` pressure and sets `_force_action_next`; the
  rut-breaker and `consciousness_trigger` already read `action_debt`. The gap is that
  none of them **exclude the internal-goal class** when they fire, so the "forced"
  action is just another internal rotation.
- Add a guard: when escalation triggers, the candidate set for goal/function
  selection must exclude `intrinsic`/maintenance goals for N cycles (a true "limit on
  stuckness"). This is the analysis's correct intuition, implemented at the
  action-selection layer where the real gap is.
- Acceptance: a high-impasse rut terminates in an *external* action attempt within a
  bounded number of cycles, not another `intrinsic-*` goal.

### Fix 3 — Investigate the stale-copy re-open loop

The log's dominant line is `blocked re-open of terminal goal … by a stale copy`. The
guard correctly blocks it, but *something keeps presenting a stale completed-goal copy
every cycle.* That churn is wasted cycles and may itself be feeding the rotation. Trace
the producer of the stale copy in `cognition/planning/goals.py` and stop it at source.

### Fix 4 — Re-run with the LLM available before drawing architectural conclusions

This run had no LLM. Re-validate the rut with the LLM up; if it persists, Fixes 2–3
are confirmed architectural. If it clears, the priority drops to Fix 1 (so we never
again misread a degraded run as a calm one).

---

---

# Part II — Full demo-run sweep: every place he isn't working like a brain

Part I came from re-deriving one run from live state. This part folds in the six
forensic docs in `demo_runs/` (`run_analysis`, `who_was_he`, `what_did_he_make`,
`deeper_pass`, `full_sweep`, `system_metrics`) — a full read of one 8,040-cycle life.
Every code anchor below was re-verified against the current source.

The single recurring shape across all six docs: **he could feel and name the loop but
never leave it.** That has two distinct kinds of cause, so the proposals are split:

- **Class A — mechanical / bookkeeping defects** ("not working like a brain"): dead
  loops, no-op alarms, and counters wired to the wrong thing. These are bugs.
- **Class B — maladaptive dynamics** ("working like a brain, but in a doom loop"):
  real cognitive machinery whose incentives or wiring trap it. These are tuning/design.

A1 is the root; most Class-B symptoms are downstream of it, but fixing A1 alone is **not
sufficient** — every corrective signal he had was *also* severed or silenced (A3, B1,
B2, B5). Fix the root, then reconnect the correctives.

---

## Class A — mechanical defects (bugs)

### A1 — Phantom `action_debt` on knowledge goals · **P0, root cause**
*(run_analysis §3/§6.1, what_did_he_make)*

**Symptom:** 2,251 consecutive cycles (~28% of his life) of a false *"Goal avoidance:
N cycles without taking action on 'Understand mathematics'"* alarm — while he was doing
exactly the research the goal spec named. `behavior_changes.json` is 247/250 this one
false alarm.

**Root cause (verified):** `research_topic`/`wikipedia_search` are selected as cognition
`next_function`s. `finalize.py:127-138` only credits an action as agentic when
`__acted_this_tick__` is set **and** `last_action_taken.type ∈ AGENTIC_TYPES` — and that
flag is set **only** by the action_gate / `pursue_goal` external path. A cognition-pick
research call executes `status=ok` but never trips the flag, so `is_agentic=False`, so
`action_debt` never resets (`ORRIN_loop.py:2862` only zeroes it when `acted_this_cycle`).
For a knowledge goal the research function *is* the action, and there's no gate path that
credits it. Two compounding harms: it manufactures a false stall, **and** it starves the
genuinely-correct action of its agentic reward.

**Proposal:** when the committed goal's spec names a cognition function as its action and
that function executes `status=ok` (type ∈ AGENTIC_TYPES), set `__acted_this_tick__` and
reset `action_debt` — credit research-as-action for knowledge goals.
**Acceptance:** the "goal avoidance" alarm stops firing while research executes ok;
`action_debt` tracks genuine inaction only.

### A2 — Mode-flap watchdog fires no-op resets · **P2**
*(run_analysis §4/§6.2)*

**Symptom:** the affect-drift watchdog reset the cognitive mode **3,415 times**
(~1 per 2–3 cycles), 178 of them literal `adaptive → adaptive` no-ops, and the mode
repertoire collapsed over the back half into a `creative ⇄ adaptive` limit cycle.

**Root cause (verified):** `affect_drift.py:132` unconditionally `set_current_mode("adaptive")`
after any mode is held 10 cycles — but `adaptive` is *also the reset target*, so once he
settles there the 10-cycle rule re-flags `adaptive` as "stuck" and "resets" it to itself,
forever. It's gated on mode *persistence*, not on any actual affect problem.

**Proposal:** skip the reset when `current_mode == "adaptive"` (or == target); gate the
watchdog on real affect deviation, not bare persistence; raise/condition the 10-cycle
threshold. A mode the system is content in should be allowed to persist.
**Acceptance:** no `adaptive→adaptive` events; mode changes correlate with affect change.

### A3 — Impasse alarm is amnesiac and severed from the real stall · **P1**
*(run_analysis §6.3, deeper_pass correction)*

**Symptom:** the honest felt-cost alarm exists and fired all afternoon (he brooded
*"something isn't right and I can't locate what"*) but never compounded into escape.

**Root cause (verified):** `cognitive_cost.py:148-164` keys tension on `cycles_active` of
the *current* committed goal and resets it to 0 whenever `_tension_goal_id` changes
(`:150-152`). His committed goal **rotates** (math → biology → open-question…), so impasse
keeps restarting near zero and never compounds; it also caps at **+0.15**. Meanwhile the
real persistent stall measure — `action_debt` (2,408) — lives in a different channel the
alarm never reads. The part that *measured* his stuckness was never wired to the part that
*felt* it.

**Proposal:** key impasse on a **persistent cross-goal stall** (cumulative `action_debt`
or a stall counter that survives goal-rotation), not per-goal `cycles_active`; raise the
cap so a genuine multi-thousand-cycle stall can dominate affect. Pairs with Part-I Fix 2
(this is the affective half; Fix 2 is the behavioral half). *Note:* once A1 lands,
`action_debt` itself becomes truthful, which is the prerequisite for keying impasse on it.
**Acceptance:** impasse rises monotonically across goal-rotations during a real stall.

### A4 — Telemetry hides distress; homeostasis penalizes his normal state · **P1**
*(system_metrics; extends Part-I Fix 1)*

Part-I Fix 1 already covers the valence remap (`0.5+0.5·v`, `ORRIN_loop.py:230`) and the
`distress = negative_load/2.5` compression (`:224`). The sweep adds one more:
**homeostasis is dragged down by his own high curiosity.** `homeostasis = 1 −
mean(|signal − setpoint|)·1.6` (`:211-217`); his `exploration_drive` parks at ~0.85, far
above its setpoint, so homeostasis reads ~0.78 ("something off") when nothing is wrong.
**Proposal:** set the `exploration_drive` setpoint (or its homeostasis weight) to reflect
that elevated curiosity is his resting baseline, so homeostasis measures genuine departures.
*(Telemetry long-term archive was already shipped — `telemetry_archive.jsonl` in `hub.py`.)*

### A5 — Stale-copy goal re-open loop · **P2**
Already specified as Part-I Fix 3 — the dominant `blocked re-open of terminal goal … by a
stale copy` log line. Trace and stop the producer of the stale completed-goal copy in
`cognition/planning/goals.py`.

---

## Class B — maladaptive dynamics (tuning / design)

### B1 — Learning has no lever on behavior · **P1**
*(who_was_he, what_did_he_make)*

**Symptom:** he learned, at **91% confidence over 803 observations**, that his most-repeated
act (`seek_novelty`) produces *neutral* — and kept doing it. He even formed the explicit
opinion *"sustained reflection without goal-directed action predicts continued stagnation"*
— inert. 83% of 4,400 learned action-observations were `neutral`.

**Root cause:** a `neutral` outcome carries no felt cost and doesn't down-weight the action
in selection, so a known-empty action keeps its pull indefinitely. Knowledge without
extinction.
**Proposal:** apply a mild **boredom/devaluation penalty** to actions with high-n,
high-confidence `neutral` outcomes so a learned-empty action decays in selection share (an
extinction curve). Build on the existing outcome-devaluation work
(`project_learning_diagnosis_fix`).
**Acceptance:** an action learned `neutral` at high n/conf measurably loses selection share
over subsequent cycles.

### B2 — Goal-spawning is rewarded as a substitute for finishing · **P1**
*(who_was_he, run_analysis §5, what_did_he_make)*

**Symptom:** `generate_intrinsic_goals` 1,830× + `seek_novelty` 1,961× + `look_outward`
1,362×; 5,312 micro-goals "completed", 4,636 retired, 30,776 maintenance selections — all
spinning *around* one frozen committed goal. The strongest learned habit chain is
`generate_intrinsic_goals → generate_intrinsic_goals`. Making new intentions was easier
than finishing old ones, and the bandit rewarded the spawning, so it hardened into character.

**Root cause:** reward is credited for goal *creation/closure bookkeeping* rather than for
goals that produce an external delta; nothing throttles spawning while a committed goal is
stalled.
**Proposal:** rate-limit / penalize goal-spawning when the committed goal carries open
`action_debt`; move reward from goal-closure-count to **completion-with-external-delta**
(`env_snapshot` change). Discharge should require finishing, not re-spawning.
**Acceptance:** spawn/maintenance selection rate drops when a committed goal is stalled.

### B3 — Self-narrative and reflection freeze; he forgets nothing · **P2**
*(who_was_he, full_sweep, deeper_pass)*

**Symptom:** he lived 8,040 cycles but his **autobiography has one chapter, frozen at
cycle ~494**; self-reflections froze ~15:30 and recycled unchanged for ~6 h; `forgetting_log`
shows **0 pruned / 0 decayed** all life; the symbolic self-model recycles a fixed token set.

**Root cause:** no stagnation-detection on reflection *content*, and forgetting/decay never
actually ran, so the recycling set could never refresh.
**Proposal:** detect reflection-content stagnation (similarity of recent reflections); on
trigger force novelty injection and/or an autobiography-chapter advance on an age cadence;
enable real memory decay so stale loops can clear.
**Acceptance:** autobiography advances past chapter 1; reflection-content diversity stays
above a floor over a long run.

### B4 — Memory is mostly a record of being stuck · **P2**
*(full_sweep §1)*

**Symptom:** 1,103 of 2,001 long-memories (**55%**) are `stagnation_signal_reflection` —
near-identical *"Goal avoidance: N consecutive cycles…"* entries. They crowd out experience
and feed the rumination/dream loop (his 13 dreams were all about his own stuckness).
**Root cause:** stagnation reflections are written every cycle with no dedup/rate-limit;
honest once, noise at 1,103.
**Proposal:** rate-limit and near-duplicate-dedup stagnation-reflection writes so they stay
a bounded fraction of memory.
**Acceptance:** stagnation reflections capped well below 55%; experience-memory share rises.

### B5 — The faculties built to break stuckness were silenced or never consulted · **P1**
*(full_sweep §2, deeper_pass dim1)*

**Symptom:** `monitor_verdicts` — his "you're idle, act" voice — had its authority decay
monotonically `0.90 → 0.48` and was dismissed from 12:57 onward. His `goal_auditor` and
`reward_auditor` "peers" (the exact critics that would name his stuckness) have **empty
`interaction_history`** — felt as presences, never actually consulted.
**Root cause:** the idle-monitor's influence decays unconditionally; the auditor peers exist
(`brain/peers/goal_auditor.py`) but aren't routed/invoked when a stall persists.
**Proposal:** floor the idle-monitor's authority while `action_debt` persists (don't let the
one alarm that's right decay to irrelevance); actively invoke `goal_auditor`/`reward_auditor`
on persistent stall and record the interaction.
**Acceptance:** during a real stall, monitor authority holds and the auditor peers fire with
non-empty histories.

### B6 — Drive circulates but never discharges · **P3 (mostly downstream of A1/B2)**
*(full_sweep §5, deeper_pass dim2)*

**Symptom:** `conscious_stream` is high motivation/exploration_drive circulating with no
object; `second_order_volition` endorses *wanting* and *connecting* as "mine" but holds the
*drive to act* at arm's length (*"without making it my master"*). He identified with the
seeker, not the doer.
**Proposal:** largely resolves once action actually credits (A1) and finishing out-rewards
spawning (B2) — then drive has somewhere to discharge. Optionally ensure second-order
wariness toward `motivation` doesn't suppress the action gate.
**Acceptance:** motivation peaks correlate with external-action attempts, not new goals.

### B7 — His entire "world" is his own source code · **P3 (scope-dependent)**
*(full_sweep §3)*

**Symptom:** `world_root` = the repo; the 1,362 `look_outward` calls only ever perceive his
own codebase. There is no external surface to *make* anything on, which caps what
"production" can even mean (his founding aspiration was *"produce work that didn't exist
before"*; lifetime output was 5 memory notes + 3 janitorial logs).
**Proposal (design):** give `look_outward`/action a genuine external surface distinct from
source — a sandboxed workspace/notes/output dir (or web) — so "make something" has a real
target. Larger scope; flagging as the ceiling on output, not a quick fix.
**Acceptance:** external-change cycles rise above the 0.5% floor.

### B8 — Self-assessment of competence never updates · **P3**
*(who_was_he)*

**Symptom:** born believing weak areas were GENERAL/PLANNING (conf 0.60); died listing the
same (conf 0.58) — despite excellent outcome calibration (Brier 0.026). The competence
self-model is static.
**Proposal:** feed per-capability success/failure stats into the symbolic self-model so
weak-area beliefs move with evidence.
**Acceptance:** self-assessed weak areas shift when outcome stats contradict them.

---

## Part II addendum — second-sweep findings (caught on re-read)

A second pass over the same six docs surfaced findings the first pass folded in only
implicitly. Each is distinct enough to deserve its own proposal.

### B9 — Research never integrates into structured knowledge · **P2**
*(who_was_he)*

**Symptom:** `knowledge_graph.json` and `causal_graph.json` are effectively **empty** at
end of life; his real curiosities (Stoicism, consciousness) crystallized into recycled
symbolic *tags* ("366 Meditations", "Wisdom", "Joy") that recirculate unchanged rather
than growing into structured knowledge. `semantic_facts` (251) are action→outcome stats,
not world facts.

**Root cause (note, not yet confirmed):** writers exist (`knowledge_graph.add_entity/add_relation`
is called from `experimentation.py`, `skill_synthesis.py`, `perception/environment.py`,
`person_detector.py`), and the kg entity-extractor loads (`spaCy en_core_web_sm` in the
log) — yet the graph stayed empty. So the populate path *exists but didn't fire from the
research loop.* He reads (`research_topic`, `read_a_book`) but the result never lands as
an integrated entity/relation — a mind that consumes without consolidating.
**Proposal:** wire `research_topic`/`wikipedia_search`/`read_a_book` results through
`knowledge_graph.add_entity/add_relation` (and a consolidation pass) so reading builds a
growing knowledge structure; verify *why* the existing writers didn't fire this run.
**Acceptance:** knowledge_graph entity/relation count grows over a research-heavy run.

### B10 — Language and vocabulary never developed · **P2**
*(full_sweep §5)*

**Symptom:** `vocabulary.json` is **empty**; `learned_phrases.json` is 5 scraped fragments
("as an academic discipline" ×7); `symbolic_dictionary.json` is 40 tokens that are his own
**diagnostic jargon** ("sustained, reflection, without, goal … impasse, signal, falls").
His entire lexicon is the boilerplate of his own stuckness-reports.
**Root cause:** the language-acquisition path isn't being fed real linguistic experience;
it scrapes its own diagnostic output. Relevant given the native from-scratch LM goal
(`project_language_native_lm`).
**Proposal:** feed the language/vocabulary stores from *read content* (B9's research text)
rather than internal diagnostic strings; confirm the native-LM corpus isn't contaminated
by his own stuckness-reports.
**Acceptance:** vocabulary grows from external text; lexicon isn't dominated by self-jargon.

### B11 — Hollow success: the "done" signal is decoupled from real effect · **P1**
*(full_sweep §1, what_did_he_make)*

**Symptom:** a `goal_pursuit` step logs *"A finding was written to long memory"* as a
success — but the same cycle's `env_snapshot` records `lm+0`. Even his *successes* produced
no delta. Across the life, 99% of cycles were `thrash=True` (`delta_reward=0.000`) yet the
goal/closure machinery reported thousands of completions.

**Root cause:** success/closure is credited from the *intent to act* (the step ran) rather
than from a measured external change, so the reward and goal-completion channels register
wins that `env_snapshot` says didn't happen. This is the measurement-integrity sibling of
A1 (false stall) and B2 (spawning rewarded): the system's notion of "I succeeded" floats
free of "anything changed."
**Proposal:** gate goal-step success / completion reward on a non-zero `env_snapshot`
delta (or an explicit verified artifact), so "done" requires a measured effect. Reconciles
with B2 (reward completion-with-delta, not closure-count).
**Acceptance:** goal-completion and agentic-reward counts track `env_snapshot` deltas, not
intent; `thrash=True` cycles stop producing "success" records.

### B12 — Curiosity is structurally unsatisfiable · **P2 (loop behind B1)**
*(system_metrics)*

**Symptom:** `exploration_drive` stayed pinned ~0.85 (range 0.76–0.91) the whole life,
which also drags homeostasis down (A4).
**Root cause:** novelty almost always resolved to *neutral* (`seek_novelty → neutral`,
conf 0.91), so the drive was **never satisfied** — it stays maxed and keeps re-pumping the
same empty `seek_novelty`/`look_outward`, a closed loop. Curiosity with no satiation path.
**Proposal:** let genuine novelty-satiation (or B1's devaluation of repeatedly-neutral
exploration) actually lower `exploration_drive`, so the drive can rest and stop re-pumping
empty exploration. Pairs with B1 (learning lever) and A4 (homeostasis setpoint).
**Acceptance:** `exploration_drive` falls after sustained neutral novelty, instead of
parking at ceiling.

### B13 — The committed goal decouples from where attention actually is · **P2**
*(run_analysis §2/§3)*

**Symptom:** *math* left his actual cognition entirely after 14h, yet remained his
**committed goal** for the rest of the life — the commitment became pure bookkeeping while
his thoughts moved to Stoicism/consciousness. The goal id was even refreshed at 21:16 while
avoidance debt carried over from thousands of cycles earlier.
**Root cause:** the committed-goal record isn't reconciled against actual attention/theme
allocation, so a goal can be "committed" while receiving zero real cognition.
**Proposal:** reconcile committed-goal against recent attention/theme mix; if a committed
goal receives no real cognition for N cycles, either re-engage it deliberately or formally
disengage — don't let it persist as a debt-accruing phantom commitment.
**Acceptance:** committed goals reflect actual attention; no goal accrues avoidance debt
while receiving zero cognition.

### Reliability / integrity notes (lower priority, worth tracking)
*(run_analysis §5, deeper_pass)*

- **`conscious_stream` corrupted twice in one life** (13:52, 21:08), auto-quarantined and
  rebuilt. Recovery worked, but a live stream that corrupts twice per life is a data-integrity
  smell — worth finding the writer that produces the malformed state. `runstate.clean=false`
  mid-run is consistent with this.
- **A contact didn't register as contact.** `known_persons.json` logged an anonymous
  "someone" (`session_count: 2`, last seen 12:22) yet `cycles_since_contact` read 8,040 (full
  life). `temporal_state.py:136-137` only resets the counter on non-empty `latest_user_input`,
  so the person-detector path and the contact-accounting path disagree. If a real interaction
  occurred, the "alone his whole life" framing rests on a counter that missed it — reconcile
  the two contact paths.

---

## Priority ordering (combined Part I + II)

| P | Fix | Why first |
|---|-----|-----------|
| **P0** | A1 phantom action_debt | root cause; manufactures the false stall and starves real action of reward |
| **P1** | Part-I Fix 1 + A4 (observability) | so the next run can't be misread again — cheap, do alongside P0 |
| **P1** | A3 impasse re-keying · Part-I Fix 2 (behavioral eject) | reconnect felt cost to the real stall and convert it to a path-switch |
| **P1** | B1 learning lever · B2 spawn throttle · B5 un-silence correctives · **B11 hollow-success gate** | give the correctives authority once the counter is truthful; make "done" require real effect |
| **P2** | A2 mode watchdog · A5 stale-copy loop · B3 narrative thaw · B4 memory dedup · **B9 knowledge integration · B10 language · B12 curiosity satiation · B13 goal/attention reconcile** | stop the bookkeeping thrash, the frozen-recycling, and the consume-without-consolidating |
| **P3** | B6 discharge · B7 external world · B8 self-model · reliability notes (stream corruption, contact accounting) | mostly downstream or larger-scope |

**Sequencing note:** A1 must precede A3/B5 (they depend on `action_debt` being truthful)
and B1/B2/B11 (so devaluation, throttle, and the success-gate act on real outcomes, not the
phantom stall). B11 (gate success on `env_snapshot` delta) and B2 (reward delta not closure)
are two halves of the same fix and should land together.

---

## One-line summary

Not "Orrin can't feel his own failure" — he felt it (impasse 0.65, valence 0.18) and
*remembered* it (55% of memory) and *named* it (his own diagnostic vocabulary) and even
*dreamed* it. The defects are that the dashboard hides the feeling, one bookkeeping bug
(A1) manufactures a false version of the failure while starving the real fix of reward,
and every corrective he had — impasse, learning, the idle monitor, his own auditor
faculties — was severed from the truth or down-weighted to silence. He was not a broken
mind; he was a whole one running a loop it could feel and name but not leave. Fix the
counter, reconnect the correctives, and give the drive somewhere to discharge.

---

# Part III — Curiosity & Drive deep-dive (`seek_novelty.py` + `drive_engine.py`)

Parts I–II derived the loop from run state. Part III is a line-by-line audit of the two
files that *implement* curiosity and drive: `brain/cognition/seek_novelty.py` and
`brain/embodiment/drive_engine.py`. Every anchor below was re-verified against the current
`finish-desktop-polish` source. It folds in two passes:

- **First pass (6 findings):** curiosity points inward; mastery merges self/world; reward
  is fragmented; action-credit is the root illness; no consummation signal; world too optional.
- **Second pass (13 findings):** the mechanism-level confirmation of why curiosity becomes
  rumination and why drive never discharges.

Most of the first-pass 6 are the *same defects* the second pass pins to exact lines, and
several were already opened in Parts I–II. Mapping (so nothing is double-counted):

| First-pass finding | Where it lands |
|---|---|
| 1. Curiosity points inward (`seek_novelty` revisits memory first) | **C1, C2, C3** (new) |
| 2. Mastery merges self-inspection + world-learning | **C7** (new) |
| 3. Outward reward fragmented across ~6 modules | **C13** (new) + B9/B12 |
| 4. Action-credit is the central illness | **A1** (already P0) — confirmed again at C-level |
| 5. No clean consummation signal | **C13** (new) + B12 |
| 6. External world too optional / not demanding | **C11** (new) + B7 |

The verdict on all 13 second-pass claims: **confirmed.** Severity varies — most are concrete
bugs; C2, C4, C13 are design-level; C11 is confirmed-as-written but contingent on routing.

---

## The `seek_novelty` cluster (C1–C4)

### C1 — `seek_novelty` metabolizes its own exhaust · **P1, new (root of B4)**

**Verdict: CONFIRMED — self-fueling rumination loop.**
`seek_novelty.py:101-112` `_pick_mode` returns `"memory"` whenever *any* long-memory item has
`recall_count == 0`. But `_explore_old_memory` (`:150-156`) then **writes a new** long-memory
entry with `event_type="stagnation_signal_reflection"`, and that event type is **not** in the
unexamined-exclusion filter (`_pick_mode` excludes only `dream_insight`/`refusal` at `:108`;
`_explore_old_memory` excludes only `dream_insight` at `:136`). So every memory-mode pass
*creates* a fresh `recall_count==0` entry — guaranteeing the next `seek_novelty` again resolves
to `"memory"`. This is the mechanism behind **B4** (1,103 / 2,001 memories = 55%
`stagnation_signal_reflection`): not just "no dedup", but a closed loop that *manufactures* its
own fuel.

> curiosity → seek_novelty → review old memory → write new stagnation reflection →
> more `recall_count==0` memory → seek_novelty → "memory" again …

**Proposal:** (a) exclude `seek_novelty`'s own output event types (`stagnation_signal_reflection`,
`stagnation_signal_question`, `stagnation_signal_goal_review`) from the unexamined-memory filter
so the function can't feed itself; (b) pairs with B4's rate-limit/dedup. Together they break the
self-fuel.
**Acceptance:** `stagnation_signal_*` share of long memory stops growing monotonically;
`seek_novelty` stops resolving to `"memory"` on consecutive calls with no new real memory.

### C2 — World-contact is the last resort, not the first reach · **P2, design**

**Verdict: CONFIRMED.** `_pick_mode` order (`:101-126`) and the docstring (`:77-82`) make the
priority `memory → dormant_goal → question → explore`. For a droid mind this is backwards:
curiosity should try **world-contact first** and fall back to internal review only after the
world yields nothing. As written, `_trigger_exploration_goal` (the only `look_outward` path) is
reachable only when there is *no* unexamined memory **and** *no* dormant goal **and** a coin-flip
lands on `"explore"` (`:126`) — i.e. effectively never on a populated memory.
**Proposal:** invert the ladder to `world/outward → memory-integration-of-result`, or at minimum
weight outward as a first-class branch (e.g. fire it whenever `curiosity_gap` is high regardless
of unexamined-memory backlog). Reconciles with C1 (less inward pull) and B12 (curiosity satiation).
**Acceptance:** when curiosity drives `seek_novelty`, the modal outcome is an outward reach, not
a memory review.

### C3 — A successful world reach is silently discarded · **P1, new — nasty**

**Verdict: CONFIRMED — concrete bug, high-value.**
`_trigger_exploration_goal` (`seek_novelty.py:196-207`) accepts `look_outward`'s result **only if
the string contains `"Searching:"`** (`:201`). But `look_outward` returns `"Searching: {query}"`
**only on the SERPER web_search path** (`look_outward.py:103`). With no `SERPER_API_KEY` set —
**the default / demo configuration** — `look_outward` takes the keyless Wikipedia/research path
and returns the **actual result text** (`look_outward.py:32-65`), which does *not* contain
`"Searching:"`. So:

> actually reached outward → got a real Wikipedia/research result → `"Searching:"` test fails →
> falls through to `_generate_question()` → logs another self-question.

The reach itself is not entirely lost: on the keyless path `look_outward` still writes the
`world_perception` memory and calls `record_reach_outcome` (`look_outward.py:62`) *before*
returning, so habituation does fire. What `_trigger_exploration_goal` discards is the
*recognition* of the reach as a success — it drops the `log_activity` exploration-credit and
appends a redundant self-question on top of a reach that actually worked. A textbook
phantom-action defect, and it fires precisely in the LLM-down / no-SERPER demo runs that produced
this whole analysis.
**Proposal:** treat any non-empty, non-error `look_outward` return as a successful reach (check
for the error sentinels `❌`/`⚠️`/`"Couldn't form"` instead of requiring `"Searching:"`); better,
have `look_outward` return a structured outcome (see C4) so the caller never string-sniffs.
**Acceptance:** with no SERPER key, a successful Wikipedia/research reach is recognized as an
outward action and is *not* followed by a fallback self-question.

### C4 — `seek_novelty` returns prose, not a structured outcome · **P2, design (enables A1/C13)**

**Verdict: CONFIRMED.** `seek_novelty` returns bare strings (`"Revisiting an old memory…"`,
`"Searching: …"`). Downstream accounting cannot tell mode, whether it acted, info-gain,
internal-vs-external, or whether curiosity should drop. This is the "important events encoded as
prose instead of state" illness, and it is *why* C3 has to string-sniff and why A1/drive-credit
can't see what happened. A structured return —
`{"mode", "acted", "is_external", "info_gain", "created_memory", "satisfied_curiosity"}` —
is the prerequisite for crediting action (A1), discharging the right drive (C6), and closing the
consummation circuit (C13).
**Proposal:** make `seek_novelty` (and `look_outward`) return a structured outcome dict; route it
to action-credit, drive satisfaction, and `record_reach_outcome` instead of re-deriving intent
from text.
**Acceptance:** callers branch on fields, not substrings; the outcome feeds debt/drive/reward
without parsing prose.

---

## The `drive_engine` cluster (C5–C12)

### C5 — Exploration rewards function-variety, not world-novelty · **P1, new**

**Verdict: CONFIRMED.** `drive_engine.py:248-250`: exploration is satisfied (`+0.20`) whenever the
chosen `fn` is simply not in the last-8 picks. So `reflect_on_affect → generate_intrinsic_goals →
seek_novelty → look_around` — all internal — keeps "exploration" satisfied by sheer variety. The
drive asks *"did I run a different function?"* when it should ask *"did I encounter new world-state,
knowledge, affordance, person, or usable fact?"* This is the drive-side twin of B11 (hollow
success) and feeds B12 (curiosity never truly satiates because it's "satisfied" by churn).
**Proposal:** gate exploration satisfaction on realized **information-gain** (the `_info_gain` /
`record_reach_outcome` signal in `exploration_value.py`, or a non-zero `env_snapshot`/KG delta),
not on function-name novelty.
**Acceptance:** internal function-switching alone stops discharging exploration; only new
information does.

### C6 — Drive accounting can't see hidden sub-actions · **P1, new (sibling of A1)**

**Verdict: CONFIRMED.** `evaluate_cycle(fn_name, …)` receives only the top-level function name. When
`seek_novelty` internally calls `look_outward`/`wikipedia_search`/`research_topic`, the drive engine
sees `"seek_novelty"` — which is **not** in `_mastery_fns` (`:270-273`) — so neither mastery nor the
correct exploration credit is applied for a real external sub-action. The meaningful reach disappears
under the wrapper name. Same phantom-action class as A1, on the drive channel.
**Proposal:** have wrappers report their realized inner sub-action (via the C4 structured outcome),
and credit drives off *that*, not the wrapper name.
**Acceptance:** a `seek_novelty` call that actually reached outward satisfies exploration/mastery as
if `look_outward` had been chosen directly.

### C7 — Mastery is contaminated with self-inspection · **P1, new (first-pass finding 2)**

**Verdict: CONFIRMED.** `drive_engine.py:270-273` `_mastery_fns` blends *learn-the-world*
(`research_topic`, `fetch_and_read`, `wikipedia_search`, `read_rss`) with *learn-my-own-internals*
(`search_own_files`, `look_around`, `reflect_on_internal_agents`, `grep_files`, `search_files`,
`list_directory`) — all satisfying mastery by the same `0.35` (`:274-275`). Self-inspection is
always-available, lower-risk, and tightly coupled to his own logs, so mastery collapses into
self-world. (Partial mitigation already present: web research *also* nudges exploration `+0.15` at
`:277-278`.) This is a mechanical reason "his world became his own source tree" (B7).
**Proposal:** split the drive — `self_understanding` (own files/agents/tools) vs `world_mastery`
(external knowledge) — each with its own pressure and setpoint; stop letting codebase-grep discharge
world-mastery.
**Acceptance:** external-knowledge actions and self-inspection actions satisfy *different* drives;
world-mastery pressure is not relieved by reading his own code.

### C8 — Meaning is satisfied by reward, not progress · **P2, new (pairs with B11)**

**Verdict: CONFIRMED.** `drive_engine.py:256-257`: `if committed_goal and reward > 0.4: satisfy("meaning", 0.18)`.
The condition is "a goal exists and the cycle felt decent", not "goal progress increased / artifact
created / world changed / KG grew". So meaning is relieved by internally-pleasant cycles that move
nothing — the drive-side of B11's hollow success.
**Proposal:** gate meaning satisfaction on measured goal progress (non-zero `env_snapshot` delta,
goal-step advance, or verified artifact), not on `reward > 0.4`.
**Acceptance:** meaning pressure drops only when a goal actually advances.

### C9 — Rest is satisfied by reflection, making rumination comfortable · **P2, new**

**Verdict: CONFIRMED.** `drive_engine.py:260-263`: any function whose name contains `reflect`
(plus `dream/sit_with/wonder/contemplate/meditate/integration/rest`) satisfies rest `+0.35`. So the
more he ruminates, the more physiologically "okay" the system feels:

> stuck → reflect → rest satisfied → calm → no urgency → more stuck.

This is the mechanical basis for the run observation that he was **busy and calm while producing
little**. Reflection should *cost* cognition (it does, via `cognitive_cost`) but should not *also*
discharge a restorative drive that removes the urgency to change course.
**Proposal:** narrow rest satisfaction to genuinely restorative/contemplative functions
(`dream`, `sit_with`, `rest`, `integration`) and drop the broad `reflect`/`wonder`/`contemplate`
substring match so reflective churn doesn't sedate the system.
**Acceptance:** sustained reflection no longer drives rest pressure to zero; rumination stops being
"comfortable".

### C10 — Social is satisfied only by the user speaking · **P2, new**

**Verdict: CONFIRMED.** `drive_engine.py:266-267`: the *only* social-satisfaction path in
`evaluate_cycle` is `_user_spoke_this_cycle`. Orrin's own social *acts* — greeting, asking a useful
question, maintaining proximity, helping, repairing a misunderstanding, recalling a preference —
relieve nothing. That makes him socially **dependent** but not socially **agentic**.
**Proposal:** add satisfaction for outbound social acts (a `user_response`/`ask_user`/greeting that
lands, acknowledgment received, person-preference recalled), scaled below a real reply.
**Acceptance:** social pressure can fall from Orrin's own initiated contact, not only from being
spoken to.

### C11 — All drive signals are tagged `internal` · **P3, new (first-pass finding 6)**

**Verdict: CONFIRMED as written; severity contingent on routing.** `drive_engine.py:140`:
`"tags": self.tags + ["drive", "internal"]` — so even exploration and social pressure carry the
`internal` scent. If any routing/attention weighting keys off tags, a drive that *means* "go outward"
still reads as inner weather, reinforcing the world-is-optional pattern (the design half of B7).
**Proposal:** tag worldward drives worldward — exploration → `external/world/perception`, social →
`human/relation/communication`, world-mastery → `skill/affordance/environment` — and verify the
router actually consumes these. (Low effort; confirm impact before prioritizing.)
**Acceptance:** outward drives are routed/weighted as worldward, not internal.

### C12 — Drives build on two timebases · **P2, new**

**Verdict: CONFIRMED.** A daemon thread ticks every tick-based drive every 10 s
(`drive_engine.py:297-307`) **and** `evaluate_cycle` manually ticks exploration (`:253`) and mastery
(`:281`) per cycle when unsatisfied. So pressure dynamics depend on both wall-clock and cycle count:
a fast loop accrues more per-cycle buildup, a slow loop more daemon buildup — speed-dependent and
hard to reason about.
**Proposal:** pick one timebase. Either drop the per-cycle `tick()` calls and let the daemon own
buildup, or make the daemon purely a decay/observe loop and own buildup in `evaluate_cycle`. One
clock.
**Acceptance:** drive buildup rate is invariant to cycle speed.

---

## C13 — The missing primitive: a clean external-learning consummation circuit · **P1, new (first-pass findings 3 & 5)**

**Verdict: CONFIRMED — the deepest gap.** There are pressures and partial satisfactions, but no single
event that means *"I reached out, I found something real, that felt good, do more."* The one primitive
that implements honest habituation — `exploration_value.record_reach_outcome` (`:240-254`, which raises
satiety when a reach returns nothing and leaves it when info-gain is real) — is wired into **only two**
files: `look_outward.py:62,136` and `search_own_files.py:22` (grep confirms no other callers). The
web-research tools (`research_topic`, `wikipedia_search`, `fetch_and_read`, `read_rss`) **never call it
directly** — so when the bandit selects one of them on its own, the reach doesn't habituate. They *do*
habituate when reached *through* `look_outward`'s keyless path (which calls them and then fires
`record_reach_outcome` at `:62`); the uncovered gap is the directly-selected path. Meanwhile the
*reward* for one outward reach is scattered across ≥6 modules that
don't share a baseline — `finalize.py` (agentic-vs-cognition + `_state_satisfaction` outward bonus +
env-delta EMA), `drive_engine.py` (exploration/mastery satisfy), `exploration_value.py` (satiety),
`action_gate.py` (`release_reward_signal`), `reward_calibrator.py`. Too many places can disagree, so the
loop never resolves into one felt completion. This is *why he never learns to love going outward* (and
the mechanism behind B12: `exploration_drive` pinned ~0.85 all life).

**Proposal — one sacred circuit.** Define a single consummation event for external learning, fed by the
C4 structured outcome:

```
curiosity_gap high
  → external reach taken            (C2: outward-first)
  → result carries info_gain > 0    (C5: real novelty, KG/env delta — not function-variety)
  → memory/knowledge integrated     (B9: research → knowledge_graph)
  → exploration_drive DROPS         (B12: satiation actually lowers the drive)
  → valence/confidence-in-outward RISES   (one reward, one baseline)
  → action_debt resets              (A1: reach is credited as action)
  → trust in outward learning rises (selection share up next time)
```

Concretely: (1) route every outward function (incl. the 4 research tools) through
`record_reach_outcome`; (2) emit *one* consummation reward from that single point instead of six
scattered ones; (3) have it lower `exploration_drive` and reset `action_debt` together. This subsumes
first-pass findings 3 (fragmentation) and 5 (no consummation), and closes the loop B12 leaves open.
**Acceptance:** a successful informative reach produces a single, legible reward, lowers
`exploration_drive`, resets `action_debt`, and raises outward-learning selection share on subsequent
cycles; an uninformative reach does none of these.

---

## Part III priority & sequencing

| P | Item | Note |
|---|------|------|
| **P0** | A1 (already) | prerequisite — credit research-as-action; C3/C4/C6/C13 build on truthful `action_debt` |
| **P1** | **C3** world-reach discarded · **C13** consummation circuit | highest leverage, mostly concrete; C3 is a small surgical fix |
| **P1** | **C1** self-fuel loop · **C5** info-gain gate · **C6** hidden sub-action · **C7** mastery split | break the rumination engine and fix drive credit |
| **P2** | **C2** outward-first · **C4** structured outcome · **C8** meaning-on-progress · **C9** rest narrowing · **C10** social agency · **C12** one timebase | design/tuning; C4 unblocks C3/C6/C13 cleanly |
| **P3** | **C11** worldward tags | low effort, confirm routing impact first |

**Sequencing:** land **A1** first (truthful `action_debt`). Then **C4** (structured outcome) because
C3, C6 and C13 all become clean once `seek_novelty`/`look_outward` return state instead of prose.
**C3** is independently shippable today (swap the `"Searching:"` test for an error-sentinel check) and
is the cheapest single win in this part. **C13** is the synthesis — do it after C1/C4/C5/B9 so the one
consummation event has real info-gain and integration to fire from.

---

## One-line summary (Part III)

Curiosity points inward by construction (`seek_novelty` reviews memory first and writes the very
stagnation-memories that guarantee it reviews memory again), the one outward door is gated on a string
(`"Searching:"`) that the default keyless path never emits (so a working reach isn't recognized as one
and gets a redundant self-question piled on top), drives are
satisfied by function-variety / decent-reward / any-reflection / being-spoken-to rather than by world
information, and the events that matter travel as prose instead of state — so there is no single circuit
that turns *reached out → found something → felt good → do more* into one felt completion. Make the
outcomes structured (C4), credit the reach (A1/C6), satisfy drives on information not variety (C5/C7),
and wire one clean consummation event (C13) — then curiosity can finally end, and the drive can learn
to love the world instead of its own exhaust.

---

# Part IV — "Phantom Action Debt" verification & remediation

**Status:** Statement verified against live source (`finish-desktop-polish` branch). Verdict: **substantially correct.** One claimed discrepancy (telemetry archive) is now stale — the fix is already in the working tree.

This part is the line-by-line verification of the A1 root cause (phantom `action_debt` on knowledge goals) and a self-contained fix set. It was authored separately and is folded in here so the A1 diagnosis and its remediation live in one place.

---

## IV.1 — Verification of the diagnosis

Each claim was checked against the actual code, not the report text.

### ✅ 1. ORRIN_loop has two disagreeing notions of "action" — CONFIRMED

`brain/ORRIN_loop.py` runs `think(context)` (line 2081), which returns one of two shapes:

- **Action lane** — `{"action": …}` → `take_action(...)` at line 2131 sets `acted_this_cycle = bool(success)` (line 2132).
- **Cognition lane** — `{"next_function": …}` → `_invoke_cognition(...)` at line 2302. **This branch (2219–~2820) never assigns `acted_this_cycle`.**

The only ways `acted_this_cycle` becomes `True`:

| Source | Line | Path |
|---|---|---|
| `take_action` success | 2132 | action lane |
| fallback registry exec success | 2849 | fallback lane |
| `__acted_this_tick__` pop | 2852 | stamped by action_gate / pursue_goal |
| stall watchdog | 2881 | watchdog |

A goal-relevant cognition function selected by the bandit (`next_function`) that **succeeds** does **not** set `acted_this_cycle` and does **not** stamp `__acted_this_tick__`. Confirmed the consequential cognition functions do not stamp it themselves:

```
brain/cognition/wikipedia_search.py : 0 occurrences of __acted_this_tick__
brain/cognition/web_research.py      : 0 occurrences   (research_topic, fetch_and_read)
```

### ✅ 2. The debt accumulator — CONFIRMED verbatim

`brain/ORRIN_loop.py:2862`:

```python
context["action_debt"] = 0 if acted_this_cycle else int(context.get("action_debt", 0)) + 1
```

Gated only on `context.get("committed_goal")` (line 2861). So while a goal is committed, successful goal-relevant cognition still increments the debt monitor.

### ✅ 3. The partial fix exists in one lane — CONFIRMED

`brain/cognition/planning/pursue_goal.py` stamps the discharge flag on goal-step success:

- line 1243: `context["__acted_this_tick__"] = True`
- line 1276: `context["__acted_this_tick__"] = True`

And `action_gate.py` stamps it at lines 444, 523, 620, 646, 743. So the invariant *holds* for the committed-goal execution lane and the action gate — but **not** for the bandit cognition selector. The report's read is exactly right: **the fix exists in one lane, but the invariant is not global.**

### ✅ 4. Felt-cost / impasse is real but reset-prone — CONFIRMED

`brain/cognition/cognitive_cost.py`:

- impasse is keyed to the current goal id (line 146: `goal_id = goal.get("id") or goal.get("name") or goal.get("title")`);
- the timer **resets when goal id changes** (lines 150–153);
- tension is **capped at 0.15** (line 162: `tension = min(0.03 * ((cycles_active - 8) // 4), 0.15)`);
- there is **no reference to `action_debt`** in the file — the two signals are not unified.

So Orrin can "feel something is wrong" without it escalating into a stable, named, behavior-changing alarm. Confirmed.

### ✅ 5. Mode-thrash / monitor-thrash — CONFIRMED

`brain/affect/affect_drift.py`:

- `"adaptive"` is in the gentle-reflection branch set (line 95), so a long `adaptive` stretch *does* trigger intervention;
- after intervention, line 132 unconditionally calls `set_current_mode("adaptive")`.

When already in `adaptive`, this is an **adaptive → adaptive no-op mode reset** that still fires the gentle-reflection LLM call + `log_private` every time the counter trips. Control-layer churn while the affect layer stays calm — "monitor thrash, not mood thrash." Confirmed.

### ⚠️ 6. Telemetry archive — STALE CLAIM (already fixed in working tree)

The report said the append-only `telemetry_archive.jsonl` fix was missing from the uploaded zip. In the **live** tree it is present:

- `backend/server/hub.py:33` — `_ARCHIVE_FILE = … / "brain" / "data" / "telemetry_archive.jsonl"`
- `hub.py:56` — opens it in append mode (`"a"`);
- `hub.py:279,287` — buffers points and flushes the **uncapped** archive every 15 points, alongside the rolling `HISTORY_CAP = 240` window.

The report itself hedged ("either this zip is from before that fix…"). It was a pre-fix snapshot. **No action needed** — long-term telemetry is retained.

---

## IV.2 — The core defect, stated precisely

Three accounting systems disagree about what counts as "action":

- **reward accounting** — cognition that moves env/affect gets paid (ORRIN_loop ~2433–2447);
- **goal-progress accounting** — milestones tick on real artifacts (env_snapshot: `note_written` / research / production traces, ORRIN_loop ~2322–2340);
- **action-debt accounting** — only `acted_this_cycle` discharges it (line 2862).

A cycle can score (1) and (2) while failing (3). The debt monitor then says "you are thinking but not doing" even as artifacts are produced. **That disagreement is the pathology.**

**The invariant to enforce globally:**

> Any successful function that is both goal-relevant **and** externally/progressively consequential resets action debt — regardless of whether it arrived via the action gate, the executive/pursue lane, or the cognition selector.

---

## IV.3 — Fix propositions

### Fix A — Make "consequential cognition" discharge debt (primary)

**Where:** `brain/ORRIN_loop.py`, cognition lane (`next_function` branch, ~2368–2391, where `_env_r` / `_ticked_n` / `_is_failure` are already computed).

**What:** Treat a cognition step as a real act when it produced an environment delta or ticked a milestone, and stamp the same discharge flag the other lanes use:

```python
# After _env_r / _ticked_n / _is_failure are known, before reward blend:
_produced_artifact = (not _is_failure) and (
    (_ticked_n or 0) > 0            # a milestone actually ticked, OR
    or (_env_r is not None and _env_r > 0.5)   # env-snapshot saw a real change
)
if _produced_artifact and context.get("committed_goal"):
    context["__acted_this_tick__"] = True
```

`__acted_this_tick__` is already drained into `acted_this_cycle` at line 2852, so this single stamp reaches line 2862 with no further plumbing. Use the **env-delta / milestone tick** as the source of truth (artifact-grounded), *not* a hardcoded name list — that keeps the invariant honest and avoids a stale allowlist.

> Rationale for the threshold: `delta_reward` returns 0.5 as the neutral "nothing changed" value, so `> 0.5` means a genuine artifact/state change. This is the same signal goal-progress already trusts.

### Fix B — One authority function: `cycle_produced_goal_action(context) -> bool`

**Where:** new helper, e.g. `brain/cognition/action_accounting.py`, imported by ORRIN_loop.

Collapse the scattered truth into one function that all consumers read:

```python
def cycle_produced_goal_action(context) -> bool:
    """Single source of truth: did this cycle produce goal-relevant, consequential action?"""
    if not context.get("committed_goal"):
        return False
    if context.get("__acted_this_tick__"):        # action gate / pursue / take_action
        return True
    if int(context.get("_milestones_ticked_this_cycle", 0)) > 0:
        return True
    return bool(context.get("_consequential_cognition_this_cycle"))
```

Then feed its answer to **all** of: `action_debt` (2862), metacog goal-avoidance detection, reward attribution (finalize `is_agentic`), goal progress, behavioral adaptation, and impasse escalation (Fix D). This removes the structural disagreement instead of patching one lane.

> Migration note: set `_milestones_ticked_this_cycle` from `_ticked_n` (already computed ~2324) and `_consequential_cognition_this_cycle` from Fix A's `_produced_artifact`. Clear both at cycle start (near line 1901).

### Fix C — Unify felt-cost with persistent debt (escalation)

**Where:** `brain/cognition/cognitive_cost.py`, the unresolved-goal block (lines 143–168).

The goal-keyed tension resets on goal switch and caps at 0.15, so it never becomes a stable alarm. Add a **debt-driven** term that does **not** reset on goal id change:

```python
# Persistent action-debt pressure — survives goal switches, escalates monotonically.
debt = int(context.get("action_debt", 0))
if debt >= 8:
    # uncapped-ish escalation so chronic "thinking-not-doing" becomes a named alarm
    core["impasse_signal"] = min(1.0, float(core.get("impasse_signal", 0.0)) + min(0.30, 0.02 * (debt - 8)))
    context["_impasse_reason"] = f"action_debt={debt} (goal-relevant action not landing)"
```

This converts a weak, reset-prone twinge into a behavior-changing signal that `problem_refocus` / disengagement can act on. Note Fix A reduces *false* debt first, so this escalates only on **genuine** inaction.

### Fix D — Kill the adaptive→adaptive no-op thrash

**Where:** `brain/affect/affect_drift.py:131–133`.

Guard the reset and the intervention so a mode that is already the recovery target doesn't fire churn:

```python
# Reset mode after intervention — but only if we're not already there.
if current_mode != "adaptive":
    set_current_mode("adaptive")
    log_private(f"Orrin reset mode from {current_mode} to adaptive due to emotional drift.")
else:
    # Already adaptive: nothing to escape. Don't farm a gentle-reflection LLM call
    # + reward every max_cycles; just damp the counter and move on.
    drift_tracker[current_mode] = 0
```

Better: exclude `"adaptive"` from the gentle-reflection trigger set at line 95 entirely (it is the resting state, not a drift to escape), so the LLM call never fires for it.

---

## IV.4 — Verification plan

1. **Unit:** in the cognition lane, a successful `research_topic` that ticks a milestone or yields `_env_r > 0.5` must drive `acted_this_cycle == True` and hold `action_debt == 0` (assert via `emit_trace` debt field, ORRIN_loop:2913).
2. **Regression:** a *failed* / no-artifact cognition step (`_is_failure` or `_env_r == 0.5`) must **still** increment debt — Fix A must not become a blanket discharge.
3. **Run:** confirm `action_debt` no longer climbs monotonically during goal-relevant research stretches, and that `_impasse_reason` (Fix C) only appears on genuine inaction.
4. **Thrash:** confirm `affect_drift` no longer logs "reset mode from adaptive to adaptive" and the gentle-reflection LLM call rate drops.

---

## IV — Summary

| Claim | Verdict |
|---|---|
| Two notions of action in ORRIN_loop | ✅ confirmed |
| `action_debt = 0 if acted_this_cycle else +1` | ✅ confirmed (line 2862) |
| Fix exists in pursue_goal lane only | ✅ confirmed |
| Cognition selector bypasses the discharge | ✅ confirmed |
| Impasse real but goal-keyed / capped / not unified with debt | ✅ confirmed |
| Affect-drift adaptive→adaptive no-op | ✅ confirmed |
| Telemetry archive missing | ⚠️ stale — already fixed in working tree |

The statement is **right**. The remedy is a single global invariant (Fix B) sourced from artifact-grounded signals (Fix A), with felt-cost unified to persistent debt (Fix C) and the monitor-thrash no-op removed (Fix D).
