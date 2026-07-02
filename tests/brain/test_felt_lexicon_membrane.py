# The interoception membrane (felt_lexicon): internal signal/function IDENTIFIERS
# must never appear as raw text in perceivable content. He feels a mood, not a
# variable name (introspection.py contract). RUN diagnosis 2026-06-29.
from brain.utils.felt_lexicon import is_internal_identifier, felt_label


def test_detects_internal_identifiers():
    assert is_internal_identifier("impasse_signal rises")
    assert is_internal_identifier("The causes of affective_regulation")
    assert is_internal_identifier("reward_positive")
    assert is_internal_identifier("[appraisal] motivation rose")
    # World content is not internal.
    assert not is_internal_identifier("the history of written language")
    assert not is_internal_identifier("convection cells in heated fluid")


def test_felt_label_translates_keys_to_mood_words():
    assert "signal" not in felt_label("impasse_signal").lower()
    assert "impasse_signal" not in felt_label("impasse_signal rises")
    assert felt_label("impasse_signal") == "being stuck"
    # direction phrase → felt change
    assert felt_label("impasse_signal rises") == "being stuck grows"
    # unknown internal identifier collapses to a vague inner state (imprecise interoception)
    assert felt_label("self_query") == "an inner state"
    # non-internal passes through unchanged
    assert felt_label("the island") == "the island"


def test_no_engineering_identifier_survives_translation():
    # The leak is the engineering-shaped keys (underscores / *_signal). Plain English
    # mood words (confidence, dread, reflective) are already felt vocabulary and may
    # legitimately appear. Assert no underscored identifier survives translation.
    from brain.utils.felt_lexicon import _SIGNAL_KEYS
    for key in _SIGNAL_KEYS:
        out = felt_label(key).lower()
        assert "_" not in out, f"{key!r} leaked an engineering identifier: {out!r}"
        if "_" in key:
            assert key not in out, f"{key!r} leaked through felt_label as {out!r}"


def test_strip_scaffold_removes_conditioning_prefix():
    # The exact leak seen in the 2026-06-30 run: the serialized thought-object
    # prefix surfaced in perceivable speech. It must be stripped, content kept.
    from brain.utils.felt_lexicon import strip_scaffold, has_scaffold
    leaked = "say express_state curiosity pen uestion: Are these genuine? Something present but hard to name."
    out = strip_scaffold(leaked)
    assert out.startswith("Are these genuine")
    assert "express_state" not in out
    assert not out.lower().startswith("say express_state")
    # bracketed form too
    assert strip_scaffold("<say narrate_experience | being stuck> I looked at my files.") \
        == "I looked at my files."
    # detection
    assert has_scaffold(leaked)
    assert not has_scaffold("Are these genuine feelings?")
    # clean speech is untouched
    assert strip_scaffold("I felt stuck, so I searched my files.") == "I felt stuck, so I searched my files."


def test_strip_scaffold_does_not_eat_ordinary_say():
    # "say" not followed by an intent token is ordinary language — keep it.
    from brain.utils.felt_lexicon import strip_scaffold
    assert strip_scaffold("I wanted to say hello to you.") == "I wanted to say hello to you."


def test_causal_graph_tags_self_vs_world_edges(tmp_path, monkeypatch):
    import brain.symbolic.causal_graph as cg
    monkeypatch.setattr(cg, "EDGES_FILE", tmp_path / "edges.json", raising=False)
    # Point the loader/saver at the tmp file regardless of internal constant name.
    store = {"edges": []}
    monkeypatch.setattr(cg, "_load_edges", lambda: store["edges"])
    monkeypatch.setattr(cg, "_save_edges", lambda e: store.__setitem__("edges", e))

    cg.update_edge("look_outward", "impasse_signal falls", confirmed=True, source="intervention")
    cg.update_edge("rain", "wet streets", confirmed=True, source="temporal")

    edges = cg.get_all_edges()
    by_effect = {e["effect"]: e for e in edges}
    assert by_effect["impasse_signal falls"]["domain"] == "self"
    assert by_effect["wet streets"]["domain"] == "world"
    # world filter excludes the self edge
    world = cg.get_all_edges(domain="world")
    assert all(not cg.is_self_edge(e) for e in world)
    assert "wet streets" in {e["effect"] for e in world}
    assert "impasse_signal falls" not in {e["effect"] for e in world}
