"""T2.3 — aspiration coverage floor + credit-by-intent (WS-7 Changes 2, 3).

End-of-life coverage was 20%/0%/0%/0% — three aspirations never moved off zero,
and making/contact goals with generic text were mis-credited. These pin the two
fixes: credit blends the goal's own intent (driven_by→serves), and the generation
coverage floor deterministically serves a starved aspiration when it can.
"""
from brain.cognition import intrinsic_objectives as io
from brain.cognition import intrinsic_generators as ig


_MAKE = "Make things — produce work that didn't exist before"
_WORLD = "Understand the world more deeply"


# ── Change 3: credit by intent ────────────────────────────────────────────────

def test_generic_making_goal_credited_by_intent(monkeypatch):
    """A making goal whose title trips no outcome keyword is still credited to its
    aspiration via its driven_by intent (not defaulted to world-knowledge)."""
    monkeypatch.setattr(io, "_serves_aspiration", lambda d: _MAKE if d == "output_producing" else "")
    goal = {"title": "ship the daily thing", "driven_by": "output_producing"}
    assert io._evidenced_aspiration(goal) == _MAKE


def test_strong_keyword_evidence_still_overrides_intent(monkeypatch):
    """Real outcome evidence (≥2 keyword hits) legitimately diverges from the
    intent prior — the learned link's whole point is preserved."""
    monkeypatch.setattr(io, "_serves_aspiration", lambda d: _MAKE if d == "output_producing" else "")
    goal = {"title": "research the history and science of birds",  # world: research, history, science
            "driven_by": "output_producing"}
    assert io._evidenced_aspiration(goal) == _WORLD


def test_no_intent_no_keywords_returns_none(monkeypatch):
    monkeypatch.setattr(io, "_serves_aspiration", lambda d: "")
    assert io._evidenced_aspiration({"title": "xyzzy", "driven_by": ""}) is None


# ── Change 2: generation coverage floor ───────────────────────────────────────

def test_coverage_floor_picks_starved_aspiration(monkeypatch):
    """When an aspiration is starved (pressure ≥ floor) and the pool has a
    candidate serving it, that candidate is chosen deterministically."""
    pool = [
        {"title": "understand emergence", "driven_by": "world_knowledge"},
        {"title": "build a small tool", "driven_by": "output_producing"},
    ]
    # Force the generators to yield exactly this pool, and make output_producing starved.
    monkeypatch.setattr(ig, "_goal_from_recent_research", lambda lm: None)
    monkeypatch.setattr(ig, "_concept_deepening_goals", lambda *a, **k: [pool[0]])
    monkeypatch.setattr(ig, "_open_question_goals", lambda *a, **k: [])
    monkeypatch.setattr(ig, "_causal_frontier_goals", lambda *a, **k: [])
    monkeypatch.setattr(ig, "_tension_goals", lambda *a, **k: [])
    monkeypatch.setattr(ig, "_autobiographical_continuity_goals", lambda *a, **k: [])
    monkeypatch.setattr(ig, "_making_goals", lambda *a, **k: [pool[1]])
    monkeypatch.setattr(ig, "_contact_goals", lambda *a, **k: [])
    monkeypatch.setattr(ig, "_active_goal_titles", lambda: set())
    monkeypatch.setattr(ig, "_acceptable_goal_subject", lambda t: True)
    monkeypatch.setattr(ig, "objective_pressure", lambda ctx: {_MAKE: 0.9, _WORLD: 0.1})
    monkeypatch.setattr(ig, "_serves_aspiration",
                        lambda d: _MAKE if d == "output_producing" else _WORLD)

    for _ in range(8):  # deterministic: always the starved-aspiration candidate
        picked = ig._varied_symbolic_goal({}, [])
        assert picked["driven_by"] == "output_producing"


def test_no_floor_when_nothing_starved(monkeypatch):
    """With all pressure below the floor, the floor doesn't fire (weighted draw)."""
    pool = [{"title": "a", "driven_by": "world_knowledge"}]
    monkeypatch.setattr(ig, "_goal_from_recent_research", lambda lm: None)
    monkeypatch.setattr(ig, "_concept_deepening_goals", lambda *a, **k: [pool[0]])
    for fn in ("_open_question_goals", "_causal_frontier_goals", "_tension_goals",
               "_autobiographical_continuity_goals", "_making_goals", "_contact_goals"):
        monkeypatch.setattr(ig, fn, lambda *a, **k: [])
    monkeypatch.setattr(ig, "_active_goal_titles", lambda: set())
    monkeypatch.setattr(ig, "_acceptable_goal_subject", lambda t: True)
    monkeypatch.setattr(ig, "objective_pressure", lambda ctx: {_WORLD: 0.1})
    monkeypatch.setattr(ig, "_serves_aspiration", lambda d: _WORLD)
    picked = ig._varied_symbolic_goal({}, [])
    assert picked["driven_by"] == "world_knowledge"
