"""P7 / A2 — run-config ablation flags + run stamping.

Each subsystem checks its flag at its own entry point and no-ops (never raises)
when ablated; the run stamp reflects the config so traces are comparable.
"""
import json

import pytest

import brain.run_config as rc


@pytest.fixture(autouse=True)
def _fresh_flags(monkeypatch):
    """Every test starts with a clean env and re-reads flags."""
    monkeypatch.delenv("ORRIN_ABLATE", raising=False)
    rc.reload()
    yield
    rc.reload()


def _ablate(monkeypatch, *names):
    monkeypatch.setenv("ORRIN_ABLATE", ",".join(names))
    rc.reload()


# ── the config itself ────────────────────────────────────────────────────────────

def test_defaults_all_on():
    assert rc.ablated() == frozenset()
    assert all(rc.snapshot().values())
    assert rc.run_stamp(date="2026_07_01") == "run_2026_07_01_all_on"


def test_env_ablation_and_stamp(monkeypatch):
    _ablate(monkeypatch, "memory", "goals")
    assert rc.subsystem_enabled("memory") is False
    assert rc.subsystem_enabled("goals") is False
    assert rc.subsystem_enabled("workspace") is True
    assert rc.run_stamp(date="2026_07_01") == "run_2026_07_01_goals_off_memory_off"


def test_unknown_names_ablate_nothing(monkeypatch):
    """A typo must not silently ablate something else — it ablates nothing."""
    _ablate(monkeypatch, "memmory", "the_vibes")
    assert rc.ablated() == frozenset()
    # ...and an unknown name queried directly stays ON (rename-safe).
    assert rc.subsystem_enabled("definitely_not_a_subsystem") is True


def test_file_config_read_when_env_absent(monkeypatch, tmp_path):
    cfg = tmp_path / "run_config.json"
    cfg.write_text(json.dumps({"ablate": ["research_tools"]}))
    import brain.paths as paths
    monkeypatch.setattr(paths, "DATA_DIR", tmp_path)
    rc.reload()
    assert rc.subsystem_enabled("research_tools") is False
    assert rc.subsystem_enabled("memory") is True


def test_capsule_provenance_carries_stamp(monkeypatch):
    _ablate(monkeypatch, "signals")
    from brain.evidence.life_capsule import _provenance
    prov = _provenance("test")
    assert prov["run_stamp"].endswith("signals_off")
    assert prov["run_config"]["signals"] is False
    assert prov["run_config"]["memory"] is True


# ── each flag disables its subsystem at the entry point (fail-safe no-op) ───────

def test_workspace_flag_gates_update_workspace(monkeypatch):
    from brain.cognition.global_workspace import update_workspace
    ctx = {"affect_state": {"core_signals": {"impasse_signal": 0.92}}}
    assert update_workspace(dict(ctx)) is not None   # on: a conscious moment
    _ablate(monkeypatch, "workspace")
    assert update_workspace(dict(ctx)) is None       # off: no winner, no crash


def test_metacognition_flag_gates_trace_buffer(monkeypatch):
    from brain.cognition.metacog import metacog_init, metacog_note
    ctx = {}
    metacog_init(ctx)
    assert "metacog" in ctx
    _ablate(monkeypatch, "metacognition")
    ctx2 = {}
    metacog_init(ctx2)
    assert "metacog" not in ctx2
    metacog_note(ctx2, "selection", "should be a no-op")   # tolerates absence


def test_idle_consolidation_flag(monkeypatch):
    from brain.cognition.idle_consolidation.consolidation_cycle import (
        should_consolidate, idle_consolidation_cycle)
    _ablate(monkeypatch, "idle_consolidation")
    assert should_consolidate({}) is False
    assert idle_consolidation_cycle({}) == {"skipped": "ablated"}


def test_llm_tools_flag_fails_closed(monkeypatch):
    _ablate(monkeypatch, "llm_tools")
    from brain.utils.generate_response import generate_response
    out = generate_response("hello", caller="test")
    assert out["status"] == "error"
    assert out["content"] is None
    assert "ablated" in out["error"]


def test_research_tools_flag(monkeypatch):
    _ablate(monkeypatch, "research_tools")
    from brain.cognition.web_research import research_topic, fetch_and_read
    r = research_topic({})
    assert isinstance(r, dict) and r.get("changed") is False and "ablated" in r["reason"]
    f = fetch_and_read({})
    assert isinstance(f, dict) and f.get("changed") is False and "ablated" in f["reason"]


def test_host_coupling_flag(monkeypatch):
    _ablate(monkeypatch, "host_coupling")
    from brain.cognition.host_resource_monitor import update_host_interoception
    assert update_host_interoception({}) == {}


def test_persistence_flag_makes_run_amnesic(monkeypatch, tmp_path):
    from brain.utils.json_utils import save_json, modify_json, load_json
    target = tmp_path / "state.json"
    save_json(target, {"alive": True})
    assert target.exists()

    _ablate(monkeypatch, "persistence")
    gone = tmp_path / "never_written.json"
    save_json(gone, {"alive": True})
    assert not gone.exists()
    # modify_json: the in-memory dict mutates (this cycle sees it) but no disk write.
    with modify_json(target) as data:
        data["alive"] = False
    assert load_json(target, default_type=dict) == {"alive": True}


def test_memory_flag_skips_recall_injection(monkeypatch):
    _ablate(monkeypatch, "memory")
    from brain.loop.reflect import integrate_recall_and_baseline

    class _Boom:  # a daemon that must never be touched when memory is ablated
        def __getattr__(self, name):
            raise AssertionError("memory daemon was queried despite ablation")

    ctx = integrate_recall_and_baseline({"working_memory": []}, _Boom())
    assert ctx.get("retrieved_memories") == []
