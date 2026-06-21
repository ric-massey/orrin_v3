# Tests for surprise-driven (Pearce-Hall) adaptive learning rate on the
# per-action reward EMA (affect/reward_signals/action_reward_ema.py).
#
# Scientific behavior under test:
#   • Schultz/Dayan/Montague 1997 + Sutton 1988: expected value follows actual
#     by a TD step (RPE shrinks as a payoff becomes reliable).
#   • Pearce & Hall 1980: associability (effective learning rate) RISES with
#     recent unsigned prediction error and DECAYS when outcomes are predictable.
#   • Behrens 2007: a volatile action ends up with a higher learning rate than a
#     stable one, so it tracks change faster.
import brain.affect.reward_signals.action_reward_ema as aem


def _ctx(monkeypatch):
    # Pure: don't touch disk. Context-local caches only.
    monkeypatch.setattr(aem, "_persist", lambda v, a: None)
    return {"_action_ema": {}, "_action_assoc": {}}


def test_first_observation_seeds_without_surprise(monkeypatch):
    ctx = _ctx(monkeypatch)
    aem.update_expected(ctx, "speak", 0.8)
    assert aem.get_expected(ctx, "speak") == 0.8          # seeded at actual
    assert aem.get_associability(ctx, "speak") == aem._ASSOC_DEFAULT  # no surprise yet


def test_surprise_raises_associability_and_learning_rate(monkeypatch):
    ctx = _ctx(monkeypatch)
    aem.update_expected(ctx, "act", 0.0)         # seed low
    rate_before = aem.get_learning_rate(ctx, "act")
    aem.update_expected(ctx, "act", 1.0)         # maximal positive surprise (|error|=1.0)
    assert aem.get_associability(ctx, "act") > aem._ASSOC_DEFAULT
    assert aem.get_learning_rate(ctx, "act") > rate_before
    # learning rate stays within the configured band
    assert aem._ALPHA_MIN <= aem.get_learning_rate(ctx, "act") <= aem._ALPHA_MAX


def test_stable_outcomes_decay_associability_toward_floor(monkeypatch):
    ctx = _ctx(monkeypatch)
    aem.update_expected(ctx, "routine", 0.6)     # seed
    for _ in range(20):
        aem.update_expected(ctx, "routine", 0.6)  # perfectly predictable
    # no surprise → associability decays → learning rate approaches the floor
    assert aem.get_associability(ctx, "routine") < 0.05
    assert abs(aem.get_learning_rate(ctx, "routine") - aem._ALPHA_MIN) < 0.02
    # expected value stayed put (RPE was ~0 throughout)
    assert abs(aem.get_expected(ctx, "routine") - 0.6) < 1e-6


def test_volatile_action_learns_faster_than_stable(monkeypatch):
    ctx = _ctx(monkeypatch)
    # stable action: same reward repeatedly
    aem.update_expected(ctx, "stable", 0.5)
    for _ in range(10):
        aem.update_expected(ctx, "stable", 0.5)
    # volatile action: alternating high/low rewards
    aem.update_expected(ctx, "volatile", 0.5)
    for r in [1.0, 0.0] * 5:
        aem.update_expected(ctx, "volatile", r)

    assert aem.get_associability(ctx, "volatile") > aem.get_associability(ctx, "stable")
    assert aem.get_learning_rate(ctx, "volatile") > aem.get_learning_rate(ctx, "stable")


def test_volatile_tracks_a_new_level_faster(monkeypatch):
    # After a volatile history (high associability) the SAME surprise moves the
    # estimate more than it does after a stable history (low associability).
    ctx = _ctx(monkeypatch)

    aem.update_expected(ctx, "stable", 0.5)
    for _ in range(10):
        aem.update_expected(ctx, "stable", 0.5)

    aem.update_expected(ctx, "volatile", 0.5)
    for r in [1.0, 0.0] * 5:
        aem.update_expected(ctx, "volatile", r)

    # bring both expectations to the same point, then apply an identical shock
    ctx["_action_ema"]["stable"] = 0.5
    ctx["_action_ema"]["volatile"] = 0.5
    before_s = aem.get_expected(ctx, "stable")
    before_v = aem.get_expected(ctx, "volatile")
    aem.update_expected(ctx, "stable", 1.0)
    aem.update_expected(ctx, "volatile", 1.0)
    moved_s = aem.get_expected(ctx, "stable") - before_s
    moved_v = aem.get_expected(ctx, "volatile") - before_v
    assert moved_v > moved_s


def test_backward_compatible_defaults(monkeypatch):
    ctx = _ctx(monkeypatch)
    assert aem.get_expected(ctx, "unknown") == aem._DEFAULT
    assert aem.get_associability(ctx, "unknown") == aem._ASSOC_DEFAULT
    # non-numeric actual is ignored, never raises
    aem.update_expected(ctx, "x", "not-a-number")
    assert "x" not in ctx["_action_ema"]
