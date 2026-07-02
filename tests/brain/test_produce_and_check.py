"""P3 — produce-and-check loop + caged-sandbox exercise
(brain/cognition/produce_and_check.py + goal_satiety check-pass proxy).

Covers the plan's acceptance:
  • a verifiable goal runs the sandbox and, on a passing check, records a
    tool_run_effect (the first emitter of that kind) — which closes it via is_sated;
  • a wrong answer keeps the goal open with an updated gap;
  • a non-verifiable goal is declined (not gated on a check it can't have);
  • the action is registered (discoverable + in the execution/explore/procedural sets).
"""
import pytest

import brain.cognition.produce_and_check as pc
from brain.cognition.planning import goal_satiety


def _verifiable_goal(**kw):
    g = {"id": "vg1", "title": "Understand modular arithmetic more deeply"}
    g.update(kw)
    return g


@pytest.fixture(autouse=True)
def _bind(monkeypatch):
    """produce_and_check pulls the active goal via global_workspace.bound_goal
    (imported inside the function) — control it per test."""
    self = {}

    def _set(goal):
        self["goal"] = goal
        monkeypatch.setattr("brain.cognition.global_workspace.bound_goal",
                            lambda ctx=None: self.get("goal"))
    return _set


# ── classification ────────────────────────────────────────────────────────────

def test_classify_verifiable():
    assert pc.classify_verifiable("modular arithmetic") == "math"
    assert pc.classify_verifiable("projectile velocity and acceleration") == "physics"
    assert pc.classify_verifiable("sampling variance of a distribution") == "statistics"
    assert pc.classify_verifiable("an insertion sort algorithm") == "code"
    assert pc.classify_verifiable("the joy of solitude") is None


def test_is_verifiable_goal():
    assert pc.is_verifiable_goal(_verifiable_goal())
    assert not pc.is_verifiable_goal({"title": "understand loneliness more deeply"})
    assert pc.is_verifiable_goal({"title": "x", "check_spec": {"code": "print('CHECK_PASS')"}})


# ── the loop ────────────────────────────────────────────────────────────────────

def test_synthesized_check_passes_and_records_effect(_bind):
    """A real math goal (no explicit spec) synthesizes a check, runs it in the
    sandbox, passes, and records a tool_run_effect credited to the goal."""
    from brain.agency import effect_ledger
    goal = _verifiable_goal()
    _bind(goal)
    out = pc.produce_and_check(context={})
    assert out.get("changed") is True
    assert out.get("check_passed") is True
    # a durable, credited effect of exactly this kind now exists for the goal
    assert effect_ledger.has_effect_kind("vg1", "tool_run_effect")


def test_passing_check_closes_via_is_sated(_bind):
    """The check-pass proxy: a verifiable goal is NOT sated before a check, and IS
    sated (check_passed) once produce_and_check records the effect."""
    goal = _verifiable_goal(id="vg_close")
    _bind(goal)
    sated, reason = goal_satiety.is_sated(goal)
    assert sated is False and reason == "awaiting_check"
    pc.produce_and_check(context={})
    sated, reason = goal_satiety.is_sated(goal)
    assert sated is True and reason == "check_passed"


def test_wrong_answer_keeps_goal_open_with_gap(_bind):
    """A failing check does not close the goal; it writes the specific gap back."""
    from brain.agency import effect_ledger
    goal = _verifiable_goal(id="vg_fail",
                            check_spec={"code": "assert 1 == 2, 'one is not two'", "label": "bad"})
    _bind(goal)
    out = pc.produce_and_check(context={})
    assert out.get("changed") is True
    assert out.get("check_passed") is False
    assert out.get("gap")                       # a concrete gap string
    assert goal.get("_last_check_gap")          # written back onto the goal
    assert not effect_ledger.has_effect_kind("vg_fail", "tool_run_effect")
    # still not sated — it must keep attempting
    sated, reason = goal_satiety.is_sated(goal)
    assert sated is False and reason == "awaiting_check"


def test_explicit_spec_pass_records_effect(_bind):
    # A substantive explicit check (clears the ledger's MIN_ARTIFACT_CHARS gate — a
    # trivial one-liner is correctly not credited, same as P1's hollow-effect rule).
    spec_code = (
        "def fib(n):\n"
        "    a, b = 0, 1\n"
        "    for _ in range(n):\n"
        "        a, b = b, a + b\n"
        "    return a\n"
        "vals = [fib(i) for i in range(12)]\n"
        "assert vals == [0, 1, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89], vals\n"
        "assert all(vals[i] == vals[i-1] + vals[i-2] for i in range(2, len(vals)))\n"
        "print('CHECK_PASS fibonacci recurrence holds')\n"
    )
    goal = {"id": "vg_spec", "title": "x",
            "check_spec": {"code": spec_code, "label": "fibonacci"}}
    _bind(goal)
    from brain.agency import effect_ledger
    out = pc.produce_and_check(context={})
    assert out.get("check_passed") is True
    assert effect_ledger.has_effect_kind("vg_spec", "tool_run_effect")


def test_non_verifiable_goal_declined(_bind):
    """Don't gate a non-verifiable goal on a check it can't have."""
    goal = {"id": "ng", "title": "Understand what loneliness feels like"}
    _bind(goal)
    out = pc.produce_and_check(context={})
    assert out.get("changed") is False
    assert "verifiable" in out.get("reason", "")


def test_no_goal_is_a_noop(_bind):
    _bind(None)
    out = pc.produce_and_check(context={})
    assert out.get("changed") is False


# ── registration ────────────────────────────────────────────────────────────────

def test_registered_as_cognitive_function():
    from brain.registry.cognition_registry import COGNITIVE_FUNCTIONS
    assert "produce_and_check" in COGNITIVE_FUNCTIONS
    assert callable(COGNITIVE_FUNCTIONS["produce_and_check"]["function"])


def test_in_selection_and_procedural_sets():
    from brain.think.think_utils.selection import tag_sets as ts
    from brain.cognition.planning import step_execution as se
    assert "produce_and_check" in ts._EXECUTION_FNS
    assert "produce_and_check" in ts._SAFE_TO_EXPLORE          # ε-exploration can force first pull
    assert "produce_and_check" in se._PROCEDURAL_FNS           # Executive lane may run it
    assert "produce_and_check" in se._KNOWN_FN_NAMES


def test_step_intent_maps_to_action():
    from brain.cognition.planning.step_execution import recognise_step_action
    assert recognise_step_action("verify the derivation and check the answer") == "produce_and_check"
    assert recognise_step_action("compute the sum and check it against the closed form") == "produce_and_check"


def test_capability_description_present():
    import json
    from pathlib import Path
    import brain
    # the manifest is read from the in-repo brain/data (not the isolated DATA_DIR),
    # matching step_execution._procedural_from_manifest's __file__-relative load
    caps_path = Path(brain.__file__).resolve().parent / "data" / "capability_descriptions.json"
    caps = json.loads(caps_path.read_text("utf-8"))
    assert "produce_and_check" in caps
