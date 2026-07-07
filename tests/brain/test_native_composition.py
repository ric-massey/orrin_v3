# AR3 (CODEBASE_AUDIT_2026-07-01 D6): with the LLM off, compose_section's draft
# must come from his own trained language organ (maturity-gated, like the mouth),
# not the fixed 4-paragraph template that gamed the artifact gate.
# F1 (2026-07-05 findings): the template is GONE entirely — it stamped 166
# identical sections into a 197 KB manuscript. An immature organ or a
# degenerate generation now fails the draft honestly (empty string), which the
# caller turns into a countable step failure instead of a manuscript write.
import pytest

from brain.agency import compose_section as cs
from brain.agency.effect_ledger import MIN_ARTIFACT_CHARS

_GOAL = {
    "id": "g-essay", "title": "Essay on emergence",
    "grounded_parts": ["local interactions", "global order", "feedback"],
}

# A recognizable sentence from the removed fixed template — it must never
# reappear in any draft.
_TEMPLATE_MARK = "The first requirement is structural clarity."

_ORGAN_TEXT = (
    "Order can grow out of many small exchanges that none of the participants "
    "understands in full. When each unit adjusts to its neighbours, the whole "
    "settles into patterns that carry information no single unit holds, and "
    "that is the sense in which the essay's subject is real rather than a "
    "figure of speech. What follows examines where such patterns get their "
    "stability and when they break."
)

_MATERIAL = [
    ("note_novel", "Small exchanges between neighbours settle into patterns "
     "that carry information no single unit holds by itself.", ""),
    ("long memory", "The order re-formed from local rules alone after the "
     "central controller was removed from the simulation.", ""),
]


@pytest.fixture(autouse=True)
def _llm_off(monkeypatch):
    monkeypatch.setattr(cs, "llm_callable_by", lambda caller: False)


def test_ready_organ_drafts_the_section(monkeypatch):
    import brain.cognition.language.voice as voice
    import brain.cognition.language.native_lm as nlm
    monkeypatch.setattr(voice, "lm_ready", lambda: True)
    monkeypatch.setattr(nlm, "generate",
                        lambda prompt, length=80, temperature=0.8, **k: prompt + _ORGAN_TEXT)

    text = cs._draft(_GOAL, "Section 1", list(_MATERIAL))
    assert _ORGAN_TEXT[:40] in text
    assert _TEMPLATE_MARK not in text
    assert len(text) >= MIN_ARTIFACT_CHARS


def test_immature_organ_fails_the_draft_honestly(monkeypatch):
    # F1: no capable writer → no draft, no template. The caller reports
    # "could not draft" as a real step failure the attempt cap can count.
    import brain.cognition.language.voice as voice
    monkeypatch.setattr(voice, "lm_ready", lambda: False)

    text = cs._draft(_GOAL, "Section 1", list(_MATERIAL))
    assert text == ""
    assert _TEMPLATE_MARK not in text


def test_degenerate_generation_fails_the_draft_honestly(monkeypatch):
    # A ready organ that emits junk under the honest floor must not fill the
    # manuscript — and there is no template to fall back to.
    import brain.cognition.language.voice as voice
    import brain.cognition.language.native_lm as nlm
    monkeypatch.setattr(voice, "lm_ready", lambda: True)
    monkeypatch.setattr(nlm, "generate",
                        lambda prompt, length=80, temperature=0.8, **k: "eee eee eee")

    text = cs._draft(_GOAL, "Section 1", list(_MATERIAL))
    assert text == ""
