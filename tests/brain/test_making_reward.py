# AR4 (CODEBASE_AUDIT_2026-07-01 R1): the per-cycle reward gradient must not
# favor intake over making. A produce-and-check ATTEMPT (pass or fail) pays a
# per-event credit >= an intake action's typical standing bonus, a verified pass
# pays more, and a credited symbolic artifact pays production reward the moment
# it is recorded (drained by finalize_cycle), not only at goal close.
import pytest

from brain.agency import effect_ledger as el
from brain.loop.cognition_reward import shape_cognition_reward

_EMO = {"core_signals": {}}


@pytest.fixture(autouse=True)
def _isolate(tmp_path):
    el.EFFECT_LEDGER_FILE = tmp_path / "effect_ledger.jsonl"
    el.reset_for_tests()
    yield
    el.reset_for_tests()


def _reward_for(fn_name: str, context=None) -> float:
    return shape_cognition_reward(
        context if context is not None else {},
        fn_name, "", _EMO, _EMO, env_r=0.0, status_r=0.0, is_failure=False,
    )


def test_making_attempt_pays_at_least_intake():
    making = _reward_for("produce_and_check")
    intake = _reward_for("research_topic")   # growth-bonused intake read
    assert making >= intake


def test_failed_check_still_pays_attempt_credit():
    # a failed CHECK is a successful attempt (the call didn't fail) — it must
    # not pay worse than a plain intake read.
    attempt = _reward_for("produce_and_check", context={})
    baseline = _reward_for("read_rss", context={})
    assert attempt > baseline


def test_verified_pass_pays_more_than_attempt():
    passed = _reward_for(
        "produce_and_check",
        context={"committed_goal": {"id": "g1", "title": "t", "_check_passed": True}},
    )
    attempted = _reward_for(
        "produce_and_check",
        context={"committed_goal": {"id": "g1", "title": "t", "_check_passed": False}},
    )
    assert passed > attempted


_RULE_TEXT = (
    "[synthesized L3 principle] conditions: uncertainty, confidence, avoidance, "
    "planning; conclusion: high uncertainty suppresses action across domains and "
    "shrinking the task restores initiation; causal: uncertainty exceeds confidence "
    "-> action initiation drops (task decomposition restores a tractable next step); "
    "generalised from 3 L2 rules"
)


def test_symbolic_artifact_queues_production_credit():
    from brain.symbolic.symbolic_effects import record_symbolic_effect
    row = record_symbolic_effect("rule", _RULE_TEXT)
    assert row is not None
    credits = el.drain_pending_production()
    assert len(credits) == 1
    assert credits[0]["sub_kind"] == "rule"
    assert credits[0]["significance"] == pytest.approx(0.5)
    # drained means paid — a second drain must not double-pay
    assert el.drain_pending_production() == []


def test_finalize_pays_symbolic_credit_on_live_context(monkeypatch):
    from brain.symbolic.symbolic_effects import record_symbolic_effect
    import brain.loop.finalize as fin

    assert record_symbolic_effect("rule", _RULE_TEXT) is not None

    paid = []
    import brain.control_signals.reward_signals.reward_signals as rs
    monkeypatch.setattr(rs, "release_reward",
                        lambda context, **kw: paid.append(kw))
    import brain.cog_memory.working_memory as wm
    monkeypatch.setattr(wm, "update_working_memory", lambda *a, **k: None)

    fin._pay_symbolic_production({})
    rewards = [p for p in paid if p.get("signal") == "reward_signal"]
    assert rewards, "credited symbolic artifact must pay at record-drain time"
    # significance-scaled: 0.7 * 0.5 — a real per-event production payment,
    # comparable to intake standing bonuses (~0.1–0.25 per cycle)
    assert rewards[0]["actual"] == pytest.approx(0.35)
    assert rewards[0]["source"] == "symbolic_production"
