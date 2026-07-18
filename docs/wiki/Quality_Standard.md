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
- `originality.py` — a **deterministic veto** on auto-promotion (not a quality judge). It answers
  one exactly-measurable question — *how much of this artifact is copied rather than authored?* —
  and holds derivative artifacts back from auto-canonisation, routing them to human review. Signals,
  in order: provenance footer (`source: fetch_and_read` = a raw web dump), the offline-synthesis
  stitch header, quoted-block ratio, verbatim n-gram overlap with the goal's own captured source
  docs (fail-open when no sources), and a floor on authored prose. See "The originality veto" below.
- `proposer.py` — proposes candidate exemplars from work that scored well in practice.
- `ratify.py` — the human-ratification path: actual changes to the rules (stricter or broader) are
  applied only here, by a person. The backend exposes this through
  `backend/server/routers/quality_standard.py` so ratification happens in the UI.
- `revisions.py` — the revision history of the standard, so every movement of the bar is auditable.
- `audit.py` — regression checks: every pinned exemplar must still pass after a rule change; each
  fixture is judged in isolation so a regression can't hide behind context.
- `cli.py` — command-line inspection and maintenance.

## Why it exists

Production reward (see [Production and the Effect Ledger](Production_and_Effect_Ledger)) only
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

## The originality veto

Because the golden set only grows and only loosens by human sign-off, canonising the *wrong* thing
is a one-way error: a bad exemplar permanently redefines "good" downward, in the one store designed
to resist exactly that. Run 9 (2026-07-17, symbolic-only) hit this — it promoted its first three
exemplars ever, and one was a raw PLOS abstract the research handler had fetched and stamped as a
"memo" (`source: fetch_and_read`). The credit anchor and the predicate both passed it; nothing was
measuring *whether Orrin wrote it*.

`originality.py` adds that measurement as a **veto, not a criterion**. The distinction is load-bearing
and matches how quality actually works: a deterministic check can establish "this was copied too
closely"; it *cannot* establish "this is good work." So copy-fraction only ever blocks the automatic
path — a derivative artifact is routed to the same human review a too-strict predicate uses, with a
`copy_report` attached — and never stands in for the real promotion criteria (downstream credit +
the predicate). This is the general rule the component follows: **use deterministic checks for
genuinely deterministic properties; build the broader judgment from credit, exemplars, consequences,
and human ratification.**

Two properties make the veto robust rather than gameable:

- **Provenance beats heuristics.** The strongest signal is the artifact's own `source:` footer.
  A raw fetch declares itself; no text-analysis heuristic is needed or trusted above it.
- **It fails open.** Missing source docs, an unresolvable goal id, a code artifact with no notion of
  "sources" — all yield *no veto*. Only the positive presence of copying blocks a promotion, so a
  filing-mess degrades to "no signal", never to a false accusation against authored work.

It is also **mode-independent by design**: turning the LLM on does not fix the contamination it
guards against (an LLM that paraphrases the same abstract is still not Orrin's authored work — a
subtler contamination, not a cure), so the veto measures copying directly from material already
captured next to the artifact, in every mode.

## Code pointers

- `brain/cognition/quality_standard/` — the component (`originality.py` = the veto,
  `tests/brain/test_originality_veto.py` = its pins)
- `backend/server/routers/quality_standard.py` — the ratification surface in the UI
