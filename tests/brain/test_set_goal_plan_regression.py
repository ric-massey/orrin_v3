# Regression: UnboundLocalError on set_goal_plan (BEHAVIOR_FIX_PLAN Phase 5).
#
# pursue_goal.py once had a code path that referenced set_goal_plan before a
# (shadowing) local binding was assigned, raising UnboundLocalError at runtime
# (error_log 2026-06-06). The top-level import is now the only binding — these
# tests exercise the call paths that hit set_goal_plan and assert no shadowing
# has crept back in.
import ast
from pathlib import Path

import brain.cognition.planning.pursue_goal as pg
from brain.cognition.planning.goals import set_goal_plan, insert_plan_step


def test_no_local_shadowing_of_set_goal_plan():
    """Static check: no function-local assignment/import of set_goal_plan."""
    src = Path(pg.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    offenders = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "set_goal_plan":
                    offenders.append(node.lineno)
        elif isinstance(node, ast.ImportFrom) and node.col_offset > 0:
            # an indented (function-local) import creates a local binding that
            # shadows the module-level name for the whole function body
            if any((a.asname or a.name) == "set_goal_plan" for a in node.names):
                offenders.append(node.lineno)
    assert not offenders, f"set_goal_plan locally bound at lines {offenders}"


def test_redirect_goal_plan_does_not_raise(monkeypatch):
    """Dynamic check: the re-plan path runs set_goal_plan without UnboundLocalError."""
    import brain.cognition.planning.goal_arbiter as ga
    monkeypatch.setattr(ga, "apply", lambda fn, source="": None)
    import brain.cog_memory.working_memory as wm
    monkeypatch.setattr(wm, "update_working_memory", lambda *a, **k: None)

    ctx = {"committed_goal": {"title": "Understand the world more deeply",
                              "name": "Understand the world more deeply"}}
    out = pg.redirect_goal_plan(ctx)
    assert "Re-planned" in out
    plan = ctx["committed_goal"]["plan"]
    assert plan and all(s["status"] == "pending" for s in plan)


def test_set_goal_plan_dedupes_and_bans_placeholders():
    goal = {"title": "t"}
    set_goal_plan(goal, [
        "Research the topic thoroughly",
        "research the topic thoroughly",   # normalized duplicate
        "do the thing",                    # placeholder
        "Write what I found to long memory",
    ])
    steps = [s["step"] for s in goal["plan"]]
    assert steps == ["Research the topic thoroughly", "Write what I found to long memory"]

    # Appending a step that exists in ANY status is refused
    goal["plan"][0]["status"] = "completed"
    assert insert_plan_step(goal, "Research the topic thoroughly") is None
    assert insert_plan_step(goal, "reflect") is None  # placeholder
    assert insert_plan_step(goal, "Check the sources for accuracy") is not None
