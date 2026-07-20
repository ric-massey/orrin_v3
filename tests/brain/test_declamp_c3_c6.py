# Run 11 §6.1 — clamp→antagonist conversions C3–C6, proven at the mechanism.
#   C3: title cooldown/cap → topic appetite (quench + recovery, no lifetime ban)
#   C4: symbolic credit window cap → marginal-novelty pricing (no cliff)
#   C5: rut-breaker forced switch → boredom drive (backstop only)
#   C6: DMN/TPN mode damping → activation economics (price + vigor)

import time

import pytest


# ── C3: topic satiety ────────────────────────────────────────────────────────

def test_completion_quenches_appetite_and_time_restores_it():
    from brain.cognition import intrinsic_helpers as ih
    title = "understand pytest-quench-topic more deeply"
    assert ih.topic_appetite(title) == 1.0
    now = time.time()
    ih.note_title_completion(title)
    # Right after completing: want is quenched below the spawn floor.
    assert ih.topic_appetite(title, now=now) < ih._APPETITE_SPAWN_FLOOR
    assert ih.title_respawn_blocked(title, now=now)
    # Two days later the want has recovered past the floor — no timer, decay.
    later = now + 2 * 24 * 3600
    assert ih.topic_appetite(title, now=later) > ih._APPETITE_SPAWN_FLOOR
    assert not ih.title_respawn_blocked(title, now=later)


def test_heavy_repetition_is_a_long_quench_not_a_lifetime_ban():
    from brain.cognition import intrinsic_helpers as ih
    title = "understand pytest-banned-topic more deeply"
    now = time.time()
    for _ in range(ih.TITLE_COMPLETION_CAP):   # the count that used to ban forever
        ih.note_title_completion(title)
    assert ih.title_respawn_blocked(title, now=now), "freshly quenched"
    # A month later the appetite has come back — the cap is retired.
    assert not ih.title_respawn_blocked(title, now=now + 30 * 24 * 3600), (
        "C3: the per-life ban must decay into a long finite quench")


# ── C4: marginal-novelty pricing ─────────────────────────────────────────────

def test_symbolic_storm_extinguishes_economically_without_a_cliff():
    from brain.agency import effect_ledger as el
    el._symbolic_credit_times.clear()
    sigs = []
    for i in range(10):
        row = el.record_effect(
            "symbolic_artifact",
            f"Rule synthesized: pattern-{i} implies consequence-{i} when "
            f"observed under condition set {i} with distinct novel content "
            f"about topic family {i} — clause {i}.",
            goal_id=f"g_storm_{i}",
        )
        if row is not None:
            sigs.append(row.significance)
    assert len(sigs) >= 4, "early storm entries must still credit"
    # Marginal price falls with volume: later credits are worth much less...
    assert sigs[0] > sigs[-1] * 3, f"no marginal decline: {sigs}"
    # ...but there is no cliff row that pays exactly 0 while its neighbors pay
    # full price (the legacy cap behavior).
    assert all(s > 0.0 for s in sigs)


# ── C5: forced switch demoted to backstop ────────────────────────────────────

def test_meta_rut_forced_switch_waits_for_the_backstop_window():
    from brain.think.think_utils.selection import pick as pk
    assert pk._BOREDOM_DRIVE, "flag must default ON for Run 11"
    think = "assess_goal_progress"
    act = "research_topic"
    scored = [(think, 0.8, {}), (act, 0.5, {})]

    # 5 all-think picks (the OLD trigger): boredom economics gets first refusal
    # — no forced switch.
    recent5 = ["abduce", "reflection", "self_review", "adapt_subgoals", think]
    chosen, override, _ = pk.apply_antirepeat_and_metarut(think, scored, recent5, {})
    assert chosen == think and not override

    # A freeze that survives the full backstop window IS broken by force.
    recent12 = (["abduce", "reflection", "self_review", "adapt_subgoals",
                 "narrative_update", "reflect_on_affect"] * 2)
    chosen, override, _ = pk.apply_antirepeat_and_metarut(think, scored, recent12, {})
    assert chosen == act and override, "dead-man backstop must still fire"


# ── C6: energy economics ─────────────────────────────────────────────────────

def _disjoint_action_reflect(eo):
    # assess_goal_progress lives in BOTH sets; a hash-order pick of it flips the
    # effort classification, so sample from the disjoint parts deterministically.
    action_fn = sorted(set(eo.ACTION_FUNCTIONS) - set(eo.REFLECT_FUNCTIONS))[0]
    reflect_fn = sorted(set(eo.REFLECT_FUNCTIONS) - set(eo.ACTION_FUNCTIONS))[0]
    return action_fn, reflect_fn


def test_low_activation_prices_out_effort_instead_of_boosting_reflection():
    from brain.motivation import energy_orientation as eo
    assert eo._ENERGY_ECONOMICS
    action_fn, reflect_fn = _disjoint_action_reflect(eo)
    boosts = eo.energy_boost_scores([action_fn, reflect_fn], "low", 0.2, True)
    # Effortful work is EXPENSIVE at low activation; reflection is just cheap.
    assert boosts.get(action_fn, 0.0) < -0.15
    assert boosts.get(reflect_fn, 0.0) > -0.05
    assert boosts.get(reflect_fn, 0.0) <= 0.0, "no artificial reflection boost"


def test_high_activation_presses_toward_action():
    from brain.motivation import energy_orientation as eo
    action_fn, reflect_fn = _disjoint_action_reflect(eo)
    boosts = eo.energy_boost_scores([action_fn, reflect_fn], "high", 0.9, False)
    assert boosts.get(action_fn, 0.0) > boosts.get(reflect_fn, 0.0), (
        "surplus activation (vigor) must favor acting")


def test_reactive_protection_survives_the_conversion():
    from brain.motivation import energy_orientation as eo
    supp = next(iter(eo._REACTIVE_SUPPRESS))
    allow = next(iter(eo._REACTIVE_ALLOW))
    boosts = eo.energy_boost_scores([supp, allow], "medium", 0.40, False)
    assert boosts.get(supp) == pytest.approx(-0.18)
    assert boosts.get(allow) == pytest.approx(0.12)
