from cognition.goal_lens import action_prior, apply_goal_lens, relevance
from cognition.planning.goal_comprehension import comprehend_goal
from cognition.planning import goals


def test_comprehension_builds_checkable_long_form_model(monkeypatch):
    monkeypatch.setattr(
        "cognition.planning.goal_comprehension.llm_callable_by",
        lambda _owner: False,
    )
    goal = comprehend_goal({"id": "book-1", "title": "Write a book about emergence"})
    assert goal["definition_of_done"]
    assert goal["grounded_parts"]
    assert goal["plan"]
    assert goal["milestones"]
    assert goal["requires_artifact"] is True
    assert goal["tracked_work"] is True


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
