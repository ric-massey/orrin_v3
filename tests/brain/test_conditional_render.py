# Phase 2C/2D (Grounded Cognition plan / THOUGHT_OBJECT_SPEC.md): the native LM
# as MOUTH — serialize a thought object, render it, and GATE the result so his
# voice only flips from templates to the organ when it is fluent and the rendering
# is faithful (membrane-clean, non-degenerate, reconstruction-consistent).
import json

import brain.cognition.language.conditional_render as cr


def _thought():
    return {
        "intent": "narrate_experience",
        "recipient": "self",
        "affect": {"felt": "being stuck", "signal": "impasse_signal"},
        "concept_refs": [{"type": "act", "handle": "search_own_files"}],
        "stance": "first_person",
    }


# ── 2C(i): serialization ─────────────────────────────────────────────────────

def test_serialize_is_compact_and_membrane_clean():
    prefix = cr.serialize_thought(_thought())
    assert prefix.startswith("<say ")
    assert "narrate_experience" in prefix
    assert "being stuck" in prefix
    assert "search_own_files" in prefix
    # the felt surface is used, never the raw signal key
    assert "impasse_signal" not in prefix
    assert len(prefix) < 120          # compact (native_lm context is 128 tokens)


def test_serialize_failsafe_on_garbage():
    assert cr.serialize_thought(None) == "<say>"
    assert cr.serialize_thought({}).startswith("<say")


# ── pairs corpus (training fuel for the conditional decoder) ─────────────────

def test_narration_pairs_corpus_formats_prefix_plus_narration(tmp_path, monkeypatch):
    pf = tmp_path / "narration_pairs.jsonl"
    pf.write_text(json.dumps({"thought": _thought(),
                              "narration": "Feeling being stuck, I looked through my own files."}) + "\n",
                  encoding="utf-8")
    monkeypatch.setattr(cr, "_PAIRS_FILE", pf)
    corpus = cr.narration_pairs_corpus()
    assert corpus.startswith("<say ")
    assert "I looked through my own files." in corpus


# ── the bright line (spec §4) ────────────────────────────────────────────────

def test_reconstruction_requires_meaning_to_survive():
    t = _thought()
    assert cr._reconstruction_ok(t, "I felt stuck and searched my files.")   # anchors present
    assert not cr._reconstruction_ok(t, "The weather is pleasant in spring.")  # unrelated


def test_non_degenerate_rejects_repetition():
    assert cr._non_degenerate("I looked through my own files quietly")
    assert not cr._non_degenerate("the the the the the")
    assert not cr._non_degenerate("hi")


def test_membrane_clean_rejects_internal_identifier():
    assert cr._membrane_clean("I felt stuck and searched my files.")
    assert not cr._membrane_clean("impasse_signal rose sharply")


# ── 2D: the gate keeps templates TODAY (no surprise behavior change) ──────────

def test_render_returns_none_when_organ_not_fluent(monkeypatch):
    monkeypatch.setattr(cr, "organ_fluent", lambda: False)
    assert cr.render_from_thought(_thought()) is None


def test_render_happy_path_passes_faithful_output(monkeypatch):
    monkeypatch.setattr(cr, "organ_fluent", lambda: True)
    prefix = cr.serialize_thought(_thought())
    import brain.cognition.language.native_lm as native_lm
    # organ returns prefix + a faithful continuation
    monkeypatch.setattr(native_lm, "generate",
                        lambda prompt="", length=60, temperature=0.8:
                        prefix + " I felt stuck, so I searched my own files.")
    out = cr.render_from_thought(_thought())
    assert out == "I felt stuck, so I searched my own files."


def test_render_rejects_unfaithful_output(monkeypatch):
    monkeypatch.setattr(cr, "organ_fluent", lambda: True)
    prefix = cr.serialize_thought(_thought())
    import brain.cognition.language.native_lm as native_lm
    # fluent but unrelated → fails reconstruction → rejected (caller keeps template)
    monkeypatch.setattr(native_lm, "generate",
                        lambda prompt="", length=60, temperature=0.8:
                        prefix + " The weather is pleasant in spring this year.")
    assert cr.render_from_thought(_thought()) is None
