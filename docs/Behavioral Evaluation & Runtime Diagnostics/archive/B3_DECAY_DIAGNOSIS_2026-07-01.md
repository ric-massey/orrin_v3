# B3 Diagnosis Note — which cause it actually was

**Date:** 2026-07-01
**Closes:** the P5 "reality check" required by
`IMPLEMENTATION_PLAN_GROUNDING_AND_SURFACE_2026-06-30.md` Phase 5. Recorded so we
do not re-litigate B3.
**Unblocks/archives when:** AR8 (energy breathes) lands and a run shows
rise-and-recover curves.
**CLOSED 2026-07-02:** condition met — AR8 landed (commit `db4a139`) and the
2026-07-02 run (10,065 telemetry rows) shows full low→high recovery arcs:
curiosity **180**, motivation **26**, confidence 2 — vs. this doc's pinned-flat
0.81–0.84 evidence from 07-01. See `demo_runs/2026-07-02-run/2026-07-02_run_analysis.md`.

## The question

The synthesis observed "hot and flat" behavior with repeated phrases and proposed
two candidate causes: (a) drives genuinely pin because pump rate beats decay rate
(a tuning stall in the existing restoring law), or (b) LM phrase-level repetition
(a `native_lm.generate` sampling defect). The plan mandated diagnosing before
touching code, because decay/repetition machinery already exists and must not be
rebuilt.

## The evidence (2026-07-01 run, ~21.7 h, 14,469 cycles)

From `demo_runs/2026-07-01-run/2026-07-01_run_analysis.md`:

- **Drives pin — confirmed.** motivation **0.836**, curiosity **0.844**,
  confidence **0.806** "pinned high and barely move all life — the same 'hot and
  flat' saturation 06-29 diagnosed" (§2, §4.4). The only terminal pullback came
  from goal *failure* registering as impasse, not from homeostatic relaxation.
- **Phrase repetition — already fixed upstream.** The "hot and flat" self-report
  went from **70× on 06-29 to 0× this run** after the appraisal-habituation work;
  the run analysis explicitly concludes "drives (not just phrases) are what pin"
  (§7 item 3).
- **`allostatic_load` = 0.000 all life** — but that integrator tracks
  `resource_deficit` (fatigue), which only accrues load above 0.60; it is not the
  drive-plateau mechanism and is not the B3 fix site.

## The verdict

**Cause (a): pump-beats-decay tuning stall in the per-call restoring force.**
The per-call pull (`update_signal_state.py`, rates 0.02/0.025/0.05 of the gap)
reaches equilibrium against every-cycle pumps at ~0.84 and stays there. Not a
missing decay law — the law exists and works for acute spikes; it just never
strengthens against *chronic* pinning.

Cause (b) was real on 06-29 but was resolved by the appraisal-habituation work;
`native_lm.generate` nonetheless had **no** repetition control at all
(temperature only), so a cheap standing guard was warranted.

## The fix (landed with this note)

Per the plan — *tune the existing law, do not add a second one*:

1. **Time-at-ceiling accelerator** on the existing per-call restoring pull
   (`homeostasis.update_pin_streaks` / `pin_multiplier`, consumed by
   `update_signal_state`): a signal sitting > `PIN_MARGIN` (0.20) above its
   setpoint accrues a streak; the restoring rate scales up linearly with the
   streak (1× fresh → `PIN_ACCEL_MAX` 4× after ~120 pinned calls, effective rate
   capped at 0.25/call). The streak clears the moment the signal relaxes below
   the margin, so behavior is rise-and-relax, not a clamp. A fresh acute spike
   (streak 0) decays at the unchanged base rate — urgency and the survival floor
   are untouched. (Opponent-process b-process growth, Solomon & Corbit 1974.)
2. **Repetition guard** in `native_lm.generate`: CTRL-style penalty
   (Keskar et al. 2019), default 1.3 over the last 64 tokens.
3. **Tunables** for the P7 ablation panel: `ORRIN_SIGNAL_DECAY` (master switch —
   off reproduces "hot and flat" for A/B), `ORRIN_PIN_MARGIN`,
   `ORRIN_PIN_ACCEL_WINDOW`, `ORRIN_PIN_ACCEL_MAX`, `ORRIN_LM_REP_PENALTY`,
   `ORRIN_LM_REP_WINDOW`.

**Tests:** `tests/brain/test_signal_decay.py`.

**Acceptance check for the next run:** drive traces show rise-and-relax curves
(motivation/curiosity/confidence leave the 0.80–0.85 band and return); no phrase
repeats pathologically; production does not stall (satiety/urgency still fire).
