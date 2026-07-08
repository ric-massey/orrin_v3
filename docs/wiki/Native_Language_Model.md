# Native Language Model

Orrin has two complementary language layers that are deliberately **not** the external LLM tool:
a symbolic phrasing tier and a from-scratch neural language organ. Both learn only from what the
runtime itself has read and said.

## The two tiers

- **Symbolic phrasing tier** (`brain/cognition/language_acquisition.py`) — mines reusable
  discourse-marker openers from what Orrin reads and lends them to the template speech builder. It
  broadens *how the template pipeline phrases things today*, with no neural network involved.
- **Neural language organ** (`brain/cognition/language/`) — a from-scratch transformer that learns
  to produce language:
  - `tokenizer.py` — the tokenizer, built from Orrin's own corpus.
  - `native_lm.py` — the model itself (checkpointed as `native_lm.pt`).
  - `acquisition.py` (+ `acquisition_noise.py`) — the training loop over what the runtime reads;
    corpus hygiene matters here (a contamination fix keeps non-language artifacts out of training).
  - `voice.py` — the speech handoff: the organ is meant to *gradually take over* speech from the
    symbolic templates, gated so it only speaks where its output quality clears the bar.
  - `conditional_render.py`, `library.py` — rendering support and the phrase library.

## Design intent

The point is developmental, and it's the same point that keeps the external LLM off the control
loop: **a pretrained model is frozen, and Orrin wants a language faculty that grows.** An external
LLM's weights never change with what this runtime lives through; the native organ's do. So rather
than borrow a fixed model, Orrin grows his own — a transformer that trains only on what he has read
and said, and gets better as that corpus of lived experience accumulates. The external LLM (see
[LLM Integration](LLM_Integration.md)) never writes Orrin's inner speech; the native organ and the
symbolic templates do, and the UI's Language panel plus the bilingual thought line
(`frontend/src/lib/thoughts.ts` / `lexicon.ts`) let you watch the vocabulary develop. This is why
the LLM is contained to a gated tool rather than made the controller — see
[Symbolic-First Design](Symbolic_First_Design.md) for the full argument.

## Relationship to memory

`memory/lexicon/` tracks learned word associations on the memory side; the language organ trains on
the reading/speech corpus. The two develop together but are separate stores.

## Practical notes

- Everything here is symbolic-only-safe: no provider key is ever required.
- The `native_lm.pt` checkpoint is runtime state; tests isolate it so a test run can't clobber a
  developing model.

## Code pointers

- `brain/cognition/language/` — the neural organ
- `brain/cognition/language_acquisition.py` — the symbolic phrasing tier
- `frontend/src/components/brain/LanguagePanel.tsx` — the UI surface
