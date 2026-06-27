# Allostatic capacity tax (ALLOSTATIC_CAPACITY_TAX_2026-06-17): a high
# resource_deficit (felt empty tank) must tax motivation/capacity the same way a
# sustained physical stress streak does, so Orrin can't be mathematically
# exhausted yet "manically content". The tax feeds the EXISTING stress_load block
# via load = max(stress_streak_load, resource_deficit_load); it stays gentle and
# floored, and surfaces one working-memory note on the upward fatigue crossing.
import json
from datetime import datetime, timezone

import brain.control_signals.update_affect_state as uas
import brain.cog_memory.working_memory as wm


def _seed(path, core_overrides, resource_deficit, extra=None):
    core = dict(uas.CORE_BASELINES)
    core.update(core_overrides)
    state = {
        "core_signals": core,
        "resource_deficit": resource_deficit,
        "social_deficit": 0.0,
        "affect_stability": 1.0,
        # Recent timestamp so the decay-to-baseline pass is ~0 and the tax is visible.
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }
    if extra:
        state.update(extra)
    path.write_text(json.dumps(state))
    return state


def _isolate(monkeypatch, tmp_path, core_overrides, resource_deficit, extra=None):
    affect_file = tmp_path / "affect_state.json"
    wm_file = tmp_path / "working_memory.json"
    wm_file.write_text("[]")
    _seed(affect_file, core_overrides, resource_deficit, extra)
    monkeypatch.setattr(uas, "AFFECT_STATE_FILE", affect_file)
    monkeypatch.setattr(uas, "WORKING_MEMORY_FILE", wm_file)
    notes = []
    monkeypatch.setattr(wm, "update_working_memory", lambda entry: notes.append(entry))
    return affect_file, notes


def _fatigue_notes(notes):
    return [e for e in notes if "running on empty" in json.dumps(e)]


def test_high_resource_deficit_taxes_motivation(monkeypatch, tmp_path):
    # Pin motivation high; with a depleted tank (rd well above the 0.55 line) the
    # tax must pull motivation lower than the same state with a full tank.
    affect_file, _ = _isolate(monkeypatch, tmp_path, {"motivation": 0.95}, resource_deficit=0.90)
    uas.update_affect_state(context=None)
    taxed = json.loads(affect_file.read_text())["core_signals"]["motivation"]

    affect_file2, _ = _isolate(monkeypatch, tmp_path, {"motivation": 0.95}, resource_deficit=0.10)
    uas.update_affect_state(context=None)
    untaxed = json.loads(affect_file2.read_text())["core_signals"]["motivation"]

    assert taxed < untaxed, f"fatigue tax did not lower motivation ({taxed} !< {untaxed})"


def test_tax_is_floored_not_a_spiral(monkeypatch, tmp_path):
    # Even from a low motivation under maximum fatigue, the tax cannot crush
    # motivation below the baseline*0.5 floor in a single cycle.
    affect_file, _ = _isolate(monkeypatch, tmp_path, {"motivation": 0.05}, resource_deficit=1.0)
    uas.update_affect_state(context=None)
    core = json.loads(affect_file.read_text())["core_signals"]
    assert 0.0 <= core["motivation"] <= 1.0
    floor = max(0.0, uas.CORE_BASELINES.get("motivation", 0.5) * 0.5)
    assert core["motivation"] >= floor - 1e-9


def test_fatigue_note_fires_once_on_crossing(monkeypatch, tmp_path):
    affect_file, notes = _isolate(
        monkeypatch, tmp_path, {"motivation": 0.95}, resource_deficit=0.90
    )
    uas.update_affect_state(context=None)
    assert len(_fatigue_notes(notes)) == 1, "fatigue note should surface exactly once on crossing"
    assert json.loads(affect_file.read_text()).get("_rd_fatigue_noted") is True

    # A second cycle still fatigued must NOT re-emit the note (one-shot).
    notes.clear()
    uas.update_affect_state(context=None)
    assert _fatigue_notes(notes) == [], "fatigue note re-fired while still fatigued"


def test_low_deficit_applies_no_fatigue_tax(monkeypatch, tmp_path):
    # Below the fatigue line and with no stress streak, the block is a no-op note-wise.
    affect_file, notes = _isolate(
        monkeypatch, tmp_path, {"motivation": 0.60}, resource_deficit=0.30
    )
    uas.update_affect_state(context=None)
    assert _fatigue_notes(notes) == []
    assert not json.loads(affect_file.read_text()).get("_rd_fatigue_noted")
