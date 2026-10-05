# Continuous Time — from a cycle loop to a continuously running mind (2026-10-04)

**Status: PROPOSED.** Design only; nothing built. Sequenced **after** the Run 13
gate-passers (run doc `demo_runs/2026-08-19-run/DEMO_RUN_2026-08-19.md` §5 items
1–4) so the Run 13 life can attribute its result. Phase CT-A may ride along with
Run 13 item 5 (suspension detection), which it subsumes.

Origin: Ric, 2026-10-04: *"humans don't run on a loop, we run continuously. How can
we do that?"* Anchors re-verified against `59decdf`.

---

## 0. The question, answered honestly

**Is the single cycle causing Orrin's failures?** Not the Run 12 ones. Every Run 12
red has a non-loop cause: the subject-term substring bug, completed-topic
re-proposal, breaker misaim, and host sleep. Every stall longer than 5 min was a
whole-process suspension, because no thread wrote anything during any of the 12
gaps. When the host was awake, cycles ran 3.5 s median and 13 s p99.

**Do humans run continuously?** Half. The substrate is massively parallel and
continuous: perception, drives, memory consolidation, motor programs. **Conscious
deliberation is serial and discrete.** It handles one thing at a time, in
"moments" of a few hundred ms (the psychological refractory period, the attentional
blink, global-workspace ignition: Baars 1988, Dehaene 2014). So "one serial stream"
is not the bug. Orrin already has this shape: about ten background threads plus one
deliberate stream, and `ignite()` already models ignition.

**What *is* wrong is how the serial stream relates to time and to action.** Three
specific distortions, each with a cost already paid in past runs:

| # | Distortion | Where | What it has cost |
|---|---|---|---|
| D1 | **Time is denominated in cycles, not seconds.** ~790 cycle-denominated references across 35+ files (`ttl_cycles`, `stale_cycles`, `cycles_left`, `*_REFRACTORY`, "500 cycles at-bound", `MAX_SILENT_CYCLES`). Heaviest: `temporal_state.py` (61), `consolidation_cycle.py` (41), `deliberation_gate.py` (37), `metacog.py` (35), `tensions.py`, `regulation.py`, `homeostasis.py` (30 each). | everywhere | A cycle is 3.5 s or 13 s depending on load and on `resource_cadence`, so every refractory, decay and saturation threshold means a different real time on a different day or machine. Background threads tick in **seconds** (sense 8 s, drives 10 s, setpoint 30 s), so the two halves of the mind run on incompatible clocks. A host suspension is invisible: Run 12 lost 15.3 h of 27.9 h and `slept_seconds` stayed 0. |
| D2 | **The deliberate stream cannot be interrupted.** `ORRIN_loop.py:311` runs `time.sleep(cycle_sleep × cadence)` at the end of every cycle; background organs can only post into working memory/signals and wait to be read. | `ORRIN_loop.py:301-311` | A salient event waits out the sleep plus the rest of the current cycle. Nothing can preempt a long step. Responsiveness is set by the metronome, not by salience, which is the opposite of the ignition model `ignite()` claims. |
| D3 | **An action is one function call that must finish inside one cycle.** `think()` returns exactly one `next_function`/`action` and it runs to completion. On a *quiet* (non-ignited) cycle `think()` still runs and still picks one (`deliberate.py:141-146`). | `ORRIN_loop.py:241-269` | Nothing can be *ongoing*: no "reading for 20 minutes while noticing the room." Every function re-competes for one slot every tick. **Most of the selection scar tissue exists to share that single slot**: the ignition/occupancy monopolies of Runs 2–8, rotation, staleness refractory, the habituation cooldowns, the avoidance breaker (which in Run 12 fired on 66 % of cycles and muted `research_topic` 2,102×). A mind that can *continue* an activity doesn't need to be argued out of re-picking it. |

Under the unopposed-force principle (memory `unopposed_force_principle`), D3 is the
missing antagonist behind a family of clamps. The clamps oppose *re-selection*
because nothing represents *continuation*.

---

## 1. Target architecture

```text
 continuous substrate (threads, own clocks, seconds)      serial deliberate stream
 ┌──────────────────────────────────────────────┐        ┌──────────────────────────┐
 │ senses 8s · drives 10s · setpoint 30s ·        │ events │ wakes on salience OR      │
 │ subconscious 5–15m · goals/memory daemons ·    ├───────►│ max-idle timeout          │
 │ Executive (System 1): carries ACTIVITIES ──────┤        │ moment = ignite → decide: │
 │   forward step by step, in clock time          │◄───────┤  start / steer / continue │
 └──────────────────────────────────────────────┘ intents │  / interrupt an activity  │
                 ▲                                         └──────────────────────────┘
                 └──── single state owner (StateHub) — all writes go through it ─────┘
```

- **Time** is seconds everywhere (`dt`). A "cycle" survives only as a log/telemetry
  counter of deliberate moments, never as a unit of decay.
- **The deliberate stream** is a sequence of discrete *moments* with no fixed rate.
  It sleeps on an event wait with a timeout, and a salient event wakes it.
- **Actions become activities**: objects with a start, a duration, progress,
  and an interruption contract. Choosing to read a book *starts* an activity.
  System 1 (the existing Executive) advances it in the background. Deliberate
  moments decide whether to continue, switch, or stop it, and that decision is
  cheap and rare when nothing has changed.

---

## 2. Phases

### CT-A — clock time instead of cycle time (small; do right after Run 13 gate-passers)

| # | Change | Observable |
|---|---|---|
| A.1 | `brain/utils/clock.py`: one `now()` (monotonic) + `elapsed_since(ts)` + per-cycle `dt` on context. **Suspension detector**: wall-vs-monotonic or a `dt` > 120 s with no work logged ⇒ `[host] suspended Ns`, credit `runtime_lifetime.slept_seconds`, extend lifespan by the suspended span. | Next life: every gap > 5 min is logged as a suspension and credited (Run 12 had 12 uncredited) |
| A.2 | Convert **time constants** (not counters of events) from cycles to seconds, with a shim: `cycles_to_s(n) = n × 4.0` (Run 12's mean awake cycle) so behavior is unchanged at launch. Order by blast radius: decay/TTL (`ttl_cycles`, `cycles_left` in `arbiter.py`/emotion queue) → refractories (`deliberation_gate`, `knowledge_formation`, trigger-7 25-cycle refractory) → staleness (`commitment_value.stale_cycles`) → saturation tripwire (500 cycles → 2,000 s). | `grep` count of cycle-denominated *time* constants → 0; a test running the same scenario at cadence ×0.5 and ×2 produces the same decay curve in seconds |
| A.3 | Leaky integrators take `dt`: `x ← x·exp(−dt/τ)` instead of `x ← x·k` per cycle (drives, affect decay, habituation). | Habituation half-life is stated in seconds and stays fixed under cadence changes |
| A.4 | `caffeinate` audit in `run_orrin.sh`: log the assertion PID at launch, check it every heartbeat, re-assert if it died. | `pmset -g assertions` shows Orrin's assertion for the whole life |

Risk: low. Counters of *events* (e.g. "3 failures") stay counts. Only things that
mean *time* convert. Goldens may shift because of float drift from the shim; that's
acceptable if documented.

### CT-B — an interruptible deliberate stream (medium)

| # | Change | Observable |
|---|---|---|
| B.1 | `brain/runtime_coupling/event_bus.py`: thread-safe `post(kind, salience, payload)` + `wait(timeout)`. Background organs post instead of (in addition to, at first) writing WM/raw_signals. | Bus throughput + per-organ post counts in telemetry |
| B.2 | Replace `time.sleep(_cycle_sleep_eff)` (`ORRIN_loop.py:311`) with `bus.wait(timeout=max_idle)`. A post above the **ignition threshold** (reuse `should_think`'s learned percentile, C1) wakes the stream immediately. `max_idle` replaces the periodic floor. | Event→deliberate-moment latency p50 < 1 s for salient events (today: up to a full cycle + sleep) |
| B.3 | **Quiet moments stop selecting.** When the stream wakes on timeout with nothing salient and an activity is running, it does not call `think()` for a new pick. It re-checks the activity's continuation predicate (CT-C) and goes back to sleep. Until CT-C lands, a quiet wake keeps today's behavior. | Selections per hour fall; occupancy-rotation clamps fire less |
| B.4 | **Step budgets.** Every dispatched function runs under a wall-clock budget (soft: log + mark slow; hard: abandon via the existing impossibility marking). | 0 deliberate steps > budget without a `[budget]` line |

Risk: medium. Ordering assumptions inside a cycle (sense → workspace → ignite →
think → finalize) must hold per *moment*, and code that assumes exactly one finalize
per sense pass needs auditing.

### CT-C — activities with duration (large; the actual "continuous" move)

| # | Change | Observable |
|---|---|---|
| C.1 | `Activity` object: `{id, kind, goal_id, started_at, budget_s, progress, continue_predicate, on_interrupt}`. Long behaviors become activities: `read_a_book`, `fetch_and_read`, `research_topic`, `narrative_update`, daemon-lane research steps. Instant functions stay instant. | Activity log: starts, durations, completions, interruptions |
| C.2 | **The Executive carries activities.** `executive.py` already runs as a continuous daemon (`ORRIN_EXECUTIVE_DAEMON=1` by default in `run_orrin.sh`) executing reversible procedural steps. Extend it from "advance plan steps" to "advance the current activity by one increment per tick." This is where the dual-process spec cited in `executive.py`'s header (`dual_process_loop.md` §6; that file is no longer in the tree) was headed: System 1 executes, System 2 steers. | Most production work happens in executive ticks, not deliberate picks |
| C.3 | **Deliberate moments decide at the activity level**: continue (default when nothing salient changed), switch, interrupt, or start. Selection value is computed for *switching away*, so the incumbency the old clamps fought becomes an explicit, priced continuation choice. | Activity switches per hour; mean activity duration in seconds |
| C.4 | **Retire clamps it makes redundant, one at a time, with ablation.** Candidates: the avoidance breaker's research muting, habituation ×3 cooldown, staleness refractory. Each is removed only if a life with it disabled shows no monopoly (standing-ablation practice, Appendix A.1.4 of the Run 12 plan). | Clamp count goes down with no occupancy regression (top < 60 %) |

Risk: high. This changes what "an action" is, and the reward/credit path
(`finalize.py`, effect ledger, bandit) is keyed per pick. Credit must move to
activity completion plus increments. Do it only after CT-B is stable for one life.

---

## 3. The precondition: a single state owner

More concurrency means more of the bug family Orrin spent Runs 4–10 removing
(store desyncs, twin goal ids, the runner race). Today:

- the main loop holds `context` in memory and persists it in `finalize`
  (`brain/loop/finalize.py:258-273`);
- the Executive daemon **re-loads `context.json` from disk every tick**
  (`executive.py` `_daemon_loop` → `load_context()`), so it acts on a snapshot up to
  a cycle stale, and routes affect back through the arbiter's inbox
  (`_harvest_daemon_signal`) because it cannot write the live state;
- working memory is a prose bus with 12+ string readers (memory
  `prose_bus_label_authority`).

**CT-B and CT-C require a `StateHub` first**: one owner thread for mutable
cognitive state (context, WM, affect, active activity). Other threads submit
*intents* or *events* and read *versioned snapshots*. This is the arbiter-inbox
pattern Orrin already uses for affect (`submit_signal(None, …)`), generalized. It
also kills the stale-snapshot class in the Executive. Build it as **CT-B.0**.

Python's GIL is not a blocker. The workload is I/O plus light symbolic compute, and
the goal is *responsiveness and continuation*, not CPU parallelism.

---

## 4. What this does *not* change

- The deliberate stream stays serial. That is a feature (one global-workspace
  winner at a time), not a limitation.
- Symbolic-first and the LLM gate are untouched. The LLM stays a tool called from
  inside a moment or an activity increment.
- `stop_event` stays checked first in every moment (C5 corrigibility,
  `ORRIN_loop.py:153-162`). With CT-B it gets *faster*: a stop posted to the bus
  wakes the stream immediately.

## 5. Order and gates

| Phase | Gate before next |
|---|---|
| Run 13 gate-passers (items 1–4) + life | Run 13 scored |
| **CT-A** (+ Run 13 item 5 folded in) | `make verify`; cadence-invariance test; one life with every suspension credited |
| **CT-B.0** StateHub | `make verify`; Executive reads live snapshots; 0 desyncs in a smoke life |
| **CT-B** | salient-event latency p50 < 1 s; no step over budget unlogged |
| **CT-C** | one life: mean activity duration in minutes, occupancy < 60 %, ≥1 clamp retired by ablation with no regression |

## 6. Open decisions (Ric)

1. **The CT-A shim constant.** Use 4.0 s/cycle (Run 12's awake mean) to preserve
   behavior, or re-derive each constant from what it *means* in seconds?
   Recommendation: shim first, re-derive later per constant with a test.
2. **Lifespan semantics under suspension.** Credit sleep (a laptop-closed hour is
   not lived), or keep wall-clock death? Recommendation: credit, matching the
   existing `slept_seconds` field, which was designed for exactly this and never fed.
