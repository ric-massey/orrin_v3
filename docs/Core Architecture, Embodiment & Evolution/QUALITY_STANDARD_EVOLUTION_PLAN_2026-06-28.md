# Quality-Standard Evolution — letting the bar develop without letting it be gamed

Date: 2026-06-28
**Status:** Proposed (design only — no code). Spec to ratify before building.
Parent: `ORRIN_CORE_ARCHITECTURE_MASTER_PLAN_2026-06-25.md` §T0.5 (the quality
predicate + golden set). This plan adds the *adaptation layer* T0.5 deliberately
left out: how the standard itself develops over Orrin's life instead of staying a
frozen, human-authored snapshot.

---

## 1. The problem

T0.5 built the quality predicate (`brain/cognition/quality_predicate.py`) and a
golden set (`tests/fixtures/quality_golden/{exemplars,anti_exemplars}/`) that is
the operational definition of "real work, not slop." As shipped, that standard is
**static and human-authored**: Ric writes the exemplars, the anti-exemplars
ratchet up by hand after each run, and Orrin can never touch any of it.

That firewall is correct about the danger but too rigid about the cure. A
developing mind's sense of *what counts as good* genuinely shifts — his goals
change, his domains change, what was "a real finding" at infancy is thin later —
and a frozen bar can't track that. A bad exemplar, once written, stays wrong
forever. The standard needs to **evolve**, and to be **fixable when it's mistaken**.

## 2. The distinction that makes this safe

The original firewall was never "the bar can never change." It was the narrower —
and correct — rule: **the bar must not move because Orrin *wants to pass*.** That
is the one dangerous direction (Goodhart: the mind that grades its own work
loosening the grade to close goals).

A standard that moves on **evidence of what actually proved good** is not gaming —
it is learning. Those are different operations, and the entire design is keeping
them different:

> Move the bar on **demonstrated downstream effect**, never on **desire to close.**

This is the same line Orrin's existing self-model machinery already walks (see §3).

## 3. This rides machinery that already exists

Orrin already changes self-model surfaces from experience, through a
proposer→pending→ratify pipeline with provenance — the quality standard is simply
the one surface not yet plugged in:

- **`value_revisions`** (`VALUE_REVISIONS`) — a value changes because experience
  *contradicted* it; surfaced as a `status: "pending"` candidate (e.g. from the
  dream cycle), carrying its evidence, applied through a review step.
- **belief revisions** — `reflect_on_self_belief` / `SELF_BELIEF_REVISIONS_FILE`:
  outcomes move confidence, logged with provenance.
- **the effect ledger** — `action_accounting` / `production_funnel`
  (`credited — the artifact earned effect-ledger credit (novelty/significance)`):
  the system that already knows whether produced work *mattered downstream*.

The Quality-Standard Evolution component is a new member of this family, not a new
exception to the firewall.

## 4. Design

A **separate component** (NOT a cognition action Orrin can invoke) that watches his
experience and *proposes* changes to the golden set. It never edits the predicate
or fixtures directly at Orrin's request; it reads evidence and emits candidates.

### 4.1 Inputs (the "based on memory, past goals, emotions" wiring)

| Drives it | Source surface | Role |
| --- | --- | --- |
| past goals | goal outcomes + `definition_of_done` met-with-evidence | what "done well" actually looked like in practice |
| memory | `long_memory` importance/persistence, `recent_contributions` | did the artifact endure / get reused |
| **effect ledger** | `production_funnel` credit (novelty/significance) | **demonstrated downstream significance — the anchor** |
| "emotions" | control signals (felt meaningful / kept returning to it) | a **prior that prioritizes what gets reviewed — never a vote** |

### 4.2 Operations

1. **Promotion (raise / broaden — auto-applies).** A produced artifact that
   *later* earns effect-ledger credit (referenced, reused, drove goal progress,
   persisted as important in long_memory, externally/user-validated) becomes a
   candidate **positive exemplar** — proof-of-good by consequence, not preference.
   Raising the bar is self-correcting, so on strong effect-evidence it auto-applies
   (then the predicate is re-tuned until the regression test passes the new
   exemplar — same coupling as today).

2. **Mistake-correction (fix a bad exemplar).** An exemplar that proves
   inconsistent with what repeatedly demonstrates value (structurally like work
   that later turned out hollow; or it blocks work that downstream proves good) is
   flagged **suspect**, with the contradicting evidence attached.

3. **Anti-exemplar accretion (already the ratchet).** Slop that the predicate let
   pass in a run becomes a new anti-exemplar. Safe and automatic — this direction
   only tightens.

### 4.3 Guardrails (the entire game)

1. **Evidence-keyed, never preference-keyed.** Every proposed change carries an
   evidence basis (which goals / effect-ledger rows / memories). No evidence → no
   change. A desire to close a goal is not evidence.
2. **Direction asymmetry.** Raising/broadening the bar and adding his-own-slop
   anti-exemplars may auto-apply. **Loosening or removing** an exemplar — the only
   gameable direction — requires the strongest evidence *and* routes to **human
   ratification**.
3. **Provenance + reversibility.** Each change is logged with its justification
   (like value_revisions), so drift is inspectable and any change can be rolled
   back.
4. **Indirection stays.** Orrin cannot touch the bar directly. The evolution
   component reads his parts and proposes; it is not callable from selection, so it
   can never be chosen *in order to* pass.

With these, it is a developing standard. Without them, it is exactly the Goodhart
failure T0.5 feared — same mechanism; the guardrails decide which one you get.

---

## 5. Phases (buildable, low-blast-radius first)

```
P0  Candidate store + provenance schema (no behavior change)
P1  Promotion proposer (effect-ledger → pending positive-exemplar candidate)
P2  Ratification path (auto-apply raise; route loosen/remove to human review)
P3  Mistake-correction (suspect-exemplar flagging)
P4  Predicate re-tune loop + regression-test integration
P5  UI surface + audit trail
```

- [ ] **P0 — Candidate store.** A `quality_standard_revisions.json` (mirroring
      `VALUE_REVISIONS`): `{id, kind: promote|suspect|anti_exemplar, artifact_ref,
      evidence: {goals[], effect_rows[], memory_refs[], signal_prior}, status:
      pending|applied|rejected, direction: raise|lower, ts}`. No application yet.
- [ ] **P1 — Promotion proposer.** A background pass (dream-cycle cadence) that
      scans recently effect-credited artifacts and emits `promote` candidates above
      an effect threshold. Pure proposal; writes to the candidate store.
- [ ] **P2 — Ratification.** `raise`-direction candidates with strong evidence
      auto-apply (write a new file into `exemplars/`); `lower`/remove candidates are
      held `pending` for human ratification. Applying re-runs the regression test.
- [ ] **P3 — Mistake-correction.** Flag exemplars that contradict accumulated
      effect evidence as `suspect` (human decides). This is the "fix a bad
      exemplar" path.
- [ ] **P4 — Predicate re-tune loop.** When an exemplar is added/removed, surface
      the failing regression so the predicate can be re-tuned to keep the
      invariant (pass all exemplars, reject all anti-exemplars).
- [ ] **P5 — UI + audit.** Surface pending candidates + applied history with
      provenance (Learning page or a Settings review queue), so Ric can ratify
      loosening and audit drift.

## 6. Acceptance

- The golden set can grow and be corrected **from Orrin's own demonstrated-good
  work**, with every change traceable to effect-ledger / memory / goal evidence.
- **No change ever auto-loosens the floor**: removals/loosening are human-ratified;
  raising and anti-exemplar accretion may auto-apply.
- The T0.5 regression invariant always holds after any change (pass all exemplars,
  reject all anti-exemplars) — the standard never silently breaks.
- Orrin has **no path** to alter the bar in order to pass a goal (not callable from
  selection; preference is not evidence).
- Every applied change is reversible from its logged provenance.

## 7. Risk register

| Risk | Mitigation |
| --- | --- |
| Self-justification drift (mind loosens its own grade) | Evidence-keyed; loosening is human-ratified; raise-is-easy / lower-is-hard asymmetry |
| Effect ledger itself gets gamed → false "good" promotions | Promotion needs *downstream* credit (reuse/persistence/external validation), not self-report; significance is graded, not boolean |
| Exemplar set narrows to one shape (overfits his current domain) | Promote for diversity of shape; keep human-authored seed exemplars as permanent anchors |
| Predicate re-tune chases fixtures into incoherence | P4 keeps the regression invariant explicit; a change that can't be satisfied without breaking other fixtures is rejected, not forced |
| Emotions over-influence the standard | Signals only prioritize what gets reviewed; they are never an evidence source for a change |

---

*Relation: extends T0.5 (`ORRIN_CORE_ARCHITECTURE_MASTER_PLAN_2026-06-25.md`).
Reuses the `value_revisions` / belief-revision proposer→pending→ratify pattern and
the `production_funnel` effect ledger. No code until this spec is ratified.*
