# L3 (Run 11 §7, LIFE_AMBITION_PROPOSAL_2026-07-09) — the end-goal BELIEF organ,
# proven at the mechanism: maturity gate, starved-aspiration authoring,
# checkable destination, capped bias, arrival, and the death verdict.

import time

import pytest

from brain.cognition.self_state import life_ambition as la


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(la, "_FILE", tmp_path / "life_ambition.json")
    yield


def _hold(serves="Make things that outlast the moment", theme=None, n=3,
          formed_at=None):
    amb = {
        "statement": f"Before this life ends: bring {n} pieces of work all the "
                     f"way to completion in service of \"{serves}\".",
        "serves": serves,
        "theme_terms": theme or ["entropy", "ledger"],
        "done_criteria": {"kind": "aspiration_completions", "serves": serves, "n": n},
        "confidence": 0.5, "alpha": 1.0, "beta": 1.0,
        "formed_at": formed_at if formed_at is not None else round(time.time(), 1),
        "status": "held", "revisions": [],
    }
    from brain.utils.json_utils import save_json
    save_json(la._FILE, amb)
    return amb


def test_maturity_gate_no_story_no_ambition(monkeypatch):
    monkeypatch.setattr(la, "_first_narrative_done", lambda: False)
    assert la.maybe_author({}) is None
    assert la.get_ambition() is None


def test_authoring_targets_the_starved_aspiration(monkeypatch):
    monkeypatch.setattr(la, "_first_narrative_done", lambda: True)
    monkeypatch.setattr(la, "_theme_terms", lambda limit=4: ["ledger", "entropy"])
    import brain.cognition.intrinsic_objectives as io_mod
    monkeypatch.setattr(io_mod, "objective_pressure",
                        lambda ctx=None: {"Understand my own mind": 0.1,
                                          "Make things that outlast the moment": 0.9})
    amb = la.maybe_author({"_lifetime": {"days_remaining_felt": 1.2}})
    assert amb is not None
    assert amb["serves"] == "Make things that outlast the moment", (
        "the ambition must pull AGAINST the fed aspiration (counterweight, not amplifier)")
    assert amb["done_criteria"]["n"] >= la._MIN_DONE, "a destination, not a direction"
    # Authoring is once-per-life while one is held.
    assert la.maybe_author({}) is None


def test_bias_is_small_capped_and_only_for_serving_goals():
    amb = _hold()
    serving = {"serves": amb["serves"], "title": "x", "description": ""}
    other = {"serves": "Understand my own mind", "title": "y", "description": "",
             "driven_by": "self_exploration"}
    assert 0.0 < la.ambition_bias(serving) <= 0.1, "biases, never dictates"
    assert la.ambition_bias(other) == 0.0


def test_will_goal_matching_the_theme_gets_homed():
    amb = _hold(theme=["entropy", "ledger"])
    goal = {"driven_by": "will", "title": "reduce entropy in the ledger",
            "description": "entropy ledger work"}
    la.note_completion(goal)
    assert goal.get("serves") == amb["serves"], "the will gets an address (Finding 3)"


def test_arrival_flips_status_and_seals_history(monkeypatch):
    _hold(n=2, formed_at=0.0)
    monkeypatch.setattr(la, "_completions_since", lambda serves, since: 2)
    la.note_completion({"driven_by": "curiosity", "title": "", "description": ""})
    d = la._load()
    assert d["status"] == "arrived"
    assert d["revisions"] and d["revisions"][-1]["event"] == "arrived"
    assert la.get_ambition() is None, "an arrived ambition is history; a new one may form"


def test_death_verdict_died_trying_and_seed_question(monkeypatch):
    _hold(n=5, formed_at=0.0)
    monkeypatch.setattr(la, "_completions_since", lambda serves, since: 1)
    v = la.death_verdict()
    assert v["verdict"] == "died_trying"
    assert "seed_question" in v and "died trying" in v["seed_question"]
    # No ambition ever → never_formed, and nothing to seed.
    from brain.utils.json_utils import save_json
    save_json(la._FILE, {})
    assert la.death_verdict()["verdict"] == "never_formed"


def test_prospective_clause_reads_progress(monkeypatch):
    _hold(n=4, formed_at=0.0)
    monkeypatch.setattr(la, "_completions_since", lambda serves, since: 1)
    clause = la.prospective_clause()
    assert clause.startswith("What I'm building toward:")
    assert "(1/4" in clause
