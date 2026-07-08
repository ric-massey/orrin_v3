# Expression Membrane

`brain/behavior/express_to_user.py` is **the one door**: every artifact a person sees — a live
reply, a note, a desktop file, a dashboard announcement, an OS notification — is composed here from
a **Motive** (intent + felt state). Nothing person-facing is ever populated by scraping internal
representation.

## Why one door

Before the membrane (fixed 2026-06-14), emitters scraped working memory directly, so internal
fragments could leak to the person verbatim — unfiltered, incoherent, or not something the runtime
"meant to say." The membrane inverts this: expression starts from an intent, not from whatever
happens to be in memory.

## Two sides, one door

```
INTENT (motive)  ──►  express_to_user(...)  ──►  channel
```

Inside the door:

- **Composition** goes through `expression.express()` — affect plus the learned vocabulary,
  congruence-enforced (the text must match the actual internal state; Rogers 1959 is the cited
  inspiration for congruence).
- **The speakability invariant** is enforced in exactly one place: whatever channel the output
  takes, it passed the same checks.
- **Channel fan-out** — live reply, note, file, announcement, notification — happens after
  composition, so every channel gets the same quality of output.

## What this means in practice

- The reasoning layer describes its own state in qualitative terms (see
  [Control Signals](Control_Signals.md) — the reasoning layer never receives raw numbers), and the
  membrane keeps person-facing text consistent with that state estimate.
- Delivered notes and replies are recorded as effects on the
  [effect ledger](Production_and_Effect_Ledger.md), so communication counts as production.
- Anything that bypasses `express_to_user` to reach a person is a bug by definition — there is one
  door on purpose, which makes auditing person-facing output tractable.

## Code pointers

- `brain/behavior/express_to_user.py` — the door (design: `EXPRESSION_MEMBRANE_FIX_PLAN`, 2026-06-14)
- `brain/think/speech_builder.py`, `speech_coherence.py` — utterance construction and checks
- `frontend/src/pages/Face.tsx` — where expressed output lands in the UI
