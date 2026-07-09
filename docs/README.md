# Orrin Docs Index

Docs are grouped by track. Each track holds the **live** plans/audits at its top
level; superseded or completed docs move into that track's `archive/` (or the
shared `archive/` at the docs root). Run reports live under
`Behavioral Evaluation & Runtime Diagnostics/demo_runs/`, dated by run.

*Index refreshed 2026-07-09 (previous rewrite 2026-07-01 per
`DOC_ARCHIVE_CHECKLIST_2026-07-01.md`).*

## Root docs

- `ARCHITECTURE.md` — living reference: how the system fits together.
- `CONFIGURATION.md` — living reference: config surface and env vars.
- `NEXT_RUN_TESTS.md` — the §8 acceptance gate, plus the **Run 6 re-test gate**
  (S9/S10 + holds) from `RUN6_FIX_PLAN_2026-07-08.md`; what to measure on the
  next clean-instance life run.
- `MASTER_STATUS_2026-07-07.md` — dated status + docs-organization review; its
  §2c archive moves and §3 wiki plan are executed (see the addendum at its top).
- `DOC_ARCHIVE_CHECKLIST_2026-07-01.md` — this clearance plan (living; archives
  once the tree is clean and the README diff matches).
- `wiki/` — source copy of the [GitHub Wiki](https://github.com/ric-massey/orrin_v3/wiki);
  edit here, then sync to `orrin_v3.wiki.git`.

## Tracks

- **Behavioral Evaluation & Runtime Diagnostics/** — what Orrin actually does at
  runtime. Live: `CODEBASE_AUDIT_2026-07-01.md` (system-wide audit),
  `IMPLEMENTATION_PLAN_AUDIT_REMEDIATION_2026-07-01.md` (AR1–AR9 fixes),
  `IMPLEMENTATION_PLAN_GROUNDING_AND_SURFACE_2026-06-30.md` (P1–P8 built),
  `RUN5_FIX_IMPLEMENTATION_2026-07-07.md` (F1–F22 built, committed `f0c4698`;
  Run 5 lived 2026-07-08), and `RUN6_FIX_PLAN_2026-07-08.md` (built 2026-07-09,
  `584b76a` — value authority in selection + commitment score/rotation; gated on
  the Run 6 staging life). Five staging runs so far (Runs 1–5); the §8 gate has
  **never passed** — Run 5's verdict: S8/S7 held, S6/S9 fail, committed-goal
  monopoly at 99.9 %. Run reports live in dated `demo_runs/` folders (indexed by
  `demo_runs/DEMO_RUNS.md`). Archived: `B3_DECAY_DIAGNOSIS_2026-07-01.md`
  (closed 2026-07-02), `RUN4_FIX_PLAN_2026-07-04.md` +
  `RUN4_ISSUES_AND_IMPROVEMENTS_2026-07-04.md` (superseded by the Run 5 docs).

- **Core Architecture, Embodiment & Evolution/** — the core build track. Live:
  `ORRIN_CORE_ARCHITECTURE_MASTER_PLAN_2026-06-25.md` (Phases 0/1/3 code done;
  T1.G live-closure run + T0.5 exemplars open — both non-code, Ric-gated),
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

- **UI, Security & Desktop Packaging/** — live:
  `COMPANION_PRESENCE_MASTER_PLAN_2026-07-09.md` (proposed, unbuilt — OS
  presence via tray/notifications, companion-mode UI, theory-of-mind room,
  action ledger, body↔machine bridge; code-grounded, 6 phases). The prior
  master plan (`UI_SECURITY_DESKTOP_MASTER_PLAN_2026-06-16.md`, all items
  closed) and its consolidated sources are read-only history in `archive/`.

## Archive

- `archive/` (docs root) — completed/superseded plans, audits, and fix records
  from earlier in the project.
- Each track also keeps its own `archive/` for docs specific to it.
