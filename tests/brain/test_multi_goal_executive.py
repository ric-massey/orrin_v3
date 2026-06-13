# Multi-goal pursuit (docs/multi_goal_pursuit.md Option A + B):
# the Executive advances ALL queued goals per tick under a tier-weighted step
# budget, instead of one rotating goal per tick — while the deliberate
# conscious focus stays singular and is restored after the tick.
from typing import Any, Dict

import cognition.planning.executive as ex


def _goal(gid: str, tier: str = "growth", steps: int = 2) -> Dict[str, Any]:
    return {
        "id": gid,
        "title": f"goal {gid}",
        "status": "in_progress",
        "tier": tier,
        "plan": [{"step": f"{gid} step {i}", "status": "pending"} for i in range(steps)],
    }


# ── _allocate_steps (Option B weighting) ──────────────────────────────────────

def test_default_budget_gives_every_goal_one_step():
    q = [_goal("a", "core"), _goal("b", "minor"), _goal("c", "growth")]
    alloc = ex._allocate_steps(q, rr=0, budget=3)
    assert sorted((g["id"], n) for g, n in alloc) == [("a", 1), ("b", 1), ("c", 1)]


def test_extra_budget_goes_to_higher_tiers_first():
    q = [_goal("a", "core"), _goal("b", "minor"), _goal("c", "growth")]
    alloc = {g["id"]: n for g, n in ex._allocate_steps(q, rr=0, budget=5)}
    assert alloc["a"] == 2 and alloc["c"] == 2 and alloc["b"] == 1


def test_budget_capped_at_tier_weights():
    q = [_goal("a", "core"), _goal("b", "minor")]
    alloc = {g["id"]: n for g, n in ex._allocate_steps(q, rr=0, budget=99)}
    assert alloc == {"a": 3, "b": 1}  # core weight 3, minor weight 1


def test_scarce_budget_prefers_higher_tier():
    q = [_goal("a", "minor"), _goal("b", "core")]
    alloc = ex._allocate_steps(q, rr=0, budget=1)
    assert [(g["id"], n) for g, n in alloc] == [("b", 1)]


def test_rotation_breaks_ties_between_equal_tiers():
    q = [_goal("a", "minor"), _goal("b", "minor"), _goal("c", "minor")]
    first = [g["id"] for g, _ in ex._allocate_steps(q, rr=0, budget=1)]
    second = [g["id"] for g, _ in ex._allocate_steps(q, rr=1, budget=1)]
    assert first != second  # a different goal gets the scarce step next tick


# ── executive_tick (Option A: all K advance in ONE tick) ─────────────────────

def _run_tick(monkeypatch, goals, primary=None, pursue=None):
    pursued: list = []

    def _fake_pursue(context):
        goal = context.get("committed_goal") or {}
        pursued.append(goal.get("id"))
        if pursue is not None:
            return pursue(goal, context)
        # advance the first pending step like the real runner would
        for st in goal.get("plan") or []:
            if st.get("status") != "completed":
                st["status"] = "completed"
                break
        return {"status": "ok", "next_step": "x", "goal": goal.get("title")}

    import cognition.planning.pursue_goal as pg
    monkeypatch.setattr(pg, "pursue_committed_goal", _fake_pursue)
    monkeypatch.setattr(ex, "recognise_step_action", lambda s: "search_own_files" if s else None)
    monkeypatch.setattr(ex, "_record_history", lambda *a, **k: None)
    monkeypatch.setattr(ex, "_emit_fn_executed", lambda *a, **k: None)

    ctx: Dict[str, Any] = {
        "committed_goals": goals,
        "committed_goal": primary if primary is not None else (goals[0] if goals else None),
        "cycle_count": {"count": 1},
    }
    summary = ex.executive_tick(ctx)
    return ctx, summary, pursued


def test_all_queued_goals_advance_in_one_tick(monkeypatch):
    goals = [_goal("a", "core"), _goal("b", "minor"), _goal("c", "growth")]
    ctx, summary, pursued = _run_tick(monkeypatch, goals)
    assert set(pursued) == {"a", "b", "c"}          # Option A: everyone moved
    assert len(summary["advanced"]) == 3
    assert summary["active_fn"] == "search_own_files"


def test_deliberate_focus_restored_after_tick(monkeypatch):
    goals = [_goal("a"), _goal("b"), _goal("c")]
    primary = goals[0]
    ctx, _, _ = _run_tick(monkeypatch, goals, primary=primary)
    assert ctx["committed_goal"] is primary          # one conscious focus (I2)


def test_blocked_goal_does_not_burn_extra_budget(monkeypatch):
    goals = [_goal("a", "core", steps=3)]
    monkeypatch.setattr(ex, "_EXEC_STEP_BUDGET", 3)

    calls = {"n": 0}

    def _blocked(goal, context):
        calls["n"] += 1
        return {"status": "retry", "goal": goal.get("title"), "attempt": calls["n"]}

    _, summary, pursued = _run_tick(monkeypatch, goals, pursue=_blocked)
    assert calls["n"] == 1                           # no same-tick retry on a wall
    assert summary["advanced"][0]["status"] == "retry"


def test_idle_queue_is_a_noop(monkeypatch):
    ctx, summary, pursued = _run_tick(monkeypatch, [])
    assert pursued == []
    assert summary["queue"] == []


def test_outcome_reward_mapping():
    assert ex._outcome_reward({"status": "retry"}) == 0.05
    assert ex._outcome_reward({"status": "error"}) == 0.05
    assert ex._outcome_reward({"status": "ok", "skipped": True}) == 0.2
    assert ex._outcome_reward({"status": "ok"}) == 0.6
    assert ex._outcome_reward("plain string result") == 0.6
