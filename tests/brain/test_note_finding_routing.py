"""T2.4 — route the note body from the goal's FINDING, not the grounded_parts
planning skeleton (brain/cognition/leave_note.py).

The run's most common note (×56) was literally the grounded_parts prompt skeleton
("...: question or desired change; relevant evidence; reasoned conclusion") — the
template, not the answer. Provenance reached the topic but was severed at the
finding. These pin: a real finding is routed through, and a body that is just the
skeleton is rejected by the shared T0.5 predicate.
"""
from brain.cognition import leave_note as ln


_FINDING = (
    "Emergence arises when local interactions among many simple units produce a "
    "global pattern that none of the units encodes on its own; the coupling strength "
    "is the lever, and starling flocks, convection cells, and market prices all share "
    "that signature, so intervening on the coupling is where leverage lives."
)


def _goal_with_finding():
    return {
        "title": "understand emergence",
        "finding": _FINDING,
        "grounded_parts": ["purpose", "evidence", "conclusion"],
        "definition_of_done": [{"criterion": "explain how emergence works", "met": False}],
    }


def _template_only_goal():
    return {
        "title": "understand emergence",
        "grounded_parts": ["question or desired change", "relevant evidence",
                           "reasoned conclusion"],
        "definition_of_done": [{"criterion": "explain how emergence works", "met": False}],
    }


def test_finding_is_routed_into_the_seed():
    seed = ln._seed_from_goal_finding(_goal_with_finding())
    assert seed is not None
    assert "starling" in seed.lower() and "coupling" in seed.lower()


def test_template_only_goal_has_no_finding_seed():
    assert ln._seed_from_goal_finding(_template_only_goal()) is None


def test_grounded_parts_skeleton_is_rejected_by_predicate():
    """The grounded_parts comprehension seed (pure skeleton) is rejected, so it can
    no longer become a note body."""
    assert ln._seed_from_goal(_template_only_goal()) is None


def test_real_comprehension_seed_still_allowed():
    """A goal whose grounded_parts carry real, specific content (not the template
    skeleton) still produces a usable comprehension seed."""
    goal = {
        "title": "the role of coupling in flocking",
        "grounded_parts": [
            "starlings adjust heading to their seven nearest neighbours",
            "local alignment rules produce global murmuration waves",
            "no leader bird encodes the flock shape",
        ],
        "definition_of_done": [{"criterion": "explain murmuration", "met": False}],
    }
    seed = ln._seed_from_goal(goal)
    assert seed is not None
    assert "starlings" in seed.lower()
