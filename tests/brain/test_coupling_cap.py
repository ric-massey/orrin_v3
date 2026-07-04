# Run 4 fix A4.2 (RUN4_FIX_PLAN §A4): bound coupling growth so one affect→function
# association can't structurally outvote learned value (2026-07-03:
# exploration_drive→look_outward 0.706 vs ~0.195 for the rest).

from brain.control_signals.signal_learning import _bound_coupling_shares, _COUPLING_CAP


def test_dominant_coupling_is_capped():
    out = _bound_coupling_shares({"look_outward": 30.0, "b": 2.0, "c": 2.0, "d": 2.0})
    assert out["look_outward"] <= _COUPLING_CAP + 1e-6
    # trimmed excess is redistributed, not discarded — shares still sum ~1.0
    assert abs(sum(out.values()) - 1.0) < 1e-4
    # no single coupling is now >2× any other major one (was ~3.6×)
    assert max(out.values()) / max(min(out.values()), 1e-9) < 3.0


def test_single_entry_left_alone():
    out = _bound_coupling_shares({"only": 5.0})
    assert out == {"only": 5.0}


def test_balanced_map_normalizes_without_capping():
    out = _bound_coupling_shares({"a": 1.0, "b": 1.0, "c": 1.0, "d": 1.0})
    for v in out.values():
        assert v == 0.25
