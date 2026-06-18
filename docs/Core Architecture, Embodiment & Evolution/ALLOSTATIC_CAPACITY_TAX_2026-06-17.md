# Allostatic Capacity Tax — wiring fatigue into emotional capacity

**Status:** design note (not yet built). Companion to the flatline fix shipped
2026-06-17 (pump-saturation ceiling enforcement + stuck-high stagnation watchdog).

## The gap

`energy = 1 − resource_deficit` (`ORRIN_loop.py`, `interoception.py`,
`working_memory.py`). `resource_deficit` accumulates ~+0.002/cycle and decays
toward an allostatic τ with accelerated recovery above 0.75
(`update_affect_state.py`, the resource_deficit block). Today it gates:

- working-memory capacity (`working_memory.py` — energy → WM cap), and
- function-selection scoring (`select_function.py` — the `s_energy` term).

What it does **not** do: tax the affective drives. There is no path by which a
high `resource_deficit` forces `motivation` / `confidence` / `positive_valence`
down. Orrin can be mathematically exhausted and still "manically content" — the
two systems are decoupled.

Note there *are* already two capacity taxes, but both are keyed on **physical
vitals**, not on the affective deficit float:

- `body_sense.interoceptive_deltas` — `heavy`/`strained` body states sap
  `motivation` and pump `impasse_signal`, but those states derive from RSS /
  cycle-latency vitals, not `resource_deficit`.
- the `stress_load` allostatic-load block in `update_affect_state.py` — reduces
  `motivation` and raises `risk_estimate`, but it is gated on `_stress_streak`
  (consecutive stressed body readings), again physical.

So the machinery and the biological framing already exist; they are simply not
fed by the affective fatigue signal.

## The idea

Extend the **existing** `stress_load` block (do not add a second parallel
system) so the motivation/capacity tax is driven by `max(stress_streak_load,
resource_deficit_load)`. Concretely:

- Derive a load term from `resource_deficit` once it crosses a fatigue
  threshold (e.g. `> 0.55`): `rd_load = (resource_deficit − 0.55) / 0.45`.
- Take `load = max(existing_stress_load, rd_load)` and apply the same gentle
  per-cycle pulls already in that block: `motivation −= load * k`,
  `risk_estimate += load * k'`, with the same baseline floor so it can fatigue
  but not flatline to zero.
- Optionally surface one working-memory note on threshold crossing ("I'm
  running on empty — drive is harder to summon") so the felt state is legible,
  mirroring the existing `[allostatic_load]` note.

McEwen (2007) / Arnsten (2009): sustained allostatic load degrades PFC-mediated
motivation and executive control — the same citation the `stress_load` block
already carries. This change just makes the affective deficit a legitimate
*source* of that load, not only the physical streak.

## Why this is a separate change from the flatline fix

The flatline observed on 2026-06-17 (motivation ≈ 0.96, variance ≈ 0) happened
while `resource_deficit` was **low (0.12)** — Orrin was pinned without being
fatigued. So a fatigue→capacity tax would not have touched that instance; the
pin was caused by reward pumps out-running the once-per-cycle ceiling clawback
(now fixed by routing pumps through `homeostasis.pump_signal`, which respects
`EMO_CEILINGS`). This tax is the *complementary* case: when Orrin genuinely is
depleted, capacity should shrink so the drives can't stay maxed on an empty
tank. The two together close both halves of the allostatic loop — one bounds the
ceiling against runaway pumps, the other lowers the effective ceiling under load.

## Risks / notes

- Keep the pull gentle and floored. The goal is "drive is harder under
  exhaustion," not a depression spiral. The `stress_load` block's existing floor
  (`baseline * 0.5`) is the right model.
- Recovery is already non-linear (faster above 0.75), so the tax self-limits:
  as deficit recovers, the tax fades.
- This taxes *capacity*, not the felt positives directly — pair it with the
  existing stagnation/boredom watchdog rather than crushing `_EMO_CEILINGS`
  (crushing ceilings flattens arousal toward a low-energy state instead of
  prompting a behavioural change).
