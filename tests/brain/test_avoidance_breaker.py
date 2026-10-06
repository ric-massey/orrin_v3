# 1D.4 (Run 12) — realign the avoidance breaker. Built and wired since the
# audit era, it had fired ZERO times ever: the severe branch demanded one
# substitute function with ≥3 of the last 8 picks — a monopoly-era shape.
# Post-Run-8 rotation keeps picks diverse, so the avoidance the audit watched
# live (debt climbing 33→72) was spread across the window and the threshold
# was unreachable. Locked in here: (a) ≥2/8 substitution now fires at severe
# debt; (b) fully-diverse substitution is broken at deep debt; (c) the per-life
# max-debt streak and firing count are persisted for the run analysis.

import json

import pytest

from brain.cognition import metacog_analyze as ma
from brain.cognition import action_accounting


def _ctx(picks, debt, cycle=100):
    return {
        "recent_picks": list(picks),
        "action_debt": debt,
        "committed_goal": {"title": "understand symbolic rules", "id": "g1"},
        "cycle_count": {"count": cycle},
        "affect_state": {"core_signals": {}},
    }


@pytest.fixture(autouse=True)
def _no_goal_action(monkeypatch):
    monkeypatch.setattr(action_accounting, "cycle_produced_goal_action",
                        lambda ctx: False)
    # Determinism: never miss a real pattern, never add a vague impression.
    monkeypatch.setattr(ma.random, "random", lambda: 0.99)
    yield


def _stats():
    if not ma._AVOIDANCE_STATS_FILE.exists():
        return {}
    return json.loads(ma._AVOIDANCE_STATS_FILE.read_text(encoding="utf-8"))


def _reset_stats():
    if ma._AVOIDANCE_STATS_FILE.exists():
        ma._AVOIDANCE_STATS_FILE.unlink()


def test_deep_debt_breaks_fully_diverse_substitution():
    _reset_stats()
    # Eight DISTINCT substitutes — the exact rotation shape the audit watched
    # while the old breaker stayed silent at debt 33→72.
    picks = ["reflection", "associative_recall", "narrative_update", "self_review",
             "detect_tensions", "reflect_on_outcomes", "introspective_planning",
             "consolidate_from_long_memory"]
    ctx = _ctx(picks, debt=30)
    obs = ma.metacog_analyze(ctx)
    assert any("Goal avoidance" in o for o in obs)
    assert ctx.get("_fn_suppression"), "deep-debt diverse substitution did not fire the breaker"
    stats = _stats()
    assert stats.get("breaker_fires", 0) >= 1
    assert stats.get("max_debt_streak", 0) >= 30
    assert stats.get("suppressed")


def test_severe_debt_fires_on_two_of_eight_substitution():
    _reset_stats()
    picks = ["reflection", "associative_recall", "reflection", "self_review",
             "detect_tensions", "reflect_on_outcomes", "introspective_planning",
             "narrative_update"]   # 'reflection' ×2 — below the old ≥3 bar
    ctx = _ctx(picks, debt=12)
    ma.metacog_analyze(ctx)
    assert "reflection" in (ctx.get("_fn_suppression") or {}), \
        "2/8 substitution at severe debt did not fire"
    assert _stats().get("breaker_fires", 0) >= 1


def test_moderate_debt_observes_but_does_not_suppress():
    _reset_stats()
    picks = ["reflection", "associative_recall", "narrative_update", "self_review",
             "detect_tensions", "reflect_on_outcomes", "introspective_planning",
             "consolidate_from_long_memory"]
    ctx = _ctx(picks, debt=5)   # above warn (4), below severe (12)
    obs = ma.metacog_analyze(ctx)
    assert any("Goal avoidance" in o for o in obs)
    assert not ctx.get("_fn_suppression")
    # The streak is still reported even when the breaker holds fire.
    assert _stats().get("max_debt_streak", 0) >= 5
    assert _stats().get("breaker_fires", 0) == 0


def test_max_debt_streak_ratchets_up_only():
    _reset_stats()
    picks = ["reflection"] * 8
    ma.metacog_analyze(_ctx(picks, debt=40))
    ma.metacog_analyze(_ctx(picks, debt=6))
    assert _stats().get("max_debt_streak", 0) >= 40


def test_goal_service_functions_are_never_muted_as_substitutes():
    # Run 13 item 6: Run 12 muted research_topic 2,102x as "avoidance" while it was
    # the committed research goal's own work. Goal instruments that loop without
    # producing are a stalled goal (Fix 7's stall path), not a substitute.
    _reset_stats()
    picks = ["research_topic", "fetch_and_read", "research_topic", "wikipedia_search",
             "research_topic", "fetch_and_read", "assess_goal_progress", "research_topic"]
    ctx = _ctx(picks, debt=40)
    ma.metacog_analyze(ctx)
    muted = set(ctx.get("_fn_suppression") or {})
    assert not (muted & ma._GOAL_DRIVEN_FNS), f"goal instruments muted: {muted}"


def test_real_substitute_still_muted_beside_goal_work():
    _reset_stats()
    picks = ["research_topic", "narrative_update", "fetch_and_read", "narrative_update",
             "research_topic", "narrative_update", "research_topic", "fetch_and_read"]
    ctx = _ctx(picks, debt=20)
    ma.metacog_analyze(ctx)
    assert "narrative_update" in (ctx.get("_fn_suppression") or {})
