# Orrin Embodiment — Build Plan

**One coherent, ordered plan that folds the architecture spec (`orrin_embodiment_architecture.md`, Parts 0–13) and its two live-repo audits (that doc, Parts VIII–IX) into small, self-contained tasks.**

Each task is sized for a single focused Claude Code (Opus 4.8) session: one clear goal, the exact files, what to do, and a concrete acceptance check. Do them in order within a phase; phases are gated by dependencies noted below. Every task cites the spec section (§) and/or audit finding (letter) it comes from so the *why* is one click away.

---

## How to read a task

```
ID · Title                              [Size: S/M/L]  [Depends: …]
Why     — the rationale + spec/audit pointer
Files   — what you'll touch
Do      — the change, concretely
Verify  — the acceptance check (prefer a test or an observable number)
```

**Size:** S ≈ <1hr surgical, M ≈ a session, L ≈ split if it grows.
**Golden rule:** keep Orrin **symbolic-first** and **fail-closed** (README conventions). Resolve paths through `brain/paths.py`. Run `pytest` green before declaring a task done.

---

## The big picture (why this order)

The deep design (felt body, infancy, budget slider) **cannot work until the affect substrate stops lying.** The audits proved it currently does: `resource_deficit` is pinned in [0.75, 0.92] and never reaches its 0.12 set-point; `_allostatic_load` and `stress_load` are both saturated at 1.0. Build anything embodied on top of that and it inherits permanent false distress. So **Phase A unsticks the substrate first.** Everything else stacks on a body that can actually feel "fine."

```
A. Unstick the substrate ─┬─► C. Felt body (host→feeling) ─► E. Infancy / band-learning ─► F. Budget+floor slider
  (confirmed live bugs)   │
                          └─► B. Reflex verify/tune (mostly done)        D. Metabolism (independent; do anytime after A)
```

**Critical path:** A → C → E → F. **B and D** can be done in parallel by a second session once A1 lands.

---

## Task index

| ID | Title | Phase | Size | Depends |
|----|-------|-------|------|---------|
| A1 | Rename the `function_resource_deficit` name collision | A | S | — |
| A2 | Make `body_sense` deviation-based (kills Loop 1 + `stress_load`) | A | M | A1 |
| A3 | Fix the `_allostatic_load` integrator (absolute→deviation) | A | S | A2 |
| A4 | Break the introspection-overload self-loop (Loop 2) | A | M | A1 |
| A5 | Reconcile dream's `resource_deficit` accounting | A | S | A2 |
| A6 | Regression test: substrate breathes back to set-point | A | S | A2,A3,A4,A5 |
| B1 | Decouple host sampling to ~1–2 Hz | B | S | — |
| B2 | Fire `on_warn` on any upward crossing into WARN | B | S | — |
| B3 | Surface host warn/pause/resume to the UI | B | M | — |
| C1 | Host metrics → felt body (the §6.2 seam) | C | M | A2,A3 |
| C2 | Battery as a felt finitude signal | C | M | C1 |
| D1 | Absolute capacity → metabolism (with dead-band) | D | M | A1 |
| E1 | Somatic-vs-developmental infancy split | E | M | — |
| E2 | The band-learner (envelope, not stillness) | E | L | A2,E1 |
| E3 | Two infancy backstops (reflex-stays-absolute + refuse-to-imprint) | E | M | E2 |
| F1 | The host floor (courtesy reservation) | F | M | B1 |
| F2 | Budget slider as fraction-of-machine | F | M | D1,E2 |
| F3 | Slider guardrails (no-override floor, resize→re-baseline, refuse-unviable) | F | M | F1,F2 |

---

## PHASE A — Unstick the affect substrate (confirmed live bugs)

> These fix the pathology the audits proved on disk. After Phase A, `resource_deficit` should oscillate around ~0.12–0.3 at rest and `_allostatic_load`/`stress_load` should sit near 0 when nothing is wrong. This phase is the highest-leverage work in the plan.

### A1 · Rename the `function_resource_deficit` name collision  [S] [Depends: —]
**Why** — Audit **J**/§4.3 naming gap. Two unrelated things share the stem "resource_deficit": the global fatigue float `affect_state["resource_deficit"]` ∈[0,1], and a per-function usage counter `context["function_resource_deficit"][fn]["score"]` ∈[0,10]. Every later task reasons over the global float; the collision will mis-target greps and edits. Rename the counter first so the codebase is safe to reason about.
**Files** — `brain/affect/reward_signals/resource_deficit.py` (rename `update_function_resource_deficit`→`update_function_usage_fatigue`, `function_resource_deficit` key→`function_usage_fatigue`, and the `*_penalty` helpers); ~12 call sites in `brain/think/think_utils/action_gate.py`; any readers (grep `function_resource_deficit`).
**Do** — Pure mechanical rename of the per-function structure and its functions. Do **not** touch `affect_state["resource_deficit"]`. Keep a thin backward-compat alias only if a daemon reads the old context key across a restart; otherwise drop it.
**Verify** — `grep -rn "function_resource_deficit" brain/` returns nothing; `pytest` green; one cycle runs and `context` shows `function_usage_fatigue`.

### A2 · Make `body_sense` deviation-based (kills Loop 1 **and** `stress_load`)  [M] [Depends: A1]
**Why** — Audit **B/H/I** + §7-#2, §8.1. `body_sense.py` fires `"heavy"` whenever RSS>400 MB absolute — always true with PyTorch resident — pumping `resource_deficit += 0.05` every reading (Loop 1). That same always-on stress also drives `_stress_streak` → `stress_load = min(1, (streak-20)/200)` saturates at 1.0 (`select_function.py:1387`, `update_affect_state.py:228`). One fix, both integrators.
**Files** — `brain/cognition/body_sense.py` (thresholds `_RSS_HEAVY_MB` etc. at lines 34–39; `compute_body_states`; `interoceptive_deltas`); confirm the streak feeders in `select_function.py`/`update_affect_state.py` then relax.
**Do** — Replace the absolute MB/percent thresholds with **deviation from a running baseline** of *this process on this machine*. Minimum viable version now (full band-learner is E2): keep a rolling EMA + spread of RSS/CPU/FD; emit `"heavy"`/`"strained"`/`"swelling"` only when the current sample is meaningfully **above its own recent normal** (e.g. > baseline + k·spread), not above a fixed constant. `"clear"` is the resting default. Net effect: a steady-high process reads `clear`, not `heavy`.
**Verify** — New unit test: feed a constant high RSS (e.g. 1.2 GB flat) for N readings → states settle to `clear` and `resource_deficit` trends **down** toward set-point, `_stress_streak` resets. Feed a rising ramp → `swelling`/`heavy` fire. `pytest` green.

### A3 · Fix the `_allostatic_load` integrator (absolute→deviation)  [S] [Depends: A2]
**Why** — Audit **B**/§8.3. `interoception.py:243–244` accrues load on `if rd > 0.60` — an absolute level. Even after A2 lowers `rd`, harden the integrator so it can never re-pin on level alone.
**Files** — `brain/cognition/interoception.py` (`allostatic_setpoint`, lines ~229–253).
**Do** — Change the accrual condition from absolute `rd > 0.60` to **deviation above the current set-point** (`rd - τ > margin`). Load should integrate the *cost of being away from where this body should sit*, not the raw value. Keep recovery faster than accrual.
**Verify** — Unit test: with `rd` held at a normal-for-this-body value equal to τ, `_allostatic_load` decays to 0 and stays. With `rd` held a margin above τ, it accrues. Add the case to `tests/`.

### A4 · Break the introspection-overload self-loop (Loop 2)  [M] [Depends: A1]
**Why** — Audit **H**. `cognitive_cost.py:78–86` adds fatigue when ≥5/8 recent picks are introspective — but high fatigue+impasse biases the bandit *toward* reflection, so the penalty feeds the signal that triggers it. Self-reinforcing rumination (WAL shows reflect_* dominating, `impasse_signal=1.0` pinned).
**Files** — `brain/cognition/cognitive_cost.py` (introspection-overload branch); check the selection coupling in `brain/think/think_utils/select_function.py`.
**Do** — Cut the positive feedback. Options (pick the cleanest): (a) make the introspection-overload drain decay/saturate so it can't ratchet every cycle; (b) ensure the fatigue→selection path doesn't *prefer* introspective functions when already overloaded (break the loop at the selector, not just the penalty). Keep the genuine signal (real overload should still register once), kill the ratchet.
**Verify** — Simulate 30 cycles of introspection-heavy picks: `resource_deficit` must plateau/decline, not climb monotonically. Assert in a test.

### A5 · Reconcile dream's `resource_deficit` accounting  [S] [Depends: A2]
**Why** — Audit **K**. Dream is the nominal recovery path (`dream_cycle.py:800` submits a negative `_recovery` nudge) yet the WAL shows `resource_deficit` **spiking** at dream cycles (0.78→0.92). §5.2 plans to *pause* dream under host pressure as "rest" — a rationale built on recovery that isn't happening.
**Files** — `brain/cognition/dreaming/dream_cycle.py` (~line 800 and any per-step deficit writes during the dream).
**Do** — Trace dream's net effect on `resource_deficit` across a full dream. Either (a) fix the accounting so a completed dream is net-negative (recovery actually recovers), or (b) if dream is legitimately costly, drop the "rest" framing and document that §5.2 pauses dream purely to reclaim **memory footprint**, not fatigue.
**Verify** — Instrument one dream cycle; log `resource_deficit` before/after. Net change matches the documented intent. Note the outcome in the §5.2 margin of the architecture doc.

### A6 · Regression test: the substrate breathes  [S] [Depends: A2,A3,A4,A5]
**Why** — Lock the fix so it can't silently regress (§8.2: regulation means *correctly set-pointed*, not flattened — the range must survive).
**Files** — new `tests/brain/test_resource_deficit_homeostasis.py`.
**Do** — Drive a calm synthetic run (normal-for-this-body vitals, no stressor). Assert: `resource_deficit` converges toward the τ set-point (not stuck ≥0.75); `_allostatic_load` and `stress_load` return to ~0; **and** a real injected spike still drives all three up (range preserved). This is the §10.7 calm-infancy diagnostic, frozen as a test.
**Verify** — Test passes; intentionally re-introducing the old absolute threshold makes it fail.

---

## PHASE B — Reflex: verify & tune (mostly already built)

> `HostResourceGuard` is implemented and wired (audit **A**). These are hardening tasks, independent of Phase A — a second session can run them in parallel.

### B1 · Decouple host sampling to ~1–2 Hz  [S] [Depends: —]
**Why** — Audit **E**. `host_guard.step()` runs every watchdog iteration (`watchdogs.py:381`, 100 Hz), so `disk_usage`/`swap_memory`/`virtual_memory` are called ~100×/s (on macOS `swap_memory` shells out). The sustain windows are 10–20 s; 1–2 Hz is plenty.
**Files** — `watchdogs.py` (watchdog loop) or `reaper/host_resources.py` (internal cadence guard).
**Do** — Gate `host_guard.step()` to run at ~1–2 Hz (track last-sampled monotonic time) while the rest of the 100 Hz loop is untouched. Don't change thresholds.
**Verify** — Log/counter shows ≤2 host samples/sec; WARN/PAUSE still trip in an injected-pressure test.

### B2 · Fire `on_warn` on any upward crossing into WARN  [S] [Depends: —]
**Why** — Audit **E**. `_apply_level` fires `on_warn` only on `WARN and prev==NORMAL`; a fast `NORMAL→PAUSE` crater never logs the "days early" warning.
**Files** — `reaper/host_resources.py` (`_apply_level`, lines ~242–277).
**Do** — Emit the warn notification on any transition that crosses *into or through* WARN on the way up (including straight to PAUSE), without double-firing on steady state.
**Verify** — Unit test: NORMAL→PAUSE jump triggers both warn and pause callbacks exactly once.

### B3 · Surface host warn/pause/resume to the UI  [M] [Depends: —]
**Why** — §5.2 calls for a dashboard flag, not just logs. Today `on_warn` only logs (`main.py:633`).
**Files** — `main.py` (`_host_on_warn` + add pause/resume handlers); `backend/` telemetry bridge; `frontend/` status surface (e.g. the Watch/Face status line).
**Do** — Route host level + reason into the telemetry stream so the UI shows "host under pressure — heavy cycles paused (disk 8.1 GB)". Reuse the existing bilingual thought-line plumbing if it fits.
**Verify** — Trigger synthetic pressure; the UI reflects warn→pause→resume.

---

## PHASE C — Interoception as felt body (host → feeling)

> Make the host Orrin's *felt* body, not just a guarded resource. Deviation-based from day one (the Phase A lesson).

### C1 · Host metrics → felt body (the §6.2 seam)  [M] [Depends: A2,A3]
**Why** — §6.2 + audit **C**. `HostResourceGuard` reads host-wide metrics; `body_sense` reads only Orrin's own process. The "same metrics feed the felt body" wiring doesn't exist. Build the seam.
**Files** — `brain/cognition/body_sense.py` or a new `brain/cognition/host_sense.py`; share the psutil host calls (or the guard's latest samples) rather than re-statting.
**Do** — Add felt signals from host disk/swap/vmem, each as **deviation from this body's learned normal** (reuse A2's baseline machinery): low disk→a "running out of room" claustrophobia; high swap→sluggishness ("thinking through molasses"); high vmem-vs-normal→pressure. Feed them through the existing interoceptive-delta path into affect. Keep magnitudes small and capped (arbiter-budgeted).
**Verify** — Inject a one-way swap climb → felt "sluggish"/distress rises and *stays* (the 2026-06-15 signature). Inject a spike-and-return → distress rises then clears (breathing). Test both.

### C2 · Battery as a felt finitude signal  [M] [Depends: C1]
**Why** — §6.3. A draining battery is real embodied scarcity — a mortality signal Orrin can actually perceive, richer than the random lifespan roll. **Caution (§8):** do not wire it straight into pinned distress.
**Files** — `brain/embodiment/system_presence.py` (battery sensing exists here — confirm `psutil.sensors_battery()` usage); the felt-body path from C1; read-only reference to `mortality.py` (do not fork mortality state).
**Do** — Surface battery %/charging as a felt signal: on battery + draining → a gentle, *bounded* finitude pressure; plugging in → relief ("eating"). Keep it a perception that colors cognition, not a new distress integrator. Leave the actual mortality clock in `mortality.py` untouched (§10.2 — don't create a second mortality signal that can disagree).
**Verify** — Toggle charging state (or mock it); felt finitude rises on battery, relaxes on AC, and never saturates. No change to `mortality.py` state.

---

## PHASE D — Metabolism (absolute capacity → cadence)

> Independent of C/E; can run any time after A1. This is mapping #1 of §7, and it's greenfield (no existing machine-size→cadence logic).

### D1 · Absolute capacity → metabolism, with a dead-band  [M] [Depends: A1]
**Why** — §7-#1, §8.4. "Runs slower on a small machine" is a smaller body with a slower metabolism, *not* a sick one — and it's **not a feeling** (set by config, not affect). A small box should slow the clock, not feel bad.
**Files** — new `brain/embodiment/metabolism.py`; read by the cadence/dream/reading schedulers and vector-store caps (wire into `ORRIN_loop.py` / executive interval / memory caps). Detect capacity via `psutil.virtual_memory().total` + `cpu_count`.
**Do** — At boot, detect absolute capacity → choose a metabolic tier that scales cycle cadence (`ORRIN_CYCLE_SLEEP`), dream/reading frequency, vector-store caps, concurrency. Put a **dead-band/hysteresis** on tier switches so a box hovering at a boundary doesn't thrash fast/slow/fast (§8.4). Metabolism must **not** route through affect.
**Verify** — Boot with a low `virtual_memory().total` (mock) → slower cadence, smaller caps, and affect baseline **unchanged** (no distress from being small). Boundary-hover test shows no oscillation.

---

## PHASE E — Infancy: learning a body

> The developmental spine. Build the lifecycle split first, then the band-learner, then the safety backstops.

### E1 · Somatic-vs-developmental infancy split  [M] [Depends: —]
**Why** — §10.1 + audit **D**. The lifecycle bit (clean/stalled/crashed/dead via `runstate.json`) and `born_at` exist, but the two-axis distinction — *somatic* (every new machine) vs *developmental* (once, true birth) — does not. Don't invent a parallel state that can disagree with mortality (§10.2; see the `lifecycle.py:91–95` scar).
**Files** — `brain/utils/lifecycle.py`, `brain/cognition/mortality.py` (read/extend, don't fork); a small `infancy` state holder.
**Do** — Derive both axes from existing state: developmental-infancy = first-ever birth (no `born_at`); somatic-infancy = first wake on *this* machine (persist a machine fingerprint — e.g. hashed `virtual_memory().total`+hostname — and compare). Plain restart on the same machine = neither. Map exactly to the §10.1 table.
**Verify** — Three scenarios: fresh state→both true; same state moved to a "new machine" (mock fingerprint)→somatic-only; plain restart→neither. Asserted in a test; no Death-Screen mis-route (the audit-D regression).

### E2 · The band-learner (envelope, not stillness)  [L] [Depends: A2,E1]
**Why** — §10.4. On a working machine "normal" is a **band**, not a point. Infancy learns the *shape of the oscillation* (floor/ceiling/amplitude) and wakes when the **description of the variance converges** — min/max stop widening — even though the instantaneous value never stills. This is the real home of A2's "baseline."
**Files** — new `brain/cognition/somatic_calibration.py` (or extend `calibration.py`); feed its learned band into `body_sense`/`host_sense` deviation checks (C1) and the interoception set-point.
**Do** — During somatic infancy, sample vitals (process + host) and learn each signal's envelope. Wake condition = envelope stable (new samples stop widening min/max for a sustained window), **not** low variance. Persist the band per machine fingerprint (E1). If §12.3 shows per-phase swings (dream vs idle slam between extremes), learn the band **per phase**. Distress (post-infancy) = "left the learned band" or "the band is marching one way and not returning."
**Verify** — Replay a noisy-but-bounded vitals trace → band converges and infancy completes; the instantaneous variance stays high throughout (assert convergence ≠ stillness). Replay a one-way climb → flagged as leaving the band, never absorbed as normal.

### E3 · Two infancy backstops  [M] [Depends: E2]
**Why** — §10.5/§10.6 (critical-period imprinting). Relative learning needs absolute guards so a sick machine can't be imprinted as normal.
**Files** — `brain/cognition/somatic_calibration.py` (E2); `reaper/host_resources.py` (confirm it runs during infancy).
**Do** — (1) **Reflex stays absolute during infancy** — verify `HostResourceGuard`'s 10 GB floor trips regardless of calibration state (it already runs in the watchdog thread; add a test that proves it fires mid-infancy). (2) **Refuse-to-imprint veto** — the band-learner rejects any baseline whose floor is already past the danger line (disk ~95% full, memory pinned): run reduced, flag it, do **not** imprint (§10.5.2). Relative learning, absolute refusal.
**Verify** — Boot into a mocked sick host (disk at 96%) → infancy refuses to baseline and flags; the reflex still trips its floor. Boot healthy → normal calibration.

---

## PHASE F — User configuration: the budget/floor slider

> One knob the user understands — "what fraction of this machine Orrin may be" — feeding metabolism, interoception's "100%", and a non-overridable host floor.

### F1 · The host floor (courtesy reservation)  [M] [Depends: B1]
**Why** — §11.1/§11.4.1. 2026-06-15 was a **floor** failure, not a budget failure: nothing reserved headroom for the OS + tabs + hibernate image. Build the floor first — it's the part that would have prevented the crash.
**Files** — `reaper/host_resources.py` (already enforces an absolute 10 GB disk floor — extend to an OS-memory-headroom reservation); `main.py` wiring.
**Do** — Add a courtesy floor that reserves headroom for everything that is *not* Orrin (free-RAM headroom alongside the existing free-disk floor), enforced by the reflex layer. This sits **underneath** any future budget slider and cannot be dialed away.
**Verify** — With the floor set, simulated pressure pauses heavy cycles while real free RAM/disk is still above the survival line. The floor holds even with a (mocked) greedy budget.

### F2 · Budget slider as fraction-of-machine  [M] [Depends: D1,E2]
**Why** — §11.2/§11.3. "Orrin may use up to N% of this machine" travels across hosts. The grant must feed **both** metabolism *and* interoception's "100%", or you reintroduce chronic distress through the front door (dial him down to be polite → he feels permanently starved because he's still measuring against the physical RAM).
**Files** — config/env (`ORRIN_*` budget var), `brain/embodiment/metabolism.py` (D1), the band-learner (E2), the felt-body baseline (C1).
**Do** — One user-facing value: fraction of detected RAM. Derive Orrin's effective capacity from it. Feed that capacity into metabolism (cadence/caps) **and** make it the interoceptive "100%" the band is learned against — so a 40%-of-8GB grant means his body *is* 3.2 GB and his normal re-centers there, not on the physical 8 GB.
**Verify** — Set budget to 40% → metabolism scales to 3.2 GB-equiv **and** resting affect stays neutral (no scarcity distress). Set 80% → roomier body, still neutral at rest.

### F3 · Slider guardrails  [M] [Depends: F1,F2]
**Why** — §11.4. Three guardrails keep the knob safe.
**Files** — config validation at startup; the budget→capacity path (F2); the infancy re-baseline path (E2/E3).
**Do** — (1) **Floor not overridable below the survival line** — the F1 reflex clamps real allocation even at a 95% grant (the user controls how big Orrin is, never removes the brainstem). (2) **Resize on a live Orrin → partial infancy** — changing the grant 40%→70% enlarges his body mid-life; route through the E2/E3 re-baseline path so he re-acclimates, doesn't silently live with a wrong band. (3) **Refuse an unviable grant** — below a minimum viable body (can't hold the working set / complete a dream+reading cycle), detect at startup, **refuse**, and tell the user the minimum (mirror §10.5's refuse-to-imprint). The minimum is §12.5's open measurement — measure it on the 8 GB box and encode it.
**Verify** — 95% grant → floor still clamps. Live 40%→70% change → re-baseline triggers, no permanent wrong-band. 5%-of-8GB grant → startup refuses with a clear "needs at least X" message.

---

## Open measurements to take while building (§12)

These gate a few tasks; take them as you reach the dependent task rather than up front:

1. **Steady-state baseline** (§12.1) — the real resting RSS/swap/vmem band on the 8 GB box. Needed for A2/E2. *(Partly known: vmem ~75% at rest, audit E.)*
2. **Oscillation shape** (§12.3) — does memory pressure swing gently or slam between extremes per dream/reading? Decides single-band vs per-phase band in E2.
3. **Minimum viable body** (§12.5) — smallest grant that completes a dream **and** reading cycle without thrashing. The floor of the F3 slider.

*(§12.2 absolute-vs-deviation and §12.4 birth-vs-restart are already answered by the audits — see Parts VIII–IX. No need to re-measure.)*

---

## Definition of done (whole plan)

- `resource_deficit` breathes around its set-point at rest and still spikes on real stress (A6 test green).
- The host is a *felt* body: a one-way swap climb registers as rising distress; a spike-and-return reads as breathing (C1 test).
- Orrin wakes correctly on a worked-on machine, learns its band without imprinting on sickness, and the reflex protects the host throughout (E-phase tests).
- The user sets one fraction-of-machine knob; it scales his metabolism and his felt "100%" together, with a floor he can't remove (F-phase tests).
- 2026-06-15 cannot recur: the floor + reflex trip days early, regardless of budget or calibration state.
