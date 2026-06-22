# Tests for dynamic subgoal adaptation.
#
# Primitives live in cognition/planning/goals.py; the orchestrator
# adapt_subgoals() lives in cognition/planning/pursue_goal.py. All operations
# are symbolic (no LLM) and must be progress-preserving: completed steps are
# never removed or reordered, only the pending tail is adapted.
import brain.cognition.planning.pursue_goal as pg
# adapt_subgoals was extracted to goal_adaptation.py (Phase 4D) and resolves
# _save_plan_version there, so patch that module (pg re-exports adapt_subgoals).
import brain.cognition.planning.goal_adaptation as adapt_mod
from brain.cognition.planning.goals import (
    insert_plan_step,
    skip_pending_steps,
    reprioritize_pending_steps,
    prune_satisfied_steps,
    met_milestone_tokens,
    unmet_milestone_texts,
    set_goal_plan,
    get_goal_plan,
    TERMINAL_STEP_STATUSES,
)


def _goal(steps=None, milestones=None, **extra):
    g = {"title": "Understand my reward system", "name": "Understand my reward system"}
    g.update(extra)
    if steps is not None:
        set_goal_plan(g, steps)
    if milestones is not None:
        g["milestones"] = [
            {"text": t, "met": met, "met_at": None} for (t, met) in milestones
        ]
    return g


# ── insert_plan_step ───────────────────────────────────────────────────────────

def test_insert_goes_to_head_of_pending_region():
    g = _goal(["step one alpha", "step two beta"])
    # complete the first step, then insert
    g["plan"][0]["status"] = "completed"
    inserted = insert_plan_step(g, "urgent remediation gamma", reason="blocker")
    assert inserted is not None
    statuses = [s["status"] for s in g["plan"]]
    # completed step stays first; new pending step comes right after it
    assert statuses[0] == "completed"
    assert g["plan"][1]["step"] == "urgent remediation gamma"
    assert g["plan"][1]["inserted_reason"] == "blocker"


def test_insert_dedups_pending():
    g = _goal(["research the topic thoroughly"])
    assert insert_plan_step(g, "research the topic thoroughly") is None
    assert len(g["plan"]) == 1


def test_insert_empty_is_noop():
    g = _goal(["only step here"])
    assert insert_plan_step(g, "   ") is None
    assert len(g["plan"]) == 1


# ── skip_pending_steps / progress preservation ──────────────────────────────────

def test_skip_only_touches_pending():
    g = _goal(["completed work item", "pending work item"])
    g["plan"][0]["status"] = "completed"
    n = skip_pending_steps(g, lambda s: True, reason="obsolete")
    assert n == 1
    assert g["plan"][0]["status"] == "completed"   # untouched
    assert g["plan"][1]["status"] == "skipped"
    assert g["plan"][1]["closed_reason"] == "obsolete"


# ── prune_satisfied_steps (milestone-coupled) ───────────────────────────────────

def test_prune_skips_steps_covered_by_met_milestone():
    g = _goal(
        steps=["Write summary findings to memory", "Reflect on overall progress"],
        milestones=[("summary findings written memory", True)],
    )
    pruned = prune_satisfied_steps(g, {})
    assert pruned == 1
    assert g["plan"][0]["status"] == "skipped"
    assert g["plan"][1]["status"] == "pending"   # unrelated step survives


def test_prune_noop_without_met_milestones():
    g = _goal(
        steps=["Write summary findings to memory"],
        milestones=[("summary findings written memory", False)],
    )
    assert prune_satisfied_steps(g, {}) == 0
    assert g["plan"][0]["status"] == "pending"


# ── reprioritize_pending_steps ──────────────────────────────────────────────────

def test_reprioritize_pushes_relevant_step_forward():
    g = _goal(["unrelated filler chatter", "examine reward calibration details"])
    unmet = {"reward", "calibration"}
    changed = reprioritize_pending_steps(
        g, lambda s: sum(1 for t in unmet if t in s["step"].lower())
    )
    assert changed is True
    assert "reward calibration" in g["plan"][0]["step"]


def test_reprioritize_keeps_completed_fixed():
    g = _goal(["done first item", "filler chatter here", "reward calibration work"])
    g["plan"][0]["status"] = "completed"
    unmet = {"reward", "calibration"}
    reprioritize_pending_steps(
        g, lambda s: sum(1 for t in unmet if t in s["step"].lower())
    )
    assert g["plan"][0]["status"] == "completed"   # head stays put
    assert "reward calibration" in g["plan"][1]["step"]


# ── milestone token helpers ─────────────────────────────────────────────────────

def test_milestone_token_helpers():
    g = _goal(milestones=[("first thing done", True), ("second thing pending", False)])
    assert "first" in met_milestone_tokens(g)
    assert "second" not in met_milestone_tokens(g)
    assert any("second thing" in t for t in unmet_milestone_texts(g))


# ── adapt_subgoals orchestrator ─────────────────────────────────────────────────

def _reset_cooldown():
    # _last_adapt_ts lives in goal_adaptation now (where adapt_subgoals reads it).
    adapt_mod._last_adapt_ts = 0.0


def test_adapt_noop_without_goal():
    _reset_cooldown()
    adapt_noop = pg.adapt_subgoals({})
    assert adapt_noop["skipped"] is True
    assert adapt_noop["reason"] == "no_committed_goal"


def test_adapt_respects_cooldown():
    _reset_cooldown()
    ctx = {"committed_goal": _goal(["do the thing properly"])}
    first = pg.adapt_subgoals(ctx)
    assert "skipped" not in first or not first["skipped"]
    second = pg.adapt_subgoals(ctx)   # immediately again
    assert second["skipped"] is True
    assert second["reason"] == "cooldown"


def test_adapt_prunes_and_fills(monkeypatch, tmp_path):
    _reset_cooldown()
    # Avoid touching the real goal tree on disk.
    monkeypatch.setattr(adapt_mod, "_save_plan_version", lambda *a, **k: None)
    import brain.cognition.planning.goals as goals_mod
    monkeypatch.setattr(goals_mod, "load_goals", lambda: [])
    monkeypatch.setattr(goals_mod, "save_goals", lambda *a, **k: None)

    goal = _goal(
        steps=["Reflect on overall direction"],
        milestones=[
            ("draft artifact written to memory", False),   # uncovered → gap fill
        ],
    )
    ctx = {"committed_goal": goal, "working_memory": []}
    result = pg.adapt_subgoals(ctx)
    assert result["status"] == "ok"
    # A step covering the uncovered milestone should have been appended.
    steps = [s["step"].lower() for s in get_goal_plan(goal)]
    assert any("draft artifact" in s for s in steps)


def test_adapt_inserts_blocker_step(monkeypatch):
    _reset_cooldown()
    monkeypatch.setattr(adapt_mod, "_save_plan_version", lambda *a, **k: None)
    import brain.cognition.planning.goals as goals_mod
    monkeypatch.setattr(goals_mod, "load_goals", lambda: [])
    monkeypatch.setattr(goals_mod, "save_goals", lambda *a, **k: None)

    goal = _goal(steps=["continue analysis as planned"])
    ctx = {
        "committed_goal": goal,
        "working_memory": [
            {"content": "I am blocked: the data file is missing.", "event_type": "note"},
        ],
    }
    pg.adapt_subgoals(ctx)
    steps = [s["step"].lower() for s in get_goal_plan(goal)]
    assert any(s.startswith("resolve blocker:") for s in steps)


def test_terminal_statuses_constant():
    assert "completed" in TERMINAL_STEP_STATUSES
    assert "skipped" in TERMINAL_STEP_STATUSES
