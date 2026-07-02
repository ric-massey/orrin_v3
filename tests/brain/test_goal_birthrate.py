# AR5 (CODEBASE_AUDIT_2026-07-01 G2/AD4): the goal birth-rate quota. ~95% of
# generated goals were "understand X"; with the making path built (AR1–AR3),
# make/connect goals must actually be BORN. Over a window of births, the
# make/connect share must reach the configured floor whenever the candidate
# pool can serve it — and the quota must never force an empty pool.
import pytest

import brain.cognition.intrinsic_generators as gen


def _goal(driven_by: str, title: str) -> dict:
    return {"title": title, "driven_by": driven_by}


@pytest.fixture(autouse=True)
def _fresh_window(monkeypatch):
    monkeypatch.setattr(gen, "_recent_births", [])
    # pin the drive→aspiration mapping to the cold-start prior so a learned
    # drive-credit file on the dev machine can't flip the test
    monkeypatch.setattr(gen, "_serves_aspiration", lambda d: {
        "world_knowledge": "Understand the world more deeply",
        "self_exploration": "Understand my own mind and how I work",
        "output_producing": "Make things — produce work that didn't exist before",
        "genuine_contact": "Be genuinely useful and connected to the people I talk to",
    }.get(d, ""))


def test_floor_forces_makers_when_births_are_all_intake():
    for _ in range(6):
        gen._record_birth(_goal("world_knowledge", "Understand X"))
    pool = [_goal("world_knowledge", "Understand Y"),
            _goal("output_producing", "Write a synthesis of Y")]
    narrowed = gen._quota_filter(pool)
    assert all(gen._aspiration_drive_of(g) in ("output_producing", "genuine_contact")
               for g in narrowed)


def test_quota_never_empties_the_pool():
    for _ in range(6):
        gen._record_birth(_goal("world_knowledge", "Understand X"))
    pool = [_goal("world_knowledge", "Understand Y")]   # no maker available
    assert gen._quota_filter(pool) == pool


def test_intake_cap_benches_intake_candidates():
    # births: 5 intake + 2 making → make share 2/7 ≈ 0.29 (floor met),
    # intake share 5/7 ≈ 0.71 (over the 0.60 cap) → intake sits this round out
    for _ in range(5):
        gen._record_birth(_goal("world_knowledge", "Understand X"))
    for _ in range(2):
        gen._record_birth(_goal("output_producing", "Make X"))
    pool = [_goal("world_knowledge", "Understand Y"),
            _goal("self_exploration", "Trace my selector"),
            _goal("genuine_contact", "Write Ric a real note")]
    narrowed = gen._quota_filter(pool)
    assert all(gen._aspiration_drive_of(g) != "world_knowledge" for g in narrowed)
    assert narrowed


def test_small_window_is_not_judged():
    gen._record_birth(_goal("world_knowledge", "Understand X"))
    pool = [_goal("world_knowledge", "Understand Y")]
    assert gen._quota_filter(pool) == pool


def test_births_over_window_respect_floor_end_to_end(monkeypatch):
    # Simulate N generation rounds with a mixed pool and no starvation pressure:
    # the quota alone must keep make/connect births at/above the floor.
    monkeypatch.setattr(gen, "objective_pressure", lambda ctx: {})
    intake_pool = [_goal("world_knowledge", f"Understand topic {i}") for i in range(4)]
    maker = _goal("output_producing", "Write a synthesis")
    contact = _goal("genuine_contact", "Send a real note")

    def fake_candidates(*a, **k):
        return []

    # Drive the pick loop directly: pool assembly is exercised elsewhere; here we
    # replay the filtered pick + birth recording the function performs.
    import random
    random.seed(7)
    births = []
    for i in range(24):
        pool = gen._quota_filter(intake_pool + [maker, contact])
        chosen = random.choice(pool)
        gen._record_birth(chosen)
        births.append(gen._aspiration_drive_of(chosen))
    window = births[-gen._BIRTH_WINDOW:]
    share = sum(1 for b in window
                if b in ("output_producing", "genuine_contact")) / len(window)
    assert share >= gen._MAKE_CONNECT_FLOOR
