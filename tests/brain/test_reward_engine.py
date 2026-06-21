# RewardEngine: one RPE definition, single EMA-based expected baseline (V3 D5).
import brain.affect.reward_signals.reward_engine as re_mod
from brain.affect.reward_signals.action_reward_ema import get_expected, _DEFAULT


def test_submit_reward_uses_ema_expected(monkeypatch):
    seen = {}

    def fake_release(context, *, signal, actual, expected, effort, mode, source):
        seen.update(actual=actual, expected=expected, signal=signal, source=source)

    monkeypatch.setattr(re_mod, "release_reward", fake_release)

    ctx = {"_action_ema": {}}  # empty EMA cache → default baseline
    re_mod.submit_reward(ctx, actual=0.8, action_type="speak", source="t")

    assert seen["expected"] == _DEFAULT          # first time → default baseline
    assert seen["actual"] == 0.8
    # EMA learned toward the observed actual
    assert get_expected(ctx, "speak") != _DEFAULT


def test_repeated_rewards_drive_expected_toward_actual(monkeypatch):
    monkeypatch.setattr(re_mod, "release_reward", lambda *a, **k: None)
    ctx = {"_action_ema": {}}
    for _ in range(50):
        re_mod.submit_reward(ctx, actual=0.9, action_type="reflect")
    # After many identical actuals, expected converges near 0.9 → RPE shrinks.
    assert abs(get_expected(ctx, "reflect") - 0.9) < 0.1


def test_bad_actual_is_noop(monkeypatch):
    called = []
    monkeypatch.setattr(re_mod, "release_reward", lambda *a, **k: called.append(1))
    re_mod.submit_reward({"_action_ema": {}}, actual="not-a-number", action_type="x")
    assert called == []
