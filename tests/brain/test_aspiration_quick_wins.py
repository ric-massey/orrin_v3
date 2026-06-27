# T0.3 (WS-7 Changes 5, 1, 3-core) — aspiration scoreboard + seed-at-birth +
# orphaned-`will` mapping. Regression coverage for the three Phase-0 aspiration
# quick wins from the Core Architecture master plan.
import brain.cognition.intrinsic_aspirations as ia
import brain.cognition.aspiration_scoreboard as sb
import brain.cognition.production_funnel as pf


def _title(drive: str) -> str:
    return ia._BASE_DRIVE_TO_ASPIRATION[drive]


def test_orphaned_will_maps_to_a_real_aspiration_not_world_default():
    # `will` (will.py:243) used to lack any prior, so the first keyword-classified
    # completion captured its credit for "Understand the world…". It must now carry
    # an explicit prior — and NOT world-knowledge.
    assert "will" in ia._DRIVE_TO_ASPIRATION
    assert ia._DRIVE_TO_ASPIRATION["will"] == _title("output_producing")
    assert ia._DRIVE_TO_ASPIRATION["will"] != _title("world_knowledge")


def test_every_emitted_secondary_drive_has_a_prior():
    # Each secondary drive the generators emit resolves to a real aspiration title.
    for drive in ("self_exploration", "simulate_selves", "curiosity",
                  "problem_solving", "will"):
        assert ia._serves_aspiration(drive) in {t for t, _ in ia._ASPIRATIONS}


def test_seed_at_birth_seeds_a_prior_for_every_drive():
    ia._seed_drive_priors()
    credit = ia._load_drive_credit()
    weights = credit["weights"]
    for drive, title in ia._DRIVE_TO_ASPIRATION.items():
        assert weights.get(drive, {}).get(title) == ia._PRIOR_SEED_WEIGHT


def test_seeded_prior_is_not_overturned_by_a_single_weak_completion():
    # A single world-keyword hit on a will-goal (weight ~alpha*reward) must not
    # exceed the 0.50 prior — so credit stays on the seeded aspiration.
    ia._seed_drive_priors()
    credit = ia._load_drive_credit()
    ia._learn_drive_aspiration(
        "will", _title("world_knowledge"), reward=0.8, credit=credit)
    row = credit["weights"]["will"]
    assert max(row, key=row.get) == _title("output_producing")


def _clear_scoreboard():
    try:
        sb._FILE.unlink()
    except FileNotFoundError:
        pass


def test_scoreboard_records_and_reads_back_by_stage():
    _clear_scoreboard()
    asp = _title("output_producing")
    sb.record(asp, "generated")
    sb.record(asp, "generated")
    sb.record(asp, "completed")
    board = sb.scoreboard()
    assert board[asp]["generated"] == 2
    assert board[asp]["completed"] == 1
    assert board[asp]["attempted"] == 0
    assert sb.generation_counts()[asp] == 2


def test_scoreboard_ignores_unknown_stage():
    _clear_scoreboard()
    sb.record(_title("world_knowledge"), "bogus_stage")
    assert sb.scoreboard() == {}


def _clear_funnel():
    try:
        pf._FILE.unlink()
    except FileNotFoundError:
        pass


def test_production_funnel_names_the_drop_edge():
    _clear_funnel()
    # A candidate was generated and committed, but the producer never ran.
    pf.record("candidate", "g1")
    pf.record("committed", "g1")
    counts = pf.funnel()
    assert counts["candidate"] == 1
    assert counts["committed"] == 1
    assert counts["producer_ran"] == 0
    # The drop edge is the first zero stage after a non-zero one.
    assert pf.drop_edge() == "handoff"


def test_production_funnel_clean_flow_has_no_drop_edge():
    _clear_funnel()
    for stage in pf.STAGES:
        pf.record(stage, "g2")
    assert pf.drop_edge() == ""
