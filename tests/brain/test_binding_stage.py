def test_lexically_related_signals_bind_but_unrelated_signal_stays_out(monkeypatch):
    import brain.cognition.binding as binding

    monkeypatch.setattr(binding, "_known_entities", lambda: set())
    context = {
        "top_signals": [
            {"content": "the cat is approaching the doorway", "signal_strength": 0.7},
            {"content": "the approaching cat looks familiar", "signal_strength": 0.6},
            {"content": "disk capacity remains healthy", "signal_strength": 0.5},
        ],
    }

    composites = binding.bind_situation(context)

    assert len(composites) == 1
    assert composites[0]["source"] == "binding"
    assert composites[0]["members"] == ["signal", "signal"]
    assert "lexical" in composites[0]["referent_links"]
    assert "disk capacity" not in composites[0]["content"]


def test_unrelated_signals_do_not_bind(monkeypatch):
    import brain.cognition.binding as binding

    monkeypatch.setattr(binding, "_known_entities", lambda: set())
    context = {
        "top_signals": [
            {"content": "the cat approaches quietly", "signal_strength": 0.7},
            {"content": "disk capacity remains healthy", "signal_strength": 0.6},
        ],
    }

    assert binding.bind_situation(context) == []
    assert context["_bound_candidates"] == []


def test_event_appraisal_and_named_object_form_bound_facets(monkeypatch):
    import brain.cognition.binding as binding

    monkeypatch.setattr(binding, "_known_entities", lambda: {"cat"})
    context = {
        "affect_state": {
            "core_signals": {"warmth": 0.62},
            "recent_emotion_causes": [{
                "emotion": "warmth",
                "delta": 0.12,
                "cause": "[appraisal] the cat is approaching",
            }],
        },
        "top_signals": [{
            "content": "the cat is approaching",
            "signal_strength": 0.7,
            "routing_target": "visual_cortex",
        }],
    }

    composite = binding.bind_situation(context)[0]

    assert composite["object"] == "cat"
    assert composite["facets"]["affect"] == {"warmth": 0.62}
    assert "motion" in composite["facets"]
    assert "appraisal_cause" in composite["referent_links"]


def test_binding_is_fail_safe(monkeypatch):
    import brain.cognition.binding as binding

    monkeypatch.setattr(binding, "_collect_items", lambda _context: (_ for _ in ()).throw(RuntimeError("boom")))
    context = {"_bound_candidates": [{"content": "stale"}]}

    assert binding.bind_situation(context) == []
    assert context["_bound_candidates"] == []


def test_workspace_composite_competes_broadcasts_facets_and_is_consumed(monkeypatch):
    import brain.cognition.global_workspace as workspace

    monkeypatch.setattr(workspace, "_append_stream", lambda _moment: None)
    monkeypatch.setattr(workspace, "log_private", lambda *_args, **_kwargs: None)
    context = {
        "top_signals": [{"content": "cat motion", "signal_strength": 0.4}],
        "_bound_candidates": [{
            "source": "binding",
            "kind": "situation",
            "content": "cat: approaching — warmth",
            "salience": 0.82,
            "object": "cat",
            "facets": {"object": "cat", "motion": "approaching", "affect": {"warmth": 0.62}},
            "members": ["signal", "affect"],
            "referent_links": ["entity:cat", "appraisal_cause"],
        }],
    }

    moment = workspace.update_workspace(context)

    assert moment["source"] == "binding"
    assert moment["object"] == "cat"
    assert moment["facets"]["motion"] == "approaching"
    assert context["_bound_candidates"] == []
    assert any(candidate["source"] == "signal" for candidate in context["_workspace_candidates"])


def test_bound_workspace_routes_on_multiple_facets():
    from brain.think.think_utils.select_function import _workspace_routes_for

    routes = _workspace_routes_for({
        "source": "binding",
        "facets": {
            "object": "cat",
            "goal": "welcome the cat",
            "affect": {"warmth": 0.62},
        },
    })

    assert routes["look_outward"] == 0.9
    assert routes["attend_goal"] == 1.0
    assert routes["reflection"] == 0.8
