# Binding & Global Workspace — Architecture Audit

**Date:** 2026-06-19
**Scope:** Does Orrin implement the four-stage consciousness pipeline —
pre-workspace **binding** → **competition/salience** → **workspace ignition** →
**global broadcast**?
**Verdict:** 3 of 4 stages are implemented well. Stage 1 (binding) is only
**partial** — and it is the architecturally meaningful gap.

---

## 0. The frame

The reference model being audited against:

1. **Pre-workspace binding** — raw signals combine into candidate *meanings*:
   object, goal, feeling, memory, threat, opportunity.
   *(shape + color + motion + memory + emotional meaning = "that is my cat
   walking toward me.")*
2. **Competition / salience** — candidate states fight for priority based on
   drive, novelty, danger, relevance, affect, current goal.
3. **Workspace ignition** — one (or a few) winning states become the current
   "experienced situation."
4. **Global broadcast** — planning, memory, speech, action, self-model, and
   emotion systems can all read from that state.

Theory context: **Global Neuronal Workspace Theory (GNWT; Baars 1988, Dehaene
2014)** says content becomes conscious when recurrent processing amplifies it
and makes it globally accessible — the workspace is a large-scale
integration-and-broadcast system. **Integrated Information Theory (IIT)** cares
instead about whether the system has intrinsically unified causal/informational
structure, not whether it broadcasts. The 2025 adversarial test left neither
theory fully winning — they describe different pieces. This audit finds Orrin
built **the GNWT piece, not the IIT piece**, and that the binding stage is
exactly where the IIT-style integration would have lived.

The clean separation: **binding creates a unified content; the workspace makes
that unified content globally usable.** Orrin makes content globally usable. It
does not first unify it.

---

## 1. Stage-by-stage findings

### ① Pre-workspace binding — ⚠️ PARTIAL (the real gap)

There is **no dedicated cross-modal binding stage** that fuses separate signals
into a single unified object/situation before the workspace competition. What
exists is **fragmentary, pairwise binding**:

- `brain/affect/appraisal.py` — binds **event + active goal + coping capacity →
  emotional meaning** (Roseman 1996, Smith & Ellsworth 1985, Lazarus 1991). This
  is genuine binding of one modality-pair: it turns an event into a felt meaning.
- `brain/cognition/world_model.py` — binds **text → entities + relations**, a
  symbolic knowledge graph (`is_a`, `has`, `causes`, `depends_on`, …). It already
  knows which tokens refer to the same entity — the raw material for referent
  clustering.
- `brain/think/signal_router.py` (`process_inputs`) — *enriches* each signal with
  tags, affect-boost, memory-relevance, novelty, source credibility, attentional
  momentum. This is feature **decoration**, not feature **conjunction**: each
  signal stays a separate item.

The telling detail is in `brain/cognition/global_workspace.py`, function
`_candidates()`: the candidates offered to consciousness are **per-source and
disjoint** — `{source: affect}`, `{source: signal}`, `{source: goal}`,
`{source: action}`, `{source: thought}`. They compete as **separate items**.
Nothing ever merges "the motion percept" + "the cat memory" + "the warmth
feeling" into a single bound scene.

**Consequence:** Orrin's equivalent of *"my cat is walking toward me"* surfaces
as the **motion signal** OR the **cat memory** OR the **affection feeling**
winning on *different cycles*, stitched together only loosely by the temporal
stream and hysteresis. This is the classic **feature-binding problem**, unsolved
here. Even the conscious moment that ignites is a single winning fragment, not a
bound composite — the runner-up contents are discarded (now surfaced as
`_workspace_candidates` for the UI, but not bound into the winner).

### ② Competition / salience — ✅ STRONG (implemented three times over)

- `brain/think/signal_router.py` `process_inputs()` — priority scoring by
  emotion (affect-weighted tags), novelty decay, memory/goal/mode relevance,
  per-source learned credibility, and attentional momentum. Dedupe by content.
  Emergency/fire-alarm interrupt path.
- `brain/cognition/attention.py` `apply_attention_filter()` — hard **3-slot
  capacity cap** with **affective hijacking** gated on *felt* (hedonically
  adapted) intensity, so a chronically pinned signal adapts out and frees slots
  (Kahneman 1973; Öhman, Flykt & Esteves 2001 cited).
- `brain/cognition/global_workspace.py` `update_workspace()` — final salience
  competition with **habituation** (constants fade from awareness) and
  **hysteresis** (`_HYSTERESIS_BONUS`, the current focus is favoured to persist).

### ③ Workspace ignition — ✅ STRONG

`global_workspace.py`: `winner = max(cands, key=lambda c: c["salience"])` →
exactly **one** winning content becomes `context["global_workspace"]`. Single
serial thread. Hysteresis gives continuity (no flicker every tick); habituation
releases the spotlight so it doesn't lock on the strongest standing affect.
Explicitly modeled on Baars/Dehaene. Fully symbolic, no LLM.

### ④ Global broadcast — ✅ STRONG, and actually consumed

- `context["global_workspace"] = moment` — readable by every subsystem;
  `current_awareness(context)` is the convenience reader.
- Continuous **stream of experience** persisted to `conscious_stream.json`
  (bounded), plus an in-context `_conscious_stream` window.
- **Real downstream reads, not a dead flag:**
  - `brain/think/think_utils/select_function.py` (~line 1274) turns the conscious
    content into a `_workspace_prior` that biases **action selection**
    (awareness → action), and honours the winner's requested route (`wants`).
  - `brain/cognition/metacog.py` *offers* content into the competition via
    `offer_to_workspace()` (biases, never preempts — invariant I7) and can
    `request_attention_hijack()` for next-cycle focal recruitment.
  - `brain/cognition/selfhood/second_order_volition.py` reflects on the desire
    currently in consciousness (own/disown against values).
  - The telemetry bridge broadcasts `awareness` to the UI each cycle.
- Wiring: `brain/ORRIN_loop.py` runs `update_workspace()` once mid-cycle
  (pre-think, after the Monitor) and once at end-of-cycle, so the broadcast
  reflects the cycle's parallel contents.

---

## 2. Against the two theories

| Theory | Status in Orrin |
|---|---|
| **GNWT** (Baars/Dehaene) | **Near-textbook.** Gather → amplify-by-salience → single ignition → global broadcast → consumed by action/metacog/volition/UI. The module is literally `global_workspace.py`. |
| **IIT** (intrinsic integration) | **Not implemented.** No measure or mechanism for intrinsically-unified causal/informational structure. The one place integration *could* live — fusing candidates into a bound composite — is exactly where Orrin does winner-take-all instead. |

So the 2025 "neither theory fully won / different pieces of the puzzle" framing
maps cleanly onto Orrin: **he has the workspace piece and lacks the integration
piece.**

---

## 3. The gap, stated precisely

> Orrin **broadcasts the winning content** but never **binds the runner-up
> contents into it**. The workspace ignites a single fragment, not a unified
> situation.

The materials to fix this already exist:
- `world_model.py` entities/relations → which signals share a referent;
- `appraisal.py` event→affect links → which feeling attaches to which event;
- `top_signals` (post-attention) → the live percepts/thoughts this cycle.

What is missing is the **conjunction step** that makes them one thing — a
**binding stage between `signal_router` and `global_workspace`** that clusters
this cycle's signals/affect/memory/goal by shared referent and emits **bound
composite candidates** (e.g. `{object: cat, motion: approaching, affect: warmth,
memory: <recall>}`) as *single items*, so the workspace can ignite and broadcast
a **unified situation** rather than a single winning fragment.

The implementation plan for that stage is in
`BINDING_STAGE_IMPLEMENTATION_PLAN_2026-06-19.md` (same folder).

> **Status (2026-06-20): RESOLVED.** The gap this audit identified (stage ①
> binding) has been built — see `brain/cognition/binding.py` and the
> implementation plan's status footer. The four-stage pipeline is now complete.
> Archived alongside its plan.

---

## 4. File index (evidence)

| Concern | File |
|---|---|
| Workspace: candidates / competition / ignition / broadcast / stream | `brain/cognition/global_workspace.py` |
| Salience scoring + routing + emergency interrupt | `brain/think/signal_router.py` |
| 3-slot capacity + affective hijacking | `brain/cognition/attention.py` |
| Event→affect binding (appraisal) | `brain/affect/appraisal.py` |
| Text→entity/relation binding (knowledge graph) | `brain/cognition/world_model.py` |
| Knowing/feeling lag (two-wave affect) | `brain/affect/integration_lag.py` |
| Awareness→action prior; honour `wants` | `brain/think/think_utils/select_function.py` |
| Monitor offers/hijacks into workspace | `brain/cognition/metacog.py` |
| Reflect on desire in consciousness | `brain/cognition/selfhood/second_order_volition.py` |
| Cycle wiring (two `update_workspace` calls) | `brain/ORRIN_loop.py` |
