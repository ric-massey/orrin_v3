# Canonical affect observers + schema normalization (V3 D6/D9).
from affect.observers import negative_load, normalize_affect_state, core_of, NEGATIVE_SIGNALS


def test_negative_load_sums_negative_signals_nested():
    state = {"core_signals": {"impasse_signal": 0.2, "threat_level": 0.1, "motivation": 0.9}}
    # only the negative signals count; motivation is ignored
    assert abs(negative_load(state) - 0.3) < 1e-9


def test_negative_load_flat_layout():
    state = {"impasse_signal": 0.2, "conflict_signal": 0.15}
    assert abs(negative_load(state) - 0.35) < 1e-9


def test_negative_load_handles_garbage():
    assert negative_load(None) == 0.0
    assert negative_load({"core_signals": {"threat_level": "x"}}) == 0.0


def test_normalize_migrates_flat_to_nested():
    flat = {"impasse_signal": 0.3, "motivation": 0.5, "resource_deficit": 0.4}
    norm = normalize_affect_state(flat)
    assert isinstance(norm["core_signals"], dict)
    assert norm["core_signals"]["impasse_signal"] == 0.3
    assert norm["core_signals"]["motivation"] == 0.5
    # scalar stays top-level, not migrated into core
    assert "resource_deficit" not in norm["core_signals"]
    assert norm["resource_deficit"] == 0.4


def test_normalize_seeds_required_scalars():
    norm = normalize_affect_state({"core_signals": {}})
    assert "resource_deficit" in norm
    assert "affect_stability" in norm
    assert norm["_emotion_queue"] == []


def test_normalize_preserves_existing_nested():
    state = {"core_signals": {"threat_level": 0.7}, "resource_deficit": 0.2}
    norm = normalize_affect_state(state)
    assert norm["core_signals"]["threat_level"] == 0.7
    assert norm["resource_deficit"] == 0.2
