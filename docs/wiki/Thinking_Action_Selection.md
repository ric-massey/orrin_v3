# Thinking / Action Selection

`brain/think/` decides what runs next, every cycle. It is the module where control signals, the
workspace, goals, and learned value all converge into a single pick.

## The selection path

1. **Deliberation gate** (`deliberation_gate.py`, `should_think()`) — decides whether this cycle
   ignites into full deliberation or stays in low-power default mode (see
   [Workspace and Ignition](Workspace_and_Ignition)). Non-ignited cycles damp effortful
   functions so quiet time drifts toward cheap work.
2. **Function selector** (`think_utils/select_function.py`) — a contextual bandit picks the next
   cognitive function. Control-signal floats, demands, cost predictions, and the workspace winner
   (an additive prior, `ORRIN_WORKSPACE_PRIOR`) all bias the draw. The bandit honors an explicit
   learning rate (constant-step), with a modulated adaptive rate available. Candidate scoring
   (`think_utils/selection/score_actions.py`) also adds each action's learned reward EMA (once the
   action is mature, ≥8 observations) directly, so
   realized outcomes — not just priors — decide what wins (see
   [Learning and Adaptation](Learning_and_Adaptation)).
3. **Action arbiter** (`action_arbiter.py`) — the convergence layer's action half: reactive and
   analytical subsystems **propose**, the arbiter resolves, so nothing races on shared state.
4. **Execution** — the chosen function runs; `sandbox_runner.py` executes generated code safely;
   outcomes feed reward accounting and the effect ledger.

## Deliberate reasoning (System 2)

- `inner_loop.py` — the deliberate draft→critique→revise reasoning loop, recruited on ignited
  *and conflicted* cycles (`ORRIN_CONFLICT_RECRUIT`) rather than fired on a schedule.
- `inner_loop_symbolic.py` — the symbolic-only variant, so deliberation works without an LLM.
- `inner_loop_critique.py` — the critique pass; `depth_bandit.py` (UCB1) learns how many rounds
  are worth running; `meta_controller.py` chooses shallow vs. deep chains for goal pursuit.
- `scratchpad.py` and `simulate.py` — working notes and look-ahead simulation of candidate actions.

## Cost-aware selection

`brain/cognition/cost_prediction.py` is an expected-value-of-control layer: each function's
predicted cost (time, tokens, energy) competes against its predicted payoff, so expensive functions
must be worth it. Attention can still be hijacked by urgent signals (`brain/cognition/attention.py`).

## Speech

`speech_builder.py`, `speech_coherence.py`, `speech_comprehension.py` — building and checking
person-facing utterances. Actual delivery goes through the one door:
[Expression Membrane](Expression_Membrane).

## Debugging

Bandit statistics, per-function EMAs, and EVC predictions are surfaced in the UI's Cognition room;
instrument those first when diagnosing mis-selection. The Reward Auditor peer flags a reward signal
that has collapsed to noise.

## Code pointers

- `brain/think/` — everything above
- `brain/think/bandit/` — bandit implementation
- `brain/cognition/cost_prediction.py` — EVC layer
