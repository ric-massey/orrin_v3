# P0/P8 contract: the external-effect ledger is the denominator the reward
# function was missing. These lock in the anti-gaming invariants
# (ORRIN_PRODUCTION_REWARD_PLAN §3 P0 + P8): a repeat earns nothing, boilerplate
# earns nothing, and only a novel+structural effect gates a production goal.
import pytest

from agency import effect_ledger as el

_LONG = ("I worked out that emergence is the way large-scale order and patterns "
         "arise from many small local interactions that individually know nothing "
         "of the whole — and that this matters for how a mind can be more than its "
         "neurons.")


@pytest.fixture(autouse=True)
def _isolate(tmp_path):
    el.EFFECT_LEDGER_FILE = tmp_path / "effect_ledger.jsonl"
    el.reset_for_tests()
    yield
    el.reset_for_tests()


def test_novel_effect_is_credited():
    row = el.record_effect("note_novel", _LONG, goal_id="g1")
    assert row is not None
    assert row.novelty > 0.0
    assert row.significance > 0.0
    assert not row.dedupe


def test_exact_duplicate_earns_nothing():
    assert el.record_effect("note_novel", _LONG, goal_id="g1") is not None
    # byte-identical repeat — the 100-identical-notes case — collapses to no credit.
    assert el.record_effect("note_novel", _LONG, goal_id="g1") is None


def test_boilerplate_and_short_earn_nothing():
    assert el.record_effect("note_novel", "i feel a bit tired today", goal_id="g2") is None
    assert el.record_effect("note_novel", "TODO: placeholder note", goal_id="g2") is None
    assert not el.has_qualifying_effect("g2")


def test_artifact_gate_tracks_goal():
    assert not el.has_qualifying_effect("g3")
    el.record_effect("note_novel", _LONG, goal_id="g3")
    assert el.has_qualifying_effect("g3")


def test_unknown_kind_is_ignored():
    assert el.record_effect("not_a_real_kind", _LONG, goal_id="g4") is None
    assert not el.has_qualifying_effect("g4")


def test_unparseable_code_has_zero_significance():
    # novel but structurally junk → no production credit (P8 structural gate).
    row = el.record_effect("code_committed", "def broken(:\n  return " + ("x " * 60), goal_id="g5")
    # either rejected outright or recorded with zero significance — never a free win
    assert row is None or row.significance == 0.0
