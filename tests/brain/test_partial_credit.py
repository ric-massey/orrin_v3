"""T3.1 — partial credit on real sub-progress (WS-7 Change 4).

Aspirations used to move only on a FULL completion (the run ended 20/0/0/0). A goal
that has genuinely met some milestones, or already produced a real artifact, has
advanced its direction and should register fractional progress. The guard: partial
credit rides on the SAME satisfaction-evidence rule as closure (met milestones /
a real artifact judged by the shared T0.5 predicate) and is strictly < a completion,
so it can never become rubber-stamping.
"""
import json

import brain.cognition.intrinsic_objectives as io


_MAKE = "Make things — produce work that didn't exist before"


def _aspiration_nodes():
    return [
        {"id": f"aspiration-{d}", "title": t, "name": t, "kind": "aspiration",
         "tier": "long_term", "status": "in_progress", "driven_by": d,
         "_aspiration": True, "milestones": []}
        for t, d in io._ASPIRATIONS
    ]


def _setup(tmp_path, monkeypatch, extra_goals, completed=None):
    gf = tmp_path / "goals.json"
    cf = tmp_path / "completed.json"
    gf.write_text(json.dumps(_aspiration_nodes() + list(extra_goals)))
    cf.write_text(json.dumps(list(completed or [])))
    monkeypatch.setattr(io, "GOALS_FILE", gf)
    monkeypatch.setattr(io, "COMPLETED_GOALS_FILE", cf)
    monkeypatch.setattr(io, "_seed_drive_priors", lambda: None)  # don't touch DATA_DIR
    monkeypatch.setenv("ORRIN_LEARNED_ASPIRATION", "0")          # static prior, no credit writes
    return gf


def _node(gf, title):
    for g in json.loads(gf.read_text()):
        if g.get("title") == title:
            return g
    raise AssertionError(f"aspiration {title!r} missing")


# ── The helper itself ─────────────────────────────────────────────────────────

def test_partial_units_zero_without_evidence():
    # No met milestone, no artifact → nothing. Existing / merely-present milestones
    # earn no credit; only real evidence does.
    assert io._partial_progress_units({"milestones": [{"met": False}, {"label": "x"}]}) == 0.0
    assert io._partial_progress_units({}) == 0.0


def test_partial_units_scale_with_met_milestones_and_stay_below_a_completion():
    one_of_two = io._partial_progress_units({"milestones": [{"met": True}, {"met": False}]})
    all_met = io._partial_progress_units({"milestones": [{"met": True}, {"met": True}]})
    assert 0.0 < one_of_two < all_met < 1.0          # graded, and never a full completion
    assert all_met <= io._PARTIAL_CAP                 # capped below a completion's worth


# ── The rollup ────────────────────────────────────────────────────────────────

def test_open_goal_with_met_milestone_moves_its_aspiration(tmp_path, monkeypatch):
    gf = _setup(tmp_path, monkeypatch, [
        {"id": "g1", "title": "build a small tool", "status": "in_progress",
         "driven_by": "output_producing",
         "milestones": [{"met": True}, {"met": False}]},
    ])
    io.credit_objectives()
    make = _node(gf, _MAKE)
    assert make["partial_credit"] > 0.0       # the open goal registered
    assert make["progress"] > 0.0
    assert make["contribution_count"] == 0    # but NOT counted as a completion


def test_partial_credit_never_equals_a_completion(tmp_path, monkeypatch):
    # One open goal (all milestones met) must still be worth strictly less than one
    # actually-completed goal — the anti-rubber-stamp invariant.
    gf = _setup(
        tmp_path, monkeypatch,
        extra_goals=[{"id": "open1", "title": "open making goal",
                      "status": "in_progress", "driven_by": "output_producing",
                      "milestones": [{"met": True}, {"met": True}]}],
        completed=[{"id": "done1", "title": "finished making goal",
                    "status": "completed", "driven_by": "output_producing"}],
    )
    io.credit_objectives()
    make = _node(gf, _MAKE)
    assert make["contribution_count"] == 1            # the completion
    assert make["partial_credit"] < 1.0               # the open goal < one completion


def test_open_goal_without_evidence_does_not_move_aspiration(tmp_path, monkeypatch):
    gf = _setup(tmp_path, monkeypatch, [
        {"id": "g2", "title": "vague making goal", "status": "in_progress",
         "driven_by": "output_producing", "milestones": [{"met": False}]},
    ])
    io.credit_objectives()
    make = _node(gf, _MAKE)
    assert make.get("partial_credit", 0.0) == 0.0
    assert make["progress"] == 0.0


def test_failed_open_goal_earns_no_partial_credit(tmp_path, monkeypatch):
    gf = _setup(tmp_path, monkeypatch, [
        {"id": "g3", "title": "failed making goal", "status": "failed",
         "driven_by": "output_producing", "milestones": [{"met": True}]},
    ])
    io.credit_objectives()
    make = _node(gf, _MAKE)
    assert make.get("partial_credit", 0.0) == 0.0
