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
| 2026-06-17 | Full-life run analysis (8,040-cycle life) | `Behavioral Evaluation & Runtime Diagnostics/demo_runs/2026-06-17-run/` — 6 docs (see index below) | Captured |
| 2026-06-18 | First life **after** the 2026-06-17 fixes (~10,300-cycle life) | `…/demo_runs/2026-06-18-run/` — 4 docs (`DEMO_RUN_2026-06-18.md` index) | Captured |
| 2026-06-18 | **Rut-mechanism fix lands (positive result)** | `…/2026-06-18-run/2026-06-18_did_the_fixes_land.md` — phantom avoidance loop 2,251→**5** cycles, mode-flap 3,415→**6**, telemetry 240→**10,260** pts | **Captured (mechanism)** |
| 2026-06-19 | First life under **binding / goal-lens / production** machinery (11,633-cycle life) | `…/demo_runs/2026-06-19-run/` — 6 docs (`DEMO_RUN_2026-06-19.md` index) | Captured |
| 2026-06-19 | **Ops shutdown fixes verified** (clean death) | `…/2026-06-19-run/2026-06-19_final_audit_and_shutdown.md` — single instance, zero binding/lens exceptions in 11,633 cycles, `runstate {"clean": true}`, no respawn (vs 06-18's wedge) | **Captured** |
| 2026-06-19 | **Production gate proven honest** | `…/2026-06-19-run/2026-06-19_what_did_he_make.md` — 146 effect-ledger notes all novelty 0.0; aspirations all **0 %** (vs 06-18's false 100 %); the grader works and credits nothing | **Captured (negative — by design)** |
| TBD | Rut fix **redistributes effort** (deeper positive result) | Action distribution actually spreads to "make things"/"be useful"; notes carry real content; **first non-zero effect-ledger row** | Not captured (follow-ups queued — see 2026-06-19 `run_analysis.md §6`) |
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

### 2026-06-19 analysis — document index

A full forensic read of one **11,633-cycle (~13 h 54 m)** life — the first under the uncommitted
binding stage, goal lens, goal comprehension, and `compose_section` production capability. Folder:
`docs/Behavioral Evaluation & Runtime Diagnostics/demo_runs/2026-06-19-run/`

| Doc | What it covers |
|---|---|
| `DEMO_RUN_2026-06-19.md` | Index + snapshot + verdict table + open follow-ups. |
| `2026-06-19_run_analysis.md` | Snapshot + full-life arc (distress climbs all back-half); what the new machinery is and that it ran fault-free; keystone D1 (146 effects → 0 credited, aspirations all 0 %); prioritized issues. |
| `2026-06-19_did_the_fixes_land.md` | Before/after the five 2026-06-18 follow-ups (ops ✅, content/aspiration 🟡, spawn/autobiography 🔴) + verification that binding/lens/production are built & safe but the loop isn't closed. |
| `2026-06-19_who_is_he.md` | Identity: instruments finally honest; motivated and calm on top, felt-cost maxed underneath; the most alone, most silent life yet. |
| `2026-06-19_what_did_he_make.md` | Output: the content-grader came online and graded all 146 notes zero; aspiration meter stopped lying; 0 tools/code/works; 6 utterances. |
| `2026-06-19_final_audit_and_shutdown.md` | **Clean-death record** — both 06-18 ops fixes verified; final un-goaled positive-valence stream; native LM still training (loss 0.121, 12.5 M tokens). |

**Relation to the Current Demo Target:** this run is the **honest-baseline** the target needs before a positive result is possible. With the production gate (`effect_ledger`) now trustworthy, the *after distribution* that counts is no longer "more actions" but "the first effect-ledger row with novelty > 0." This life proves the grader is sound (146 → 0, all aspirations 0 %) and the operational base is clean (fault-free 14 h, clean death); the next captured run's job is to make `compose_section` produce one creditable artifact from a *comprehended* goal — see 2026-06-19 `run_analysis.md` §6.1.
