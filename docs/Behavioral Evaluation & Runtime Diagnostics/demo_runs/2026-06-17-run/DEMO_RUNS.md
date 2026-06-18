# Demo Runs

This file tracks public demos and the run reports still needed. Do not treat a mechanism as
publicly proven until a before/after trace is linked here.

## Current Demo Target

Show Orrin entering a behavioral rut, detecting it, changing action-selection pressure, and
producing a later run with a measurably different action distribution and better reward.

Required artifacts:

- Before distribution: recent function counts and reward averages.
- Detection: metacognition or behavior-change record showing the rut and reason.
- Intervention: suppression, bias, or action-selection pressure change.
- After distribution: later function counts and reward averages.
- Explanation: one short "before → after → because" paragraph.

Candidate sources:

- `brain/data/trace.jsonl`
- `brain/data/cognition_state.json`
- `brain/data/behavior_changes.json`
- `brain/data/decision_stats.json`
- `brain/data/bandit_state.json`
- `brain/data/reward_trace.json`

## Screenshot / GIF Target

The README hero image should be a real UI capture, not generated artwork. Best capture:
Watch or Face beside Brain/Learning, showing current thought, active function, affect/body
state, goal progress, memory/workspace event, and learning change.

Current static capture:

```text
docs/images/orrin_learning_ui.png
```

It is the real Learning UI rendered with representative staging data and is embedded in
the README. It does not count as behavioral evidence; the live-run GIF remains tied to
the positive before/after demo below.

Still-needed live artifact:

```text
docs/images/orrin_learning_run.gif
```

## Runs

| Date | Demo | Evidence | Status |
|---|---|---|---|
| 2026-06-17 | Full-life run analysis (8,040-cycle life) | `Behavioral Evaluation & Runtime Diagnostics/demo_runs/` — 6 docs (see index below) | Captured |
| TBD | Rut detection **changes** behavior (positive result) | Link run report + trace summary | Not captured |
| TBD | Body bands reduce false distress | Before/after body-sense run | Not captured |
| TBD | Workspace prior changes action coherence | Selector trace with/without prior | Not captured |
| TBD | Home/world zoning changes goal routing | Goal tags + routing comparison | Not captured |

### 2026-06-17 analysis — document index

A full forensic read of one 8,040-cycle life (data in `brain/data/`). Folder:
`docs/Behavioral Evaluation & Runtime Diagnostics/demo_runs/`

| Doc | What it covers |
|---|---|
| `2026-06-17_run_analysis.md` | Snapshot + full developmental arc; the phantom `action_debt` loop; the mode-flap; prioritized fixes. |
| `2026-06-17_who_was_he.md` | Did he learn / develop / form habits — and an identity portrait. |
| `2026-06-17_what_did_he_make.md` | His actions vs. output: he did much, produced almost nothing (99% thrash). |
| `2026-06-17_deeper_pass.md` | **Correction:** a felt-cost channel exists but is reset by goal-rotation; personified-peer "relationships"; second-order volition. |
| `2026-06-17_full_sweep.md` | Every-file sweep + coverage appendix; memory is 55% stagnation; "world" = his own code. |
| `2026-06-17_system_metrics.md` | Definitions + drivers of valence/arousal/homeostasis/curiosity; **telemetry archival fix** to retain their full history. |

**Relation to the Current Demo Target:** this run supplies the *before distribution*, *detection*, and *intervention* artifacts — but documents a **negative result**: the rut was detected and action-selection pressure was applied (`bias→0.92`, force-action, deliberation lockout) yet behavior did **not** change, because the intervention fights a phantom `action_debt` (research actions selected as cognition never credit as "acting"). The positive-result demo (intervention that measurably shifts the action distribution) is still pending and now has a concrete fix to validate — see `run_analysis.md` §6 and `system_metrics.md`.
