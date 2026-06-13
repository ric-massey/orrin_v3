# Invariant tests (Finding 11): affect signals must always end a cycle clamped
# to [0, 1], no matter how out-of-range the on-disk state is when a cycle
# starts. update_affect_state is the sole writer of AFFECT_STATE_FILE; this
# guards that contract against regressions in any of the many decay/ceiling/
# velocity passes it runs each cycle.
import json

import affect.update_affect_state as uas


def _seed_affect_state(path, core_overrides):
    core = dict(uas.CORE_BASELINES)
    core.update(core_overrides)
    state = {
        "core_signals": core,
        "resource_deficit": 0.15,
        "social_deficit": 0.0,
        "affect_stability": 1.0,
        "last_updated": "1970-01-01T00:00:00+00:00",
    }
    path.write_text(json.dumps(state))


def _isolate(monkeypatch, tmp_path, core_overrides):
    affect_file = tmp_path / "affect_state.json"
    wm_file = tmp_path / "working_memory.json"
    wm_file.write_text("[]")
    _seed_affect_state(affect_file, core_overrides)
    monkeypatch.setattr(uas, "AFFECT_STATE_FILE", affect_file)
    monkeypatch.setattr(uas, "WORKING_MEMORY_FILE", wm_file)
    return affect_file


def test_clamps_signals_blown_far_above_one(monkeypatch, tmp_path):
    overrides = {k: 999.0 for k in uas.CORE_BASELINES}
    affect_file = _isolate(monkeypatch, tmp_path, overrides)

    uas.update_affect_state(context=None)

    saved = json.loads(affect_file.read_text())
    core = saved["core_signals"]
    for name, val in core.items():
        assert isinstance(val, (int, float)), f"{name}={val!r} is not numeric"
        assert 0.0 <= val <= 1.0, f"{name}={val} outside [0,1] after update"


def test_clamps_signals_blown_far_below_zero(monkeypatch, tmp_path):
    overrides = {k: -50.0 for k in uas.CORE_BASELINES}
    affect_file = _isolate(monkeypatch, tmp_path, overrides)

    uas.update_affect_state(context=None)

    saved = json.loads(affect_file.read_text())
    core = saved["core_signals"]
    for name, val in core.items():
        assert isinstance(val, (int, float)), f"{name}={val!r} is not numeric"
        assert 0.0 <= val <= 1.0, f"{name}={val} outside [0,1] after update"


def test_resource_and_social_deficit_clamped(monkeypatch, tmp_path):
    affect_file = _isolate(monkeypatch, tmp_path, {})
    raw = json.loads(affect_file.read_text())
    raw["resource_deficit"] = 17.0
    raw["social_deficit"] = -3.0
    affect_file.write_text(json.dumps(raw))

    uas.update_affect_state(context=None)

    saved = json.loads(affect_file.read_text())
    assert 0.0 <= saved["resource_deficit"] <= 1.0
    assert 0.0 <= saved["social_deficit"] <= 1.0


def test_repeated_cycles_stay_clamped(monkeypatch, tmp_path):
    # Run several consecutive cycles from an extreme start to make sure no
    # later pass (velocity budget, hedonic drift, dup-key sync, ...) can ever
    # push a signal back outside [0,1] once _prev_core is populated.
    overrides = {k: 999.0 for k in uas.CORE_BASELINES}
    affect_file = _isolate(monkeypatch, tmp_path, overrides)

    for _ in range(5):
        uas.update_affect_state(context=None)

    saved = json.loads(affect_file.read_text())
    core = saved["core_signals"]
    for name, val in core.items():
        assert 0.0 <= val <= 1.0, f"{name}={val} outside [0,1] after repeated cycles"
