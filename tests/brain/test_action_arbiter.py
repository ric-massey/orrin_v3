# Tests for the ActionArbiter convergence layer (think/action_arbiter.py).
from think.action_arbiter import ActionProposal as P, resolve


def test_no_proposals_returns_none():
    winner, info = resolve([])
    assert winner is None
    assert info["reason"] == "no_proposals"


def test_plan_wins_when_alone():
    props = [P("pursue_goal", 1.0, 1.0, source="bandit"),
             P("reflect", 0.3, 1.0, source="bandit")]
    winner, _ = resolve(props, incumbent=None)
    assert winner == "pursue_goal"


def test_acute_threat_dominates():
    props = [P("pursue_goal", 1.0, 1.0, source="bandit"),
             P("speak", 0.9, 1.2, urgency=0.9, source="threat")]
    winner, info = resolve(props, incumbent="pursue_goal")
    assert winner == "speak"
    assert info["reason"] == "vote"


def test_moderate_threat_loses_on_merit():
    # spike 0.5: speak = 0.5*1.2 + 0.5*0.5 = 0.85 < plan 1.0
    props = [P("pursue_goal", 1.0, 1.0, source="bandit"),
             P("speak", 0.5, 1.2, urgency=0.5, source="threat")]
    winner, _ = resolve(props, incumbent="pursue_goal", margin=0.10)
    assert winner == "pursue_goal"


def test_hysteresis_keeps_incumbent_within_margin():
    # Challenger beats incumbent but by less than the margin → incumbent holds.
    props = [P("a", 1.05, 1.0, source="x"),   # challenger
             P("b", 1.00, 1.0, source="y")]   # incumbent
    winner, info = resolve(props, incumbent="b", margin=0.10)
    assert winner == "b"
    assert info["hysteresis"] is True


def test_hysteresis_yields_when_beaten_by_margin():
    props = [P("a", 1.30, 1.0, source="x"),
             P("b", 1.00, 1.0, source="y")]
    winner, info = resolve(props, incumbent="b", margin=0.10)
    assert winner == "a"
    assert info["hysteresis"] is False


def test_veto_wins_outright():
    props = [P("pursue_goal", 1.0, 5.0, source="bandit"),
             P("refuse", 0.1, 1.0, veto=True, source="boundary")]
    winner, info = resolve(props, incumbent="pursue_goal")
    assert winner == "refuse"
    assert info["reason"] == "veto"


def test_votes_for_same_name_accumulate():
    props = [P("x", 0.4, 1.0, source="a"),
             P("x", 0.4, 1.0, source="b"),
             P("y", 0.7, 1.0, source="c")]
    winner, _ = resolve(props)
    assert winner == "x"  # 0.8 > 0.7
