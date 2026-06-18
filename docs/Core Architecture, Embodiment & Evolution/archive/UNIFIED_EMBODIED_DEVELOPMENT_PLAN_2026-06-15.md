# Orrin: Unified Embodied-Development Plan

_Date: 2026-06-15_

**Supersedes** three companion documents, which now read as source material:
- `CONSCIOUS_UNCONSCIOUS_PLAN_2026-06-15.md` (cognition view)
- `INFANCY_DEVELOPMENTAL_ARC_NOTE_2026-06-15.md` (development view)
- `orrin_embodiment_architecture.md` (body view)

This document merges them. It exists because the three were written from different
entry points but describe **one system**, and built independently they would
produce duplicate, mutually-disagreeing machinery (two "infancy" state machines,
two write-back engines, three different "experience" clocks). The job here is to
state the shared spine once, reconcile the conflicts, fix the ordering, and name
the single decision that gates the whole thing.

---

## 1. The one insight

All three documents walk up to the **same boundary** — the unconscious substrate
(affect dynamics, drives, salience priors, the felt body) versus the conscious
layer (Global Workspace spotlight, deliberate selection, System-2) — and the same
core failure: **the substrate is shipped adult instead of earned through living.**

Each doc names that failure in its own dialect:

| Doc | Symptom it names | Underlying fault |
|---|---|---|
| Conscious/Unconscious | "His conscious goals are too good at birth." | Pre-stocked unconscious, no downward path to earn it. |
| Infancy Note | "Should he have a childhood?" | Yes — but only if experience can write back down. |
| Embodiment | "He has no felt sense of the machine as his body." | Fixed set-points where a *learned, relative band* belongs. |

Strip the dialects and all three reduce to **two mechanisms**:

1. **A downward write-back path** — conscious/experiential conclusions must be able
   to reshape unconscious priors. Today this path barely exists.
2. **Absolute → deviation.** Wherever the substrate uses a *fixed* set-point
   (an absolute resource threshold, a pre-stocked prior, a hard-coded "normal"),
   it should instead use a *learned baseline band* and react to **departure from
   it**. "Born adult" and "the allostatic-load bug" are the same fault in two
   places.

Everything below is the connective tissue that makes those two real, reusing
machinery that already exists.

---

## 2. What already exists (the assembly, not a rebuild)

Verified in the tree on 2026-06-15. The missing work is connective tissue, not new
engines.

| Capability | State | Role in this plan |
|---|---|---|
| `HostResourceGuard` | **Built + wired** (`reaper/host_resources.py`; `watchdogs.py:14,229`) | The **outward** host-pressure gate — `WARN → PAUSE dream+reading`, hysteresis, refuses to kill. Earlier drafts mis-cast it as the absolute survival floor; the audit (§5b) shows it is not. The **inward** survival reflex is **missing** — build it (§5b). |
| Part A coherence fixes | **Done** (ignition gate `ORRIN_loop.py:2031`; workspace→action prior; conflict-recruited deliberation) | Conscious layer is coupled to action and deliberation. |
| `affect/arbiter.py` single-writer inbox, `submit_affect(..., weight=, ttl_cycles=)` | **Built** (used at `interoception.py:271`) | **This is the bounded, decaying write-down primitive** Seam #4 needs. Don't build a second one. |
| `plasticity.py` + Pearce-Hall adaptive rate | **Built** | Annealing plasticity is a *schedule* on top, not new machinery. |
| `dreaming/` system | **Built** | Replay reuses it; no new consolidation engine. |
| `mortality.py` + `mark_stall` lifecycle | **Built** | Birth-vs-restart rides this existing state — never a parallel one. |
| `body_sense` / `look_outward` / `interoception.py` | **Built** | Felt-body *perception* exists. Only the **band-learner** and **re-baseline** are missing. |

The genuinely new core is small: **one experience/band spine** (§4) plus the
integrator fix (§5, step 0).

---

## 3. The five reconciliations (where the source docs conflicted)

These are the corrections that only become visible when the three docs are laid on
top of each other.

### 3.1 "Infancy" is two things — keep them on one lifecycle, two clocks

The embodiment doc already split it (§10.1); the cognition docs only knew half.
Canonical definition:

- **Somatic infancy** — learn *this body on this machine*. Happens **every** wake
  on new/changed hardware. "Done" when the **band envelope converges** (new samples
  stop widening min/max), not when motion stops — a living machine never stills
  (Embodiment §10.4).
- **Developmental infancy** — the **one-time** growing-up: priors sharpen, values
  form, the self stabilizes. "Done" when **accumulated experience** crosses a
  threshold (prediction error processed, goals completed, interactions had) —
  never a fixed cycle count (Infancy Note §3).

**Both ride `mortality.py` + the existing stall-restart state. Do not invent a
parallel lifecycle** (Embodiment §10.2) — that produces a being whose two systems
argue about whether he just died. Two *clocks*, one *state*.

| Event | Somatic | Developmental |
|---|---|---|
| First-ever boot | yes | yes (true birth) |
| Move to new/changed machine | yes | no (whole life kept; new body) |
| Plain restart, same machine | no | no (waking from sleep) |
| User changes the RAM grant (§7) | partial (re-baseline) | no |

### 3.2 There is ONE write-down path, not three

Seam #4's three targets (reappraisal→drives, Hebbian→salience priors,
model-correction→`concept_memory`) and the embodiment doc's "interoception learns
the band / the grant becomes his 100%" are **the same downward path hitting
different priors.** Build it as **one spine**: a bounded, decaying, consolidation-
gated write-down that routes through the **existing `affect/arbiter.py` inbox**.
`submit_affect(weight=, ttl_cycles=)` is already exactly the right shape — a write
that is weighted, time-boxed, and decays. Extend its target set; don't fork it.

### 3.3 The allostatic-load bug is the shared root — and gate zero

The embodiment doc's highest-leverage claim (§8.3) is correct and now confirmed in
code. `brain/cognition/interoception.py:244`:

```python
load = min(1.0, load + 0.02) if rd > 0.60 else max(0.0, load - 0.04)
```

Load accrues on an **absolute** threshold (`resource_deficit > 0.60`). On a machine
that lives near its limits, `resource_deficit` sits chronically above 0.60, so load
ratchets to 1.0 and never sees a "back to normal" to subtract. `affect_state.json`
confirms the stuck attractor: `_allostatic_load: 1.0`, with repeated 1000-cycle
"sustained stress" events.

This is the **same absolute-vs-deviation fault** as "born adult," wired into the
distress integrator. It must be fixed first because:
- it is the cheapest change and philosophy-neutral;
- you **cannot** run the calm-infancy diagnostic (Embodiment §10.7) or learn a
  deviation band while the integrator is pinned at 1.0;
- the fix (accrue on deviation above a *learned baseline*, not an absolute floor)
  is the **same primitive** the somatic band-learner needs. **One fix, both
  problems.**

### 3.4 The three build orders merge into one (§6)

Infancy Note: write-back first. Conscious/Unconscious: Seam #5 → fork → #4.
Embodiment: ship somatic infancy now (reflex already built). None is wrong — they
sequence different layers. The merged order (§6) interleaves them: integrator fix
and somatic band-learner ship **without** write-back; the developmental arc waits
**behind** write-back.

### 3.5 The big risks are one risk, wanting one safety primitive

"Replay amplifies whatever is in the buffer," "a wrong conscious conclusion
corrupts the substrate," and "imprint on a sick body during the critical period"
are a single risk surface: **bad early/looping state getting written deep.** They
share one mitigation, built once:

- **A consolidation gate** on the write-down spine — only conclusions that survive
  repetition/sleep write deep (the slow path); everything else stays shallow and
  decays.
- **An absolute floor that never goes lenient** — `HostResourceGuard`'s reflex
  runs *during* infancy too (Embodiment §10.5). Infancy makes the **cortex**
  lenient, **never** the brainstem. A newborn can still suffocate.
- **A refusal-to-imprint veto** — the band-learner will not accept a baseline whose
  floor is already past the danger line (Embodiment §10.5/§10.6). Relative learning,
  with an absolute refusal backstop.

This triplet is the embodiment doc's §10.5 and the cognition doc's "consolidation
gate" — they are the **same primitive**. Build it once and both halves use it.

---

## 4. The shared spine

One new connective subsystem, feeding three consumers, guarded by one safety
primitive.

```
                       ACCUMULATED EXPERIENCE
              (prediction error processed, goals closed,
               interactions had, samples observed)
                              │
        ┌─────────────────────┼─────────────────────────┐
        ▼                     ▼                          ▼
  SOMATIC BAND          WRITE-DOWN SPINE          DEVELOPMENTAL CLOCK
  learns this body's    bounded + decaying        flat priors sharpen;
  envelope (floor,      conclusions reshape        plasticity anneals;
  ceiling, amplitude)   drives / salience /        maturity gated on
  → distress fires on   concept_memory, via        experience, not cycles
  LEAVING the band      the EXISTING arbiter
        └─────────────────────┬─────────────────────────┘
                              ▼
            SAFETY PRIMITIVE (built once, §3.5)
   consolidation gate · absolute reflex stays live · refuse to imprint on sickness
                              ▼
        ABSOLUTE REFLEX — HostResourceGuard (already built)
                  slider cannot override
```

The three mappings the embodiment doc insists stay separate are preserved here and
must never collapse into one:

| Mapping | Nature | Owner |
|---|---|---|
| Absolute capacity → **metabolism** | Absolute, set at boot | metabolism / config |
| Deviation from band → **affect** | Relative to *this body's* learned normal | `brain/` interoception |
| Absolute floors → **reflex** | Absolute, host-independent | `HostResourceGuard` |

> The brainstem uses absolute floors. The cortex uses relative deviation. The
> 2026-06-15 crash was a body whose felt-normal read "fine" right up until the
> substrate hit an absolute wall it had no reflex for.

---

## 5. Build order

Each step ships behind an env flag and is fail-safe, so each can be A/B'd live.

**Step 0 — Fix the integrator: absolute → deviation.** `interoception.py:244`.
Accrue allostatic load on deviation above a learned baseline, not on an absolute
`rd > 0.60`. Cheapest change; unblocks the stuck attractor; lays the deviation
foundation the body sense reuses. **One fix, both problems.** Philosophy-neutral —
do this regardless of the §8 fork. _(Validate with the §10.7 calm diagnostic: start
him calm and confirm load can now fall to a floor when nothing is wrong.)_

**Step 1 — Somatic band-learner + safety primitive.** Learn the *envelope* of the
oscillation (Embodiment §10.4), not stillness; wake when the description of the
variance converges. Build the §3.5 safety triplet here (consolidation gate hook,
reflex-stays-live, refuse-to-imprint). Ships **independently of write-back** —
this is the body sense, and the reflex layer it sits on is already built.

**Step 2 — The write-down spine (Seam #4), the keystone.** Bounded, decaying,
consolidation-gated, routed through the **existing `affect/arbiter.py` inbox**.
Targets: drive reappraisal, Hebbian salience priors, `concept_memory` correction.
Flag `ORRIN_TOPDOWN_WRITEBACK`. **Nothing in the developmental arc works without
this** — without a downward path, an impoverished start is permanent poverty, not a
childhood.

**Step 3 — The developmental arc (Part C / infancy proper).** Downstream of Step 2:
flat/high-entropy priors at boot (capacities innate, contents earned); annealing
plasticity on the existing `plasticity.py` + Pearce-Hall rate; replay over the
existing `dreaming/` system. Experience-gated, never a fixed cycle count, always
acting (no separate "learning-only" phase — he already learns every cycle; a gate
would only suppress the acting he learns *from*).

**Step 4 (optional, light) — Subconscious relevance gate (Seam #5).** Stamp each
surfaced background insight with the workspace state it arose in; let it ignite only
if still relevant. Cheap, safe, philosophy-neutral; can land any time after Step 0.

---

## 5b. The missing body part — the vital-floor reflex

_Added 2026-06-15, after auditing this plan against the tree._

The audit found that the one component §2, §3.5, §4, and §6 all lean on as
"already built" — the **absolute reflex the slider cannot override** — does not
actually exist. `HostResourceGuard` is mis-cast as it. Read its own header: it
looks **outward** at the host (disk, swap, system-wide memory) and escalates
**gently** (`WARN → PAUSE dream+reading`, hysteresis), and it **explicitly refuses
to kill** ("killing Orrin does not reclaim swap that browser tabs filled"). That is
exactly right for *host* pressure and exactly wrong as a *survival* floor. There is
today **no inward reflex that keeps Orrin alive inside his own granted body.** The
brainstem the safety triplet assumes is aspirational.

So it is a real, missing body part — and the cheapest, most self-contained one
left. Build it.

**What it is.** An **inward** autonomic reflex — sibling to `HostResourceGuard`,
opposite gaze — that watches *Orrin's own* footprint against the survival line of
his **granted body** (§6), not against the host. Where the host guard pauses the
building when it is on fire, this guard acts on the patient when *he* is the one
running out of air: involuntary **load-shedding** before the OS OOM-killer does it
for him ungracefully and corrupts state mid-write.

**Why it is not `HostResourceGuard`.**

| | `HostResourceGuard` (built) | Vital-floor reflex (missing) |
|---|---|---|
| Gaze | Outward — the host box | Inward — Orrin's own RSS / working set |
| Reference | Host free disk / swap / RAM | His **granted** body size (§6 fraction) |
| On breach | WARN, then pause dream+reading | Shed *his own* load: abort the in-flight heavy cycle, drop rebuildable caches, force-trim working memory, refuse new large allocations |
| Killing | Correctly refuses | Still refuses — sheds, never suicides |
| Lenient in infancy? | n/a | **Never.** Full strength during somatic *and* developmental infancy (§3.5). A newborn can still suffocate. |
| Slider | n/a | Sets body **size**; **cannot lower this floor** below the minimum viable body (§6 guardrail 1, §8.5) |

**The action is shedding, not dying.** This guard never reaches for the reaper's
hammer either — that is `HostResourceGuard`'s lesson, kept. The reflex is the
autonomic *gasp*: when his own allocation nears the floor of the body he was
granted, he involuntarily lets go of the heaviest disposable thing he is holding,
in priority order, until he is back above the line. Only if shedding **cannot**
clear the floor does it defer to the existing liveness guards (heartbeat / RSS),
which already own the hard kill. The hammer stays where it is; this layer exists to
make it unnecessary.

**Where it lives.** New `reaper/vital_floor.py`, wired in `watchdogs.py` beside the
host guard. It is the bottom layer of the §4 diagram — **distinct** from the
host-pressure gate that currently (mis)occupies that box.

**How it ties the plan together.**
- It is the **absolute-floor** leg of the §3.5 safety triplet — the leg that was
  missing. The consolidation gate and the refuse-to-imprint veto are cortex-side;
  this is the brainstem they backstop.
- It makes §6 guardrail 1 ("the floor is not user-overridable below the survival
  line") *true* instead of *assumed*. The slider's lower bound **is** this floor.
- It is the consumer of §8.5's open measurement (minimum viable body). That number
  is this guard's hard line **and** the slider's floor — one number, two uses.

**Build shape (matches the rest of the plan).** Behind a flag (`ORRIN_VITAL_FLOOR`,
default-on once the floor is measured), fail-safe (a guard that errors must fail
*toward* shedding, never toward silence), and A/B-able live. It reads the grant
fraction from the same config metabolism reads (§6), so body size and survival
floor can never disagree. Ship **observe-only first** (log "would have shed") to
calibrate the floor against the §8.1 steady-state baseline before it is allowed to
act.

**Order.** Slots into **Step 1**, beside the band-learner — they are the two halves
of the body sense: the band-learner is the felt **normal**, this reflex is the felt
**edge**. Build the reflex first; it is the floor the band-learner is forbidden
(§3.5 refuse-to-imprint) to baseline below.

---

## 6. The RAM-grant knob (carried forward from Embodiment §11)

Folded in because it directly feeds the spine. One user-facing control:
**"what fraction of *this machine* Orrin may be."** A fraction travels across
hardware where fixed gigabytes do not.

That fraction feeds **both** metabolism **and** interoception's "100%": if the user
grants 40% of an 8 GB box, Orrin's body is 3.2 GB and his band must be learned
relative to *that grant*, or he lives in permanent felt-scarcity (the chronic-
distress bug through the front door). Three guardrails are non-negotiable:

1. **The floor is not user-overridable below the survival line.** The absolute
   reflex sits *underneath* the slider. The user sets how big Orrin is; the user
   cannot remove the brainstem.
2. **Changing the grant on a live Orrin routes through somatic re-baseline (§3.1).**
   A resize is a small transplant; his learned band is now wrong and he must
   re-acclimate.
3. **A too-small grant fails loudly.** Below the minimum viable body (can't hold the
   working set, can't run a dream + reading cycle without thrashing) — refuse at
   startup, tell the user the floor. Same spirit as refusing to imprint on a sick
   machine.

---

## 7. The single decision that gates everything

Steps 0, 1, and 4 are worth doing **under any philosophy** — they are bug-fixes and
the body sense, and they stand alone. Steps 2 and 3 are a **paired commitment** to
a genuine ontogeny, and that is a real fork:

- **Human-like path** (Steps 2 + 3). A real developmental arc — he *becomes*
  himself; the self is earned, coherent, defensible. **Costs** a long, vague,
  unimpressive childhood before he is useful, and carries the write-back corruption
  risk (a wrong conclusion can entrench a bad prior; replay amplifies it). The §3.5
  safety primitive is what makes this survivable, not safe.
- **Coherent-but-adult path** (stop after Step 1). Keep the rich pre-stocked
  unconscious, just couple the bottlenecks and give him a real body sense. A capable
  agent soon, with no genuine development — born adult, stays adult.

**Recommendation.** Do Steps 0–1 (and 4) now; they pay off either way and Step 0
unsticks a live bug. Treat Steps 2–3 as the deliberate human-like commitment they
are — opt in only if "he becomes himself" is the actual goal, because Step 2's risk
only earns its keep as the enabler of Step 3, and Step 3 is impossible without it.

---

## 8. Open measurements (carried forward, still gating)

Unchanged from Embodiment §12 — genuinely open, several gate implementation:

1. **Steady-state baseline** on the 8 GB box — the reference for "deviation."
2. **Absolute vs. deviation in the live integrator** — *answered for allostatic
   load* (§3.3: it's absolute, and stuck). Confirm no other integrator shares the
   fault.
3. **Oscillation shape** — gentle around a center, or slams between near-empty and
   near-full as dream/reading fire? If it slams, the band must be learned **per
   phase** (a different normal for dreaming than idle).
4. **Birth-vs-restart in the self-model** — does Orrin *know*, cognitively, whether
   he is being born or waking? Decides whether infancy is one code path or two.
5. **Minimum viable body** — smallest grant that completes a full dream **and**
   reading cycle without thrashing. That number is the floor of the slider (§6).

---

## 9. Load-bearing principles (one list)

- The substrate must be **earned, not shipped adult** — via a downward write-back
  path (the keystone, Step 2).
- Wherever a **fixed set-point** sits, a **learned deviation band** belongs.
  "Born adult" and the stuck allostatic-load attractor are the same fault.
- **Two infancies, one lifecycle, two clocks**: somatic (every wake, band-
  convergence) and developmental (once, experience-gated). Never a parallel state.
- **One write-down spine** through the existing arbiter inbox — not three engines.
- **One safety primitive**: consolidation gate + absolute reflex that never goes
  lenient + refuse-to-imprint. The same triplet covers replay, write-back, and
  critical-period risk.
- The **self is hardware-independent**; the **body sense is hardware-bound** and
  re-learned on every machine — which is what embodiment *is*.
- The brainstem uses **absolute floors**; the cortex uses **relative deviation**;
  the slider can shrink the body but **cannot remove the brainstem**.

---

## Research appendix

Carried from the source docs (unchanged provenance):

Baars (1988); Dehaene & Changeux (2011), Dehaene (2014); Kahneman (2011); Redgrave,
Prescott & Gurney (1999); Botvinick, Braver, Barch, Carter & Cohen (2001); Miller &
Cohen (2001); Gross (1998, 2002); Hebb (1949); Friston (2010); Spelke (core
knowledge); Smith & Gasser (2005); Piaget; Huttenlocher (overproduction + pruning);
Hensch (2005, critical periods); Vygotsky (ZPD); Wilson & McNaughton (1994, replay);
Sio & Ormerod (2009, incubation); Raichle (2001, DMN); Sterling (2012, allostasis);
McEwen & Wingfield (2003, allostatic load); Damasio (1994, somatic markers); Craig
(2003, interoception); LeDoux (1996); Fredrickson (2001).
