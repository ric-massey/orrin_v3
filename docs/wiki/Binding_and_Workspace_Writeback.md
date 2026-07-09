# Binding and Workspace Writeback

Two mechanisms bracket the global-workspace competition described in
[Workspace and Ignition](Workspace_and_Ignition): **binding** composes richer candidates on the
way *in*, and **writeback** lets the winning content gently bias the substrate on the way *out*.

## Binding (pre-workspace)

`brain/cognition/binding.py` is pre-workspace symbolic feature binding. Instead of the workspace
competing only over atomic fragments ("disk pressure", "goal X stalled", "user said Y"), the
binding stage composes bounded, **unified situation candidates** from co-occurring fragments and
adds them to the competition.

Design constraints that keep it honest:

- It **never removes** atomic candidates and never declares anything conscious; composites must
  win the existing salience competition on their own merits.
- Composites are bounded in size and count, so binding cannot flood the competition.
- Since the 2026-07-03 run, bound situations feed the workspace for the whole life of a run, so the
  thought stream can be *about a situation* rather than about disconnected fragments.

## Writeback (post-broadcast)

`brain/cognition/workspace_writeback.py` closes the loop downward — in a deliberately **decaying**
form (on the main path, no flag). After a conscious moment is selected, writeback nudges priors:

- a small, low-weight, TTL-bounded **affect proposal** (integrated by the next cycle's
  `commit_signals`) keyed to the *kind* of conclusion reached, and
- Hebbian **priming of the winner's tokens** in a bounded, per-cycle-decaying salience-prior store
  that biases the next competition toward the same theme.

Two properties make it permanent and safe to keep on:

1. **Every write decays** — affect TTL drain plus salience decay. Nothing accumulates.
2. **There is no promotion path** to a durable baseline, to `concept_memory`, or to identity. The
   substrate *tracks* recent conclusions for long-run coherence but never *becomes* a different
   substrate ("coherent-but-adult" — no ontogeny).

Reflex floors and absolute scalars are never writeback targets ("refuse-to-imprint" by
construction): the safety reflexes cannot be re-tuned by whatever the runtime happens to conclude.

## Why it matters

Together, binding and writeback give the thought stream continuity of *topic* without giving the
reasoning layer the ability to rewrite its own substrate. Attention can dwell; identity cannot
drift by accident.

## Code pointers

- `brain/cognition/binding.py` — situation composition
- `brain/cognition/workspace_writeback.py` — decaying downward path
- `brain/cognition/global_workspace.py` — the competition both plug into
