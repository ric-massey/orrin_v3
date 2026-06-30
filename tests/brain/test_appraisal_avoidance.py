# RUN diagnosis 2026-06-29: a stuck, goal-avoiding Orrin had motivation/confidence/
# reward pinned ~0.89 because the appraiser read his own "Goal avoidance: N
# consecutive cycles... I'm thinking but not doing" / "💔 Goal failed ... 3x"
# self-reports as goal-CONGRUENT (positive). These tests lock in that avoidance /
# repeated-failure self-reports produce NEGATIVE affect (impasse / lower confidence),
# never a reward.
from brain.control_signals.appraisal import appraise_event, appraise_working_memory

_GOAL = ["The causes of affective_regulation"]
# High coping = the worst case (it's what routed setbacks into a motivation reward).
_HIGH_COPING = {"core_signals": {"confidence": 0.9, "motivation": 0.9}, "resource_deficit": 0.0}


def _by_emotion(rows):
    out = {}
    for r in rows:
        out[r["emotion"]] = out.get(r["emotion"], 0.0) + r["delta"]
    return out


def test_goal_avoidance_self_report_is_not_rewarded():
    text = ("[metacog/pattern] Goal avoidance: 23 consecutive cycles without taking "
            "action on 'The causes of affective_regulation'. I'm thinking but not doing.")
    deltas = _by_emotion(appraise_event(text, _GOAL, _HIGH_COPING, mood=0.6))
    # No positive reward/confidence/motivation for paralysis.
    assert deltas.get("reward_positive", 0.0) <= 0.0, deltas
    assert deltas.get("confidence", 0.0) <= 0.0, deltas
    assert deltas.get("motivation", 0.0) <= 0.0, deltas
    # It should register as a block: impasse up and/or confidence down.
    assert deltas.get("impasse_signal", 0.0) > 0.0 or deltas.get("confidence", 0.0) < 0.0, deltas


def test_repeated_goal_failure_is_not_a_motivation_reward():
    text = "💔 Goal failed: The causes of affective_regulation. plan_generation_failed_3x"
    deltas = _by_emotion(appraise_event(text, _GOAL, _HIGH_COPING, mood=0.6))
    # The high-coping "challenge response" must NOT reward a repeated dead end.
    assert deltas.get("motivation", 0.0) <= 0.0, deltas
    assert deltas.get("reward_positive", 0.0) <= 0.0, deltas
    assert deltas.get("impasse_signal", 0.0) > 0.0, deltas


def test_genuine_progress_still_rewards():
    # Guard against over-correction: a real success must still feel good.
    text = "I finally solved the parser bug and the build is working — real progress."
    deltas = _by_emotion(appraise_event(text, ["fix the parser bug"], _HIGH_COPING, mood=0.2))
    assert deltas.get("reward_positive", 0.0) > 0.0, deltas


def test_positive_mood_does_not_mint_reward_from_ambiguous_content():
    # The runaway that kept reward pinned ~0.89: a positive mood made ambiguous,
    # goal-relevant dream/analogy text read as congruent and mint reward_positive.
    # With no real help-word, mood must NOT manufacture reward/motivation.
    text = ("Dream: In a labyrinth at dusk, [analogy/COMPARE] a similar situation about "
            "affective_regulation and what it might mean.")
    deltas = _by_emotion(appraise_event(text, ["affective_regulation"], _HIGH_COPING, mood=0.7))
    assert deltas.get("reward_positive", 0.0) <= 0.0, deltas
    assert deltas.get("motivation", 0.0) <= 0.0, deltas


def test_fresh_surmountable_setback_still_motivates():
    # A first-time, non-repeated circumstantial block under high coping should still
    # produce the challenge response (motivation), so we didn't kill that path.
    text = "The network request to the archive was refused this time."
    deltas = _by_emotion(appraise_event(text, ["download the archive"], _HIGH_COPING, mood=0.1))
    assert deltas.get("motivation", 0.0) > 0.0, deltas


def test_recurring_event_habituates_and_stops_pumping():
    # THE structural bug: update_signal_state re-appraises the last WM entries every
    # cycle and accumulates. A standing condition (counter-varying text) must NOT keep
    # producing full-strength deltas — it habituates. First few land, then it damps.
    hab: dict = {}
    goals = ["The causes of affective_regulation"]

    def _impasse_of(n):
        wm = [{"event_type": "metacog", "content":
               f"[metacog/pattern] Goal avoidance: {n} consecutive cycles without "
               f"taking action on 'The causes of affective_regulation'. I'm thinking but not doing."}]
        rows = appraise_working_memory(wm, goals, _HIGH_COPING, mood=0.6, habituation=hab)
        return sum(r["delta"] for r in rows if r["emotion"] == "impasse_signal")

    first = _impasse_of(20)
    assert first > 0.0, "first appraisal of a real avoidance should register"
    # Subsequent number-varying recurrences of the SAME condition must shrink fast.
    later = [_impasse_of(n) for n in (21, 22, 23, 24, 25)]
    assert later[-1] < first * 0.2, (first, later)  # damped to <20% by repetition


def test_habituation_does_not_blunt_a_genuinely_new_event():
    # Habituation must be per-event: a brand-new, distinct event still lands full.
    hab: dict = {}
    g = ["fix the parser"]
    wm_a = [{"event_type": "note", "content": "I finally solved the parser bug — it builds and works now."}]
    wm_b = [{"event_type": "note", "content": "I completed the migration and the database upgrade succeeded."}]
    a = appraise_working_memory(wm_a, g, _HIGH_COPING, mood=0.2, habituation=hab)
    b = appraise_working_memory(wm_b, ["finish the migration"], _HIGH_COPING, mood=0.2, habituation=hab)
    assert any(r["emotion"] == "reward_positive" and r["delta"] > 0 for r in a), a
    assert any(r["emotion"] == "reward_positive" and r["delta"] > 0 for r in b), b
