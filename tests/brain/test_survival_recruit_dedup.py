"""T2.2 — survival recruit dedup on the deficit key + autonomic-vs-felt boundary
(brain/cognition/planning/survival_goals.py).

WS-4: the run recruited 627× but accumulated 233 DISTINCT goals because the title
carried a raw entry/file count, so each recurrence forked a new title; and pure
housekeeping (file-size/WAL/cache) was being escalated into conscious goals.
"""
from brain.cognition.planning import survival_goals as sg


def _alert(aid, desc, tags, fn="rest"):
    return {"id": aid, "description": desc, "tags": tags, "suggested_fn": fn}


def test_title_is_deficit_keyed_not_count_bearing():
    """Two recurrences of the same deficit with different counts produce the SAME
    title (keyed to the stable alert id), and no count leaks into the title."""
    a1 = _alert("long_memory_growth", "Long-memory has 12345 entries", ["memory", "maintenance"])
    a2 = _alert("long_memory_growth", "Long-memory has 67890 entries", ["memory", "maintenance"])
    g1 = sg.build_survival_goal(a1)
    g2 = sg.build_survival_goal(a2)
    assert g1["title"] == g2["title"]
    assert not any(ch.isdigit() for ch in g1["title"]), g1["title"]
    # The varying count is still preserved in the (informative) description.
    assert "12345" in g1["description"]


def test_autonomic_maintenance_never_recruits_conscious_goal():
    """A maintenance/reaper_risk alert is handled autonomically — never escalated
    into a committed survival goal."""
    ctx = {}
    for tags in (["memory", "maintenance"], ["memory", "reaper_risk"]):
        alert = _alert("working_memory_bloat", "working_memory has 9999 entries", tags,
                       fn="metacog_flush")
        assert sg.recruit_survival_goal(alert, ctx) is None
        assert sg.is_autonomic_maintenance(alert) is True
    assert ctx.get("proposed_goals", []) == []


def test_felt_resource_deficit_still_recruits():
    """A genuine felt deficit (no housekeeping tags) still recruits a survival goal."""
    alert = _alert("resource_deficit_critical", "resource_deficit is critical (0.91)",
                   ["resource_deficit", "rest", "recovery", "internal"],
                   fn="update_signal_state")
    assert sg.is_autonomic_maintenance(alert) is False
    ctx = {}
    goal = sg.recruit_survival_goal(alert, ctx)
    assert goal is not None
    assert goal["tier"] == sg.SURVIVAL_TIER
    assert goal["recruit_aid"] == "resource_deficit_critical"
    assert len(ctx["proposed_goals"]) == 1


def test_refractory_dedup_blocks_second_recruit_same_cycle():
    """The same deficit id can't be recruited twice while one is already queued."""
    alert = _alert("resource_deficit_critical", "resource_deficit is critical (0.91)",
                   ["resource_deficit", "rest"], fn="update_signal_state")
    ctx = {}
    assert sg.recruit_survival_goal(alert, ctx) is not None
    assert sg.recruit_survival_goal(alert, ctx) is None  # refractory
    assert len(ctx["proposed_goals"]) == 1
