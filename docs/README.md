# Orrin Docs Index

Docs are grouped by track. Each track holds the **live** plans/audits at its top
level; superseded or completed docs move into that track's `archive/` (or the
shared `archive/` at the docs root). Run reports live under
`Behavioral Evaluation & Runtime Diagnostics/demo_runs/`, dated by run.

*Index rewritten 2026-07-01 per `DOC_ARCHIVE_CHECKLIST_2026-07-01.md`.*

## Root docs

- `ARCHITECTURE.md` — living reference: how the system fits together.
- `CONFIGURATION.md` — living reference: config surface and env vars.
- `NEXT_RUN_TESTS.md` — the §8 acceptance gate for the production-reward work;
  what to measure on the next clean-instance life run.
- `DOC_ARCHIVE_CHECKLIST_2026-07-01.md` — this clearance plan (living; archives
  once the tree is clean and the README diff matches).

## Tracks

- **Behavioral Evaluation & Runtime Diagnostics/** — what Orrin actually does at
  runtime. Live: `CODEBASE_AUDIT_2026-07-01.md` (system-wide audit),
  `IMPLEMENTATION_PLAN_AUDIT_REMEDIATION_2026-07-01.md` (AR1–AR9 fixes),
  `IMPLEMENTATION_PLAN_GROUNDING_AND_SURFACE_2026-06-30.md` (P1–P8 built;
  staging run pending), `B3_DECAY_DIAGNOSIS_2026-07-01.md` (blocked on AR8),
  plus all dated `demo_runs/` (indexed by `demo_runs/DEMO_RUNS.md`).

- **Core Architecture, Embodiment & Evolution/** — the core build track. Live:
  `ORRIN_CORE_ARCHITECTURE_MASTER_PLAN_2026-06-25.md` (Phase 0 done; Phase 1
  code done, T1.G live run + T0.5 exemplars open),
  `GROUNDED_COGNITION_IMPLEMENTATION_PLAN_2026-06-29.md` (Phases 1/2/3/4A done;
  Phase 2 dormant behind the fluency gate; 4B/5 open),
  `TOPDOWN_WRITEBACK_IMPLEMENTATION_PLAN_2026-06-27.md` (proposed, unbuilt).
  Superseded sources in `archive/`.

- **Language & Cognition/** — `ORRIN_LANGUAGE_PLAN.md` (the human-level-language
  roadmap), `THOUGHT_OBJECT_SPEC.md` (the pre-verbal thought representation), and
  `ORRIN CREATIVITY NOVELTY PROPOSAL 2026-06-25.md` (blocked on the AD1/D8 fork
  in the audit-remediation plan).

- **Engineering & Code Health/** — non-behavioral engineering debt. Live:
  `OWNERSHIP.md` (module ownership reference) and
  `STRUCTURAL_RISK_REGISTER_2026-07-01.md` (standing risk register).

- **Capability, Benchmarks & Evidence/** — `BENCHMARKS.md` (run guide).
  `CLAIMS_AND_EVIDENCE.md` is retired to that track's `archive/`.

- **UI, Security & Desktop Packaging/** — no live docs; the master plan
  (`UI_SECURITY_DESKTOP_MASTER_PLAN_2026-06-16.md`, all items closed) and its
  consolidated sources are read-only history in `archive/`.

## Archive

- `archive/` (docs root) — completed/superseded plans, audits, and fix records
  from earlier in the project.
- Each track also keeps its own `archive/` for docs specific to it.
