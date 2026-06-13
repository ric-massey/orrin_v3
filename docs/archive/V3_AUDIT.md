# Orrin V3 Architecture Audit — Homeostatic Convergence

> **Status (verified 2026-06-10): ALL phases 0–7 implemented.** Re-verified
> against the working tree on `convergence-layer`:
> - **P0** safety net: `tests/brain/test_affect_single_writer.py` (incl. the
>   concurrency + drain_consolidations tests) green.
> - **P1/D2** daemon race closed: dream/consolidation submit to the thread-safe
>   arbiter inbox; no daemon `save_json(AFFECT_STATE_FILE)` remains.
> - **P2/D3** single decay law: `decay_affect_state` deleted;
>   `affect/homeostasis.py` owns restoring forces toward `setpoints.py`
>   (`CORE_BASELINES` co-located there as the one source of truth).
> - **P3/D1** writers folded: remaining direct writes are only the canonical
>   owner (`update_affect_state.py`), the boot-event cap (`ORRIN_loop.py` —
>   explicitly allowed by §3.1), and the documented context-less fallbacks in
>   `log_penalty_signal` / `affect.py` (per the Phase-3 rollback posture).
> - **P4/D8** velocity budget: `enforce_velocity_budget` enforced in
>   `update_affect_state` (writes `_affect_velocity_l1`), plus a post-clamp
>   chronic-distress drain.
> - **P5/D4/D7** behavioral queue: every `insert(0)` injector replaced by
>   `propose_action` (`action_gate.py`); the threat shortcut joins the
>   ActionArbiter as a spike-weighted proposal (`select_function.py` threat-vote
>   block), with hysteresis. `tests/brain/test_behavioral_queue.py` green.
> - **P6/D5** RewardEngine: `affect/reward_signals/reward_engine.py` is the
>   single RPE funnel (EMA baseline); finalize / priming / calibrator submit
>   through it, goal_progress / env_snapshot are actual-providers.
> - **P7/D6/D9/D10** observers + schema: `affect/observers.py`
>   (`negative_load`, `normalize_affect_state` — called on load by the canonical
>   owner), threat computed once per cycle into
>   `context["threat_detector_response"]`, priming prefers in-context state over
>   disk. Arbiter retains a defensive flat-layout branch as belt-and-suspenders.
>
> Full `tests/brain` suite: 161 passed. Audit retained below for reference.

**Scope:** transition from a research-grade *override* model to a production-grade
*homeostatic convergence* model. Branch `convergence-layer` already lands a V2
foundation (AffectArbiter, ActionArbiter, setpoints, reward `release_reward`). This
audit assesses what V2 covers, where the override/race model still leaks, and the
contract + migration path to V3.

Evidence is cited as `file:line`. All citations verified against working tree on
branch `convergence-layer`.

---

## 0. State of play (what V2 already fixed)

| Surface | V2 status |
|---|---|
| Affect convergence point | `affect/arbiter.py` — `submit_affect`/`commit_affect`, stability budget 0.60, away-from-setpoint costs 2× |
| Action convergence point | `think/action_arbiter.py` — weighted vote + hysteresis margin 0.10 + veto lane |
| Setpoints SoT | `affect/setpoints.py` |
| Threat override → vote | `select_function.py:950-991` (was step-function `if spike>0.65`) |
| Reward emitter dedup | `reward_signals.release_reward` (finalize/execute_cognitive aliases) |
| Commit point | `ORRIN_loop.py:2246-2250` (`commit_affect` once per cycle) |

V2 is sound but **partial**: it added the convergence *primitives* and routed the
in-loop callers through them. The leaks below are the writers, daemons, and
recalculators that still bypass those primitives.

---

## 1. Surface Contention & Thread Safety

### 1.1 Affect state — last-writer-wins is still live (CRITICAL)

`save_json` is atomic at the *write* but the **read-modify-write sequence is not
transactional**:

- `save_json` takes the advisory `flock` only around the temp-write + `os.replace`
  (`json_utils.py:296-311`), then **unlinks the lockfile in `finally`**
  (`json_utils.py:331`). Two writers can therefore `flock` *different inodes* — the
  lock does not reliably serialize.
- `load_json` takes **no lock at all** (`json_utils.py:336-350`).

So every `load_json(AFFECT_STATE_FILE) → mutate → save_json(AFFECT_STATE_FILE)`
is a classic lost-update window. There are **12 direct affect-file writers**:

| Site | Pattern | Thread |
|---|---|---|
| `ORRIN_loop.py:547` | boot cap → full overwrite | main |
| `utils/emotion_utils.py:35` (`decay_affect_state`) | load→pull-to-0.5→save | caller-dependent |
| `utils/emotion_utils.py:148` (`log_penalty_signal`) | load→+inc→save | main + action_gate |
| `utils/emotion_utils.py:259` (`contextual_emotion_priming`) | load→priming→save | main |
| `affect/affect.py:133` | full overwrite | main |
| `affect/emotional_feedback.py:50` | full overwrite | main |
| `affect/consolidation.py:154` (`drain_consolidations`) | full overwrite | **dream daemon** |
| `affect/regulation.py:235` (`attempt_regulation`) | full overwrite | main |
| `affect/update_affect_state.py:654` | canonical owner | main |
| `affect/feedback_log.py:122` | full overwrite | main |
| `eval/drive_expectations.py:118` | full overwrite | main |
| `cognition/dreaming/dream_cycle.py:709` | load→mutate→save | **dream daemon** |

The **provable cross-thread race**: `dream_cycle` is spawned as a daemon thread
(`ORRIN_loop.py:2128-2134`, `name="orrin-dream", daemon=True`). Inside it,
`dream_cycle.py:705-709` does `load_json(AFFECT_STATE_FILE) → mutate → save_json`,
and `consolidation.drain_consolidations` (`consolidation.py:154`) overwrites the
whole file — both concurrent with the main loop's `update_affect_state`
(`update_affect_state.py:654`) and `commit_affect`. Whichever finishes second
silently discards the other's deltas, including the carefully budgeted output of
the AffectArbiter.

**Design smell beyond the race:** two *different* decay laws fight each other.
`emotion_utils.decay_affect_state` pulls every signal toward **0.5**
(`emotion_utils.py:27`), while `update_affect_state` decays toward
**per-signal baselines** (negatives→0, drives→mid; `update_affect_state.py:66-105,
317-323`). These are contradictory restoring forces depending on which writer ran
last — a homeostatic system cannot have two setpoints for one signal.

**V3 fix:** single-writer. Only `update_affect_state` (main loop) may write
`AFFECT_STATE_FILE`. Every other producer becomes a `submit_affect` proposal
(see §5). Daemons never touch affect on disk; they submit proposals onto a
thread-safe inbox drained at commit. Retire `decay_affect_state` entirely;
`setpoints.py` becomes the only restoring-force authority.

### 1.2 Action execution — competing priority-jump injectors (HIGH)

`pending_actions` is a list and **every injector does `insert(0, …)`** to force
front-of-queue execution, bypassing `score_action`:

- `action_gate.py:214` spontaneous expression
- `action_gate.py:261` values-check refuse
- `action_gate.py:277` boundary refusal
- `action_gate.py:318` user response
- `action_gate.py:427` clarification question
- `action_gate.py:436` retry re-insert
- `action_gate.py:628, 636` forced-agentic / best-action

The consumer (`action_gate.py:394-456`) pops the head and runs `take_action`
*before* the proposal scorer (`score_action` at `:474`) is ever consulted. So the
scorer only ranks what the injectors didn't pre-empt — exactly the "centralized
scorer routinely bypassed" pattern. Priority is encoded two incompatible ways: a
string `priority` field on goals/events (`ORRIN_loop.py:577`,
`alive_brain.py:133+`) and list-position urgency in `pending_actions`. There is no
single arbiter for "what runs now."

Note the **threat reflex is already converged** (`select_function.py:950-991`
routes through `ActionArbiter`) — but that arbiter governs *cognitive-function
selection*, while the *behavioral* action queue (`pending_actions`) has no arbiter
at all. The two halves of "what to do" are themselves split.

**V3 fix:** all behavioral entry points emit `ActionProposal`s into the
ActionArbiter (urgency/veto already model what `insert(0)` was hacking). User
response and boundary-refuse map to `veto`/high-urgency proposals — same effect,
one resolution path. `score_action` becomes the vote function feeding the arbiter,
not a parallel ranker.

---

## 2. Functional Convergence & De-Duplication

### 2.1 Reward — five formulas, no single signal (HIGH)

`release_reward_signal` (`reward_signals.py:13`) is the emitter, but the
*reward value* is computed independently in at least five places, each with its
own scale and expected-reward baseline:

| Source | Formula / baseline | File |
|---|---|---|
| Core RPE | `actual-expected`, effort-modulated, phasic ×1.7 | `reward_signals.py:36-53` |
| Goal progress | `compute_goal_progress`, blended `0.6·gp+0.4·base` | `planning/goal_progress.py:81-104` |
| Delta reward | env pre/post snapshot diff | `planning/env_snapshot.py` |
| Calibrated | 4 weighted sources, retrieval capped 0.08, `expected=0.05` | `reward_calibrator.py:15-103` |
| Priming | `total_delta/len`, hardcoded `expected=0.5` | `emotion_utils.py:247-255` |

These feed the **same** `motivation`/`exploration_drive`/`positive_valence`
signals with **different expected-reward baselines** (0.05 vs 0.5 vs per-action
EMA). A goal-progress reward and a calibrated reward for the same cycle can encode
contradictory RPE because they disagree on the prediction baseline — the learning
signal is internally inconsistent.

**V3 fix:** a `RewardEngine` that owns one RPE definition `(actual − expected)`
where `expected` always comes from the per-action EMA (`action_reward_ema.py`,
already the intended SoT per memory). goal_progress / delta / calibrated become
*actual-reward providers* feeding that single RPE, not parallel emitters.
`release_reward` stays the only thing that touches affect.

### 2.2 Salience & threat — recalculated per consumer (MEDIUM)

- **Threat** is computed canonically by `threat_detector.process_affective_signals`
  (`threat_detector.py:16`) into `context["threat_detector_response"]`. But
  `threat_level`/`spike` are *also* re-derived ad hoc in `select_function.py:533,
  1034`, `reward_signals.novelty_penalty:261,288,297`, and the `_gd_neg` sum at
  `select_function.py:1034`. Each consumer re-reads core signals and re-applies its
  own thresholds.
- **Salience** has no single producer: `CycleState`/`compute_cycle_state`
  (`state_processor.py:111`) computes output-pressure salience; `memory_io.py:119,
  181` computes memory salience; `reward_signals.decay_reward_trace:219` reads a
  per-entry `salience`. Three unrelated notions share the word.

**V3 fix:** promote `threat_detector_response` to a canonical read-only observer
written once per cycle (before selection) that all consumers *read* rather than
recompute. Define salience explicitly per domain (attention-salience vs
memory-salience) so the overload stops masquerading as one concept.

---

## 3. Cognitive Hysteresis & Stability

### 3.1 Split-brain binary overrides

- **Threat → cognitive function:** FIXED in V2 (`select_function.py:950-991`).
- **Threat → behavior shortcut:** `threat_detector.py:80-111` still emits a hard
  `shortcut_function` from step-function thresholds (`_FIGHT_THRESHOLD=0.75`,
  etc., `threat_detector.py:6-13`). Downstream consumers of `shortcut_function`
  still get a binary flip at the boundary. This shortcut should become an
  `ActionProposal` weighted by `spike_intensity`, not a hard label.
- **Boot dampening** (`ORRIN_loop.py:526-543`): a one-shot `×0.65` multiply +
  hard `_POSITIVE_CEILING=0.75` clamp written straight to disk — outside any
  budget. Acceptable as a boot event, but it should go through the same restoring
  machinery rather than a bespoke overwrite.

### 3.2 Centralized homeostasis — partially built, not unified

Restoring/decay logic is scattered across **at least six** locations with
independent rates and targets:

| Logic | Target | Rate | File |
|---|---|---|---|
| `decay_affect_state` | → 0.5 | `stability_decay_rate` | `emotion_utils.py:16-36` |
| `update_affect_state` baseline decay | → per-signal baseline | `decay_rate`, hours-scaled | `update_affect_state.py:317-323` |
| antagonist decay | → baseline | `×0.7` excess | `update_affect_state.py:437-457` |
| habituation decay | — | time-based | `affect_dynamics.py:71` |
| hedonic baseline | drifting baseline | EMA | `affect_dynamics.py:267` |
| reward-trace decay | strength→0 | `0.015` modulated | `reward_signals.py:188-237` |

The AffectArbiter's stability budget (`arbiter.py:45`) caps *inbound* velocity but
nothing caps the *net* per-cycle velocity once decay + drain + triggers all apply
inside `update_affect_state`. The "max emotional velocity" the objective asks for
is not yet enforced as a single mathematical cap.

**V3 fix:** a `HomeostasisManager` that owns *all* restoring forces (one decay law
toward `setpoints.py`, replacing `decay_affect_state` and folding the antagonist
pull) and enforces a per-cycle **velocity budget**: after drain+decay+commit, the
total L1 movement of `core_signals` from its cycle-start snapshot is clamped to a
configured max (the snapshot already exists — `capture_prev_core`,
`update_affect_state.py:146`).

---

## 4. Production-Grade Engineering Rigor

### 4.1 Interface enforcement
- Affect state is a free-form `dict` with **dual layout** (`core_signals` nested
  *or* flat) handled defensively everywhere (`arbiter.py:124-127`,
  `threat_detector.py:20-29`, `reward_signals.py:46-48`). This branching is a
  schema smell — pick one layout, validate on load.
- No typed boundary between fast daemons (dream, tool_runner, tamper_guard) and
  the analytical loop; daemons reach directly into shared dict + disk.
- `ActionProposal` is a clean dataclass; affect proposals are bare dicts
  (`arbiter.py:82-88`). Unify on dataclasses + a schema validator.

### 4.2 Performance
- `contextual_emotion_priming` reloads `WORKING_MEMORY_FILE`, `MODE_FILE`,
  self-model from disk every call (`emotion_utils.py:175-178`) — high-frequency
  disk reads of state already in `context`.
- Multiple `load_json(AFFECT_STATE_FILE)` per cycle across the 12 writers when one
  in-memory `context["affect_state"]` already exists.
- `select_function` recomputes negative-sum / threat features twice
  (`:533`, `:1034`).

---

## Deliverable 1 — Technical Debt Ledger (prioritized)

| # | Severity | Class | Item | Evidence | Fix |
|---|---|---|---|---|---|
| D1 | **CRITICAL** | Race | Non-transactional load→mutate→save on affect; lockfile unlinked per write | `json_utils.py:296-333`, 12 writers §1.1 | Single-writer + thread-safe proposal inbox |
| D2 | **CRITICAL** | Race | Dream daemon writes affect concurrently with main loop | `ORRIN_loop.py:2128`, `dream_cycle.py:705-709`, `consolidation.py:154` | Daemons submit proposals only |
| D3 | **HIGH** | Conflict | Two contradictory decay laws (→0.5 vs →baseline) | `emotion_utils.py:27` vs `update_affect_state.py:317` | Retire `decay_affect_state`; setpoints SoT |
| D4 | **HIGH** | Silo | `pending_actions.insert(0)` injectors bypass scorer | `action_gate.py:214,261,277,318,427,628` | Route all through ActionArbiter |
| D5 | **HIGH** | Silo | 5 reward formulas, inconsistent `expected` baselines | §2.1 table | `RewardEngine`, single RPE |
| D6 | **MEDIUM** | Dup | threat/salience recomputed per consumer | `select_function.py:533,1034`; salience §2.2 | Canonical observers |
| D7 | **MEDIUM** | Override | Binary `shortcut_function` threshold flip | `threat_detector.py:80-111` | Weighted ActionProposal |
| D8 | **MEDIUM** | Stability | No net per-cycle velocity cap | `update_affect_state.py` | `HomeostasisManager` velocity budget |
| D9 | **LOW** | Schema | Dual nested/flat affect layout branching everywhere | `arbiter.py:124`, `threat_detector.py:20` | One validated schema |
| D10 | **LOW** | Perf | Redundant disk reloads of in-context state | `emotion_utils.py:175` | Read from `context` |

---

## Deliverable 2 — Interface Contract Blueprint (Arbiter layer)

Three arbiters mediate **all** state mutation and action resolution. Nothing
outside an arbiter may write `affect_state`, emit reward, or run an action.

```
                 ┌───────────── main cognitive loop (single writer) ──────────────┐
 daemons ──┐     │                                                                 │
 (dream,   │ submit_affect()      submit_reward()        propose_action()          │
 tool,     ├────────────►  AffectArbiter   RewardEngine    ActionArbiter           │
 tamper)   │ (thread-safe   │ integrate→     │ one RPE       │ weighted vote        │
           │  inbox)        │ budget→        │ (actual,      │ +hysteresis          │
           │                │ velocity cap   │  expected=EMA)│ +veto                │
           │                ▼                ▼               ▼                      │
           │          HomeostasisManager  release_reward   take_action             │
           │          (decay→setpoints,   (only emitter)   (only executor)         │
           │           velocity budget)        │               │                   │
           │                └──────► update_affect_state ◄──────┘                  │
           │                         (ONLY writer of AFFECT_STATE_FILE)            │
           └─────────────────────────────────────────────────────────────────────┘
```

### Contract A — AffectArbiter (extend existing)
```python
# Producers (any thread):
submit_affect(context|inbox, target: str, delta: float, *,
              weight: float = 1.0, source: str, ttl_cycles: int = 3) -> None
# Convergence (main loop, once/cycle, just before persist):
commit_affect(context) -> dict[str, float]      # integrate→budget→queue
```
- **Invariant:** only `update_affect_state` writes `AFFECT_STATE_FILE`.
- **Thread safety:** daemon submissions go to a `queue.Queue`/lock-guarded inbox;
  `commit_affect` drains it. Replaces the per-thread `load→save`.
- **Stability:** away-from-setpoint deltas cost 2× (kept); add net velocity cap.

### Contract B — ActionArbiter (extend existing)
```python
@dataclass
class ActionProposal:
    name: str; vote: float; weight: float = 1.0
    urgency: float = 0.0; veto: bool = False; source: str = ""
resolve(proposals, *, incumbent, margin=0.10) -> (winner, info)
```
- **New:** behavioral entry points emit proposals instead of `insert(0)`.
  user_response/refuse → `urgency≥0.9` or `veto=True`; forced-agentic → high
  `weight`; retry → incumbent re-vote. `score_action` becomes the `vote` function.
- **Invariant:** `take_action` runs exactly the arbiter winner per cycle.

### Contract C — RewardEngine (new, thin)
```python
submit_reward(context, *, actual: float, kind: str, action_type: str,
              effort: float = 0.5, source: str) -> None
#   expected := action_reward_ema.expected(action_type)   # single baseline
#   rpe := actual - expected  → release_reward(...)        # single emitter
```
- goal_progress / delta / calibrated become `actual` providers, not emitters.

### Contract D — HomeostasisManager (new)
```python
apply_restoring_forces(state, core, *, hours_passed) -> None   # → setpoints only
enforce_velocity_budget(core, prev_core, *, max_l1) -> None     # net cap
```
- Owns the single decay law; `decay_affect_state` deleted.

### Schema (Contract E)
- Canonical `AffectState`: `{core_signals: dict[str,float], resource_deficit,
  affect_stability, _emotion_queue, last_updated}`. Validate on load; drop the
  flat-layout branches once migrated.

---

## Deliverable 3 — Incremental Refactoring Strategy

Each phase is independently shippable, test-gated, and leaves the core loop green.
Baseline before starting: full suite (memory notes 396 pass / 12 pre-existing
fails). No phase may increase the failure count.

**Phase 0 — Safety net (no behavior change).**
Add `tests/brain/test_affect_single_writer.py` asserting only `update_affect_state`
writes `AFFECT_STATE_FILE` (monkeypatch `save_json`, run a cycle). Add a
concurrency stress test spawning the dream daemon + main update to reproduce D2.
These start red — they are the acceptance gate.

**Phase 1 — Close the daemon race (D2, D1 partial).**
Make daemon affect writes proposals: `dream_cycle.py:705-709`,
`consolidation.py:154` → `submit_affect` into a lock-guarded inbox; remove their
`save_json(AFFECT_STATE_FILE)`. Fix `json_utils` lockfile lifetime (don't unlink;
or switch reads to take the shared lock) so any residual writer is at least
serialized. Ship when the Phase-0 concurrency test goes green.

**Phase 2 — Single decay law (D3).**
Introduce `HomeostasisManager.apply_restoring_forces` wrapping the existing
`update_affect_state` baseline decay; delete `decay_affect_state` and repoint its
caller(s). Setpoints become the only target. Regression: affect snapshot tests.

**Phase 3 — Fold remaining affect writers (D1 complete).**
Convert the 8 remaining file-writers (§1.1) to `submit_affect`. `emotion_utils`
already has the routed path (`emotion_utils.py:59-71`) — extend that pattern to
`log_penalty_signal`, `contextual_emotion_priming`, `affect.py`,
`emotional_feedback.py`, `regulation.py`, `feedback_log.py`,
`drive_expectations.py`. Keep file-write fallback only for genuinely context-less
callers, log when it fires. Then make `update_affect_state` the sole writer.

**Phase 4 — Velocity budget (D8).**
Add `enforce_velocity_budget` using the existing `prev_core` snapshot
(`update_affect_state.py:146`). Tune `max_l1` so normal cycles pass untouched
(mirror the budget-tuning approach in `arbiter.py:42-45`).

**Phase 5 — Unify behavioral queue (D4, D7).**
Replace `pending_actions.insert(0)` injectors with `ActionProposal`s; make
`score_action` the vote fn; route `threat_detector.shortcut_function` through the
arbiter as a spike-weighted proposal. The cognitive-function arbiter
(`select_function.py:950`) and behavioral arbiter now share one resolution path.

**Phase 6 — RewardEngine (D5).**
Introduce `submit_reward`; repoint goal_progress / env_snapshot / reward_calibrator
/ priming to provide `actual` only; single `expected` from EMA. `release_reward`
stays the lone emitter.

**Phase 7 — Observers & schema (D6, D9, D10).**
Promote `threat_detector_response` to a once-per-cycle read-only observer; remove
ad-hoc threat recomputes. Validate `AffectState` schema on load; delete flat-layout
branches. Read in-context state instead of disk in `contextual_emotion_priming`.

**Rollback posture:** Phases 1/3 keep the file-write fallback path until the
single-writer test is green in CI for N runs; the arbiters already swallow
exceptions and fall back (`arbiter.py:120-122`, `emotion_utils.py:72-73`), so a
bad proposal degrades to no-op rather than a crash.

---

## Appendix — Verified key citations
- `json_utils.py:296-333` lock around write only; lockfile unlinked per write
- `json_utils.py:336-350` `load_json` takes no lock
- `ORRIN_loop.py:2128-2134` dream daemon spawn; `:2246-2250` commit point; `:547` boot affect write
- `dream_cycle.py:705-709`, `consolidation.py:154` daemon affect writes
- `arbiter.py:45,48,106-162` budget/integrate/commit
- `action_arbiter.py:52-100` resolve/hysteresis/veto
- `select_function.py:950-991` threat→vote (V2)
- `action_gate.py:214,261,277,318,427,628,636` `insert(0)` injectors; `:474` score_action
- `threat_detector.py:6-13,80-111` step-function thresholds + shortcut
- `emotion_utils.py:16-36` decay→0.5; `:39-116` adjust (routed); `:247-255` priming reward
- `reward_signals.py:13,36-53,324-348` emitter/RPE/release_reward
- `goal_progress.py:81-104`, `reward_calibrator.py:15-103`, `env_snapshot.py` reward formulas
- `update_affect_state.py:66-105,146,317-323,437-457,457-484` baseline/decay/ceiling/velocity
