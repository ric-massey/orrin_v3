# AR3 (CODEBASE_AUDIT_2026-07-01 D6): with the LLM off, compose_section's draft
# must come from his own trained language organ (maturity-gated, like the mouth),
# not the fixed 4-paragraph template that gamed the artifact gate. The template
# survives only as the organ-not-ready fallback, and a degenerate generation
# still has to clear MIN_ARTIFACT_CHARS honestly.
import pytest

from brain.agency import compose_section as cs
from brain.agency.effect_ledger import MIN_ARTIFACT_CHARS

_GOAL = {
    "id": "g-essay", "title": "Essay on emergence",
    "grounded_parts": ["local interactions", "global order", "feedback"],
}

# A recognizable sentence from the fixed template — its presence marks the fallback.
_TEMPLATE_MARK = "The first requirement is structural clarity."

_ORGAN_TEXT = (
    "Order can grow out of many small exchanges that none of the participants "
    "understands in full. When each unit adjusts to its neighbours, the whole "
    "settles into patterns that carry information no single unit holds, and "
    "that is the sense in which the essay's subject is real rather than a "
    "figure of speech. What follows examines where such patterns get their "
    "stability and when they break."
)


@pytest.fixture(autouse=True)
def _llm_off(monkeypatch):
    monkeypatch.setattr(cs, "llm_callable_by", lambda caller: False)


def test_ready_organ_drafts_the_section(monkeypatch):
    import brain.cognition.language.voice as voice
    import brain.cognition.language.native_lm as nlm
    monkeypatch.setattr(voice, "lm_ready", lambda: True)
    monkeypatch.setattr(nlm, "generate",
                        lambda prompt, length=80, temperature=0.8, **k: prompt + _ORGAN_TEXT)

    text = cs._draft(_GOAL, "Section 1", {})
    assert _ORGAN_TEXT[:40] in text
    assert _TEMPLATE_MARK not in text
    assert len(text) >= MIN_ARTIFACT_CHARS


def test_immature_organ_falls_back_to_template(monkeypatch):
    import brain.cognition.language.voice as voice
    monkeypatch.setattr(voice, "lm_ready", lambda: False)

    text = cs._draft(_GOAL, "Section 1", {})
    assert _TEMPLATE_MARK in text


def test_degenerate_generation_falls_back(monkeypatch):
    # A ready organ that emits junk under the honest floor must not fill the
    # manuscript — the template fallback still runs.
    import brain.cognition.language.voice as voice
    import brain.cognition.language.native_lm as nlm
    monkeypatch.setattr(voice, "lm_ready", lambda: True)
    monkeypatch.setattr(nlm, "generate",
                        lambda prompt, length=80, temperature=0.8, **k: "eee eee eee")

    text = cs._draft(_GOAL, "Section 1", {})
    assert _TEMPLATE_MARK in text
    assert len(text) >= MIN_ARTIFACT_CHARS
