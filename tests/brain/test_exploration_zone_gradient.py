def _curious_ctx():
    return {
        "affect_state": {
            "core_signals": {
                "exploration_drive": 0.8,
                "wonder": 0.2,
                "stagnation_signal": 0.0,
            }
        }
    }


def test_zone_for_fn_splits_homeward_and_worldward():
    import cognition.exploration_value as ev

    assert ev.zone_for_fn("search_own_files") == "home"
    assert ev.zone_for_fn("look_around") == "home"
    assert ev.zone_for_fn("look_outward") == "world"
    assert ev.zone_for_fn("research_topic") == "world"
    assert ev.zone_for_fn("reflect_on_affect") == "self"


def test_worldward_reach_value_exceeds_homeward_when_other_terms_equal(monkeypatch):
    import cognition.exploration_value as ev

    monkeypatch.setattr(ev, "_decayed_satiety", lambda fn: 0.0)
    monkeypatch.setattr(ev, "_opportunity_cost", lambda fn: 0.0)

    ctx = _curious_ctx()
    world = ev.reach_value("look_outward", ctx)
    home = ev.reach_value("search_own_files", ctx)

    assert world > home > 0.0


def test_self_or_non_outward_actions_get_no_reach_value(monkeypatch):
    import cognition.exploration_value as ev

    monkeypatch.setattr(ev, "_decayed_satiety", lambda fn: 0.0)
    monkeypatch.setattr(ev, "_opportunity_cost", lambda fn: 0.0)

    assert ev.zone_gradient("reflect_on_affect", _curious_ctx()) == 0.0
    assert ev.reach_value("reflect_on_affect", _curious_ctx()) == 0.0
