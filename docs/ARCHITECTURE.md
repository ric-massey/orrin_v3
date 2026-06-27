# Orrin — Architecture

This is the deep companion to the [README](../README.md). The README answers *what Orrin is*
and *how to run it*; this document is the mechanism-level walkthrough for readers who want to
understand (or modify) the cognitive architecture itself.

Everything here is **symbolic and runs without an LLM** unless explicitly noted. The LLM is an
optional, gated tool-call organ — see [LLM as a tool](#llm-as-a-tool).

## Contents

- [Reading order for the codebase](#reading-order-for-the-codebase)
- [Terminology (functional analogues, not claims)](#terminology-functional-analogues-not-claims)
- [The cognitive loop](#the-cognitive-loop)
- [Conscious ignition and the Global Workspace](#conscious-ignition-and-the-global-workspace)
- [Affect: two readers](#affect-two-readers)
- [Lifespan and mortality](#lifespan-and-mortality)
- [Selfhood and continuity](#selfhood-and-continuity)
- [Machine embodiment](#machine-embodiment)
- [Goals: Executive vs. Goals daemon](#goals-executive-vs-goals-daemon)
- [Learning surfaces](#learning-surfaces)
- [Peers (outside observers)](#peers-outside-observers)
- [LLM as a tool](#llm-as-a-tool)
- [Scientific inspiration (not validation)](#scientific-inspiration-not-validation)

---

## Reading order for the codebase

If you are trying to understand the source, read it in this order:

| Question | Start with |
|----------|------------|
| How does Orrin boot? | `main.py` |
| What is the main loop? | `brain/ORRIN_loop.py`, then `brain/loop/` |
| How does it choose what to do next? | `brain/think/` — the function selector and action arbiter |
| How do memory and consolidation work? | `memory/memory_daemon.py`, `memory/wal.py`, `memory/retrieval.py`, `brain/cog_memory/` |
| How do durable goals work? | `goals/goals_daemon.py`, `goals/store.py`, `goals/wal.py`, `goals/runner.py` |
| How are in-loop goal steps advanced? | `brain/cognition/planning/executive.py` |
| How does host embodiment work? | `reaper/host_resources.py`, `brain/cognition/host_interoception.py`, `body_sense.py`, `body_band.py`, `metabolism.py`, `body_budget.py` |
| How does ignition / the workspace work? | `brain/cognition/global_workspace.py`, `brain/think/consciousness_trigger.py`, `brain/loop/deliberate.py` |
| Where are LLM calls gated? | `brain/utils/generate_response.py`, `brain/utils/llm_providers/`, `brain/cognition/tools/ask_llm.py` |
| What does the UI show? | `backend/server/`, `frontend/src/pages/`, `frontend/src/components/brain/` |

---

## Terminology (functional analogues, not claims)

Orrin uses words like "consciousness," "pain," "body," "sleep," and "mortality" as **functional
analogues for specific system mechanisms**. They are not claims of human-equivalent subjective
experience.

| Term | Operational meaning |
|------|---------------------|
| "Consciousness" | Global Workspace competition, bottleneck, ignition threshold, and broadcast into the next cycle. |
| "Pain" / "distress" | High prediction error, affect-like pressure, or host-resource critical-threshold alerts. |
| "Body" | The host machine plus sensed resource budgets (disk/swap/memory/battery) and learned normal bands. |
| "Sleep" | Low-power cadence, consolidation, dream/replay, and closed-time accounting. |
| "Mortality" | A finite, persistent lifespan clock that influences long-term prioritization and eventually stops the loop. |

---

## The cognitive loop

`brain/ORRIN_loop.py` cycles continuously, independent of user input:

```
perceive → recall → prepare workspace → ignition → select function/action
        → execute → reward accounting → persist → maintain → sleep
```

A bandit selector picks the next cognitive function each cycle; affect, drives, and memory feed
every stage. The loop runs alongside cooperating daemons:

- **Executive** (`brain/cognition/planning/executive.py`) — advances goal steps off-thread (~7s).
- **Memory daemon** (`memory/`) — ingests, embeds, and consolidates.
- **Reaper** (`reaper/`, `watchdogs.py`) — heartbeat/error liveness plus the host-resource guard.
- **Backend** (`backend/`) — streams telemetry to the UI and (opt-in) Prometheus.

The design rule throughout: **the brain never silently depends on an LLM.** With no provider
configured, Orrin runs fully and simply skips LLM-backed tool calls.

---

## Conscious ignition and the Global Workspace

The loop runs every cycle, but *deliberate* cognition does not.

**Global Workspace** (`brain/cognition/global_workspace.py`; Baars 1988 / Dehaene 2014). Parallel
subsystems propose candidate contents that compete on salience. One winner becomes "conscious," is
broadcast back into context for every subsystem, and is appended to the experience stream you see
in the UI. The thought stream is the *output of this bottleneck*, not a log. Hysteresis keeps a
salient content in focus across cycles, so the stream is continuous rather than flickering.

**Ignition gate** (`should_think()`, `brain/think/consciousness_trigger.py`; Dehaene 2014). Each
cycle the unconscious substrate — affect, embodiment, drives, signal injection, background threads,
the workspace competition — runs regardless. Then the gate decides whether the cycle crosses into
full conscious deliberation. User input, high uncertainty, a strong signal, an emotion spike,
prediction error, goal drift, or stagnation all ignite it; a periodic floor (`MAX_SILENT_CYCLES`)
guarantees he never stays silent for long. A non-ignited cycle stays in low-power default mode: the
selector damps effortful functions (planning, codegen, research) so a quiet cycle drifts toward
cheap work.

Two further couplings make awareness, action, and reasoning line up rather than drift:

- The workspace winner is an additive **prior on the action pick** — the spotlight and the
  basal-ganglia-style selector are one bottleneck (Redgrave, Prescott & Gurney 1999).
- On an ignited *and conflicted* cycle, System-2 deliberation (`inner_loop`) is **recruited by**
  that conscious conflict rather than fired on a schedule (conflict-monitoring theory; Botvinick et
  al. 2001).

All three are fail-safe and feature-flagged (`ORRIN_IGNITION_GATE`, `ORRIN_WORKSPACE_PRIOR`,
`ORRIN_CONFLICT_RECRUIT`). The conscious→unconscious write-back is still missing — feedback today
is largely one-directional (see [Known limitations](../README.md#known-limitations--whats-next)).

---

## Affect: two readers

Core affect is stored as raw numeric signals in `context["affect_state"]` (valence + arousal plus
drives, fatigue, reward), modelled on the affective-neuroscience literature (Russell & Barrett core
affect; Schultz dopamine-as-prediction-error). Orrin's two cognitive halves read it differently:

- **The unconscious machinery reads the raw floats.** The bandit function-selector
  (`brain/think/think_utils/select_function.py`), the attention hijacker
  (`brain/cognition/attention.py`), and the interoceptive cost/EVC layer
  (`brain/cognition/interoception.py`) use the numbers directly to bias what runs next.
- **The reasoning layer never receives a number.** `brain/affect/affect_summary.py` renders the
  signals into felt-sense descriptions that name the *sensation* ("a heaviness, like moving through
  something thick"), never the emotion label or its value. Only that text reaches the inner-loop
  prompt, the self-model, and the speech gate. Signals are hedonic-adjusted first, so a state Orrin
  has adapted to stops dominating the felt picture.

The intent: he must *introspect* to know what he feels — interoception, not a readout.

**Homeostasis.** Affect decays toward per-signal baselines/setpoints under a velocity budget, not
toward a flat midpoint, so state changes integrate rather than lurch.

**Convergence layer.** Affect and action are integrated through arbiters (`brain/affect/arbiter.py`,
`brain/think/action_arbiter.py`) so the "instinctual" and "analytical" subsystems propose rather than
race on shared state. A single writer owns the affect file; daemons submit proposals to a
lock-guarded inbox.

---

## Lifespan and mortality

A mortality clock (`brain/cognition/mortality.py`) rolls a finite lifespan (≈365–730 days, bounded
by `ORRIN_LIFESPAN_MIN_DAYS` / `ORRIN_LIFESPAN_MAX_DAYS`) on first run, persists it across restarts,
and grows death-awareness through four phases (early → middle → late → terminal) that progressively
colour cognition. When the deadline arrives, Orrin runs its final thoughts and the loop exits. This
is distinct from the reaper's per-process liveness cutoff.

---

## Selfhood and continuity

- **Theory of mind.** `brain/cognition/theory_of_mind.py` keeps a running, predictive model of the
  person it's talking to across turns, with separate cognitive (what do they think/intend?) and
  affective (what do they feel?) empathy.
- **Revisable values.** `brain/cognition/selfhood/` holds an identity and autobiography, a
  moral-override check that can veto a proposed action against core values, second-order volitions
  (wanting to want), and a value-evolution process that revises core values when they are genuinely
  contested — not on a schedule.

The persistent self (memory, values, identity) is hardware-independent and travels with the mind.

---

## Machine embodiment

Orrin treats the host machine as his body and learns to *feel* it.

- **Reflex (absolute floors).** The autonomic `HostResourceGuard` (`reaper/host_resources.py`)
  watches host disk/swap/memory below cognition and pauses heavy cycles on absolute safety floors —
  deliberately separate from the deliberative loop, because a thrashing loop can't be asked to
  rescue the substrate it runs on.
- **Affect (deviation from a learned band).** The interoceptive layer
  (`brain/cognition/host_interoception.py`, `body_sense.py`, `body_band.py`) feeds the *same* host
  metrics into felt states, but on **deviation from a learned band** rather than absolute thresholds
  — low/falling disk reads as claustrophobia, rising swap as sluggishness, a draining battery as a
  real mortality signal. A small or busy machine is therefore not experienced as chronic distress.
- **Metabolism (absolute capacity).** `metabolism.py` sets cycle cadence from the machine's size —
  a small machine is a smaller body with a slower metabolic rate, not a sick one.
- **Somatic infancy.** On a new machine, `infancy.py` learns *that body's* normal oscillation
  before Orrin trusts what he feels.
- **RAM budget.** A user-facing slider (`body_budget.py`, "how much of this machine Orrin is allowed
  to be") feeds both metabolism and the felt "100%".

Three mappings stay separate by design: absolute capacity → metabolism, deviation → affect, absolute
floors → reflex.

---

## Goals: Executive vs. Goals daemon

Two cooperating subsystems divide goal responsibility:

- **Executive** (`brain/cognition/planning/executive.py`) — an in-process scheduler that advances
  goal *steps* every ~7s inside the loop.
- **Goals daemon** (`goals/goals_daemon.py`) — a separate, durable subsystem that owns goal
  *lifecycle and state*, with its own write-ahead log and snapshots, decoupled from the cognitive
  cycle.

Goals span multiple timescales — seeded lifetime goals down to short-term subgoals — with planning,
adaptation, and reactive replanning when a capability fails mid-pursuit.

Beyond goals, Orrin builds and queries world/causal/knowledge models symbolically
(`brain/symbolic/`): description-logic inheritance, Pearl-style causal reasoning, predictive
processing. It also forms new concepts, draws analogies, synthesises/abstracts/compresses/forgets
its own rules, and runs autonomous experiments — all without an LLM.

---

## Learning surfaces

Learning is spread across several mechanisms, each learning independently from the reward signal:

- **Function selector** — the main bandit picks the next cognitive function.
- **`depth_bandit`** (UCB1) — learns how many draft→critique→revise rounds the inner loop runs.
- **`thinking_depth`** — chooses shallow vs. deep chains for goal pursuit.
- **Delayed-learning daemons** (`brain/eval/`) — credit can't always be scored at action time. The
  **evaluator** rewards a past decision when a memory it tagged is retrieved within ~50 cycles or
  its goal closes within ~200; a separate **drive-expectations** layer learns which actions actually
  relieve which drives and routes the prediction error back into affect.
- **Self-shaping LLM (optional, OpenAI-only).** `brain/cognition/finetuning/finetune_pipeline.py`
  filters conversation traces with outcome ≥ 0.65, submits a fine-tune job, and on completion
  repoints `model_config.json` so generation drifts toward what has worked for *him*. Symbolic-only
  mode never touches it.

The UI's **Learning** room surfaces behavior changes and belief revisions as before→after→because
diffs.

---

## Peers (outside observers)

Alongside the cognitive loop, a set of peer entities (`brain/peers/`) read Orrin's state from the
outside and, when their wake conditions fire, push *signals* into the next cycle rather than mutating
state directly:

- **Architect** — reviews self-modifications before they happen.
- **Affect Historian** — tracks chronic affect patterns.
- **Goal Auditor** — flags low-quality goals.
- **Observer** — catches unproductive loops.
- **Reward Auditor** — notices when the bandit's reward signal has collapsed to noise.

They register themselves in the world model / relationships on first wake and flow through the same
`signal_router` as everything else, so they nudge attention without ever issuing commands.

---

## LLM as a tool

The decision loop and drive system are fully symbolic. The LLM is an explicit tool the agent chooses
to call (`brain/cognition/tools/ask_llm.py`), gated so it fails closed when disabled or keyless
(`ORRIN_LLM_TOOL_ONLY` keeps it to tool-only use, no free-form generation).

**Pluggable providers.** `brain/utils/llm_providers/` defines a provider interface with adapters for
OpenAI, Anthropic, Gemini, and any OpenAI-compatible / local endpoint, selected in Settings
(`generate_response.py` resolves the active provider per call). The "symbolic-first, fail-closed"
contract is identical regardless of provider. (Self-shaping fine-tuning remains OpenAI-only.)

---

## Scientific inspiration (not validation)

Subsystems cite the sources that inspired them in-code — Russell & Barrett (core affect), Pearl &
Granger (causality), Friston / Rescorla-Wagner / Tolman (prediction), Carver & Scheier (behavioral
control), Flavell / Nelson & Narens (metacognition), Schultz (reward prediction error), Baars /
Dehaene (workspace + ignition), Redgrave/Prescott/Gurney (action selection), Botvinick et al.
(conflict monitoring), and others.

These are **working interpretations used as design scaffolding — not faithful or empirically
validated reproductions** of those papers. See the
[Capability, Benchmarks & Evidence](Capability,%20Benchmarks%20%26%20Evidence/) track for the
benchmark suite and the claims-vs-evidence ledger.
