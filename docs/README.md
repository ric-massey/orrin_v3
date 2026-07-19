# Orrin Docs Index

Docs are grouped by track. Each track holds the **live** plans/audits at its top
level; superseded or completed docs move into that track's `archive/` (or the
shared `archive/` at the docs root). Run reports live under
`Behavioral Evaluation & Runtime Diagnostics/demo_runs/`, dated by run.

*Index refreshed 2026-07-19 (Run 11 preparation; previous refresh 2026-07-09).*

## Start here for Run 11

The current work is the **Run 11 build** ("the Growth Run" — ~20k cycles,
batch-everything, de-clamp). The reading order:

1. `Behavioral Evaluation & Runtime Diagnostics/RUN11_BACKLOG_2026-07-19.md` —
   **the build sheet.** Ric's directives, §0b Run-10-verdict deltas, the
   membranes/growth/de-prosing/de-clamp packages, sequencing (§9), and the
   finalized gate (§10, with Run 10 baselines).
1b. `Behavioral Evaluation & Runtime Diagnostics/RUN11_IMPLEMENTATION_PLAN_2026-07-19.md`
   — **the executable companion**: build order by slice with code targets
   verified at `4d69ce5` (file:line for every clamp and fix site), the
   ground-truth corrections ([GT]: 20k cycles ≈ 30 h not 4.6 days; C1 layers on
   B1 habituation; E2/E3 mostly exist), adopted decisions, and the launch
   checklist.
2. `Behavioral Evaluation & Runtime Diagnostics/demo_runs/2026-07-18-run/DEMO_RUN_2026-07-18.md`
   — the Run 10 verdict the backlog builds on (gate NOT passed: reuse 0 < 8,
   daemon lane starved; 9/12 items green; findings classified
   broken-pipe / unopposed-force / misaimed-force).
3. `NEXT_RUN_TESTS.md` — gate history, all runs; the Run 10 result block points
   into the backlog.
4. `Core Architecture, Embodiment & Evolution/QUALITY_GROUNDING_DESIGN_2026-07-18.md`
   — the value-grounding frame the growth package serves (epistemic close-out =
   rung 0/1).

## Root docs

- `ARCHITECTURE.md` — living reference: how the system fits together.
- `CONFIGURATION.md` — living reference: config surface and env vars.
- `NEXT_RUN_TESTS.md` — acceptance-gate history (Runs 6–10 result blocks) and
  what to measure on the next life run.
- `orrin-field-guide.html` — narrative field guide: mechanics, philosophy, the
  Fourteen Laws, plain-language glossary (2026-07-19; spot-checked against code).
- `DOC_ARCHIVE_CHECKLIST_2026-07-01.md` — the docs-clearance convention.
- `wiki/` — source copy of the [GitHub Wiki](https://github.com/ric-massey/orrin_v3/wiki);
  edit here, then sync to `orrin_v3.wiki.git` (byte-identical mirror; sync after
  the Run 11 build lands, per backlog §7-L5).

## Tracks

- **Behavioral Evaluation & Runtime Diagnostics/** — what Orrin actually does at
  runtime. Live: **`RUN11_BACKLOG_2026-07-19.md`** (the current build sheet),
  `RUN10_LIVE_NOTES_2026-07-18.md` (in-flight findings LN-1..4 from the Run 10
  life), `RUN9_DEEP_ANALYSIS_2026-07-15.md` (§7e growth analysis feeds backlog
  §3), and the `RUN5`–`RUN8` fix plans (all built; kept live as the record of
  the clamp era the backlog §6 now retires). **Ten staging runs so far; the
  gate has never passed** — but the constraint has climbed the ladder:
  mechanics (1–4) → economics/monopoly (5–8) → honesty (9) → **feed/growth
  (10→11)**. Run 10 (2026-07-18/19, 11,565 cycles, first reproducible build
  `4d69ce5`): 9/12 gate items green, reuse 0 because the daemon lane starved —
  the Run 11 headline diagnostic. Run reports in dated `demo_runs/` folders
  (indexed by `demo_runs/DEMO_RUNS.md`).

- **Core Architecture, Embodiment & Evolution/** — the core build track. Live:
  `QUALITY_GROUNDING_DESIGN_2026-07-18.md` (the five-sources-of-good frame;
  epistemic close-out is its keystone — Run 10 proved the mechanism fires and
  measured 10/10 questions unanswered, hence backlog F-LN4b),
  `ORRIN_WORLD_DESIGN_2026-07-18.md` (the design-night note: internet-as-world
  "houses", reward anneal, watch-first infancy, unopposed-force taxonomy —
  post-gate axes, sequenced behind the predictive core per backlog §11),
  `ORRIN_COGNITION_GAP_ANALYSIS_2026-07-19.md` (external gap map **with review
  caveats appended** — its "more daemons" recommendation is rejected on run
  evidence; keep the memory-as-simulation and automaticity axes),
  `LIFE_AMBITION_PROPOSAL_2026-07-09.md` (conditional-in for Run 11 per backlog
  §7-L3 — its monopoly-gate precondition is now green),
  `ORRIN_CORE_ARCHITECTURE_MASTER_PLAN_2026-06-25.md` (Phases 0/1/3 code done;
  T0.5 exemplars still Ric-gated),
  `GROUNDED_COGNITION_IMPLEMENTATION_PLAN_2026-06-29.md` (4B/5 open — backlog
  §7-L2), `TOPDOWN_WRITEBACK_IMPLEMENTATION_PLAN_2026-06-27.md` (proposed,
  unbuilt). Superseded sources in `archive/`.

- **Language & Cognition/** — `ORRIN_LANGUAGE_PLAN.md` (native-LM roadmap;
  Phase-2 corpus schooling explicitly deferred per backlog §7),
  `THOUGHT_OBJECT_SPEC.md` (**in for Run 11** — backlog §4-T1, the de-prosing
  keystone), `ORRIN CREATIVITY NOVELTY PROPOSAL 2026-06-25.md` (**in for Run
  11** — backlog §5, all four issues).

- **Engineering & Code Health/** — non-behavioral engineering debt. Live:
  `OWNERSHIP.md` (module ownership reference) and
  `STRUCTURAL_RISK_REGISTER_2026-07-01.md` (standing risk register).
  Cleanup Phases 3–7 ride in backlog §7-L5.

- **Capability, Benchmarks & Evidence/** — `BENCHMARKS.md` (run guide). B8–B18
  battery is backlog §7-L4. `CLAIMS_AND_EVIDENCE.md` retired to that track's
  `archive/`.

- **UI, Security & Desktop Packaging/** — live:
  `COMPANION_PRESENCE_MASTER_PLAN_2026-07-09.md` (all 6 phases built 2026-07-10;
  staged verification outstanding). Prior master plan closed, in `archive/`.

## Archive

- `archive/` (docs root) — completed/superseded plans, audits, and fix records,
  including `MASTER_STATUS_2026-07-07.md` (read-only history per its own
  addendum; this README is the current status surface).
- Each track also keeps its own `archive/` for docs specific to it.
