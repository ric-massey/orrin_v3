# Invariant test (Finding 11): the homeostasis-weighted cost of the deltas
# commit_affect actually applies must never exceed STABILITY_BUDGET, no matter
# how many proposals (across how many signals, in either direction) were
# submitted in a cycle. test_affect_arbiter.py covers specific worked
# examples; this fuzzes the proposal mix and recomputes the same weighted-cost
# formula commit_affect uses internally.
import random

from brain.control_signals.arbiter import (
    commit_affect,
    submit_affect,
    STABILITY_BUDGET,
    _AWAY_COST_MULTIPLIER,
)
from brain.control_signals.setpoints import setpoint

SIGNALS = ["threat_level", "motivation", "uncertainty", "reward_positive", "impasse_signal"]


def _ctx(core):
    return {"affect_state": {"core_signals": dict(core)}}


def _weighted_cost(applied, core):
    total = 0.0
    for t, d in applied.items():
        cur = float(core.get(t, setpoint(t)))
        sp = setpoint(t)
        moving_away = (d > 0 and cur >= sp) or (d < 0 and cur <= sp)
        total += abs(d) * (_AWAY_COST_MULTIPLIER if moving_away else 1.0)
    return total


def test_stability_budget_never_exceeded_random_proposals():
    random.seed(1234)
    for _trial in range(50):
        core = {s: round(random.uniform(0.0, 1.0), 3) for s in SIGNALS}
        ctx = _ctx(core)
        for _ in range(random.randint(1, 30)):
            target = random.choice(SIGNALS)
            delta = random.uniform(-0.3, 0.3)
            weight = random.uniform(0.1, 2.0)
            submit_affect(ctx, target, delta, weight=weight, source="random")

        applied = commit_affect(ctx)
        cost = _weighted_cost(applied, core)
        assert cost <= STABILITY_BUDGET + 1e-3, f"trial {_trial}: cost {cost} > budget {STABILITY_BUDGET}"


def test_stability_budget_never_exceeded_single_signal_flood():
    random.seed(99)
    for _trial in range(20):
        core = {s: round(random.uniform(0.0, 1.0), 3) for s in SIGNALS}
        target = random.choice(SIGNALS)
        ctx = _ctx(core)
        sign = random.choice([-1, 1])
        for _ in range(random.randint(5, 40)):
            submit_affect(ctx, target, sign * random.uniform(0.05, 0.2),
                          weight=random.uniform(0.5, 3.0), source="flood")

        applied = commit_affect(ctx)
        cost = _weighted_cost(applied, core)
        assert cost <= STABILITY_BUDGET + 1e-3, f"trial {_trial}: cost {cost} > budget {STABILITY_BUDGET}"
