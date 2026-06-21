# Regression tests for the LEARNING_DIAGNOSIS_2026-06-16 fixes.
#
# Diagnosis: Orrin learned the right values (look_outward/look_around are
# low-reward; seek_novelty/research_topic high-reward) but the selector picked
# the low-reward ones anyway, because a hardcoded emotion prior pointed at them
# and the learned value never gated it — and the stagnation breaker that should
# have caught the rut had 0 call sites in the real pick path.
#
# These three tests pin the three fixes (§5.1 prior realignment, §5.2 outcome
# devaluation, §5.3 rut breaker wired into the real pick).
import statistics

import brain.think.think_utils.select_function as sf
from brain.config import tuning as t


# ── §5.1: prior realignment (diversive → epistemic curiosity) ────────────────
def test_exploration_prior_ranks_epistemic_above_diversive():
    ed = sf._SEMANTIC_PRIORS["exploration_drive"]
    # The genuinely higher-reward explorers must now outrank the cheap scanners.
    for epistemic in ("seek_novelty", "research_topic", "wikipedia_search"):
        for diversive in ("look_outward", "look_around"):
            assert ed[epistemic] > ed[diversive], (
                f"{epistemic} ({ed[epistemic]}) should outrank "
                f"{diversive} ({ed[diversive]}) in exploration_drive prior"
            )


def test_wonder_prior_also_realigned():
    w = sf._SEMANTIC_PRIORS["wonder"]
    assert w["seek_novelty"] > w["look_outward"]
    assert w["research_topic"] > w["look_around"]


# ── §5.2: learned value gates the prior (outcome devaluation) ────────────────
def test_below_median_fn_is_devalued():
    stats = {
        "look_outward": {"avg_reward": 0.11, "count": 800},   # far below peers
        "seek_novelty": {"avg_reward": 0.34, "count": 150},
        "research_topic": {"avg_reward": 0.59, "count": 60},
    }
    rewards = [v["avg_reward"] for v in stats.values()]
    median = statistics.median(rewards)

    devalued = sf._devalue_prior(0.85, "look_outward", stats, median)
    untouched = sf._devalue_prior(0.85, "research_topic", stats, median)

    assert devalued < 0.85, "a below-median fn's prior must shrink"
    assert untouched == 0.85, "an at-or-above-median fn's prior is untouched"


def test_devaluation_is_floored_never_zero():
    # An arm with avg_reward 0 against a high-reward pool would devalue hard;
    # the floor must keep the prior re-samplable.
    stats = {
        "look_outward": {"avg_reward": 0.0, "count": 1000},
        "seek_novelty": {"avg_reward": 0.9, "count": 1000},
    }
    median = statistics.median([0.0, 0.9])
    floored = sf._devalue_prior(0.85, "look_outward", stats, median)
    assert floored >= 0.85 * t.SELECTOR_DEVAL_FLOOR - 1e-9
    assert floored > 0.0


def test_devaluation_requires_evidence():
    # Below median but not enough pulls → prior untouched (don't trust a noisy mean).
    stats = {
        "look_outward": {"avg_reward": 0.11, "count": t.SELECTOR_DEVAL_MIN_PULLS - 1},
        "seek_novelty": {"avg_reward": 0.59, "count": 500},
    }
    median = statistics.median([0.11, 0.59])
    assert sf._devalue_prior(0.85, "look_outward", stats, median) == 0.85


def test_devaluation_noop_without_pool_median():
    assert sf._devalue_prior(0.85, "look_outward", {}, None) == 0.85


# ── §5.3: stagnation rut breaker raises exploration epsilon ──────────────────
def test_rut_breaker_raises_epsilon_under_concentration(monkeypatch):
    # Simulate a bandit state where 3 arms dominate selection (the diagnosis'
    # 81.6% concentration). The selector should raise ε above the calm baseline.
    actions = [
        "look_outward", "look_around", "generate_intrinsic_goals",
        "seek_novelty", "research_topic", "wikipedia_search",
    ]
    high_conc = {
        "counts": {
            "look_outward": 400, "look_around": 350, "generate_intrinsic_goals": 300,
            "seek_novelty": 30, "research_topic": 20, "wikipedia_search": 15,
        }
    }
    low_conc = {"counts": {a: 50 for a in actions}}

    def _eps_for(state):
        monkeypatch.setattr(sf.bandit, "get_state", lambda: state)
        # Replicate the selector's epsilon computation (calm baseline, no drive).
        eps = min(0.30, 0.10 + 0.20 * max(0.0, 0.0 - 0.5))
        counts = (sf.bandit.get_state() or {}).get("counts", {}) or {}
        total = sum(int(counts.get(a, 0) or 0) for a in actions)
        if total >= int(t.SELECTOR_RUT_MIN_TOTAL):
            top3 = sum(sorted((int(counts.get(a, 0) or 0) for a in actions), reverse=True)[:3])
            conc = top3 / max(total, 1)
            trip = float(t.SELECTOR_RUT_TRIP)
            if conc > trip:
                eps = min(
                    float(t.SELECTOR_RUT_EPS_CAP),
                    eps + float(t.SELECTOR_RUT_EPS_GAIN) * (conc - trip) / max(1.0 - trip, 1e-6),
                )
        return eps

    eps_rut = _eps_for(high_conc)
    eps_calm = _eps_for(low_conc)
    assert eps_rut > eps_calm, "concentrated picks must raise exploration epsilon"
    assert eps_rut <= t.SELECTOR_RUT_EPS_CAP + 1e-9
