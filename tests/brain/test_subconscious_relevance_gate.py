def test_subconscious_write_stamps_workspace_origin(monkeypatch):
    from embodiment.subconscious import SubconsciousProcessor
    from cog_memory import working_memory

    written = []
    proc = SubconsciousProcessor()
    monkeypatch.setattr(proc, "_workspace_snapshot", lambda: {
        "content": "working on allocator resize pressure",
        "source": "goal",
        "ts": 123.0,
    })
    monkeypatch.setattr(working_memory, "update_working_memory", lambda entry: written.append(entry))

    proc._write_to_wm("[Incubation] allocator pressure connects to resize", "incubated_insight")

    assert written
    assert written[0]["source"] == "subconscious"
    assert written[0]["workspace_origin"]["content"] == "working on allocator resize pressure"


def test_relevant_subconscious_entry_can_surface(monkeypatch):
    import cognition.global_workspace as gw

    monkeypatch.setattr(gw, "_append_stream", lambda moment: None)
    monkeypatch.setattr(gw, "log_private", lambda *_args, **_kwargs: None)

    context = {
        "global_workspace": {"content": "working on allocator resize pressure"},
        "working_memory": [{
            "content": "[Incubation] allocator pressure resembles the resize loop",
            "event_type": "incubated_insight",
            "source": "subconscious",
            "workspace_origin": {"content": "working on allocator resize pressure", "source": "goal"},
        }],
    }

    moment = gw.update_workspace(context)

    assert moment["source"] == "subconscious"
    assert moment["subconscious_gate"] == "relevant"
    assert moment["subconscious_relevance"] >= 0.22


def test_stale_subconscious_entry_is_soft_damped(monkeypatch):
    import cognition.global_workspace as gw

    monkeypatch.setattr(gw, "_append_stream", lambda moment: None)
    monkeypatch.setattr(gw, "log_private", lambda *_args, **_kwargs: None)

    context = {
        "committed_goal": {"title": "debug allocator resize pressure"},
        "working_memory": [{
            "content": "[Incubation] a dream image about old music keeps returning",
            "event_type": "incubated_insight",
            "source": "subconscious",
            "workspace_origin": {"content": "thinking about old music and memory", "source": "thought"},
        }],
    }

    moment = gw.update_workspace(context)

    assert moment["source"] == "goal"
    stale = next(c for c in context["_workspace_candidates"] if c["source"] == "subconscious")
    assert stale["subconscious_gate"] == "stale"
    assert stale["salience"] < 0.35
