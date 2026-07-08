from brain.cognition.goal_lens import action_prior, apply_goal_lens, relevance
from brain.cognition.planning.goal_comprehension import comprehend_goal, hydrate_goal_model
from brain.cognition.planning.step_execution import recognise_step_action
from brain.cognition.planning import goals


def test_comprehension_builds_checkable_long_form_model(monkeypatch):
    monkeypatch.setattr(
        "brain.cognition.planning.goal_comprehension.llm_callable_by",
        lambda _owner: False,
    )
    goal = comprehend_goal({"id": "book-1", "title": "Write a book about emergence"})
    assert goal["definition_of_done"]
    assert goal["grounded_parts"]
    assert goal["plan"]
    assert goal["milestones"]
    assert goal["requires_artifact"] is True
    assert goal["tracked_work"] is True
    assert goal["artifact_strategy"]["function"] == "compose_section"
    # F10: the plan gathers before it composes — the grounded-or-failed composer
    # needs material, so the first steps are research/fetch, then composes.
    fns = [step["action"]["function"] for step in goal["plan"]]
    assert fns[0] == "research_topic"
    assert fns[1] == "fetch_and_read"
    assert fns[2:] and all(fn == "compose_section" for fn in fns[2:])


def test_hydration_promotes_spec_and_preserves_structured_production_action(monkeypatch):
    monkeypatch.setattr(
        "brain.cognition.planning.goal_comprehension.llm_callable_by",
        lambda _owner: False,
    )
    goal = hydrate_goal_model({
        "id": "synthesis-1",
        "title": "Write a synthesis of the binding results",
        "spec": {"description": "Produce durable cumulative prose."},
    })

    assert goal["definition_of_done"]
    assert goal["spec"]["definition_of_done"] == goal["definition_of_done"]
    assert goal["tracked_work"] is True
    # F10: gather first; compose_section still present once material can exist.
    assert recognise_step_action(goal["plan"][0]) == "research_topic"
    assert any(
        (step.get("action") or {}).get("function") == "compose_section"
        for step in goal["plan"]
    )


def test_intrinsic_commitment_is_hydrated_before_it_becomes_active(monkeypatch):
    from brain.cognition import intrinsic_goals

    monkeypatch.setattr(
        "brain.cognition.planning.goal_comprehension.llm_callable_by",
        lambda _owner: False,
    )
    goal = intrinsic_goals._build_committed_goal({
        "title": "Write a synthesis about pre-workspace binding",
        "description": "Turn the findings into durable prose.",
        "driven_by": "output_producing",
        "requires_artifact": True,
    }, "g-production")

    assert goal["grounded_parts"]
    assert goal["definition_of_done"]
    assert goal["tracked_work"] is True
    # F10: the committed plan opens with material gathering, not a compose.
    assert goal["plan"][0]["action"]["function"] == "research_topic"
    assert any(
        (step.get("action") or {}).get("function") == "compose_section"
        for step in goal["plan"]
    )


def test_planned_action_recruitment_does_not_require_impasse():
    from brain.think.think_utils.select_function import _planned_action_recruitment

    boost = _planned_action_recruitment({
        "committed_goal": {"_needs_deliberate_action": "compose_section"},
        "affect_state": {"core_signals": {"impasse_signal": 0.0}},
    }, ["compose_section", "reflection"])

    assert boost["compose_section"] == 0.22


def test_production_capability_is_reachable_through_runtime_surfaces():
    from brain.agency.compose_section import compose_section
    from brain.ORRIN_loop import _verify_production_capability
    from brain.paths import COGNITIVE_FUNCTIONS_LIST_FILE
    from brain.registry.cognition_registry import persist_names

    functions = {
        "compose_section": {"function": compose_section, "is_cognition": True},
    }
    prior = (
        COGNITIVE_FUNCTIONS_LIST_FILE.read_bytes()
        if COGNITIVE_FUNCTIONS_LIST_FILE.exists()
        else None
    )
    try:
        persist_names(functions)
        result = _verify_production_capability(functions)
    finally:
        if prior is None:
            COGNITIVE_FUNCTIONS_LIST_FILE.unlink(missing_ok=True)
        else:
            COGNITIVE_FUNCTIONS_LIST_FILE.write_bytes(prior)

    assert result["reachable"] is True


def test_goal_lens_is_bounded_and_lifts_on_completion():
    context = {
        "committed_goal": {
            "id": "g1",
            "title": "Write a book about emergence",
            "status": "in_progress",
            "grounded_parts": ["thesis", "chapters", "emergence"],
            "definition_of_done": [{"criterion": "three substantive chapters"}],
            "requires_artifact": True,
            "tracked_work": True,
        }
    }
    apply_goal_lens(context)
    lens = context["goal_lens"]
    assert relevance(lens, "A chapter develops the emergence thesis") > 0
    assert action_prior(lens, "compose_section", "draft a manuscript chapter") > 0
    assert action_prior(lens, "seek_novelty", "wander randomly") < 0
    assert action_prior(lens, "compose_section", "") <= 0.36

    context["committed_goal"]["status"] = "completed"
    apply_goal_lens(context)
    assert "goal_lens" not in context


def test_llm_success_flag_cannot_close_goal_without_evidence(monkeypatch):
    goal = {
        "id": "internal-1",
        "name": "Understand a difficult pattern",
        "status": "in_progress",
        "definition_of_done": [
            {"criterion": "Record relevant evidence", "kind": "evidence", "met": False}
        ],
        "history": [],
    }
    monkeypatch.setattr(goals, "llm_callable_by", lambda _owner: True)
    monkeypatch.setattr(goals, "generate_response", lambda *_a, **_k: '{"success": true}')
    monkeypatch.setattr(goals, "llm_ok", lambda value, _owner: value)
    assert goals.try_to_accomplish(goal) is False
    assert goal["status"] == "in_progress"
