# Run 4 fix B4 (RUN4_FIX_PLAN_2026-07-04 §B4): tighten aspiration credit +
# candidate quota. (1) A research/intake goal that writes a memo file must NOT
# be credited to the making aspiration. (2) No single aspiration may hold more
# than ~50% of the generated candidate pool.

import brain.cognition.intrinsic_objectives as io
import brain.cognition.intrinsic_generators as ig


# ── B4.1: making credit requires a make-shaped goal ──────────────────────────

def test_make_shaped_recognition():
    assert io._goal_is_make_shaped({"kind": "coding"})
    assert io._goal_is_make_shaped({"driven_by": "output_producing"})
    assert io._goal_is_make_shaped({"spec": {"synthesize": "evolution"}})
    assert not io._goal_is_make_shaped({"kind": "research", "driven_by": "world_knowledge"})


def test_research_memo_not_credited_to_making():
    # A research goal whose title trips making keywords but is intake-driven.
    goal = {
        "title": "Produce a written overview of evolutionary biology research",
        "kind": "research",
        "driven_by": "world_knowledge",
        "spec": {},
    }
    asp = io._evidenced_aspiration(goal)
    assert asp != io._OUTPUT_PRODUCING_TITLE, \
        "an intake research goal must not wear the making hat"


def test_make_goal_still_credited_to_making():
    goal = {
        "title": "Turn what I know about evolution into a written synthesis",
        "kind": "generic",
        "driven_by": "output_producing",
        "spec": {"synthesize": "evolution"},
    }
    assert io._evidenced_aspiration(goal) == io._OUTPUT_PRODUCING_TITLE


# ── B4.2: candidate pool aspiration cap ──────────────────────────────────────

def test_candidate_cap_trims_monoculture(monkeypatch):
    # 18 intake candidates + 1 make + 1 contact — intake is 90% of the pool.
    pool = ([{"title": f"Understand thing {i}", "driven_by": "world_knowledge"}
             for i in range(18)]
            + [{"title": "Make a synthesis", "driven_by": "output_producing"}]
            + [{"title": "Answer Ric", "driven_by": "genuine_contact"}])
    out = ig._cap_candidate_aspiration_share(pool)
    n = len(out)
    intake = sum(1 for g in out if ig._aspiration_drive_of(g) == "world_knowledge")
    assert intake / n <= 0.5 + 1e-9, f"intake still {intake}/{n} of the pool"
    # the minority aspirations are preserved
    assert any(ig._aspiration_drive_of(g) == "output_producing" for g in out)
    assert any(ig._aspiration_drive_of(g) == "genuine_contact" for g in out)


def test_candidate_cap_noop_for_single_aspiration():
    pool = [{"title": f"Understand {i}", "driven_by": "world_knowledge"} for i in range(6)]
    assert ig._cap_candidate_aspiration_share(pool) == pool
