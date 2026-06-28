from brain.cognition.idle_consolidation.consolidation_cycle import set_consolidating


def test_cognitive_cost_does_not_add_resource_deficit_during_sleep():
    from brain.cognition.cognitive_cost import apply_cognitive_costs

    ctx = {
        "affect_state": {"core_signals": {}, "resource_deficit": 0.40},
        "recent_picks": ["reflect_on_affect"] * 8,
    }
    try:
        set_consolidating(True)
        apply_cognitive_costs(ctx, "reflect_on_affect", repeat_count=5)
    finally:
        set_consolidating(False)

    assert ctx["affect_state"]["resource_deficit"] == 0.40
    assert ctx["_introspection_overload"] == 8


def test_interoception_positive_latency_nudge_is_suppressed_during_sleep(monkeypatch):
    import brain.cognition.cost_prediction as cost_prediction

    calls = []
    monkeypatch.setattr(cost_prediction, "_signals_enabled", lambda: True)
    monkeypatch.setattr(cost_prediction, "predict_cost", lambda fn, context: 100.0)
    monkeypatch.setattr(cost_prediction, "record_cost", lambda fn, latency_ms: latency_ms - 100.0)
    monkeypatch.setattr(
        "brain.control_signals.arbiter.submit_signal",
        lambda context, target, delta, **kwargs: calls.append((target, delta, kwargs)),
    )

    try:
        set_consolidating(True)
        out = cost_prediction.observe("idle_consolidation_cycle", 500.0, {"affect_state": {"resource_deficit": 0.40}})
    finally:
        set_consolidating(False)

    assert out["deficit_nudge"] == 0.0
    assert calls == []
