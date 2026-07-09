# Production and the Effect Ledger

The effect ledger (`brain/agency/effect_ledger.py`) is the **denominator the reward function was
missing**. Before it, reward was denominated in internal events — and internal events are free and
infinite — so the rational policy was to churn cognition forever and never produce anything.
Reading paid exactly what making paid. The ledger fixes that by making *durable outward effects*
the thing that pays.

## What the ledger is

An append-only, **content-addressed** log of real outward effects, written at the moment of the
effect. Duplicates earn nothing (novelty dedup), so re-emitting the same artifact can't farm
reward. It lives in `brain/agency/` — the action side — not in cognition.

## What counts as an effect

- **Symbolic productions** — synthesized principles, crystallized skills, resolved experiments,
  established causal edges → `symbolic_artifact`, recorded via `brain/symbolic/symbolic_effects.py`.
- **Goal handler artifacts** — research memos, housekeeping reports → `file_write`, registered at
  the goals runner's DONE-step chokepoint from `Step.artifacts`.
- **Delivered notes and replies** — things a person actually received (through the
  [expression membrane](Expression_Membrane)).
- **Verified sandbox checks** — `produce_and_check` outputs that passed → `tool_run_effect`.
- **Tracked-work sections** — durable sections of long-form work
  (`brain/data/tracked_work/`).

Artifact files are captured under `brain/data/effect_artifacts/` (`EFFECT_ARTIFACTS_DIR` in
`brain/paths.py`); the ledger stores content hashes.

## How reward keys on it

- A credited effect pays **production reward at record time** (`finalize_cycle`).
- **Goal closure and milestone checks ground on the ledger** (`has_qualifying_effect`) — a goal
  cannot claim completion without a qualifying recorded effect.
- **Making actions pay per attempt**, so the per-cycle gradient never favors pure intake over
  production, even before an attempt succeeds.
- Quality is enforced upstream by the [quality standard](Quality_Standard): passing the bar is
  what makes an artifact creditable, so template-stamped or low-effort output doesn't pay.

## Fail-able aspirations

The complement to paying for production is being allowed to fail: long-horizon aspirations carry
guards instead of living forever, so a goal that stops producing is failed and replaced rather than
absorbing attention indefinitely.

## Code pointers

- `brain/agency/effect_ledger.py` — the ledger (design: `ORRIN_PRODUCTION_REWARD_PLAN_2026-06-18`)
- `brain/symbolic/symbolic_effects.py` — symbolic production recording
- `goals/runner.py` — the DONE-step artifact chokepoint
- `brain/data/effect_artifacts/`, `brain/data/tracked_work/` — runtime artifact trees
