# Quality Standard

`brain/cognition/quality_standard/` is Orrin's evolving quality bar: an executable predicate that
decides whether a piece of work is good enough to credit, backed by a **golden set** of exemplars
that develops from demonstrated-good work. Its defining property: **Orrin cannot edit its own
standard.** The bar only moves through human-ratified rule changes.

## The pieces

- `gate.py` — the promotion gate, **the only auto-apply path** in the component. It is a
  ratchet-pin, not bar-development: adding an exemplar the current predicate already accepts
  imposes no new constraint — it only *pins* that artifact as protected-good, so a future rule
  loosening that would start rejecting it shows up as a regression.
- `proposer.py` — proposes candidate exemplars from work that scored well in practice.
- `ratify.py` — the human-ratification path: actual changes to the rules (stricter or broader) are
  applied only here, by a person. The backend exposes this through
  `backend/server/routers/quality_standard.py` so ratification happens in the UI.
- `revisions.py` — the revision history of the standard, so every movement of the bar is auditable.
- `audit.py` — regression checks: every pinned exemplar must still pass after a rule change; each
  fixture is judged in isolation so a regression can't hide behind context.
- `cli.py` — command-line inspection and maintenance.

## Why it exists

Production reward (see [Production and the Effect Ledger](Production_and_Effect_Ledger.md)) only
works if "production" can't be gamed. Without a bar, the cheapest path to reward is stamping out
template output — which a staging run actually demonstrated (a 197KB fake manuscript from a
template stamper). The quality standard is the counterweight: an artifact must pass the current
predicate to be creditable, and the predicate's history is pinned so it can only be loosened
knowingly, by a human, with regressions surfaced.

## The safety property

Direction + predicate-conformance, not just the regression test:

1. The **auto path can only pin**, never loosen or tighten.
2. **Loosening requires ratification** by a person, with the audit showing exactly which pinned
   exemplars a proposed change would reject.
3. The standard's development is **grounded in demonstrated-good work**, not in self-assessment —
   Orrin proposes, the human disposes.

## Code pointers

- `brain/cognition/quality_standard/` — the component
- `backend/server/routers/quality_standard.py` — the ratification surface in the UI
