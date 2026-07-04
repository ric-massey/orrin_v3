# Run 4 fix A2.3 (RUN4_FIX_PLAN_2026-07-04 §A2): the production handoff. A
# make-shaped act being dispatched with a committed make-goal must stage
# context["pending_production_action"] so production_telemetry counts a handoff.
# The 2026-07-03 run had production_handoff_count == 0 in 10k cycles.

from brain.cognition.planning.step_execution import (
    _goal_is_make_shaped, _MAKE_SHAPED_FNS,
)


def test_make_shaped_goal_recognition():
    assert _goal_is_make_shaped({"driven_by": "output_producing"})
    assert _goal_is_make_shaped({"kind": "coding"})
    assert _goal_is_make_shaped({"spec": {"synthesize": "evolution"}})
    assert not _goal_is_make_shaped({"kind": "research", "driven_by": "world_knowledge"})
    assert not _goal_is_make_shaped({})


def test_handoff_staged_on_make_dispatch(monkeypatch):
    """A make-shaped fn dispatched with a make-goal stages the handoff marker;
    production_telemetry then pops it and increments production_handoff_count."""
    import brain.cognition.planning.step_execution as se

    dispatched = {}

    def _fake_fn(context):
        # by dispatch time the marker must already be staged
        dispatched["pending"] = context.get("pending_production_action")
        return "wrote a genuine synthesis note with real novel content in it"

    fake_meta = {"function": _fake_fn}
    monkeypatch.setattr(
        "brain.registry.cognition_registry.COGNITIVE_FUNCTIONS",
        {"leave_note": fake_meta}, raising=False)

    assert "leave_note" in _MAKE_SHAPED_FNS
    ctx = {}
    goal = {"id": "g-make", "driven_by": "output_producing", "title": "Make a synthesis"}
    executed, _ = se.execute_step_action("leave_note", ctx, step_text="write the synthesis", goal=goal)
    assert executed
    assert dispatched["pending"] is not None
    assert dispatched["pending"]["goal_id"] == "g-make"


def test_no_handoff_for_non_make_goal(monkeypatch):
    import brain.cognition.planning.step_execution as se

    def _fake_fn(context):
        return "read an article about evolutionary biology and its history here"

    monkeypatch.setattr(
        "brain.registry.cognition_registry.COGNITIVE_FUNCTIONS",
        {"leave_note": {"function": _fake_fn}}, raising=False)

    ctx = {}
    goal = {"id": "g-read", "driven_by": "world_knowledge", "kind": "research"}
    se.execute_step_action("leave_note", ctx, step_text="note it", goal=goal)
    assert ctx.get("pending_production_action") is None
