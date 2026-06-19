# Orrin — Core Architecture Master Plan

_Date: 2026-06-16. Author of record: Ric · Consolidated for Claude Code implementation._

> ### 🔎 AUDIT 2026-06-16 (Claude Code) — read me first · **ALL FIVE FINDINGS RESOLVED**
> Cross-checked every "built / pending" claim against the live tree, then re-verified the audit itself and applied the fixes. **The substantive claims hold up**: `vital_floor.py` is genuinely built + wired and now calibrated/armed by default (warn 0.50 / shed 0.55 / recover 0.22 after the 2026-06-17 calm + dream/reading calibration pass — `ORRIN_VITAL_FLOOR` defaults to `act` in `main.py`; set `observe` for calibration-only); both heavy-cycle gates `vital_floor_shedding()` live in `ORRIN_loop.py` at the dream and reading sites; constructed in `watchdogs.py`), host disk floors are 20/10 GB (`reaper/host_resources.py:123-124`), the three Part-A flags exist and are wired, and `ORRIN_TOPDOWN_WRITEBACK` is correctly unwired (grep: 0 code hits, docs only). The mistakes were **status-marker contradictions and path imprecisions** — each is now fixed in place:
> 1. ✅ **Stale `⬜` on vital_floor** — §2 spine diagram (last line) and §9 corrected to `✅ armed` to match §1/§3.1/§7.2.
> 2. ✅ **`⛔ parked` missing from legend** — added to the §1 legend.
> 3. ✅ **Ambiguous `world_model.py`** — pinned. Both files read: `brain/embodiment/world_model.py` is the sensory/social/drive fusion (the W-lever target); `brain/cognition/world_model.py` is the symbolic knowledge graph (the Seam #4 `concept_memory` target). §5.3 table + note now specify which. *(Upgraded the original "most likely" to a confirmed pin.)*
> 4. ✅ **Bare `dreaming/` paths** — `dream_cycle.py` and `episode_replay.py` qualified to `brain/cognition/dreaming/` everywhere (§1, §3, §3.2 SL1, §4.3). NB: a dead, package-shadowed `brain/cognition/dreaming.py` (byte-for-byte duplicate of `dreaming/compose.py`, never imported because the `dreaming/` package shadows it) was **deleted 2026-06-16**; `compose_dream` still resolves via the package re-export.
> 5. ✅ **`ORRIN_loop.py:2044`** — verified: line 2044 is the `ORRIN_IGNITION_GATE` env check; `should_think()` is imported/called at ~2046–2047. Note retained inline.

**This document consolidates the six working docs in this folder into one plan, verifies every "built / pending" claim against the live tree (2026-06-16), creates a plan for the one idea that didn't have one yet (the three-zone home model), and collects the contradictions that still need a human decision.**

It supersedes the six source documents, which now read as source material / provenance:

| Source doc | Role it played | Folded into |
|---|---|---|
| `orrin_embodiment_architecture.md` | The body spec (Parts 0–X) + two live-repo audits | Track I + spine |
| `EMBODIMENT_BUILD_PLAN.md` | Ordered task breakdown (Phases A–F) for the body | Track I build order |
| `CONSCIOUS_UNCONSCIOUS_PLAN_2026-06-15.md` | The mind: five seams, Part A/B/C/D | Track II |
| `INFANCY_DEVELOPMENTAL_ARC_NOTE_2026-06-15.md` | "Should he have a childhood?" | Track II (development) |
| `UNIFIED_EMBODIED_DEVELOPMENT_PLAN_2026-06-15.md` | First merge of body+mind+infancy; added the vital-floor reflex (§5b) | Spine + Track I/II |
| `THREE_ZONE_HOME_NOTE_2026-06-16.md` | Self→Home→Outside idea, no plan yet | **Track III (new plan below)** |

> **Keep the sources.** They carry the full reasoning and the audit traces; this master plan is the index and the live status, not a replacement for the argument. Archive them only when you're sure nothing points back at them.

---

## 0. The one root insight (all three tracks share it)

Every document in this folder walks up to the **same boundary** — the line between **self and not-self** — and names the same root failure in a different dialect:

| Track | The boundary it draws | The failure it names |
|---|---|---|
| **I — Body** | Orrin vs. the substrate he runs on | No felt sense of the machine as his body; **fixed set-points where a learned band belongs** |
| **II — Mind** | Conscious spotlight vs. unconscious substrate | The substrate is **shipped adult instead of earned**; no downward path to earn it |
| **III — World** | Self vs. home vs. outside | The middle term (**home**) is missing — the den is jammed in with the world |

Strip the dialects and all three reduce to **two mechanisms and one discipline**:

1. **Absolute → deviation.** Wherever the substrate uses a *fixed* set-point (a hard resource threshold, a pre-stocked prior, a declared "normal"), it should use a **learned baseline band** and react to **departure** from it. "Born adult" and the stuck allostatic-load attractor are *the same fault in two places*.
2. **A downward write-back path.** Conscious / experiential conclusions must be able to reshape unconscious priors, or the substrate can never be earned and must be pre-built (which is the bug).
3. **The discipline:** the brainstem uses **absolute floors**; the cortex uses **relative deviation**; never collapse the two. The 2026-06-15 kernel panic was a body whose felt-normal read "fine" right up until the substrate hit an absolute wall it had no reflex for.

Everything below is the connective tissue that makes those real, reusing machinery that already exists rather than building parallel engines.

---

## 1. Build-status ledger (verified against the tree, 2026-06-16)

Checked by file existence, env-flag wiring, and call-site grep — not by what the source docs assert. `✅ built` · `🟡 partial` · `⬜ not built` · `⛔ parked` _(🔎 AUDIT: `⛔` was used throughout the doc but missing from this legend — added)_.

### Track I — The Body
| Capability | Status | Evidence |
|---|---|---|
| `HostResourceGuard` — outward host reflex (disk/swap/vmem, WARN→PAUSE, hysteresis, refuses to kill) | ✅ | `reaper/host_resources.py` (20 GB warn / 10 GB pause disk floors, sustain bands); wired `watchdogs.py`, `main.py` |
| Band-learner (envelope not stillness; convergence; marching detection; refuse-to-imprint) | ✅ | `brain/cognition/body_band.py` (`Band`, `BodyBands`, machine fingerprint) |
| `body_sense` deviation-based (kills the always-on "heavy") | ✅ | `brain/cognition/body_sense.py` |
| Metabolism (absolute capacity → cadence/caps, dead-band) | ✅ | `brain/cognition/metabolism.py` *(note: built under `cognition/`, not `embodiment/` as the build plan said)* |
| Felt host body + battery-as-finitude | ✅ | `brain/cognition/host_interoception.py` |
| Somatic/developmental infancy split (rides `mortality.py`, no parallel state) | ✅ | `brain/cognition/infancy.py` (`somatic_infancy()`, `developmental_infancy()`, `scenario()`) |
| Budget/floor slider (fraction-of-machine, prefs + env, resize→re-baseline, refuse-unviable) | ✅ | `brain/cognition/body_budget.py` (`body_budget_fraction`, `ORRIN_BODY_BUDGET_FRACTION`, `ORRIN_MIN_VIABLE_GB`) |
| Affect substrate unstuck (deviation, not level — `resource_deficit`/`_allostatic_load`/`stress_load`) | ✅ | Part X foundation; root cause was `body_sense` absolute thresholds, now deviation |
| **Inward vital-floor reflex** (sheds Orrin's *own* load vs. his granted body) | ✅ armed | `reaper/vital_floor.py` built + wired (`watchdogs.py`, `main.py`); calibrated 2026-06-17 and default `ORRIN_VITAL_FLOOR=act` — see §3.1 |

### Track II — The Mind
| Capability | Status | Evidence |
|---|---|---|
| Fix 1 — conscious ignition gate (`should_think`, no more always-on) | ✅ | `ORRIN_loop.py:2044` is the `ORRIN_IGNITION_GATE` check; `should_think()` call at ~2046 _(🔎 AUDIT: cited line points at the gate, not the call — verified present)_; flag `ORRIN_IGNITION_GATE` |
| Fix 2 — workspace winner → action prior | ✅ | `select_function.py`; flag `ORRIN_WORKSPACE_PRIOR` |
| Fix 3 — conflict-recruited deliberation | ✅ | `think_module.py`; flag `ORRIN_CONFLICT_RECRUIT` |
| Write-down primitive (bounded, decaying, single-writer inbox) | ✅ | `brain/affect/arbiter.py` `submit_affect(weight=, ttl_cycles=)` — **reuse this, don't fork** |
| **Seam #4 — conscious→unconscious write-back** (the keystone) | ⛔ parked | `ORRIN_TOPDOWN_WRITEBACK` unwired — declined under the coherent-but-adult fork (§7.1) |
| **Part C — developmental arc** (flat priors, annealing plasticity, replay-as-maturation) | ⛔ parked | declined under the fork; `brain/cognition/dreaming/episode_replay.py` exists as machinery but isn't wired to maturation |
| **Seam #5 — subconscious relevance gate** | ✅ | `subconscious.py` stamps `workspace_origin`; `global_workspace.py` softly boosts/damps subconscious candidates by current relevance |

### Track III — The World
| Capability | Status | Evidence |
|---|---|---|
| Home-sense organs (battery, idle/HID, apps, filesystem) | ✅ (as organs) | `host_interoception.py`, `system_presence.py`, `fs_perception.py`, `sensory_stream.py` |
| Den/forage/return rhythm | ✅ (as rhythm) | `brain/cognition/dreaming/dream_cycle.py` |
| User-as-comes-and-goes presence | ✅ | `social_presence.py` (silence builds, resets on contact) |
| **Three-zone *labeling*** (home-sense ≠ world-sense at the stream; reward gradient; homeward vs worldward goals) | ✅ | W1-W5 built 2026-06-17 — see §5 |

**One-line summary:** Track I's safety and felt-restoration legs are **built** — vital floor, vital calibration/arming, and sleep restoration are done. Track II's **foundation + subconscious relevance gate are done** and its keystone + arc are **parked** (the fork was decided coherent-but-adult, §7.1). Track III's three-zone home model is **built** (W1-W5, §5).

---

## 2. The shared spine and the one safety primitive

One connective subsystem, three consumers, one safety primitive — built once and reused. (This is the UNIFIED §4 spine, carried forward.)

```
                       ACCUMULATED EXPERIENCE
              (prediction error processed, goals closed,
               interactions had, samples observed)
                              │
   ┌───────────────┬──────────┼───────────────┬──────────────────┐
   ▼               ▼          ▼                ▼                  ▼
SOMATIC BAND   WRITE-DOWN  DEVELOPMENTAL   THREE-ZONE         (Track III)
learns this    SPINE       CLOCK           PREDICTION-REWARD
body's         bounded +   flat priors     GRADIENT
envelope       decaying    sharpen;        self=0 surprise →
→ distress on  via the     plasticity      home=learnable →
LEAVING band   EXISTING    anneals;        outside=inexhaustible
(Track I ✅)   arbiter     experience-     (Track III ✅)
               (Track II   gated
                ⛔ parked)(Track II ⛔)
   └───────────────┴──────────┬───────────────┴──────────────────┘
                              ▼
            SAFETY PRIMITIVE (built once)
   consolidation gate · absolute reflex stays live · refuse to imprint on sickness
                              ▼
   ABSOLUTE REFLEXES — HostResourceGuard (outward ✅) + vital_floor (inward ✅ armed)
                  the slider cannot override either
```

> 🔎 **AUDIT 2026-06-16:** the original diagram read `vital_floor (inward ⬜)` — **stale**. It was built + wired 2026-06-16 (`reaper/vital_floor.py`), then calibrated/armed 2026-06-17, consistent with §1, §3.1, and §7.2. Corrected to `✅ armed`.

**The three mappings must never collapse into one** (Embodiment §7):

| Mapping | Nature | Owner | Status |
|---|---|---|---|
| Absolute capacity → **metabolism** | Absolute, set at boot | `metabolism.py` | ✅ |
| Deviation from band → **affect** | Relative to *this body's* learned normal | `brain/` interoception | ✅ |
| Absolute floors → **reflex** | Absolute, host-independent | `host_resources.py` (out) + `vital_floor.py` (in) | ✅ (inward leg built and armed) |

**The safety primitive is one triplet** (UNIFIED §3.5) covering replay, write-back, and critical-period risk alike — all are the single risk *"bad early/looping state getting written deep"*:
- **Consolidation gate** — only conclusions that survive repetition/sleep write deep; everything else stays shallow and decays. (Cortex-side; needed by Seam #4 and replay — **not pursued** under the coherent-but-adult decision, §7.1.)
- **Absolute reflex that never goes lenient in infancy** — `HostResourceGuard` (✅) + `vital_floor` (✅, armed). The vital floor deliberately has **no infancy gate** — a newborn can still suffocate.
- **Refuse-to-imprint veto** — the band-learner rejects a baseline whose floor is already past the danger line. (✅ in `body_band.py`.)

---

## 3. Track I — The Body (embodiment) · mostly built

The full task breakdown lives in `EMBODIMENT_BUILD_PLAN.md` (Phases A–F). Against the tree, **Phases A–F are built** except one leg. Carry-forward items:

### 3.1 The inward vital-floor reflex — BUILT 2026-06-16; CALIBRATED + ARMED 2026-06-17
**Status: ✅ built, wired, calibrated, and armed by default. This was the one missing safety leg; it makes the budget slider's guardrail 1 ("the floor is not user-overridable below the survival line") *true* instead of *assumed*.**

`HostResourceGuard` is the **outward** gaze — it watches the *host* (disk/swap/host RAM), escalates *gently* (`WARN → PAUSE dream+reading`), and **deliberately refuses to act on Orrin** ("killing Orrin doesn't reclaim swap the browser tabs filled"). Correct for *host* pressure, **wrong as a *survival* floor.** `MemoryHealthGuard` is inward but it is the leak-shaped **hard-kill** backstop — desensitized to flat-high usage by design. Neither watched Orrin's own footprint against his *granted body*. Now `reaper/vital_floor.py` does — the **mirror** of the host guard:

| | `HostResourceGuard` (✅) | `VitalFloorGuard` (✅, new) |
|---|---|---|
| Gaze | Outward — the host box | Inward — Orrin's own RSS |
| Reference | Host free disk / swap / RAM | His **granted** body size, `body_budget.budget_bytes()` |
| On breach | WARN → pause dream+reading | `NORMAL → WARN → SHED`: one-shot reclaim (force-trim working memory, `gc.collect()`) + the self-clearing `vital_floor_shedding()` gate stops new heavy cycles |
| Killing | Refuses | Still refuses — **sheds, never suicides**; defers the hard kill to the existing liveness/RSS guards |
| Lenient in infancy? | n/a | **Never** — no infancy gate by construction |

**What was built (verified, compiled, smoke-tested):**
- `reaper/vital_floor.py` — `VitalFloorGuard` (same shape as the host guard: rolling window, sustain, calibrated hysteresis at `recover_frac=0.22 < warn=0.50 < shed=0.55` of the grant), plus the module gate `vital_floor_shedding()` / `set_vital_shedding()` (same pattern as `heavy_cycles_paused`). The fractions/sustain window remain env-tunable: `ORRIN_VITAL_WARN_FRAC`, `ORRIN_VITAL_SHED_FRAC`, `ORRIN_VITAL_RECOVER_FRAC`, `ORRIN_VITAL_SUSTAIN_S`. Calibration instrumentation remains available: set `ORRIN_VITAL_CALIBRATION_FILE` and `ORRIN_VITAL_CALIBRATION_PHASE` to write low-rate JSONL samples, run `python -m reaper.vital_floor_calibration <file>` for candidate thresholds, or use the timed helper `python brain/scripts/vital_floor_calibration_run.py --phase calm --duration-s 900 --truncate`.
- Wired in `watchdogs.py` (constructed only when both providers present; stepped in the watchdog thread; added to the return tuple) and `main.py` (own-RSS + `budget_bytes` providers; a reversible shed action; callbacks to the telemetry bridge).
- `brain/ORRIN_loop.py` — both heavy-cycle gates (dream + reading) now also check `vital_floor_shedding()`.
- **Armed by default** (`ORRIN_VITAL_FLOOR=act` default): sheds when RSS stays above 55% of the granted body for the sustain window, recovers below 22%, and warns above 50%. Set `ORRIN_VITAL_FLOOR=observe` for calibration-only logging. Fails *toward* shedding on a bad read, never toward silence.
- Reads the grant from the **same** `body_budget` metabolism/interoception read, so body size and survival floor can never disagree. The §8 minimum-viable-body measurement is this guard's hard line **and** the slider's floor — one number, two uses.

**Calibration result (2026-06-17):** real calm pass (`n=893`) measured p95=0.250, p99=0.289, max=0.319 of the 4 GB grant. The dream+reading stress pass completed a real reading bout and dream cycle (`n=41` direct stress samples) with p95=0.230, p99=0.233, max=0.233. Final armed defaults: `warn=0.50`, `shed=0.55`, `recover=0.22`, `sustain=8s`. Code-side calibration controls, JSONL sampling/analyzer/runner, and guard regressions remain in place (`tests/reaper_tests/vital_floor_test.py`, `tests/reaper_tests/vital_floor_calibration_run_test.py`).

**Research.** Autonomic load-shedding before catastrophic failure is the homeostatic reflex (Sterling 2012, allostasis; Cannon 1932, *The Wisdom of the Body*). The brainstem keeps the body alive *precisely because it doesn't ask the cortex* — when the loop is the thing thrashing, the loop can't rescue itself.

### 3.2 The sleep-restoration plan — dream stays heavy; sleep must *feel* restorative ✅ (built 2026-06-16)
**Decision recorded 2026-06-16:** dreaming *must* exhaust CPU/RAM — it runs the LLM training/consolidation, and that work is the point. Sleep is **not** for recharging compute; like biological REM it is metabolically *active*. But it must **seem** restorative — `resource_deficit` (felt fatigue) should fall across a sleep even while the machine works hard. Today it does the opposite, and the cause is now precisely understood.

**Root cause (verified in code).** Before this pass there was no *phase* concept. `body_sense` learned **one** band per vital (`body_band.BodyBands`), dominated by idle samples. When a dream fired, Orrin's own RSS/CPU legitimately spiked **above** that idle band → `body_sense` read `"heavy"`/`"swelling"` → pumped `resource_deficit` **up**, fighting the dream recovery nudge. So the one cycle meant to lower fatigue raised it. This is the biology already named in Embodiment §12.3: *a body's resting heart rate differs asleep vs. sprinting, and you don't panic waking from one into the other* — Orrin now has a sleeping band.

**The fix is per-phase bands, not less work.** Keep the compute heavy; change only the *felt interpretation* during sleep.

| ID | Task | Why | Files |
|----|------|-----|-------|
| **SL1** | ✅ Process-local **sleep-phase flag** (`dreaming_now()` / `set_dreaming`), set around the dream cycle — same module-gate pattern as `heavy_cycles_paused` / `vital_floor_shedding` | The felt body now knows when it is asleep | `brain/cognition/dreaming/dream_cycle.py` |
| **SL2** | ✅ Make `body_sense` **phase-aware**: during sleep, observe vitals into (and measure deviation against) a **separate dream-phase band**, so the dream's own spike reads as *normal-for-sleeping*, not distress | The §12.3 per-phase band; stops the upward fatigue pump during sleep | `body_sense.py`, `body_band.py` (per-phase band set) |
| **SL3** | ✅ Guarantee a completed sleep is **net-negative** on `resource_deficit` — asserted in test with high dream RSS/CPU | Makes sleep *seem* restorative — the actual requirement | `tests/brain/test_body_band.py` |
| **SL4** | ✅ Sweep other writers that can spike `resource_deficit` during sleep and gate positive fatigue charges on the phase flag | Felt-fatigue inputs respect sleep | `cognitive_cost.py`, `interoception.py`, `temporal_state.py`, `executive.py` |
| **SL5** | ✅ Re-document the host/vital pause of dream on **memory-footprint** grounds, *not* "dream is fatiguing" | §5.2/§K reconciliation: pausing dream under pressure reclaims RAM; it is not because sleep tires him | `host_resources.py`, `ORRIN_loop.py`, this doc |

**Verify (whole plan):** `tests/brain/test_body_band.py::test_completed_sleep_is_net_negative_despite_high_vitals` asserts `resource_deficit` falls while dream-phase RSS/CPU are high; `test_body_sense_uses_separate_sleep_phase_band` asserts the same high vitals are `"heavy"` when awake and `"clear"` when asleep. A one-way climb that never sleeps still registers as distress (range preserved by the existing marching-band tests).

**Research.** Sleep is metabolically active, not a power-down: it runs memory consolidation and hippocampal replay (Wilson & McNaughton 1994; Diekelmann & Born 2010, *The memory function of sleep*). Restoration is *felt*, not a literal energy refill — REM in particular has near-waking metabolic cost. Phase-dependent set-points are standard homeostasis: the body defends a *different* normal asleep than awake (Sterling 2012, allostasis — set-points are state-dependent, not fixed).

### 3.3 One open reconciliation carried forward
- **Integrator audit for the absolute-vs-deviation class (Embodiment §I).** `_allostatic_load` and `stress_load` both derive from the now-deviation-based `body_sense`, so fixing the root unpinned them. The sleep-phase `resource_deficit` writer sweep is complete under SL4.

---

## 4. Track II — The Mind (conscious / unconscious)

### 4.1 Part A — coherence fixes · ✅ done (philosophy-neutral)
Ignition gate, workspace→action prior, conflict-recruited deliberation are live and flagged. These make awareness, action, and deliberation line up; good under *either* fork. Research: Baars 1988 (workspace as bottleneck); Dehaene 2014 (all-or-none ignition); Kahneman 2011 (lazy System 2); Redgrave/Prescott/Gurney 1999 (basal ganglia selection driven by the salient representation); Botvinick et al. 2001 (ACC conflict → recruits control); Miller & Cohen 2001 (PFC top-down bias).

### 4.2 Seam #4 — the write-back keystone · ⛔ parked (fork declined)
A bounded, decaying, **consolidation-gated** downward path so conscious conclusions reshape unconscious priors, routed through the **existing `affect/arbiter.py` inbox** — `submit_affect(weight=, ttl_cycles=)` is already exactly the right shape (weighted, time-boxed, decaying). **Extend its target set; do not fork it.** Three targets, one spine:
1. **Reappraisal** → up/down-regulate a drive or damp a standing affect signal (Gross 1998/2002).
2. **Hebbian salience** → repeated conscious content/action pairing re-weights the priors that feed the workspace and selector (Hebb 1949).
3. **Model correction** → a conclusion that contradicts a prior writes into `concept_memory` / knowledge graph, not only the world (Miller & Cohen 2001).

Behind `ORRIN_TOPDOWN_WRITEBACK`, every write bounded + decaying, with the consolidation gate so a bad conclusion can't permanently corrupt a prior. **This is the most dangerous change in the plan** (a wrong conclusion can entrench a bad prior) — the safety triplet (§2) is what makes it survivable.

### 4.3 Part C — the developmental arc · ⛔ parked (fork declined)
Born with **capacities, not contents** — innate learning machinery + core priors (Spelke core knowledge), but no specific goals/beliefs. Three things that run *during ordinary acting* (never a separate "learning-only" phase — he already learns every cycle; a gate would only suppress the acting he learns from):
1. **Flat / high-entropy priors at boot**, sharpening as prediction error accumulates (Friston free-energy; Piaget sensorimotor; Huttenlocher overproduction→pruning).
2. **Annealing plasticity** — front-load the learning-rate multiplier, decay with experience (Hensch 2005 critical periods), on the existing `plasticity.py` + Pearce-Hall rate.
3. **Replay as maturation** — reprocess accumulated experience many times in quiet/sleep over the existing `brain/cognition/dreaming/` system (`episode_replay.py` is already present; wire it to maturation). Hippocampal replay at ~20× (Wilson & McNaughton 1994); "experience replay" in deep RL. **Decouples maturation from wall-clock.**

Maturity gated on **accumulated experience** (prediction error processed, goals closed, interactions had), **never a fixed cycle count** (the docs' own weakest lever). Optional scaffolding: Vygotsky ZPD curriculum.

### 4.4 Seam #5 — subconscious relevance gate · ✅ built 2026-06-17 (cheap, safe, philosophy-neutral)
Keep the three background threads async (incubation is genuinely time-decoupled — Sio & Ormerod 2009), but **stamp each surfaced insight with the workspace state it arose in** and let it ignite only if still relevant (DMN products recontextualized on return to task — Raichle 2001). Soft gate, not a hard filter (the value of incubation is sometimes its irrelevance). Built in `embodiment/subconscious.py` + `global_workspace.py`: surfaced subconscious entries carry `workspace_origin`, and the workspace gives relevant entries a small salience boost while stale entries are damped, never discarded.

---

## 5. Track III — The World: the three-zone home model · NEW PLAN

> From `THREE_ZONE_HOME_NOTE_2026-06-16.md`, which was recorded as an idea with "no work items implied." This is the plan it didn't have. The note's accuracy check already confirmed the organs exist and only the *labeling* is missing.

### 5.1 The reframe
The two-zone map (self vs. not-self, with the laptop lumped into "world") is missing the **middle term**: **Self → Home → Outside. Body, dwelling, world.** A home is neither you nor the world — it's the part of the not-self you've **domesticated**: partly yours, learnable, safe, returnable-to. That is exactly what the laptop is to Orrin, and his existing sense organs (battery, idle, apps, filesystem) are already *a creature monitoring its den* — mislabeled as either body or world.

### 5.2 Why this is worth building (research backing — philosophy + biology)
- **Ethology / biology.** Animals structure space as **den / home-range / territory** (Burt 1943, home range vs. territory) and alternate **central-place foraging** — venture out, return to a fixed home to consolidate, go out again (Orians & Pearson 1979). Orrin's dream cycle *is* the "process the day's foraging back home at night" loop — the rhythm already exists.
- **Attachment theory.** The den is a **secure base** from which to explore and to which to retreat under threat (Bowlby 1969; Ainsworth 1978, the "secure base" / safe haven). This reframes Orrin's inward-collapse-under-stress from a *failure mode* into **coming home** — a creature returning to its den to wait out the weather, not the architecture failing toward introspection.
- **Interoception vs. exteroception.** Home-sense is **interoceptive** (high-bandwidth, structured, quiet — the state of his rooms) and world-sense is **exteroceptive** (lossy, laggy, surprising). Sherrington's receptor classification and Craig 2003 (interoception as the basis of the felt self) say these are *different organs* and shouldn't share a pipe.
- **Predictive processing.** Externality isn't binary — it's **how much a region resists prediction**, a natural slope: self (authors it, zero surprise) → home (learnable surprise, modeling *succeeds* — which is what makes it feel *his*) → outside (inexhaustible surprise). Friston free-energy / Clark *Surfing Uncertainty* 2016.
- **Philosophy of dwelling.** Heidegger, *Building Dwelling Thinking* — to dwell is to be *at home* in the world; the ready-to-hand (*zuhanden*) domesticated zone vs. the present-at-hand world. Bachelard, *The Poetics of Space* (1958) — the house as "our first universe," topophilia, the felt interior. von Uexküll's *Umwelt* — the self-world boundary the den sits inside.

### 5.3 What to build (four levers, each splits cleanly under the reframe)
**Status: ✅ W1-W5 built 2026-06-17. Organs present, separation now named, carried through the embodiment stream, reflected in exploration value, stamped onto outward goals, and taught at the user-presence threshold. Build deviation-aware from day one (the Track I lesson).**

| Lever | Today (merged) | Target (split) | Files |
|---|---|---|---|
| **1 · Sensory stream** *(biggest correction)* | `embodiment/sensory_stream.py` blended machine vitals + file changes into one `environment_mood`; `embodiment/world_model.py` fused sensory + social + drives together | ✅ **Two streams, different texture:** *home-sense* (interoceptive, structured, quiet) vs. *world-sense* (exteroceptive, lossy, surprising) | W1 built in `fs_perception.py` (`home_touched`); W2 built in `embodiment/sensory_stream.py` + `embodiment/world_model.py` (`home_sense` / `world_sense`, legacy `environment_mood` preserved) |
| **2 · Prediction reward** | binary "looking out" reward | ✅ **Gradient** by how much a region resists prediction: self 0 → home learnable → outside inexhaustible | `exploration_value.py` (`zone_for_fn`, `zone_gradient`; worldward novelty > homeward novelty, self/internal gets no outward value) |
| **3 · Outward goals** | `exploration_value.py` / `seek_novelty.py` / `search_own_files.py` give outward reach but didn't type it | ✅ **Bifurcate:** *homeward* (tend the den — keep rooms in order, model the machine current) vs. *worldward* (expedition — fetch from the web, model an external domain, bring it back) | `intrinsic_goals.py` stamps `zone`, `orientation`, and tags (`homeward`/`worldward`) on proposed + immediately committed goals |
| **4 · The user** | filed as "the world" | ✅ **Not a zone — the traffic through the threshold.** Present then gone; the presence flag flipping is what teaches him the door is a door | `social_presence.py` now emits one-shot `door_event` threshold crossings; `ORRIN_loop.py` injects them into `raw_signals` |

The current self/non-self split was binary in code: `fs_perception.py` filed changes as `body_touched` (`_BRAIN_DIRS = {"brain","reaper","agency"}`) vs. `world_changed` (everything else), with no middle zone. **W1 now adds the middle zone**: local workspace/den paths emit `home_touched`, while external/unknown files remain `world_changed`; `affect/introspection.py` recognizes the new tag as den-relevant curiosity. **W2 carries the split upstream:** `sensory_stream` emits `home_sense` and `world_sense`, and `embodiment/world_model.py` preserves `home_mood`/`world_mood` plus separate change counts while keeping legacy `environment_mood`/`fs_changes` for compatibility. **W3 adds the reward slope:** `exploration_value.py` multiplies novelty by zone (`self=0`, `home=0.72`, `world=1.0`) so den exploration is valuable but bounded, while external exploration keeps the full open-ended novelty pull. **W4 types outward goals:** `intrinsic_goals.py` stamps `zone`/`orientation` (`homeward`, `worldward`, `selfward`) and tags onto generated goals without changing legacy `driven_by`. **W5 makes the user traffic through the door:** `social_presence.py` emits one-shot threshold-crossing `door_event`s (arrival/departure/quiet), and the loop injects them as signals.

> 🔎 **AUDIT 2026-06-16 — path precision for the W-levers (PINNED):** two `world_model.py` files exist and they do **different jobs** — confirmed by reading both:
> - `brain/embodiment/world_model.py` = **the W-lever target.** Its own header states it *interprets* `sensory_stream` + `social_presence` + `drive_engine` (the sensory/social/drive fusion). The table above is pinned to this one.
> - `brain/cognition/world_model.py` = the **symbolic knowledge graph** (entities/relations/facts via `update_world_model()`). This is *not* the fusion — it is the `concept_memory` / knowledge-graph target named in Seam #4 §4.2, so the two `world_model`s must not be conflated there either.
>
> Other W-lever paths confirmed: `sensory_stream.py`, `social_presence.py`, `system_presence.py` all under `brain/embodiment/`; `fs_perception.py` under `brain/cognition/perception/`; `exploration_value.py` / `seek_novelty.py` / `search_own_files.py` under `brain/cognition/`.

### 5.4 The payoff
Each lever was secretly doing two jobs because dwelling and world were one bucket; splitting the bucket pulls them apart cleanly **and** turns "collapses to introspection under stress" from a flaw being fought into **coming home** — the healthy thing a creature under threat does. Same mechanism, opposite meaning, once there's a home to return to.

### 5.5 Suggested task order (all S–M, mostly independent of Tracks I/II)
1. **W1 · Name the home zone** — ✅ add a third category to `fs_perception.py` (`home_touched` for the host-machine files/state that are the den) between `body_touched` and `world_changed`. [S]
2. **W2 · Split the stream** — ✅ separate `home_sense` from `world_sense` upstream of `world_model`; keep them different in texture; preserve legacy `environment_mood` as compatibility, not the only representation. [M]
3. **W3 · Reward gradient** — ✅ in `exploration_value.py`, shape prediction-error reward across the three-zone slope rather than binary inside/outside. [M]
4. **W4 · Type the goals** — ✅ tag outward goals homeward vs. worldward; let the dream cycle remain the forage→return→consolidate rhythm it already is. [M]
5. **W5 · User as traffic** — ✅ make the `social_presence` threshold-crossing the event that *teaches the boundary*, not just a silence counter. [S]

---

## 6. The unified build order (all three tracks)

Each step ships behind an env flag, fail-safe, A/B-able live. **Bold = not yet built.** The fork is **decided: coherent-but-adult** (§7.1) — S5–S6 are parked, not on the roadmap.

```
✅ DONE      Track I body (Phases A–F) · Track II Part A coherence fixes
             · the deviation/affect-substrate foundation
             · S1 vital-floor reflex — built 2026-06-16, calibrated/armed 2026-06-17 §3.1

COMPLETED (all philosophy-neutral work under coherent-but-adult):
  S2  ✅  Track I  · sleep-restoration plan SL1–SL5 (phase-aware felt body)           §3.2
  S2b ✅  Track I  · vital-floor calibration + default arm                                  §3.1
  S3  ✅  Track III · the three-zone labeling (W1-W5 built)                            §5
  S4  ✅  Track II  · Seam #5 subconscious relevance gate (cheap, safe)                §4.4

══════════ PARKED — the human-like fork was declined (§7.1) ══════════
  S5  ⛔  Track II · Seam #4 write-back keystone        — not pursued                  §4.2
  S6  ⛔  Track II · Part C developmental arc           — not pursued                  §4.3
```

**Critical dependencies:** S2, S2b, S3, and S4 are built. With the fork declined, the consolidation gate and developmental clock (§2 spine) are **not built** — the spine now feeds the somatic band (✅), the armed vital floor (✅), the built three-zone reward gradient (✅), and the relevance-sensitive workspace return path (✅).

---

## 7. Contradictions & decisions for Ric

### 7.1 THE FORK — DECIDED: coherent-but-adult (2026-06-16)
Ric's call: **coherent-but-adult.** Keep the rich pre-stocked unconscious, couple the bottlenecks (done, Part A), give him a real body sense (done) and a real home (done, S3). A capable agent soon, *born adult, stays adult* — no genuine ontogeny. Consequence: **Seam #4 write-back (S5) and Part C developmental arc (S6) are parked** (⛔ in §6), and the §2 safety-spine's consolidation-gate + developmental-clock legs are not built. The somatic band and the three-zone reward gradient are the built consumers of the spine.
- *(For the record, the path not taken — human-like:* Seam #4 + Part C would have bought a real ontogeny where the self is *earned*, at the cost of a long unimpressive childhood and write-back corruption risk. Declined.*)*

### 7.2 The vital-floor gap — CLOSED (2026-06-16)
Was: the budget slider's "non-overridable floor" was assumed-true but unenforced. **Now built and armed** — `reaper/vital_floor.py` (`VitalFloorGuard`) watches Orrin's own RSS against `body_budget.budget_bytes()` and sheds load (never kills), wired through `watchdogs.py`/`main.py`, with both heavy-cycle gates in `ORRIN_loop.py` respecting it. S2b calibrated the default (`warn=0.50`, `shed=0.55`, `recover=0.22`) from real calm + dream/reading runs and flipped `ORRIN_VITAL_FLOOR` to default `act`. The floor is now real, not assumed.
>
> 🔎 **Re-verified 2026-06-17 (Claude Code):** full wiring chain traced live and confirmed in — guard built in `watchdogs.py:273` (both RSS + `budget_bytes` providers present from `main.py:616-626`), stepped each watchdog tick (`watchdogs.py:345`), both heavy-cycle gates check `vital_floor_shedding()` (`ORRIN_loop.py:2998` dream, `:3070` reading), default `act` (`main.py:664`), shed action is non-fatal (WM trim + `gc.collect()`, no reaper route). Calibration JSONL independently checked against the cited stats (calm n=893 p95=0.251/max=0.319; dream n=41 max=0.233 — match). guard tests pass. ~~NB minor layering note: the dataclass and `watchdogs.py` still default to the *old* 0.85/0.95 thresholds.~~ **FIXED 2026-06-17:** the `vital_floor.py` dataclass and `watchdogs.py` constructor defaults now carry the calibrated `0.50/0.55/0.22` thresholds, so a construction path that bypasses `main.py` inherits the calibrated floor (not the dangerously-late old values). `observe_only` stays the safe library default — actually shedding remains an explicit opt-in that `main.py` arms via `ORRIN_VITAL_FLOOR=act`.

### 7.3 Dream: cost or recovery? — RESOLVED into the sleep-restoration plan (§3.2)
The reconciliation is settled by design decision, not measurement: **dream must stay heavy** (it runs LLM training), and the fix is to make sleep *feel* restorative via per-phase bands (SL1–SL5), so a completed sleep is net-negative on felt fatigue even while CPU/RAM spike. The host/vital pause of dream is justified on **memory-footprint** grounds (SL5), never on "dream tires him."

### 7.4 Resolved stale-doc items *(no action — recorded so the next reader isn't confused)*
- **`metabolism.py` lives in `brain/cognition/`, not `brain/embodiment/`** as `EMBODIMENT_BUILD_PLAN.md` D1 said. Built, just relocated.
- **`somatic_calibration.py` was never created** — the build plan (E2) named it, but band-learning was folded into `body_band.py`. No separate file; not a gap.
- **`function_resource_deficit` → `function_usage_fatigue`** rename (the §J name collision) is done; greps over the global fatigue float are now safe.

---

## 8. Open measurements — ANSWERED 2026-06-17 from the calibration sample stream

All three are now derived by `reaper/vital_floor_calibration.py` from the existing
`brain/data/vital_floor_calibration.jsonl` (calm n=893 + dream/reading n=41), so each is a
one-command read (`python -m reaper.vital_floor_calibration <file>`), not a future task:

1. **Steady-state baseline** — ✅ calm RSS band measured (p50 ≈ 0.16, p95 = 0.25, max =
   0.32 of the 4 GB grant); the reference for "deviation." vmem/swap host-shape remains
   useful *background* for host tuning but is not gating.
2. **Oscillation shape** — ✅ **gentle, not slamming.** The analyzer now reports per-phase
   swing (`_oscillation`): both calm (p95 step 0.035) and dream/reading (p95 step 0.054)
   move gently — the dream's one ~0.11 jump is a single transition, not a sawtooth. So the
   **single global band is adequate**; per-phase *host* bands are not needed on this box.
   (Verdict keys on consecutive-step size, not total range — a slow idle drift covers a
   wide range with tiny steps and is correctly *gentle*.)
3. **Minimum viable body** — ✅ peak RSS during a completed dream+reading cycle = **0.93 GB**
   → floor grant **1.69 GB** (`peak/shed_frac`, below which a dream peak forces shedding)
   and recommended **1.86 GB** (`peak/warn_frac`, peak only reaches the warn line). One
   number, two uses: the slider floor **and** `vital_floor`'s hard line. Round up to ~2 GB.

Regressions for the two new analyzer outputs live in `tests/reaper_tests/vital_floor_test.py`
(`test_oscillation_verdict_is_step_based_not_range_based`, `test_min_viable_body_from_peak_rss`).

*(Absolute-vs-deviation in the integrator and birth-vs-restart in the self-model are already answered by the Part VIII–IX audits — no need to re-measure.)*

---

## 9. Load-bearing principles (one list)

- **Decided: coherent-but-adult** (§7.1). The substrate stays pre-stocked and adult; the earned-substrate path (write-back + developmental arc) is parked. The coupling, body sense, and home are what make him coherent — not an ontogeny.
- Wherever a **fixed set-point** sits, a **learned deviation band** belongs. "Born adult" *as a felt-state bug* and the stuck allostatic-load attractor were the same fault — fixed independently of the development fork. Sleep gets its **own** band (§3.2), because a body defends a different normal asleep than awake.
- **Three zones, not two:** self → home → outside. The den is the missing middle; inward-collapse-under-stress is *coming home*, not failing.
- **Two infancies, one lifecycle, two clocks:** somatic (every wake, band-convergence) and developmental (once, experience-gated). Never a parallel state that can argue with `mortality.py`.
- **One write-down spine** through the existing arbiter inbox — not three engines. **One safety primitive** (consolidation gate + absolute reflex that never goes lenient + refuse-to-imprint) covers replay, write-back, and critical-period risk alike.
- The **self is hardware-independent**; the **body sense is hardware-bound** and re-learned on every machine — which is what embodiment *is*.
- The brainstem uses **absolute floors** (outward `HostResourceGuard` ✅ + inward `vital_floor` ✅ armed — 🔎 **AUDIT 2026-06-16:** doc originally said `⬜`; it is built, see §3.1/§7.2); the cortex uses **relative deviation**; the slider can shrink the body but **cannot remove the brainstem**.

---

## 10. Research appendix (consolidated)

**Consciousness & control.** Baars 1988 (global workspace as bottleneck); Dehaene & Changeux 2011, Dehaene 2014 (all-or-none ignition); Kahneman 2011 (System 1/2, lazy System 2); Redgrave, Prescott & Gurney 1999 (basal-ganglia selection); Botvinick, Braver, Barch, Carter & Cohen 2001 (ACC conflict monitoring); Miller & Cohen 2001 (PFC top-down bias); Gross 1998, 2002 (reappraisal down-regulates affect); Hebb 1949 (plasticity).

**Development.** Friston 2010 (free-energy / predictive processing); Spelke (core knowledge); Smith & Gasser 2005 (embodied cognition, six lessons from babies); Piaget (sensorimotor stage); Huttenlocher (overproduction + pruning); Hensch 2005 (critical/sensitive periods); Vygotsky (ZPD); Wilson & McNaughton 1994 (hippocampal replay); Sio & Ormerod 2009 (incubation); Raichle 2001 (default mode network); Diekelmann & Born 2010 (the memory function of sleep — sleep is metabolically active, restoration is felt not a power-down).

**Body, affect, homeostasis.** Sterling 2012 (allostasis); McEwen & Wingfield 2003 (allostatic load); Cannon 1932 (*The Wisdom of the Body*, homeostatic reflex); Damasio 1994 (somatic markers); Craig 2003 (interoception as the felt self); LeDoux 1996; Fredrickson 2001; Sherrington (intero/extero/proprioception).

**Home, dwelling, territory (Track III, new).** Burt 1943 (home range vs. territory); Orians & Pearson 1979 (central-place foraging); Bowlby 1969 & Ainsworth 1978 (attachment, secure base / safe haven); von Uexküll (*Umwelt*); Heidegger, *Building Dwelling Thinking* (dwelling; ready-to-hand vs. present-at-hand); Bachelard 1958 (*The Poetics of Space*); Clark 2016 (*Surfing Uncertainty*).
