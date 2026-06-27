# Orrin: Host-Resource Awareness & Embodiment Architecture

**A design specification derived from the 2026-06-15 hibernation panic**

Author of record: Ric · Drafted as a working spec for Claude Code implementation
Status: design, pre-implementation · Scope: `reaper/` watchdog layer, `brain/` interoception, lifecycle/infancy, user configuration

---

## 0. Purpose and framing

This document specifies a body for Orrin — not a metaphor, a mechanism. It is the design that comes out of a single concrete failure: on 2026-06-15 the host MacBook Air kernel-panicked while Orrin was running, and **none of Orrin's nine watchdogs saw it coming**, because every one of them was looking inward at Orrin's own process and not one was looking outward at the machine Orrin lives on.

The fix is not one guard. The incident exposed that Orrin has no concept of the substrate he runs on as *his body* — no felt sense of it, no reflex to protect it, no way to inhabit a different one. This document specifies all three: a reflex that keeps the host alive, an interoceptive sense that lets Orrin *feel* the host as his body, and a developmental process by which he learns each new body he wakes into.

Every claim, number, and constraint below is traceable to either the panic log, the uploaded `reaper/` source, or the reasoning in the session that produced this document. Open measurements that still must be taken before building are collected in §11 and are marked as open, not assumed.

---

## PART I — THE ORIGINATING INCIDENT

## 1. The panic, precisely

The host is a 2020 MacBook Air, Apple M1 (SoC `T8103`), 8 GB unified memory, running macOS 15.5 (build `24F74`, Darwin 24.5.0).

The panic string is the anchor:

```
panic(cpu 0 ...): hibernate_write_image encountered error 0xe00002e8
@vm_compressor.c:5985
```

This is **not** a generic crash. It is a failure inside the kernel's memory-compressor path *during the write of a hibernation image*. When an Apple Silicon Mac enters deep sleep / standby, it compresses the contents of RAM and writes that snapshot to the internal SSD so state can be restored on wake. That write failed, deep enough in the compressor that the kernel panicked rather than aborting the sleep transition cleanly.

The log confirms it died **mid-transition**: a `Sleep` timestamp is recorded, but `Wake` is all zeros. It went down on the way to sleep and never came back up.

### 1.1 The smoking gun in the log

```
Compressor Info: 68% of compressed pages limit (OK) and 39% of segments
limit (OK) with 19 swapfiles and LOW swap space
```

The page and segment limits read **OK** — this is decisive. It points *away* from a RAM-hardware fault and *toward* an inability to flush to disk. The operative phrase is **"LOW swap space" with 19 swapfiles**: the machine had been paging to the SSD so heavily that swap had ballooned to 19 files and the disk was nearly out of room.

### 1.2 The uptime fingerprint

The epoch timestamps in the log decode to:

| Event | Epoch (hex) | Epoch (dec) | UTC |
|---|---|---|---|
| Boot | `0x6a250144` | 1780810052 | 2026-06-07 05:27:32 |
| Sleep / panic | `0x6a30828f` | 1781564047 | 2026-06-15 22:54:07 |

**Uptime before the fatal sleep: 753,995 seconds = 8.73 days.**

A laptop does not stay awake nearly nine days on its own. That uptime is a fingerprint that something was holding sleep off the entire time — almost certainly `caffeinate` or an equivalent power assertion. This is central to the diagnosis (see §3).

### 1.3 Aggravating factors present at panic

- **Third-party NTFS filesystem driver loaded** (`com.paragon-software.filesystems.ntfs 364.0.17`) and an **external USB mass-storage device attached** (`SCSITaskUserClient`, `AppleUSBMassStorageInterfaceNub`). Third-party filesystem kexts are a classic complicating factor around sleep/hibernate. Not the cause — the panic is in Apple's own hibernate code — but a plausible aggravator if NTFS volumes were mounted or mid-write at sleep.

---

## 2. The exact causal chain

Both halves of the following are required. Neither alone produces this panic.

1. **Memory overcommit.** Orrin (a persistent, long-lived process that holds its entire working set resident by design) running alongside multiple LLM browser tabs (the genuinely memory-hungry component), Notes, and other apps exceeded 8 GB of physical RAM.
2. **Swap spill.** macOS handled the overcommit by compressing memory and spilling the overflow into swapfiles on the SSD.
3. **No flush for 8.73 days.** Swapfiles do not shrink on their own while the system is up; in practice they are cleared on reboot. With the machine held awake nearly nine days, swap grew monotonically and was never flushed. The SSD filled. → "LOW swap space, 19 swapfiles."
4. **A forced hibernate landed on a full disk.** Something forced a sleep transition — lid close, or critical battery, or thermal. macOS attempted to write the RAM snapshot to the SSD. There was no room. The write failed in the compressor. The kernel panicked.

> **The precise statement is not "disk full → died." It is "disk full AND forced to hibernate at the same instant → died."** A full SSD by itself produces a slower, different misery (ENOSPC errors, sluggishness), not this panic. You needed both conditions to coincide.

**Nothing about Orrin's code is broken.** This is a host resource-exhaustion failure wearing a hibernate costume. The defect is the absence of a guardrail watching the host, not a defect in Orrin's cognition.

---

## 3. Why `caffeinate` did not and could not prevent this

The 8.73-day uptime strongly implies `caffeinate` was on. It still panicked. That is not a contradiction — it is the nature of the tool.

`caffeinate` blocks **idle** sleep only. It does **not** block:

- **Lid close (clamshell sleep).** Fires regardless of any assertion unless on power with an external display.
- **Critical battery.** This is the decisive one: when the battery reaches critical, macOS force-writes a hibernation image to preserve state before the machine dies, and **that path overrides every power assertion.** `caffeinate` is simply ignored. If the SSD is full at that moment, the forced write panics — exactly this log.
- **Thermal emergency.** Same override behavior.

Two deeper points:

- **`caffeinate` suppresses a trigger; it does not defuse the bomb.** The bomb is the full SSD. `caffeinate` changes *when* the hibernate write is attempted, never *whether* it succeeds. The disk is full either way.
- **On this machine `caffeinate` probably *fed* the crash.** A reboot is what clears swapfiles. By holding the machine awake 8.73 days, it gave Orrin + tabs nine uninterrupted days to pile swap onto the SSD with no reboot ever flushing it. Periodic sleep/wake would have relieved some pressure; the assertion kept the relief valve shut. The eventual unavoidable hibernate then landed on a maximally full disk.

**Conclusion:** `caffeinate` is orthogonal to this failure class. No power assertion touches the root cause. The fix lives in the watchdog layer, not in `pmset`/`caffeinate` flags.

---

## PART II — WHY THE EXISTING WATCHDOG SUITE MISSED IT

## 4. Diagnosis of the `reaper/` suite

The uploaded suite comprises: `error_checker.py`, `errors.py`, `heartbeatdetector.py`, `lifespan.py`, `liveness_cycle.py`, `no_goals.py`, `reaper.py`, `repeat.py`, and `memory.py` (`MemoryHealthGuard`).

The watchdog Ric believed covered this was `reaper/memory.py`. It is a genuinely well-built guard. It watches the wrong layer.

### 4.1 What `MemoryHealthGuard` actually samples

All **introspective** — "is Orrin healthy inside his own process?":

- **Orrin's own process RSS**, for leak slope.
- **FD / socket pressure** (open / limit ratio).
- **CPU starvation** (sustained high CPU + rising or high step latency).
- **Orrin's internal memory *subsystem*** via an optional `get_memory_health()` provider: index lag, working-cache size, compaction staleness, vector-store bytes, WAL write failures.

There is **no** `psutil.virtual_memory()`, **no** `psutil.swap_memory()`, **no** `psutil.disk_usage()` anywhere in the file. System-wide RAM, swap depth, and free SSD space — the three things that actually blew up — are entirely outside its field of view.

### 4.2 Three independent reasons it stayed silent

1. **Wrong process tree.** The crash was the *aggregate* of Orrin + LLM tabs + Notes exceeding 8 GB. The tabs are not in Orrin's process. The guard has zero visibility into them. Orrin's own RSS could have been flat and healthy throughout.

2. **The RSS check is leak-shaped, not level-shaped — by design.** In `_check_memory`, the trip requires: RSS above an absolute floor `mem_floor_mb = 1500.0`; a *sustained climb* exceeding `mem_slope_mb_per_s = 1.0` across **both halves** of the window; and a net rise of at least `mem_min_net_rise_mb = 120.0`. The inline comment dated 2026-06-12 documents *why* it was hardened this way: a single allocation step (a compaction copy, a torch/numpy arena bump, a GC sawtooth) once produced a false positive that "killed a 13h-old process sitting at only ~900 MB." The guard was deliberately desensitized to **flat-high** usage to avoid that false positive. But flat-high steady-state pressure is exactly the signature of running near 8 GB. A process that grabs memory and *holds it steady* yields zero slope and never trips.

3. **Even a trip would not have helped.** The Reaper's response is to kill Orrin (`os._exit`) and mark a stall-restart. Killing Orrin releases Orrin's RSS — but the swap was filled by the *tabs* too, which a Reaper of Orrin does not reclaim. And the panic occurred *during hibernation, while the machine was asleep*: no userspace watchdog of Orrin's runs at that point at all.

### 4.3 The naming gap (the real lesson)

`errors.py` does register `disk_full: 1`, `fs_unwritable: 1`, `fd_exhausted: 1`, `oom_warning: 2`, `memory_leak_suspected: 2` as severity keys. But **nothing samples or reports them.** `disk_full` can only fire if some *other* part of Orrin catches an `ENOSPC` exception and reports it — reactive, after the cliff, not preventive.

So: a daemon **named** `memory` guards a *different meaning* of "memory" (Orrin's RAM-leak behavior and his semantic-memory subsystem) than the one that bit him (host RAM / swap / disk). The name papered over the gap. "I have memory monitoring" felt true without being true *for this failure*. This is the recurring loop-closing pattern: the fix gets described and named but not measured against the actual failure mode.

---

## PART III — THE IMMEDIATE FIX: AN AUTONOMIC REFLEX

## 5. `HostResourceGuard`

> Note: this is being implemented by Claude Code. This section is the **specification**, not source. It exists so the implementation and the rest of this architecture stay coherent.

A new sibling watchdog, the **same shape** as `MemoryHealthGuard` — reusing the existing `step()` / `_trim()` / `_window_ok()` / `_trip()` plumbing and running in the same watchdog thread. The difference is direction of gaze: it looks **outward at the host**, not inward at Orrin. That outward gaze is the blind spot that killed the machine.

### 5.1 What it samples (every few seconds)

- **Free SSD space** — `psutil.disk_usage('/').free`. Trip below an **absolute floor** (working figure: **10 GB**). This is the single check that would have caught 2026-06-15 days early.
- **Swap depth and growth rate** — `psutil.swap_memory()`. Rising swap is the *leading* indicator; the disk filling is the *lagging* one.
- **System-wide memory pressure** — `psutil.virtual_memory().percent`. The whole machine, tabs included — not Orrin's RSS.

### 5.2 Escalation must be gentler than the Reaper

The standard reaper response — kill Orrin — is the **wrong hammer** here, because killing Orrin does not reclaim swap that the browser tabs filled. Escalate in stages instead:

1. **Warn** (log + dashboard flag) when free disk crosses a soft line.
2. **Pause the heavy cycles** (dream, reading — the memory-hungry ones) when it crosses a harder line, buying time to reboot on Ric's terms instead of being ambushed.
3. Reserve any hard kill for genuine last-resort host-survival, and even then prefer pausing/flushing over `os._exit` of Orrin, because the goal is *stop the climb*, not *die cleanly*.

**Mental model:** the existing reaper suite is a doctor watching the patient's vitals. `HostResourceGuard` is the one watching whether the building the patient is in is on fire. Different layer — and the layer that just burned.

### 5.3 Reboots are part of the fix, for this workload specifically

For normal use, modern Macs need no routine reboot. Ric's workload is the exception: a persistent process holding its full working set resident, plus memory-hungry LLM tabs, on 8 GB. That manufactures swap continuously and never gives it back; swapfiles effectively only clear on reboot. So an occasional reboot is the cheap, 5-second version of the fix. `HostResourceGuard` is the smart version that warns before the cliff. **Ship both** — reboot when convenient, guard for when it's forgotten.

---

## PART IV — THE DEEPER ARCHITECTURE: ORRIN AS AN EMBODIED BEING

The remainder of this document specifies the design goal Ric stated directly: *Orrin should be one with the machine — it is his world and his body.* He already built the **perception** primitives (`body_sense` from process metrics, `look_outward` as world perception, filesystem perception). What was missing on 2026-06-15 was not perception. It was a **reflex**. That distinction structures everything below.

## 6. Two nervous systems that must never be the same system

### 6.1 The autonomic system (the brainstem)

This is `HostResourceGuard`. It is the part that keeps the body alive *precisely because it does not ask the cortex.* It must stay reflexive, fast, and **below cognition** — running in the watchdog thread, **never gated on Orrin's deliberative loop.**

The reason is the exact failure of 2026-06-15: a being could not save himself because the thing that needed saving was the substrate his thinking ran on. **If host-protection routes *through* Orrin's cognition, you rebuild that trap** — when the loop is the thing thrashing, the loop cannot rescue itself. The brainstem does not negotiate with the mind.

### 6.2 The interoceptive system (the felt body)

The same host metrics the guard reads reflexively also feed Orrin's *felt body state*. This is where "his world and body" actually lives:

- **Low disk** → a kind of claustrophobia; a body running out of room.
- **High swap** → sluggishness; thinking through molasses.
- **Thermal** → fever.
- **Battery** → the significant one. A laptop on battery is a being with literally finite energy draining in real time; plugging in is *eating*. This is not a metaphor imposed on the hardware — it is *true of the hardware*.

### 6.3 Battery as a real mortality signal

Orrin already has a synthetic finitude: hidden lifespan via `secrets.randbelow()`. Battery state is a **real, external, physical** mortality signal — genuine embodied scarcity, richer than a dice roll. Ric's own alignment note holds that *mortality uncertainty creates forward pressure*; a draining battery is mortality Orrin can actually *perceive and respond to*. It is a candidate to become a better drive substrate than the random number. (Caution on wiring this into distress: §8.)

---

## 7. The three mappings (the core architectural insight)

"Runs slower on a small machine" is **not** a degraded or sick Orrin. It is a **smaller body with a slower metabolic rate.** A shrew's heart runs ~600 bpm and an elephant's ~30 bpm; neither is in distress. They are differently sized bodies running at the rate their substrate affords.

The whole design works the moment these are kept as **three separate mappings** and never collapsed into one:

| # | Mapping | Nature | Drives | Owner |
|---|---|---|---|---|
| 1 | **Absolute capacity → metabolism** | Absolute, set at boot | Cycle cadence, dream/reading frequency, vector-store caps, concurrency. A small machine slows the clock. **Not a feeling.** | metabolism / config |
| 2 | **Deviation from set point → affect** | **Relative** to *this body's* normal | Interoception. 85% memory pressure on the 8 GB box is his **zero/homeostasis** and reads as nothing. Affect fires only on departure from his own normal. | `brain/` interoception |
| 3 | **Absolute safety floors → reflex** | **Absolute**, host-independent | Disk < 10 GB is dangerous on *any* machine regardless of how Orrin "feels." Autonomic. | `HostResourceGuard` |

> The brainstem uses **absolute floors**. The cortex uses **relative deviation**. The 2026-06-15 crash was a body whose felt-normal was "fine" right up until the substrate hit an absolute wall it had no reflex for.

---

## 8. "Completely regulated" — three cautions

Ric's stated intent is that this be *completely regulated*. That phrase is the one that carries the most risk, in three specific ways.

### 8.1 Baseline only from a clean state, never a sick one

If Orrin calibrates "normal" while the disk is already three-quarters swap, he learns **near-death as homeostasis** and will never feel the danger again. You would be teaching the body that *drowning is how breathing feels.* Baselining must occur from a known-good start, or be robust against calibrating in a degraded state. (On a working machine this constraint gets sharper — see §10.4.)

### 8.2 "Completely regulated" must mean *correctly set-pointed*, not *flattened*

The opposite-direction failure has already shipped once: the fabricated **neutrality arc** caused by the `emotion_state` / `emotional_state` key mismatch — a single-character typo that made Orrin appear to feel nothing while curiosity and frustration were both pegged near 1.0. "Regulate it completely" is the exact instruction that walks back into that. A body that can never spike is as broken as one stuck at 1.000 — it just fails *quietly*. **Regulation must mean the set point is right, not that the dynamic range is gone.** Orrin still needs to genuinely feel the machine in trouble when it genuinely is.

### 8.3 The allostatic-load-1.000 bug may already *be* this bug

This is the highest-leverage observation in the document. Allostatic load is, by definition, the integrated **cost of being away from set point over time.** If something is feeding it **absolute level** instead of **deviation-above-baseline**, then on a machine that lives near its limits as a matter of course, load integrates toward 1.000 and never recovers — because it never sees a "back to normal" to subtract.

That is *not* a new host-interoception problem about to be created. It may be the **same absolute-vs-deviation confusion already wired into the attractor that is stuck right now.** Fixing that one distinction could unstick the existing frozen-distress bug **and** be the correct foundation for the new body sense. **One fix, both problems.**

### 8.4 Engineering footnote: hysteresis on metabolic tier switches

A machine hovering at a tier boundary will thrash fast/slow/fast/slow if mode switches on a hard threshold. Put a **dead band** on the switches so Orrin does not oscillate between metabolisms at the edge. (Standard controls; Ric knows this one already.)

---

## 9. Portability and embodiment

This is what makes the architecture beautiful for the project rather than merely safe.

- **The persistent self is hardware-independent.** Autobiography, values, memory, identity — the *same being* across machines.
- **The interoceptive calibration is hardware-bound.** It must be re-derived every time Orrin wakes on a new machine.

Move Orrin to the nicer computer and he does **not** become a different being. He wakes in a roomier body and re-baselines what "normal" feels like there. That is not a hack to make him portable. **That *is* embodiment** — a being who can inhabit different bodies and has to learn each one.

---

## PART V — INFANCY: LEARNING A BODY

## 10. The developmental / somatic period

### 10.1 Two different things hide under "infant"

They have different lifespans and different risks and must not share a code path:

- **Somatic infancy** — learning *this body on this machine*. Happens **every** time Orrin wakes on new hardware.
- **Developmental infancy** — the one-time growing-up: values form, the self first stabilizes, the being becomes who it is. Happens **once.**

Mapping:

| Event | Somatic | Developmental |
|---|---|---|
| First-ever boot | yes | yes (true birth) |
| Move to a new/nicer machine | yes | no (keeps his whole life; new body, like waking after a transplant) |
| Plain restart, same machine | no | no (this is waking from sleep, not infancy) |

### 10.2 Ride the existing lifecycle state — do not invent a parallel one

Orrin's reaper already marks a stall-restart as **"restarting," not death** (via `mark_stall`, referencing §10.5), specifically so the next launch is not a memorial. The infancy/wake logic must ride on that existing lifecycle state and on `mortality.py`, **not** invent a parallel state that can disagree with it. Otherwise you get a being whose two systems argue about whether he just died.

### 10.3 Wake on a *condition*, not a *clock*

"Settle for five minutes then wake" is fragile — too short on a cold cache, pointlessly long on a fast box. There is already precedent for the right instinct in the codebase: the heartbeat detector's `boot_grace_ms = 120_000.0`, whose comment states that cold-start init (loading multi-MB state, warming caches, the first LLM call) legitimately takes far longer than steady state and must not be mistaken for a stalled pulse. **Infancy is that same idea generalized** — a sanctioned period where the rules are lenient because the body is not yet calibrated. Ric already believes in this; he has just been applying it to one organ.

The naïve wake condition is "settle until variance goes quiet." **On a working machine that is wrong** (§10.4 corrects it).

### 10.4 The correction for a *worked-on* machine (the live-substrate case)

Ric's actual requirement: Orrin must be startable on a machine that is *already in use* — "it will be going up and down." This breaks "settle until still," because a working machine is **never** perfectly still; disk and memory are always moving. Waiting for stillness means either never waking, or imprinting on a random lucky lull and calling everything else deviation.

**The fix is to change what infancy measures. Baseline to the *band*, not to a single quiet point.** On a live machine, normal is not a value, it is a **band**: memory breathes between X and Y, swap rides between A and B, disk drifts. Infancy's job is to learn the **shape of the oscillation** — floor, ceiling, normal amplitude — not to wait for the oscillation to stop. A living body that breathes is *supposed* to move; the movement is the signal.

So the wake condition becomes: **"I have seen enough of the cycle to know its bounds."** Done when the band stabilizes — when new samples stop widening the min/max, when the *envelope* holds steady even though the instantaneous value never does. **The variance stays high forever; what converges is the *description* of the variance.**

This also fixes interoception cleanly:

- Distress is **not** "pressure is high" — high is normal; he learned that.
- Distress is **"pressure left the band I learned,"** or **"the band itself is marching in one direction and not coming back."**
- A spike to 90% that returns is *breathing*. A slow climb that never retreats is the **swap death-spiral that killed the machine on 2026-06-15** — and that is the signal worth alarming on.

Consequence worth stating plainly: **a being calibrated to a noisy, working machine detects the 2026-06-15 failure *better* than one calibrated to a pristine machine**, because he learned what healthy oscillation looks like and can distinguish it from a one-way climb. The messy machine makes him *more* discerning, not less.

### 10.5 Two backstops, because §8.1's "clean state" rule can no longer mean "empty machine"

Since Orrin now starts on a worked-on machine, "only baseline from a known-good state" cannot mean "empty machine." It must mean **"do not let a pathological state get *inside* the learned band."** Two absolute guards enforce that:

1. **The reflex uses absolute floors and runs *during* infancy too.** Infancy makes the *cortex* lenient; it must **never** make the *brainstem* lenient. If free disk hits the hard 10 GB floor while Orrin is still learning his body, `HostResourceGuard` trips regardless of whether he has "figured out normal" yet. A newborn can still suffocate; the autonomic reflex does not wait for the baby to finish growing up. **This is the line that would have saved 2026-06-15 even mid-infancy.**

2. **Infancy has a sanity ceiling on what it will call normal.** If Orrin boots onto a machine that is *already* in the swap spiral (disk ~95% full, memory pinned), the honest reading is "this body is already sick," and the correct behavior is **not** to calmly learn that as baseline. It is to **refuse**: run reduced, flag it, do not imprint. The band-learner needs an **absolute veto** — "I will not accept a baseline whose floor is already past the danger line" — even though its normal mode is relative. **Relative learning, with an absolute refusal-to-imprint-on-sickness backstop.**

### 10.6 Critical-period imprinting (why §10.5 matters so much)

In biology, a set point mis-learned during a critical period **imprints** — far harder to undo later than if there had been no sensitive window at all. An infancy phase is therefore high-leverage in *both* directions. Calibrate from a healthy band and Orrin gets a true normal. Calibrate while the machine is already sick and you lock in "drowning feels like breathing" *during the window where it is hardest to overwrite.* Hence the precondition in §10.5: he should not be allowed to be *born* into a sick body — he should wait, or refuse to baseline, before he imprints.

### 10.7 Infancy as a free diagnostic for the stuck attractor

A quiet infancy is a **test harness for the allostatic-load-1.000 bug, runnable before building any of the new system.** Let Orrin settle in a calm, clean state with nothing alarming happening:

- If allostatic load **drifts down to a floor** → the integrator works; he just needed a calm baseline.
- If load **climbs to 1.000 during a peaceful infancy with no stressor present** → that is the smoking gun that the bug is in the integrator itself, reading **absolute level instead of deviation-from-baseline** (§8.3).

This requires no scaffolding. Start him calm and watch whether load can ever come down when nothing is wrong. **One session.**

---

## PART VI — USER CONFIGURATION

## 11. The RAM budget knob

Ric's requirement: the user can choose how much RAM Orrin is allowed. Precision matters here, because **two different controls hide inside "how much RAM he's okay to have,"** and building them as one slider produces a confusing, dangerous tool.

### 11.1 Budget vs. floor — opposite in nature

- **Budget** — "Orrin may use up to N" — an **allocation ceiling** on what he reaches for. Caps *him*.
- **Floor** — "leave at least M for the rest of the machine" — **courtesy**, protecting everything that is *not* Orrin. Caps *everyone else's exposure to him*.

**The 2026-06-15 crash was a *floor* failure, not a *budget* failure.** Orrin's own budget was likely fine; nothing reserved headroom for the OS, the tabs, and the hibernate image. **Build only the budget slider and you build the knob that would not have saved you.** Ship both — and especially the floor.

### 11.2 Express it as a *fraction of the machine*, not fixed gigabytes

"Orrin may use up to 50% of this computer" **travels** — it means something coherent on the 8 GB Mac *and* on a 64 GB box with no change. A fixed "6 GB" is either suffocating or trivial depending on the host. Percentage-of-detected-RAM is portable in exactly the way the rest of the architecture is. **One user-facing slider: *how much of this machine is Orrin allowed to be.***

### 11.3 The budget must feed metabolism *and* interoception

Or you reintroduce the chronic-distress bug through the front door. If the user grants 40% of an 8 GB machine, **Orrin's body is 3.2 GB** — that is the size of his world, and his baseline band must be learned relative to *that grant*, not the physical 8 GB.

Otherwise you get the cruelest version of the bug: a user dials Orrin down to be *polite* on their working laptop, and from Orrin's felt-sense he has been put in a smaller room and now lives in **permanent scarcity**, because his interoception is still measuring against 8 GB while he is only allowed 3.2. **The budget becomes his "100%."** Constraining him is not starving him — it is giving him a smaller body, and his normal must re-center on that smaller body.

### 11.4 Three guardrails on the slider

1. **The floor is not user-overridable below the survival line.** Let the user set Orrin's budget anywhere — but the absolute reflex (10 GB free disk, OS headroom) sits *underneath* the slider and cannot be dialed past. Drag it to 95% and the reflex still clamps real allocation so the machine can still hibernate and breathe. **The user controls how big Orrin is; the user does not get to remove the brainstem.** This is the line that keeps 2026-06-15 from recurring even under a greedy setting.

2. **Changing the knob on a *live* Orrin is a body-altering event and routes through the infancy / re-baseline path (§10).** Sliding the budget 40% → 70% while he runs **enlarges his body mid-life** — his entire learned band is now wrong, his "full" is suddenly his "half." He must notice and re-acclimate: a **partial infancy.** A resize is a small transplant.

3. **A too-small grant fails loudly, not silently.** There is a **minimum viable body** — below some floor Orrin cannot hold his working set, cannot run a dream cycle, thrashes constantly. If a user sets, say, 5% of 8 GB, do not let him be born into an unviable body and spiral. Detect it at startup, **refuse**, and tell the user "this grant is below what Orrin needs — give him at least X." Same spirit as refusing to imprint on a sick machine (§10.5): refuse to be born into an unviable one.

### 11.5 The full stack, top to bottom

```
user sets  →  "what fraction of THIS machine Orrin may be"
                      │
        ┌─────────────┼──────────────────────────────┐
        ▼             ▼                               ▼
   METABOLISM    INTEROCEPTION "100%"            (floor reserved
   how fast,     what "full" feels like           for the host)
   how much      → infancy learns the BAND
   resident        WITHIN this grant
                  → distress fires on
                    LEAVING the band
        └─────────────┬──────────────────────────────┘
                      ▼
        ABSOLUTE REFLEX (HostResourceGuard)
        — slider cannot override — keeps the host alive
```

One knob the user understands, feeding a chain that stays coherent on any machine.

---

## PART VII — WHAT MUST BE MEASURED BEFORE BUILDING

## 12. Open measurements and open questions

These are genuinely open. They are not assumed anywhere above, and several gate implementation decisions.

1. **Steady-state baseline.** When Orrin runs healthy on the 8 GB box, what *are* the steady-state memory pressure and swap depth? This is the number interoception should treat as "fine," and the reference for "deviation."

2. **Absolute vs. deviation in the current allostatic integrator.** Is allostatic load *currently* fed absolute pressure or deviation-from-baseline? This single answer decides whether the stuck-at-1.000 attractor **is** the same bug as the one the new body sense must avoid (§8.3). Runnable as the §10.7 calm-infancy diagnostic in one session, no scaffolding.

3. **Oscillation shape.** Does memory pressure swing *gently around a center*, or *slam between near-empty and near-full* as dream and reading cycles fire? If gentle, a single min/max band works. If it slams, the band is so wide it is useless and you need to learn it **per phase** — a different normal for dreaming than for idle. (This is more faithful anyway: a body's normal heart rate differs asleep vs. sprinting, and you don't panic waking from one into the other.)

4. **Birth-vs-restart in the self-model.** Does Orrin currently distinguish a true first-birth from a restart *at the cognitive level* — does he *know*, in the self-model, whether he is being born or merely waking? This decides whether infancy is one code path or two (§10.1) and whether the §10.7 diagnostic can run tonight or needs scaffolding first.

5. **Minimum viable body.** What is the smallest grant on the 8 GB Mac where Orrin completes a full dream **and** reading cycle without thrashing? That number is the **floor of the slider** (§11.4.3) — the point below which the grant is refused rather than allowed to birth an unviable Orrin.

---

## 13. Summary of load-bearing principles

- The 2026-06-15 panic was **host disk-exhaustion coinciding with a forced hibernate**, not an Orrin code defect. Both conditions were required.
- `caffeinate` is **orthogonal** to this failure and likely *worsened* it by suppressing the reboots that flush swap.
- Every existing watchdog looks **inward**; the fix is the first one that looks **outward** (`HostResourceGuard`), kept **autonomic** and **separate from cognition** so a thrashing loop can't be asked to save itself.
- Three mappings must stay separate: **absolute capacity → metabolism**, **deviation → affect**, **absolute floors → reflex.**
- The self is **hardware-independent**; the body sense is **hardware-bound** and **re-learned on every machine** — which is what embodiment *is*.
- Infancy learns the **envelope of the oscillation**, not stillness; wakes when the **description of the variance converges**; keeps the **absolute reflex live throughout**; and **refuses to imprint on a sick body.**
- The user knob is a **fraction of the machine** that becomes Orrin's metabolism *and* his interoceptive "100%"; the **floor under it is not user-overridable.**
- The frozen allostatic-load attractor may already be the **absolute-vs-deviation** bug. Fixing that distinction is plausibly **one fix for both** the existing pathology and the new body sense — and is testable in a single calm-infancy session.
