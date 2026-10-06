"""Run 13 item 11 (DEMO_RUN_2026-08-19 §2): every aspiration's commitment value_ema
sat at its 0.5 prior all life while concrete goals learned (0.56–0.73). Credit
landed on the concrete goal's id and never reached the aspiration that held the
commitment slot ~98 % of cycles."""
from brain.cognition.planning import commitment_value as cv
from brain.paths import GOALS_FILE
from brain.utils.json_utils import load_json, save_json


def _value(gid):
    d = load_json(cv._SIGNALS_FILE, default_type=dict) or {}
    return float(((d.get("goals") or {}).get(gid) or {}).get("value_ema", 0.5))


def test_credit_on_child_goal_lifts_its_aspiration():
    save_json(GOALS_FILE, [
        {"id": "aspiration-world_knowledge", "title": "Understand the world more deeply",
         "kind": "aspiration", "driven_by": "world_knowledge", "subgoals": []},
        {"id": "g_child", "title": "Understand entropy more deeply", "kind": "research",
         "driven_by": "world_knowledge", "serves": "Understand the world more deeply"},
    ])
    before = _value("aspiration-world_knowledge")
    cv.note_goal_credit("g_child", 0.8, alignment=1.0, content_hash="h1")
    assert _value("g_child") > 0.5
    assert _value("aspiration-world_knowledge") > before


def test_unknown_goal_credits_only_itself():
    save_json(GOALS_FILE, [])
    cv.note_goal_credit("g_orphan", 0.8, alignment=1.0, content_hash="h2")
    assert _value("g_orphan") > 0.5
