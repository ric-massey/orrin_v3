# Claims and Evidence

This file keeps Orrin's public claims separated from aspirations. "Proven" means
there is code and a repeatable local check or run artifact. "Needs demo" means the
mechanism exists, but the public before/after evidence is not yet packaged.

| Claim | Evidence | Status |
|---|---|---|
| LLM use is optional | Symbolic-only mode runs without a configured provider; LLM calls are gated tool calls. | Proven |
| Orrin runs continuously rather than prompt-only | `main.py` starts the cognitive loop and daemons; traces accumulate across cycles. | Proven |
| Behavior changes are logged as before→after→because | `behavioral_adaptation.py` write path (`brain/data/behavior_changes.json`, created on the first logged change) plus `/api/behavior-changes` and the Learning room. | Proven (mechanism); needs a run that logs one |
| Belief movement can be inspected across self-beliefs, opinions, and symbolic rules | `/api/belief-revisions` merges those stores with confidence/evidence fields. | Proven |
| Body bands reduce false distress | Phase-aware `body_sense` and separate sleep bands are implemented. | Needs public before/after demo |
| Inward vital floor protects Orrin's granted body budget | `reaper/vital_floor.py` is wired, calibrated, and armed by default. | Needs long-run validation |
| Workspace contents affect action selection | Global Workspace prior is implemented behind `ORRIN_WORKSPACE_PRIOR`. | Needs selector-trace demo |
| Home/world zoning changes goal routing | Home/world/self zoning and goal tags are implemented. | Needs goal-routing demo |
| Rut detection changes behavior | Metacognition and behavioral adaptation write suppression/action-pressure changes. | Needs before/after run report |
| Sleep consolidation improves future behavior | Dream/consolidation machinery exists and sleep-phase body interpretation is built. | Needs controlled run evidence |
| Self-modification preserves continuity | Self-code and review paths exist. | Future |

## Current Evidence Sources

- `brain/data/trace.jsonl` for chosen functions, rewards, and selector state.
- `brain/data/behavior_changes.json` for policy edits (written on the first behavior change; absent on a fresh mind).
- `brain/data/decision_stats.json` and `brain/data/bandit_state.json` for action/reward distributions.
- `brain/data/conscious_stream.json` for workspace winners.
- `brain/data/body_sense.json`, body-band files, and vital-floor calibration logs for embodiment.
- `docs/Behavioral Evaluation & Runtime Diagnostics/` for run reports.

## Evidence Standard

The strongest Orrin demo has this shape:

```text
before → after → because
```

That means a run should show the original behavior distribution, the internal detection or
belief/action update that caused a change, and a later measured behavior distribution or reward
change. The goal is observable machine behavior, not claims about subjective experience.
