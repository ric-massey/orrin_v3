"""F3 of the 2026-10-17 learning investigation: the signal → function map was a
recency selector. Reward floored at +0.1, other entries pruned under a count of
2 after being normalized to shares under 0.5 — so one update, even a failure,
left only the function just run, and the selector gave that singleton full
weight. Run 13 died with one function per signal. These replace
test_coupling_cap.py (the A4.2 share cap went with the count map)."""
from __future__ import annotations

import json

import pytest

from brain.control_signals import signal_learning as sl
from brain.think.think_utils.selection import scoring


@pytest.fixture
def fresh(tmp_path, monkeypatch):
    f = tmp_path / "signal_function_map.json"
    f.write_text("{}")
    monkeypatch.setattr(sl, "SIGNAL_FUNCTION_MAP_FILE", f)
    monkeypatch.setattr(scoring, "SIGNAL_FUNCTION_MAP_FILE", f)
    return f


def _map(f):
    return json.loads(f.read_text())


def test_a_failure_does_not_wipe_what_was_learned(fresh):
    # the investigation's probe: two good associations, then a failed new action
    sl.update_signal_function_map("curiosity", "historically_good", 0.8)
    sl.update_signal_function_map("curiosity", "historically_bad", 0.2)
    sl.update_signal_function_map("curiosity", "failed_action", -1.0)
    m = _map(fresh)["curiosity"]
    assert set(m) == {"historically_good", "historically_bad", "failed_action"}
    assert m["failed_action"] < m["historically_bad"] < m["historically_good"]




def test_failure_lowers_an_existing_value(fresh):
    sl.update_signal_function_map("impasse_signal", "fetch_and_read", 0.6)
    sl.update_signal_function_map("impasse_signal", "fetch_and_read", -1.0)
    assert _map(fresh)["impasse_signal"]["fetch_and_read"] < 0.6


def test_no_reward_no_learning(fresh):
    sl.update_signal_function_map("impasse_signal", "agentic_action")
    assert _map(fresh) == {}


def test_values_stay_on_the_reward_scale(fresh):
    # what A4.2 guarded against: one coupling growing without bound
    for _ in range(500):
        sl.update_signal_function_map("exploration_drive", "look_outward", 5.0)
    assert _map(fresh)["exploration_drive"]["look_outward"] <= 1.0


def test_full_map_forgets_the_worst_other_entry(fresh):
    for i in range(sl.MAX_ASSOCIATIONS_PER_EMOTION):
        sl.update_signal_function_map("motivation", f"fn{i}", i / 100)
    sl.update_signal_function_map("motivation", "newcomer", -0.5)
    m = _map(fresh)["motivation"]
    assert len(m) == sl.MAX_ASSOCIATIONS_PER_EMOTION
    assert "newcomer" in m and "fn0" not in m


def test_selector_ranks_by_value(fresh, monkeypatch):
    monkeypatch.setattr(scoring, "load_json", lambda path, default_type=dict:
                        _map(fresh) if path == fresh else {})
    monkeypatch.setattr(scoring, "_dominant_signal", lambda: "curiosity")
    sl.update_signal_function_map("curiosity", "good", 0.9)
    sl.update_signal_function_map("curiosity", "bad", -0.5)
    s = scoring._signal_pref_scores_for_dominant(["good", "bad"])
    assert s["good"] > s["bad"]


def test_a_lone_failed_association_is_not_full_weight(fresh, monkeypatch):
    monkeypatch.setattr(scoring, "load_json", lambda path, default_type=dict:
                        _map(fresh) if path == fresh else {})
    monkeypatch.setattr(scoring, "_dominant_signal", lambda: "impasse_signal")
    sl.update_signal_function_map("impasse_signal", "fetch_and_read", -0.4)
    s = scoring._signal_pref_scores_for_dominant(["fetch_and_read"])
    assert s["fetch_and_read"] == pytest.approx(0.15)
