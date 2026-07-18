# R9-F7 (RUN9_DEEP_ANALYSIS_2026-07-15 Finding 5): the forced-fire harness that
# REPLACES the Run 9 ablation life. With F2's rotation live, Run 8's longest
# hold was 75 cycles → max stale 8.8 against a 250-cycle trip (28× margin), so
# F1's code path is unreachable in any life where rotation works — a staging
# run can never exercise it. This harness drives note_driver_selected with a
# single uncredited driver past the ceiling and scores the release directly.
# Gate G2 is scored on THIS test, not on a life; F1 stays as a zero-cost
# backstop.

import pytest

import brain.cognition.planning.commitment_value as cv


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(cv, "_SIGNALS_FILE", tmp_path / "commitment_signals.json",
                        raising=False)
    # The env gate is read at import; force-enable so the harness is
    # independent of the shell it runs in.
    monkeypatch.setattr(cv, "_STALE_REFRACTORY_ENABLED", True, raising=False)


def test_forced_fire_releases_uncredited_holder_exactly_once():
    holder = "aspiration-self_understanding"
    rivals = ["aspiration-output_producing", "aspiration-world_knowledge"]

    for _ in range(280):  # 30 pulls past the 250-cycle ceiling, zero credit
        cv.note_driver_selected(holder, [holder] + rivals)

    events = cv.refractory_events()
    assert len(events) == 1, "release must fire exactly once (block gates a re-fire)"
    assert events[0]["goal"] == holder
    # Fired AT the ceiling, not before and not thousands late (the Run 7
    # pathology this lever exists for: stale_cycles rode to 10,291).
    assert events[0]["stale_cycles"] == float(cv._STALE_REFRACTORY_CYCLES)

    row = cv.signals_snapshot()[holder]
    # Block armed at trip (pull 250) and paid one pull for each of the 30
    # subsequent pulls — the temporal ineligibility is really counting down.
    assert row["recommit_block_pulls"] == float(cv._RECOMMIT_BLOCK_PULLS - 30)


def test_released_holder_is_ineligible_for_the_driver_slot():
    holder = "aspiration-self_understanding"
    for _ in range(250):
        cv.note_driver_selected(holder, [holder])
    assert cv.refractory_events(), "precondition: release fired"

    goals = [
        {"id": holder, "title": holder, "tier": "long_term",
         "directional": True, "priority": "HIGH"},
        {"id": "aspiration-output_producing", "title": "produce",
         "tier": "long_term", "directional": True, "priority": "HIGH"},
    ]
    out = cv.order_committable(
        goals, tier_weight_fn=lambda t: 1, priority_rank_fn=lambda p: 1, limit=2)
    directionals = [g["id"] for g in out if g.get("directional")]
    # The blocked ex-holder yields the ONE directional slot to a rival even
    # though nothing outscores it — the absolute release, no rival required.
    assert directionals == ["aspiration-output_producing"]


def test_block_decrements_exactly_one_per_pull():
    holder = "h"
    for _ in range(250):
        cv.note_driver_selected(holder, [holder])
    start = cv.signals_snapshot()[holder]["recommit_block_pulls"]
    assert start == float(cv._RECOMMIT_BLOCK_PULLS)
    for i in range(5):
        cv.note_driver_selected("other", [holder, "other"])
        assert cv.signals_snapshot()[holder]["recommit_block_pulls"] == start - (i + 1)


def test_credited_effect_resets_the_accrual_cleanly():
    holder = "h"
    for _ in range(200):  # below the 250 ceiling
        cv.note_driver_selected(holder, [holder])
    assert cv.signals_snapshot()[holder]["stale_cycles"] == 200.0
    assert not cv.refractory_events()

    cv.note_goal_credit(holder, 0.8)  # real credited work
    assert cv.signals_snapshot()[holder]["stale_cycles"] == 0.0

    for _ in range(200):  # accrual restarts from zero — no spurious fire
        cv.note_driver_selected(holder, [holder])
    assert not cv.refractory_events()
    row = cv.signals_snapshot()[holder]
    assert float(row.get("recommit_block_pulls", 0.0) or 0.0) == 0.0
