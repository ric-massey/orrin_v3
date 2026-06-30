# Quality-Standard Evolution — Implementation Plan

Date: 2026-06-28
**Status:** BUILT 2026-06-29 (P0–P6). Implements `QUALITY_STANDARD_EVOLUTION_PLAN_2026-06-28.md`.

> **Implementation note (2026-06-29).** All phases landed in
> `brain/cognition/quality_standard/` (revisions/proposer/gate/ratify/audit/cli) +
> `brain/agency/effect_artifacts.py` (P1a) + effect_ledger accessors
> (`kind_for_hash`, `credited_goal_ids`). Background pass wired into
> `idle_consolidation_cycle`. Read-only audit on the Learning page; owner-only ratify
> routes (`/api/quality-standard/{approve,reject,restore}`) + CLI
> (`python -m brain.cognition.quality_standard.cli`). Tests:
> `tests/brain/test_quality_standard.py` (15, incl. the selection import-guard +
> signal_prior ordering-only). Open decisions in §6 resolved as proposed: prose
> persistence bar = importance ≥ 4 (above the long_memory retention floor); P1a sidecar
> = separate hash-keyed store (`data/effect_artifacts/`); ratify surface = Learning-page
> audit + owner console. Full suite green (1176 passed); `make verify` gate unchanged.
Parent design: that plan's §2 firewall and §4.3 guardrails are the contract this
build must satisfy. This document is the *how* and is grounded in the modules that
actually exist at HEAD.

---

## 0. Corrections this plan bakes in (vs. the design doc)

The design doc was written as a side-plan and three of its assumptions don't match
code. This implementation corrects them:

1. **Anchor = the effect ledger, not the funnel.** The proposer reads
   `brain/agency/effect_ledger.py` (`significance_for_goal`, `effects_for_goal`,
   reuse via `mark_reused`/`_reuse_counts`), which is live and producer-fed. It does
   **not** read `production_funnel.credited` (telemetry; `credited` is unwired until
   T1.P).
2. **No "predicate re-tune knob" exists.** `quality_predicate.assess_quality` is a
   set of hard rule-gates ("Not a single threshold to optimize against"), and the
   regression test loads exemplars dynamically via `iterdir()`. So an exemplar that
   the predicate rejects **cannot** be auto-applied — it would wedge the regression
   red. The promotion gate (P2) only auto-applies exemplars the predicate *already
   passes*; anything that would require a rule change is routed to a human.
3. **The human-ratify path is net-new.** `value_revisions` is selection-callable and
   self-applies (`value_evolution.propose_value_revision` → `_apply_decision`); there
   is no human in that loop. We reuse its *file/provenance schema*, not its control
   flow. The review queue (P4) is built fresh.

One new capability the design doc omits: the effect ledger stores `content_hash`,
not artifact text, so **artifact text must be captured at production time** to later
become an exemplar file (P1a).

---

## 1. Component shape & placement

A **non-cognition** package — never importable from selection/candidates, so Orrin
can't choose it to pass a goal (design §4.3 guardrail 4):

```
brain/cognition/quality_standard/
  __init__.py
  revisions.py        # candidate store (load/save/append/mark) — mirrors value_revisions
  proposer.py         # P1 promotion + P3 suspect proposers (read-only, background)
  gate.py             # P2 apply logic (add-only, predicate-conforming) + regression smoke check
  ratify.py           # P4 human-ratify API (no auto-apply for loosen/suspect/relax)
data/quality_standard_revisions.json     # candidate store (mirrors VALUE_REVISIONS)
tests/fixtures/quality_golden/exemplars/ # promotion target (already iterdir-scanned)
```

Cadence: invoked from the idle-consolidation / dream cycle
(`idle_consolidation_cycle`), the same place `value_revisions` candidates surface —
a background pass, not an action.

---

## 2. Phases

### P0 — Candidate store + provenance schema *(no behavior change)*
- `revisions.py`: `load() / save() / append(candidate) / mark(id, status, **fields)`,
  capped list like `VALUE_REVISIONS` (`save_json(..., rows[-N:])`).
- Row schema:
  ```json
  {
    "id": "...", "kind": "promote|suspect|anti_exemplar",
    "direction": "raise|lower",
    "artifact_ref": {"goal_id": "...", "content_hash": "...", "artifact_path": "..."},
    "evidence": {"goals": [], "effect_rows": [], "significance": 0.0,
                 "reuse_count": 0, "memory_refs": [], "signal_prior": null},
    "status": "pending|applied|rejected|suspect",
    "ts": "..."
  }
  ```
- **Guardrail baked into schema:** `signal_prior` is read at proposal time only to
  *order* the review queue and is **not** counted toward the evidence threshold (risk
  register: emotions never an evidence source). Store it null/ordering-only.
- Tests: round-trip, cap, schema validation.

### P1 — Promotion proposer *(read-only background pass)*
**P1a — artifact-text capture (prerequisite).** At `record_effect` call sites
(`express_to_user`, `compose_section`, `code_writer`), persist the artifact text
keyed by `content_hash` into a bounded sidecar (`data/effect_artifacts/<hash>.txt`
or a capped jsonl), so a later-credited artifact can be retrieved as exemplar text.
Cheap, append-only, gated by `MIN_ARTIFACT_CHARS` so junk isn't stored.

**P1b — proposer.** A pass that:
1. Walks recently completed/credited goals; for each, reads `significance_for_goal(gid)`
   and `effects_for_goal(gid)`.
2. Keeps only artifacts past an **effect threshold that requires the ungameable
   signal**. The two qualifying signals are **not interchangeable across artifact
   kinds** (verified against code, not assumed):
   - **`reuse > 0`** (`significance` lifted by `mark_reused`) is only reachable for
     **named authored artifacts** — tools / cognitive functions — because the only
     callers of the reuse path are `note_artifact_use` from `tool_runner.dispatch`
     and `finalize` (`brain/loop/finalize.py`), both keyed by artifact *name*. Prose
     produced via `express_to_user` and `compose_section` is **never** marked reused,
     so `reuse ≥ 1` is structurally unreachable for it.
   - **`long_memory` persistence/importance** is therefore the **only** viable anchor
     for prose, and the **required** anchor for the two prose capture sites.
   So the rule is kind-aware: **code/tool artifacts → require `reuse ≥ 1`; prose
   artifacts (`express_to_user`, `compose_section`) → require `long_memory`
   persistence.** Structural significance at write time is never sufficient on its own
   for either. (Risk register: promotion needs *downstream* credit, not self-report.)
3. Loads the artifact text (P1a) and emits a `promote` candidate (status `pending`)
   with full evidence. **Writes only to the candidate store.** No application here.

### P2 — Promotion gate *(the only auto-apply)*

**What this branch actually is — a ratchet-pin, not bar-development.** Adding an
exemplar that the *current* predicate already accepts imposes **no new constraint on
predicate behavior today** — the predicate already passes it by construction. Its only
effect is to **pin** that artifact as protected-good, so a future P4 rule loosening
that would start rejecting it shows up as a regression. The real movement of the bar
(stricter or broader *rules*) happens entirely in P4's human rule edits. This phase
does not make the standard "smarter"; it ratchets a floor under what's already known-good.
The doc says this plainly so the auto-apply path isn't oversold the way §0 corrects the
parent for overselling.

**The safety property is direction + predicate-conformance, NOT the regression test.**
The T0.5 regression (`test_quality_predicate.py`) calls `assess_quality(path.read_text())`
on each fixture **in isolation, with no `prior_outputs`** — so the near-duplicate gate
(which only runs `if prior_outputs:`) is unreachable there, and adding an exemplar the
predicate already passes **cannot turn the regression red**. Treating "run the regression"
as the gate on this branch would be claiming a guard that does nothing. What actually
makes the branch safe is: it only ever (a) *adds* an exemplar (raise-direction, never
loosens), and (b) adds one the rules *already accept* (no rule change). Both are checked
before write; neither depends on the regression.

For each `pending` `promote` candidate:
1. Run the **current predicate** on the artifact text (`assess_quality(text, goal=...)`).
2. **If it already passes** → safe to pin: write `exemplars/<slug>.md`, then run the
   regression test as a **smoke check** (catches a broken fixture file / IO error, not
   a "bad promotion" — by the above it cannot go red on a passing exemplar) and mark
   `applied`. To avoid a near-useless redundant exemplar, additionally skip-and-mark
   `rejected:near_duplicate_exemplar` if the candidate text is a near-duplicate of an
   existing exemplar — this is an **explicit** shingle/Jaccard check the proposer runs
   against the `exemplars/` set, **not** something the regression test performs.
3. **If the predicate rejects it** → this is a "predicate too strict" signal, **not**
   an auto-promotion. Mark `pending` + `needs_rule_review`, attach the failing reason,
   route to P4. A human edits the rule (or declines). This is the only path that
   changes predicate logic, and it is never automatic.

### P3 — Mistake-correction *(suspect flagging, read-only)*
Proposer flags an existing exemplar as `suspect` when it contradicts accumulated
effect evidence (structurally like artifacts that later earned **zero** downstream
credit, or it blocks work that downstream proved good). Writes a `suspect` candidate
with contradicting evidence. **Never auto-applied** — humans decide (P4).

### P4 — Human ratification path *(net-new — the core guardrail)*
The one direction that's gameable (loosen / remove / relax-predicate / resolve-suspect)
**never** auto-applies. Build:
- A review queue view over `quality_standard_revisions.json` filtered to
  `status=pending` with `direction=lower` or `kind=suspect` or `needs_rule_review`.
- `ratify.py`: `approve(id)` / `reject(id)` — the *only* code that applies a loosening,
  invoked from a human action (UI button / CLI), never from cognition. `approve`
  performs the removal/edit then re-runs the regression test as the gate; logs
  provenance; reversible from the logged row.
- Ordering by `signal_prior` (prioritize what gets reviewed) — explicitly not a vote.

### P5 — Regression integration *(invariant always holds)*
- The regression test (`test_quality_predicate.py`) is the hard gate where it can
  actually fail: **P4**. P4's rule edits / exemplar removals *can* turn it red (a
  rule change can drop an existing exemplar or admit an anti-exemplar), so P4's apply
  is the place "red → rolled back, not forced" has teeth.
- For **P2** the same test runs but is only a **smoke check** — by construction (per
  P2: each fixture judged in isolation, no `prior_outputs`) a predicate-passing
  exemplar cannot turn it red. P2's real safety is direction (add-only) +
  predicate-conformance, not the regression. Do not rely on the regression to catch a
  bad promotion; it can't.
- The invariant "pass all exemplars, reject all anti-exemplars" still holds after
  every change because every change is either (a) adding an already-passing exemplar
  (P2) or (b) a human-ratified rule/exemplar edit re-gated by the test (P4).
- Wire into `make verify` so a wedged golden set fails CI.

### P6 — UI + audit trail
- Surface pending candidates + applied history with provenance on the Learning page
  (or a Settings review queue), so Ric ratifies loosening and audits drift.
- Anti-exemplar accretion (design §4.2.3) — already the existing manual ratchet — gets
  a "promote this run's slop to anti-exemplar" affordance here; safe, only tightens.

---

## 3. Guardrail → mechanism map (the contract)

| Design §4.3 guardrail | Where enforced here |
| --- | --- |
| Evidence-keyed, never preference | P1b threshold requires downstream credit (reuse/persistence); `signal_prior` excluded from evidence |
| Direction asymmetry (raise auto, loosen human) | P2 is add-only and applies only predicate-conforming exemplars (a ratchet-pin, never a loosening); P4 owns every loosen/remove/relax |
| Provenance + reversibility | P0 schema logs evidence; P4 apply is reversible from the row |
| Indirection (not callable from selection) | `quality_standard/` never imported by `think/.../selection/*`; enforced by an import-guard test |
| Predicate can't be chased into incoherence | P5 regression gate **at P4** (the leg that can go red); rejected-not-forced on red. P2 cannot regress it (add-only, predicate-conforming) |
| Emotions don't influence the standard | `signal_prior` ordering-only, asserted by a P0 test |

---

## 4. Build order & blast radius

```
P0  store + schema            (isolated; no behavior)         ← start here
P1a artifact-text capture     (touches 3 producer call sites; additive)
P1b promotion proposer        (read-only; writes candidate store only)
P2  promotion gate            (writes exemplars/; add-only, predicate-conforming)
P4  human-ratify queue + API  (net-new; gates all loosening)
P3  suspect proposer          (read-only; feeds P4)
P5  regression/CI wiring
P6  UI + audit
```
P0→P1b are pure-additive and safe to land first. Nothing auto-loosens until P4
exists, so P2's auto-apply branch (raise-only, predicate-conforming) is the only
behavior change before a human queue is in place — by construction it cannot lower
the floor.

## 5. Acceptance (inherited from design §6, made testable)
- Golden set grows from Orrin's own demonstrated-good work, every change traceable to
  effect-ledger / memory / goal evidence — **verifiable now** (ledger is live).
- No change auto-loosens the floor: P4 owns all removals/loosening (import-guard +
  queue tests).
- Regression invariant holds after every change (P5 gate in `make verify`).
- No selection path can reach the bar (import-guard test).
- Every applied change reversible from its logged provenance.

## 6. Open decisions for Ric
- ~~**Effect threshold for promotion (P1b):** require reuse ≥ 1, or accept
  long_memory-persistence as an alternative anchor?~~ **Resolved (not actually a free
  choice):** the reuse signal only reaches *named authored artifacts*, never prose, so
  the threshold is kind-aware — code/tool → `reuse ≥ 1`, prose → `long_memory`
  persistence. See P1b. The only remaining knob is the persistence bar for prose (how
  important / how long it must endure) — propose: importance above the `long_memory`
  retention floor *and* survival of one consolidation cycle.
- **Artifact-text sidecar (P1a):** store inline in the candidate row, or a separate
  capped store keyed by hash? (Affects store size / privacy.)
- **Ratify surface (P4):** Learning page inline, or a dedicated Settings review queue?

---

*Implements `QUALITY_STANDARD_EVOLUTION_PLAN_2026-06-28.md`. Reuses the
`value_revisions` provenance schema and `brain/agency/effect_ledger.py`. The
human-ratify queue (P4) and artifact-text capture (P1a) are net-new. No predicate
auto-tuning — rule changes are human-only, regression-gated.*
