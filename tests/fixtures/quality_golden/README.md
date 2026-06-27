# Quality-predicate golden set (T0.5)

This is the **operational definition of "high quality"** for Orrin's produced work.
`tests/brain/test_quality_predicate.py` asserts that
`brain.cognition.quality_predicate.assess_quality`:

- **passes every file in `exemplars/`** — work that meets the standard, and
- **rejects every file in `anti_exemplars/`** — known slop shapes.

## exemplars/  — Ric authors these; **they *are* the standard**

Drop real, finished pieces of work here (`.md`/`.txt`), one per file. The predicate
must pass all of them. `starter_*` files are placeholders authored during the T0.5
build so the pass-path is exercised; replace/augment them with your own.

## anti_exemplars/  — pulled from the 2026-06-23 run's actual artifacts

The shapes the run produced that must NEVER count as real work: the
`grounded_parts`-template note (provenance reached the topic, severed at the
answer), the `s_*_ok.txt` machine-log stubs, and near-duplicates.

## The ratchet

Any low-quality output that slips through in a future run becomes a **new file in
`anti_exemplars/`**; the predicate must then reject it. The standard only rises —
it never silently loosens.

Files named `README.md`, `PLACEHOLDER*`, or starting with `_` are ignored by the test.
