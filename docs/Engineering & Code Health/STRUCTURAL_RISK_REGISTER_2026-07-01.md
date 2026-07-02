# Structural Risk Register (P8 — B5 / B6, standing)

**Date opened:** 2026-07-01
**Derives from:** `IMPLEMENTATION_PLAN_GROUNDING_AND_SURFACE_2026-06-30.md` Phase 8.
Not a wiring fix — a standing register, reviewed after each landed phase.

## B5 — Integration surface (~507 modules / one dev)

**Discipline:** keep `make verify` green after every phase; land work in small,
independently-verifiable slices; after each phase, a full-loop staging run and a
trace diff (integration failures only show up when it all runs together).

**Status 2026-07-01 (P5–P7 landed):**
- Full suite: **1278+ passing, zero failures** — the exception ratchet is back
  at ceiling 0 (all remaining broad handlers are annotated `# intentional:`),
  and the module-size ratchet is green (3 grounded-cognition modules exempted
  with named decomposition candidates: `acquisition.py` corpus-assembly split,
  `update_signal_state.py` restoring-force extraction, `intrinsic_generators.py`
  generator-family split — each expected to trend back under 600).
- **Isolation breach found & fixed:** the P2a tests called the real
  `native_lm.train_on`, which trained junk steps into and saved the LIVE
  lifelong checkpoint (`brain/data/language/native_lm.pt`) during test runs.
  Now isolated (`_isolated_lm` fixture redirects the checkpoint and builds a
  fresh model). The session tripwire in `tests/conftest.py` caught this —
  keep it; it earns its keep.
- Standing full-loop staging run for P1–P7 together: **still pending** (Orrin
  is stopped; next boot will carry the run stamp).

## B6 — Native learner scale + catastrophic forgetting

The 4-layer nanoGPT caps the ceiling; replay interleaving in `read_a_book` is a
band-aid over an unsolved problem. Tracked as research risk, not a wiring task:

1. **Forgetting probe (the metric).** `native_lm.evaluate(text)` is a held-out
   perplexity probe with no gradient. Protocol: freeze two probe texts —
   (a) book prose he trained on early, (b) grounded/self-experience text — and
   record both perplexities after every consolidation bout
   (`consolidate_language`). Rising (a) while (b) falls = forgetting book
   language; both rising = degenerate diet. Any replay-ratio or diet-weight
   change (P2a knobs) is an EXPERIMENT against this probe, not a tweak.
2. **Scale path.** Evaluate a larger native model or a pluggable provider
   (Desktop plan Group H) only after the probe shows the 4-layer ceiling is the
   binding constraint — not before there's a measurement to beat.
3. **Diet interactions.** P2a's reward-weighted sampler shifts the diet toward
   experience; the book-prose floor exists precisely to bound forgetting. The
   floor's value is a probe-tunable, not a constant to hand-tune blind.

## Review cadence

After each phase lands (and before any commit batch): run the full suite, skim
this register, update the status lines above. If a ratchet exemption's named
decomposition gets done, remove the exemption in the same change.
