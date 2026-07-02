# Orrin — Architecture

This is the deep companion to the [README](../README.md). The README answers *what Orrin is*
and *how to run it*; this document is the mechanism-level walkthrough for readers who want to
understand (or modify) the cognitive architecture itself.

Everything here is **symbolic and runs without an LLM** unless explicitly noted. The LLM is an
optional, gated tool-call interface — see [LLM as a tool](#llm-as-a-tool).

## Contents

- [Reading order for the codebase](#reading-order-for-the-codebase)
- [Terminology (engineering terms, not claims)](#terminology-engineering-terms-not-claims)
- [The cognitive loop](#the-cognitive-loop)
- [Ignition and the global workspace](#ignition-and-the-global-workspace)
- [Control signals: two readers](#control-signals-two-readers)
- [Runtime lifetime](#runtime-lifetime)
- [Identity and continuity](#identity-and-continuity)
- [Host coupling](#host-coupling)
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
| How does host coupling work? | `supervisor/host_resources.py`, `brain/cognition/host_resource_monitor.py`, `resource_self_monitor.py`, `host_band.py`, `resource_cadence.py`, `host_budget.py` |
| How does ignition / the workspace work? | `brain/cognition/global_workspace.py`, `brain/think/deliberation_gate.py`, `brain/loop/deliberate.py` |
| Where are LLM calls gated? | `brain/utils/generate_response.py`, `brain/utils/llm_providers/`, `brain/cognition/tools/ask_llm.py` |
| What does the UI show? | `backend/server/`, `frontend/src/pages/`, `frontend/src/components/brain/` |

---

## Terminology (engineering terms, not claims)

Orrin is described in engineering terms throughout — each names a specific runtime mechanism, not a
claim of subjective experience. Some subsystems are still inspired by, and cite, cognitive-science
sources (see [Scientific inspiration](#scientific-inspiration-not-validation)); the names below are
the operational meaning, not a metaphor.

| Term | Operational meaning |
|------|---------------------|
| Workspace arbitration | Global-workspace competition, bottleneck, ignition threshold, and broadcast of the winner into the next cycle. |
| Control signals | Regulated internal-state vector (a reward signal + activation level + named pressures) that biases what runs next. |
| Distress signal | High prediction error, control-signal pressure, or a host-resource critical-threshold alert. |
| Host coupling | The host machine plus sensed resource budgets (disk/swap/memory/battery) and learned normal bands. |
| Idle / consolidation | Low-power cadence, memory consolidation, replay, and closed-time accounting. |
| Runtime lifetime | A finite, persistent lifetime-budget clock that influences long-term prioritization and eventually stops the loop. |

---

## The cognitive loop

`brain/ORRIN_loop.py` cycles continuously, independent of user input:

```
perceive → recall → prepare workspace → ignition → select function/action
        → execute → reward accounting → persist → maintain → idle/consolidate
```

A bandit selector picks the next cognitive function each cycle; control signals, demands, and memory
feed every stage. The loop runs alongside cooperating daemons:

- **Executive** (`brain/cognition/planning/executive.py`) — advances goal steps off-thread (~7s).
- **Memory daemon** (`memory/`) — ingests, embeds, and consolidates.
- **Supervisor** (`supervisor/`, `watchdogs.py`) — heartbeat/error liveness plus the host-resource guard.
- **Backend** (`backend/`) — streams telemetry to the UI and (opt-in) Prometheus.

The design rule throughout: **the brain never silently depends on an LLM.** With no provider
configured, Orrin runs fully and simply skips LLM-backed tool calls.

---

## Ignition and the global workspace

The loop runs every cycle, but *deliberate* cognition does not.

**Global workspace** (`brain/cognition/global_workspace.py`; Baars 1988 / Dehaene 2014). Parallel
subsystems propose candidate contents that compete on salience. One winner crosses the bottleneck, is
broadcast back into context for every subsystem, and is appended to the thought stream you see in the
UI. The thought stream is the *output of this bottleneck*, not a log. Hysteresis keeps a salient
content in focus across cycles, so the stream is continuous rather than flickering.

**Ignition gate** (`should_think()`, `brain/think/deliberation_gate.py`; Dehaene 2014). Each cycle the
background substrate — control signals, host coupling, demands, signal injection, background threads,
the workspace competition — runs regardless. Then the gate decides whether the cycle crosses into
full deliberation. User input, high uncertainty, a strong signal, a control-signal spike, prediction
error, goal drift, or stagnation all ignite it; a periodic floor (`MAX_SILENT_CYCLES`) guarantees it
never stays silent for long. A non-ignited cycle stays in low-power default mode: the selector damps
effortful functions (planning, codegen, research) so a quiet cycle drifts toward cheap work.

Two further couplings make broadcast, action, and reasoning line up rather than drift:

- The workspace winner is an additive **prior on the action pick** — the broadcast bottleneck and the
  basal-ganglia-style selector are one bottleneck (Redgrave, Prescott & Gurney 1999).
- On an ignited *and conflicted* cycle, System-2 deliberation (`inner_loop`) is **recruited by**
  that workspace conflict rather than fired on a schedule (conflict-monitoring theory; Botvinick et
  al. 2001).

All three are fail-safe and feature-flagged (`ORRIN_IGNITION_GATE`, `ORRIN_WORKSPACE_PRIOR`,
`ORRIN_CONFLICT_RECRUIT`).

The downward path is now closed in a **decaying** form (`brain/cognition/workspace_writeback.py`,
on the main path, no flag). After a conscious moment is selected, write-back nudges priors back
*down*: a small, low-weight, TTL-bounded affect proposal (integrated by next cycle's `commit_signals`)
keyed to the *kind* of conclusion, plus Hebbian priming of the winner's tokens in a bounded,
per-cycle-decaying salience-prior store that biases the next competition toward the same theme.
Two properties make it permanent and safe to keep on: every write **decays** (affect TTL drain +
salience decay), and there is **no promotion path** to a durable baseline, to `concept_memory`, or
to identity — the substrate *tracks* recent conclusions for long-run coherence but never *becomes* a
different substrate ("coherent-but-adult"; no ontogeny). Reflex floors and absolute scalars are never
write-back targets ("refuse-to-imprint" by construction).

---

## Control signals: two readers

The control-signal state is stored as raw numeric values in `context["affect_state"]` (a reward
signal + activation level plus demands, throttle, reward), modelled on the affective-neuroscience
literature (Russell & Barrett core affect; Schultz reward-prediction error). Orrin's two cognitive
halves read it differently:

- **The background machinery reads the raw floats.** The bandit function-selector
  (`brain/think/think_utils/select_function.py`), the attention hijacker
  (`brain/cognition/attention.py`), and the cost-prediction / EVC layer
  (`brain/cognition/cost_prediction.py`) use the numbers directly to bias what runs next.
- **The reasoning layer never receives a number.** `brain/control_signals/signal_summary.py` renders
  the signals into qualitative state descriptions that name the *quality* ("a heaviness, like moving
  through something thick"), never the signal label or its value. Only that text reaches the
  inner-loop prompt, the self-descriptor, and the speech gate. Signals are adaptation-adjusted first,
  so a state the runtime has habituated to stops dominating the picture. (This rendering is
  behaviorally load-bearing — it shapes how the runtime describes its own state — and is deliberately
  kept as authored copy.)

The intent: the reasoning layer must *read its own state estimate* rather than receive a raw readout.

**Setpoint regulation.** Control signals decay toward per-signal baselines/setpoints under a velocity
budget, not toward a flat midpoint, so state changes integrate rather than lurch.

**Convergence layer.** Control signals and action are integrated through arbiters
(`brain/control_signals/arbiter.py`, `brain/think/action_arbiter.py`) so the reactive and analytical
subsystems propose rather than race on shared state. A single writer owns the control-signal state
file; daemons submit proposals to a lock-guarded inbox.

---

## Runtime lifetime

A runtime-lifetime clock (`brain/cognition/runtime_lifetime.py`) rolls a finite lifetime budget
(≈365–730 days, bounded by `ORRIN_LIFESPAN_MIN_DAYS` / `ORRIN_LIFESPAN_MAX_DAYS`) on first run,
persists it across restarts, and grows horizon-awareness through four phases (early → middle → late →
terminal) that progressively colour long-term prioritization. When the deadline arrives, the runtime
runs its final cycle and the loop exits. This is distinct from the supervisor's per-process liveness
cutoff.

---

## Identity and continuity

- **Theory of mind.** `brain/cognition/theory_of_mind.py` keeps a running, predictive model of the
  person it's talking to across turns, with separate cognitive (what do they think/intend?) and
  affective (what do they feel?) empathy.
- **Revisable values.** `brain/cognition/self_state/` holds an identity and run history, a policy gate
  that can veto a proposed action against core values, a meta-policy layer (endorsing or rejecting its
  own intentions), and a value-evolution process that revises core values when they are genuinely
  contested — not on a schedule.

The persistent identity state (memory, values, identity) is hardware-independent and travels with the
runtime state.

---

## Host coupling

Orrin treats the host machine as part of its runtime context and learns that machine's normal
behavior. The same host metrics feed three deliberately separate mappings.

- **Reflex (absolute floors).** The autonomic `HostResourceGuard` (`supervisor/host_resources.py`)
  watches host disk/swap/memory below cognition and pauses heavy cycles on absolute safety floors —
  deliberately separate from the deliberative loop, because a thrashing loop can't be asked to
  rescue the substrate it runs on.
- **Control signals (deviation from a learned band).** The resource self-monitoring layer
  (`brain/cognition/host_resource_monitor.py`, `resource_self_monitor.py`, `host_band.py`) feeds the
  *same* host metrics into internal-state signals, but on **deviation from a learned band** rather
  than absolute thresholds — low/falling disk reads as a constriction signal, rising swap as a
  slowdown signal, a draining battery as a finite-horizon signal. A small or busy machine is
  therefore not registered as chronic distress.
- **Resource cadence (absolute capacity).** `resource_cadence.py` sets cycle cadence from the
  machine's size — a small machine simply runs at a slower cadence, not a degraded one.
- **Calibration on a new machine.** `infancy.py` learns *that machine's* normal oscillation before
  the runtime trusts its own deviation signals.
- **RAM budget.** A user-facing slider (`host_budget.py`, how much of the machine the runtime is
  allowed to use) feeds both the resource-cadence policy and the reported "100%".

Three mappings stay separate by design: absolute capacity → cadence, deviation → control signals,
absolute floors → reflex.

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

**Production is visible on the effect ledger** (`brain/agency/effect_ledger.py`, AR1): every
durable artifact records a content-addressed, novelty-deduped effect at the moment it is made —
symbolic productions (synthesized principles, crystallized skills, resolved experiments,
established causal edges → `symbolic_artifact`, via `brain/symbolic/symbolic_effects.py`), v2
handler artifacts (research memos, housekeeping reports → `file_write`, via the runner's
DONE-step chokepoint reading `Step.artifacts`), delivered notes/replies, verified sandbox checks
(`produce_and_check` → `tool_run_effect`), and tracked-work sections. Reward keys on the ledger:
a credited effect pays production reward at record time (`finalize_cycle`), goal closure and
milestone checks ground on `has_qualifying_effect`, and making actions pay per attempt so the
per-cycle gradient never favors pure intake (AR4).

---

## Learning surfaces

Learning is spread across several mechanisms, each learning independently from the reward signal:

- **Function selector** — the main bandit picks the next cognitive function.
- **`depth_bandit`** (UCB1) — learns how many draft→critique→revise rounds the inner loop runs.
- **`thinking_depth`** — chooses shallow vs. deep chains for goal pursuit.
- **Delayed-learning daemons** (`brain/eval/`) — credit can't always be scored at action time. The
  **evaluator** rewards a past decision when a memory it tagged is retrieved within ~50 cycles or
  its goal closes within ~200; a separate **demand-expectations** layer learns which actions actually
  relieve which demands and routes the prediction error back into the control signals.
- **Self-shaping LLM (optional, OpenAI-only).** `brain/cognition/finetuning/finetune_pipeline.py`
  filters conversation traces with outcome ≥ 0.65, submits a fine-tune job, and on completion
  repoints `model_config.json` so generation drifts toward what has worked for *it*. Symbolic-only
  mode never touches it.

The UI's **Learning** room surfaces behavior changes and belief revisions as before→after→because
diffs.

---

## Peers (outside observers)

Alongside the cognitive loop, a set of peer entities (`brain/peers/`) read Orrin's state from the
outside and, when their wake conditions fire, push *signals* into the next cycle rather than mutating
state directly:

- **Architect** — reviews self-modifications before they happen.
- **Signal Historian** — tracks chronic control-signal patterns.
- **Goal Auditor** — flags low-quality goals.
- **Observer** — catches unproductive loops.
- **Reward Auditor** — notices when the bandit's reward signal has collapsed to noise.

They register themselves in the world model / relationships on first wake and flow through the same
`signal_router` as everything else, so they nudge attention without ever issuing commands.

---

## LLM as a tool

The decision loop and demand system are fully symbolic. The LLM is an explicit tool the agent chooses
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
