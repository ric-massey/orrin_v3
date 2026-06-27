"""F5 / D6 — leave_note seed-provenance hardening (PRODUCTION_LOOP_CLOSURE).

Verification test #10: filesystem/path noise cannot seed a note. The 2026-06-19
life wrote junk notes seeded from path output and lock/data fragments; the seed
quality gate must reject those classes while still admitting real prose.
"""

from brain.cognition.leave_note import _qualifies_as_seed, _seed_from_goal


def test_path_and_lock_fragments_are_rejected():
    junk = [
        "/Users/ricmassey/orrin_v3/brain/data/long_memory.json",
        "data/goals/state.jsonl data/memory/wal/events.jsonl",
        "brain/data/.orrin.instance.lock",
        "snapshot_20260619_081225_pre_reset/decision_stats.json",
        "[] {} === ---- :::",                       # empty-delimiter output
        "chunk chunk chunk chunk chunk chunk",      # low-information token soup
        "ok",                                       # too short
    ]
    for frag in junk:
        assert not _qualifies_as_seed(frag), f"should reject junk seed: {frag!r}"


def test_real_prose_finding_qualifies():
    prose = ("emergence describes how higher-level order arises from many simple "
             "local interactions without any central controller directing them")
    assert _qualifies_as_seed(prose)


def test_goal_grounded_parts_seed_when_present():
    goal = {
        "title": "Understand emergence",
        "grounded_parts": [
            "local interactions producing global order",
            "the absence of a central controller",
            "examples like ant colonies and markets",
        ],
        "definition_of_done": [
            {"criterion": "A clear explanation of emergence is recorded", "met": False},
        ],
    }
    seed = _seed_from_goal(goal)
    assert seed and "emergence" in seed.lower()
    assert _qualifies_as_seed(seed)


def test_path_payload_cannot_seed_from_goal():
    # A degraded goal whose grounded parts are path noise must not yield a seed.
    goal = {"title": "x", "grounded_parts": ["/Users/x/data/foo.json", "a/b/c.lock"]}
    assert _seed_from_goal(goal) is None
