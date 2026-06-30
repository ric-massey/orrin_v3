# The Thought Object — Specification (Grounded Cognition Plan, Phase 2A)

Status: **spec.** This is the first and hardest deliverable of Phase 2 (LM-as-mouth).
Until it exists, "the native LM is the mouth, not the mind" is a slogan. This document
defines the structured internal object the symbolic mind builds and the native LM
*renders* — and, critically, draws the line between what the thought object **fixes**
(the mind's job) and what it **leaves to the LM** (the mouth's job), with the argument
for why the latter is *rendering*, not *originating content*.

It builds on what already exists: `express_to_user.Motive`
(`intent / why / recipient / seed / goal_id`) already half-implies this object. The
thought object is `Motive` made explicit and decoder-ready.

---

## 1. Why this object has to exist

The direction doc's honest tension (Part D, item 3): a thought object rich enough to
render *unambiguously* means the symbolic layer already did the hard work of language
production and the LM is a thin formatter; a thought object too thin means the LM is
*originating content* — which `llm_tool_only` forbids and which is the corpus-
contamination risk the membrane (invariant #2) exists to prevent.

The resolution is not to pick a point on that spectrum but to **name two registers**
and assign each to the right faculty:

- **Semantic register (the mind owns it):** *what* is meant — the speech-act intent,
  the propositional referents (grounded concept handles), the felt state, and the
  first-person stance toward it. Fixed in the thought object. The LM may not add to,
  remove from, or contradict it.
- **Surface register (the mouth owns it):** *how* it is said — lexical choice, syntax,
  word order, register, rhythm, connective tissue, which of many true phrasings to
  emit. Deliberately underspecified in the thought object; the LM selects it.

This mirrors real production (the direction doc's own caveat): humans do heavy
lexical/syntactic selection *during* speech — thoughts are not fully word-specified
before language. The surface register is exactly that latitude, bounded so it cannot
leak into the semantic register.

---

## 2. The schema

A thought object is a JSON-serialisable dict. `_BLOCK=128` in `native_lm`, so the
serialised conditioning prefix must be **compact** (Phase 2C constraint) — every field
below is short by design.

```jsonc
{
  "intent":    "narrate_experience",     // the speech act (closed vocabulary, §3)
  "recipient": "self",                   // "Ric" | "self" | "dashboard"
  "affect": {                            // the FELT state — never a raw gauge read
    "felt":     "being stuck",           //   felt_label() output (membrane-safe surface)
    "signal":   "impasse_signal",        //   machine key — conditioning input ONLY (§5)
    "valence":  -0.4,                    //   [-1,1] optional
    "arousal":   0.6                     //   [0,1]  optional
  },
  "concept_refs": [                      // the grounded handles the thought is ABOUT
    {"type": "act",   "handle": "assess_goal_progress"},
    {"type": "goal",  "handle": "g_1842"},
    {"type": "skill", "handle": "search_files"}      // (Phase 5 — grounded skill names)
  ],
  "stance":  "first_person",             // "first_person" | "endorsed" | "disowned"
                                         //   | "ambivalent" (from intention_endorsement)
  "seed":    ""                          // optional meaning kernel (Motive.seed), sanitised
}
```

### Field contract
- **`intent`** — *required.* One value from the closed speech-act vocabulary (§3). The
  LM may not change it. This is the single most important constraint: it fixes the
  illocutionary force so the renderer cannot turn a check-in into a complaint.
- **`recipient`** — *required.* Selects register (self-talk vs. addressing Ric vs. a
  dashboard line). Routing, not content.
- **`affect`** — *required.* Carries the felt translation (`felt`, what a human-facing
  surface may show) and the machine `signal` key (conditioning input only, §5).
  `valence`/`arousal` are optional scalars that let the renderer pick congruent tone.
- **`concept_refs`** — *the propositional core.* The grounded handles the utterance is
  about. **The LM may reference these but may not introduce a handle not in this list**
  — that is the bright line that keeps it from originating content (§4). Today these are
  the act picked, the bound goal, and (Phase 5) grounded skill names. As grounding
  matures (Phase 3/4A) these become predictive-signature concept handles, not strings.
- **`stance`** — *required.* The first-person attitude, sourced from
  `intention_endorsement` when available (endorsed / disowned / ambivalent), else
  plain `first_person`. Lets the renderer say "I refuse to be ruled by X" vs. "I want X"
  without the LM inventing the attitude.
- **`seed`** — *optional.* `Motive.seed`'s sanitised meaning kernel; reworded, never
  copied. Empty is fine.

---

## 3. The speech-act intent vocabulary (closed)

Closed on purpose — a closed set is what makes the intent *fixed* rather than something
the LM negotiates. Seeded from the existing expressive surfaces; extend deliberately,
never ad hoc.

| intent                | when                                        | existing trigger              |
|-----------------------|---------------------------------------------|-------------------------------|
| `narrate_experience`  | first-person felt summary of what he did    | `acquisition.narrate_experience` |
| `report_blocker`      | surfacing an impasse to Ric                 | `express_to_user` EXPRESSIVE  |
| `share_finding`       | reporting a result/insight                  | `express_to_user` EXPRESSIVE  |
| `check_in`            | low-stakes presence / connection            | `express_to_user` EXPRESSIVE  |
| `ask_question`        | requesting information he lacks             | goal/curiosity path           |
| `reflect`             | self-directed reflection (recipient=self)   | reflection/volition path      |

---

## 4. The bright line: rendering vs. originating content

The LM is **rendering** (allowed) and never **originating** (forbidden). Concretely,
a rendering is valid iff:

1. **No new referent.** Every entity/concept the output is *about* traces to a
   `concept_refs` handle. The LM may not name a concept absent from the list.
2. **Intent preserved.** The illocutionary force equals `intent`. A `check_in` may not
   render as a `report_blocker`.
3. **Affect not contradicted.** The rendered tone is congruent with `affect`
   (valence/arousal sign), as the existing `expression.express` congruence check
   (Rogers 1959) already enforces.
4. **Stance preserved.** An endorsed desire is not rendered as disowned, or vice versa.

Everything *else* — which synonym, which clause order, how many words, what rhythm — is
the LM's to choose. That latitude is large (it is most of what makes speech sound like a
person), but it is **orthogonal to meaning**: it cannot add a referent, flip an intent,
or invert an affect. That orthogonality is precisely why exercising it is rendering, not
authoring. The four checks above are the testable form of the bright line.

---

## 5. Membrane relationship (invariant #2)

The thought object is **machine-facing conditioning input**, not perceivable content.
So it MAY carry the raw `affect.signal` key (`impasse_signal`) — richer conditioning for
the decoder. This does **not** violate the membrane: the membrane keeps internal
identifiers out of *perceivable stores* (working memory, goals, the conscious stream)
that the mind then reasons over. The thought object is consumed by the renderer and
discarded; it is never written back as something he perceives.

The **output** of rendering, however, is perceivable, so it passes through the same
seal as today: `strip_internal` / `assert_speakable` in `express_to_user`. The renderer
can emit only surface forms; the membrane guards the door regardless. So:

- conditioning input (thought object) → may contain `signal` keys;
- rendered output (what a person sees) → membrane-clean by construction.

This is the same mouth-vs-mind boundary `ORRIN_LANGUAGE_PLAN.md` and the direction doc
already accept (Part D′): the corpus teaches the organ *how to say*, the thought object
fixes *what to say*, and the mouth cannot author concepts.

---

## 6. How it is produced and consumed

- **Produced** by the symbolic mind at the moment of expressive intent:
  `express_to_user.build_motive` (today) and `acquisition.narrate_experience` (the
  self-narration path). Phase 2B captures the thought object **alongside** the existing
  templated narration as a `(thought_object → narration)` conditioning pair, so the
  conditional-decoder training set accumulates now without changing behaviour.
- **Consumed** (later, Phase 2D, gated on fluency) by
  `native_lm.generate(conditioned_on=thought_object)`, replacing the template/LLM path;
  template only on a fluency-gated fallback (`native_lm.evaluate` perplexity gate).

---

## 7. The ceiling and the second-signal decision (Phase 2C — DECIDED)

Distillation from the templated narrator cannot exceed its teacher without a second
signal (direction doc Part D): a decoder trained only to reproduce templates regresses
to template-mean. The thought object makes the *conditioning* principled; the
supra-template signal was the open choice.

**Decision (recorded):** the **default is to accept the near-template ceiling** — the
project's authenticity-over-fluency value (direction doc Part E). For a supra-template
signal we use **reconstruction consistency** (round-trip thought→words, check the
meaning survived), chosen over human ratings (needs Ric in the loop) and contrastive
preference (needs a preference model) because it is the only **self-contained** option —
no human, no external model — which fits the offline ethos. It is implemented in
`conditional_render._reconstruction_ok` as the per-output gate, and is the seed of a
future reconstruction *training* loss.

**Conditioning mechanism (2C-i):** a compact tagged prefix
(`<say intent | felt | handles>`, `conditional_render.serialize_thought`) prepended to
`native_lm.generate` — chosen over a learned conditioning embedding because it needs no
architecture change and keeps within the 128-token context. The accumulating Phase-2B
pairs are reformatted as `prefix + narration` and folded into consolidation training
(`acquisition.consolidate_language`), so the organ learns to render from the prefix.

## 8. The render path and its gate (Phase 2D — BUILT, fluency-gated)

`conditional_render.render_from_thought(thought)` is the mouth: serialize → generate →
strip prefix → **validate against the bright line (§4)** — membrane-clean,
non-degenerate, reconstruction-consistent. It returns rendered text only when
`organ_fluent()` (held-out perplexity on the pair format below threshold) *and* the
output passes; otherwise `None`, and the caller keeps its template.

**Wired callers:** `express_to_user.compose_from_motive` tries the native render first,
falling back to `expression.express` unchanged. `compose_section` is **deliberately out
of scope** — it produces 350+ word long-form sections, which an 8–9M-param / 128-token
organ cannot render; it stays on its LLM/template path. `narrate_experience` keeps its
template as the corpus *teacher* (flipping the teacher to render from itself is a
self-training feedback risk, deferred past mere fluency).

Because `organ_fluent()` is False until the organ has trained on the conditioning
pairs, **today every caller falls back to its template** — his voice is unchanged. The
flip happens automatically, per-utterance, when the organ crosses the gate.

## 9. First implementation step (Phase 2B — done)

Capture `(thought_object → narration)` pairs in a sidecar `narration_pairs.jsonl`,
keyed to the **same throttle** the narrator already uses (`_NARRATE_MIN_INTERVAL_S`), so
pairs accumulate during every other phase. The thought object at narration time is:
`intent=narrate_experience`, `recipient=self`, `affect` from `perceived_affect_state`,
`concept_refs` = the picked act (+ bound goal), `stance=first_person`. This realised the
in-code TODO at `acquisition.py:373` and is implemented in
`acquisition._build_thought_object` / `_append_narration_pair`.
