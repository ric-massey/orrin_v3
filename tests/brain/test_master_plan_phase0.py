# Phase 0 regression tests (docs/archive/ORRIN_MASTER_PLAN.md).
#
# 0.1 — detect_rule_contradictions must hand resolve_conflict (rule, score)
#       pairs, not bare dicts. The old shape crashed with ValueError on every
#       invocation and record_failure swallowed it for months. The test pins
#       the *class* of bug: silent type mismatch at a module boundary.
# 0.2 — mark_goal_failed's metrics import is aliased so the failure-counter
#       record_failure(site, exc) is never shadowed; both failure paths
#       (metrics call raising, import missing) must still complete the
#       long-memory write and emotional penalty.
# 0.3 — a regulation attempt with an affect_stability side-effect routes the
#       delta through the AffectArbiter to the TOP-LEVEL field, never into
#       core_signals (convergence path must not silently regress).
import pytest

import brain.utils.failure_counter as fc


class _StubBridge:
    def log(self, *args, **kwargs):
        pass


@pytest.fixture(autouse=True)
def _isolated_failure_counter(monkeypatch, tmp_path):
    monkeypatch.setattr(fc, "_counters", {})
    monkeypatch.setattr(fc, "_last_logged", {})
    monkeypatch.setattr(fc, "_data_dir_cache", tmp_path)
    monkeypatch.setattr(fc, "_STRICT", "")
    monkeypatch.setattr("backend.telemetry_bridge.get_bridge", lambda *a, **k: _StubBridge())
    yield


# ── 0.1 coherence check ───────────────────────────────────────────────────────

_CONTRADICTORY_RULES = [
    {"id": "r1", "condition": "files explored", "conclusion": "exploring new files is helpful for learning",
     "confidence": 0.9},
    {"id": "r2", "condition": "files explored", "conclusion": "exploring new files is not helpful for learning",
     "confidence": 0.8},
]


def test_detect_rule_contradictions_no_failure_tick(monkeypatch):
    import brain.symbolic.symbolic_cognition as sc
    import brain.symbolic.meta_rules as mr

    monkeypatch.setattr(sc, "_rules", lambda: list(_CONTRADICTORY_RULES))
    monkeypatch.setattr(mr, "_record_application", lambda *a, **k: None)
    monkeypatch.setattr(mr, "log_activity", lambda *a, **k: None)

    results = sc.detect_rule_contradictions({"core_beliefs": []})

    assert "symbolic_cognition.detect_rule_contradictions" not in fc.get_summary(), (
        "detect_rule_contradictions still crashes internally — the (rule, score) "
        "pairing regressed"
    )
    # A seeded contradictory pair must surface as a logged contradiction.
    assert any(r.get("type") == "rule_conflict" for r in results)


def test_detect_rule_contradictions_handles_non_contradictory_rules(monkeypatch):
    import brain.symbolic.symbolic_cognition as sc
    import brain.symbolic.meta_rules as mr

    rules = [
        {"id": "a", "conclusion": "reading books deepens understanding", "confidence": 0.9},
        {"id": "b", "conclusion": "notes preserve context across restarts", "confidence": 0.7},
    ]
    monkeypatch.setattr(sc, "_rules", lambda: rules)
    monkeypatch.setattr(mr, "_record_application", lambda *a, **k: None)

    results = sc.detect_rule_contradictions({"core_beliefs": []})
    assert "symbolic_cognition.detect_rule_contradictions" not in fc.get_summary()
    assert not any(r.get("type") == "rule_conflict" for r in results)


# ── 0.2 mark_goal_failed shadowing ───────────────────────────────────────────

@pytest.fixture
def _quiet_goals(monkeypatch):
    """Silence mark_goal_failed's live side-channels and capture the ones the
    test asserts on (long-memory write, WM write)."""
    # mark_goal_failed lives in goal_outcomes (Phase 4.5C split); patch its
    # top-level side-channels there. update_long_memory is a lazy import in the
    # handler, so patching the source module still captures it.
    import brain.cognition.planning.goal_outcomes as goal_outcomes
    import brain.cog_memory.long_memory as lm

    written = {"long_memory": [], "working_memory": []}
    monkeypatch.setattr(goal_outcomes, "release_reward_signal", lambda *a, **k: None)
    monkeypatch.setattr(goal_outcomes, "log_activity", lambda *a, **k: None)
    monkeypatch.setattr(goal_outcomes, "update_working_memory",
                        lambda entry, *a, **k: written["working_memory"].append(entry))
    monkeypatch.setattr(lm, "update_long_memory",
                        lambda content, **k: written["long_memory"].append((content, k)))
    return written


def test_mark_goal_failed_survives_metrics_raise(monkeypatch, _quiet_goals):
    import brain.cognition.planning.goals as goals
    import brain.cognition.planning.outcome_metrics as om

    def _boom():
        raise RuntimeError("metrics exploded")

    monkeypatch.setattr(om, "record_failure", _boom)

    goal = {"name": "test goal"}
    context = {"affect_state": {"core_signals": {"impasse_signal": 0.1}}}
    goals.mark_goal_failed(goal, "seeded failure", context)  # must not raise

    # The handler used the failure-counter record_failure (two-arg), not the
    # shadowed no-arg metrics function.
    assert "goals.mark_goal_failed" in fc.get_summary()
    # The rest of the function ran: durable memory write + emotional penalty.
    assert goal["status"] == "failed"
    assert _quiet_goals["long_memory"], "long-memory write was skipped"
    core = context["affect_state"]["core_signals"]
    assert core["impasse_signal"] > 0.1, "emotional penalty was skipped"


def test_mark_goal_failed_survives_metrics_import_failure(monkeypatch, _quiet_goals):
    import brain.cognition.planning.goals as goals
    import brain.cognition.planning.outcome_metrics as om

    # `from ... import record_failure as record_outcome_failure` now raises
    # ImportError; the handler must hit the real failure counter, not
    # UnboundLocalError.
    monkeypatch.delattr(om, "record_failure")

    goal = {"name": "test goal 2"}
    context = {"affect_state": {"core_signals": {"impasse_signal": 0.1}}}
    goals.mark_goal_failed(goal, "seeded import failure", context)

    assert "goals.mark_goal_failed" in fc.get_summary()
    assert goal["status"] == "failed"
    assert _quiet_goals["long_memory"]
    assert context["affect_state"]["core_signals"]["impasse_signal"] > 0.1


# ── 0.3 regulation affect_stability routing ──────────────────────────────────

def test_regulation_stability_side_effect_stays_out_of_core(monkeypatch):
    import brain.control_signals.regulation as reg
    import brain.cog_memory.working_memory as wm
    from brain.control_signals.arbiter import commit_affect

    log_state = {}
    monkeypatch.setattr(reg, "_load_log", lambda: log_state)
    monkeypatch.setattr(reg, "_save_log", lambda log: None)
    monkeypatch.setattr(reg, "log_private", lambda *a, **k: None)
    monkeypatch.setattr(wm, "update_working_memory", lambda *a, **k: None)
    monkeypatch.setattr(reg.random, "random", lambda: 0.0)  # force success

    context = {
        "cycle_count": 100,
        "affect_state": {
            "core_signals": {"impasse_signal": 0.9, "confidence": 0.5},
            "affect_stability": 0.5,
        },
    }
    assert reg.attempt_regulation(context) is True
    applied = commit_affect(context)

    state = context["affect_state"]
    # (a) the side-effect never lands inside core_signals
    assert "affect_stability" not in state["core_signals"]
    # (b) the top-level field actually moved (reappraisal carries +0.04)
    assert "affect_stability" in applied
    assert state["affect_stability"] > 0.5
