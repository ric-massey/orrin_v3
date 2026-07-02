"""B3 / P5 — homeostatic decay: diagnosis-confirmed tune of the EXISTING law.

The 2026-07-01 run confirmed drives pin (~0.84 all life) because every-cycle pumps
beat the flat per-call restoring rate. The fix is a time-at-ceiling accelerator on
the existing per-call pull (homeostasis.update_pin_streaks / pin_multiplier), a
master ablation switch (ORRIN_SIGNAL_DECAY), and a CTRL-style repetition guard in
native_lm.generate (which previously had NO repetition control).
See docs/.../B3_DECAY_DIAGNOSIS_2026-07-01.md.
"""
import json
from datetime import datetime, timezone

import pytest

import brain.control_signals.homeostasis as hom
import brain.control_signals.update_signal_state as uas
from brain.control_signals.setpoints import setpoint


# ── isolation (same pattern as test_signal_invariants.py) ───────────────────────

def _seed_affect_state(path, core_overrides, extra=None):
    core = dict(uas.CORE_BASELINES)
    core.update(core_overrides)
    state = {
        "core_signals": core,
        "resource_deficit": 0.15,
        "social_deficit": 0.0,
        "signal_stability": 1.0,
        # NOW, not 1970 — a stale stamp makes hours_passed huge, and the
        # hours-based apply_restoring_forces then fully decays everything on the
        # first call, masking the per-call pull these tests measure.
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }
    state.update(extra or {})
    path.write_text(json.dumps(state))


def _isolate(monkeypatch, tmp_path, core_overrides, extra=None):
    affect_file = tmp_path / "control_signals_state.json"
    wm_file = tmp_path / "working_memory.json"
    wm_file.write_text("[]")
    _seed_affect_state(affect_file, core_overrides, extra)
    monkeypatch.setattr(uas, "SIGNAL_STATE_FILE", affect_file)
    monkeypatch.setattr(uas, "WORKING_MEMORY_FILE", wm_file)
    return affect_file


def _run_idle_cycles(affect_file, n):
    for _ in range(n):
        uas.update_signal_state(context=None)
    return json.loads(affect_file.read_text())


# ── the accelerator primitives ──────────────────────────────────────────────────

def test_fresh_spike_decays_at_base_rate():
    """A signal with no pin streak gets multiplier 1.0 — acute urgency untouched."""
    state = {}
    assert hom.pin_multiplier(state, "motivation") == 1.0


def test_streak_grows_while_pinned_and_clears_on_relax():
    state = {}
    core = {"motivation": setpoint("motivation") + hom.PIN_MARGIN + 0.1}
    for _ in range(3):
        hom.update_pin_streaks(state, core)
    assert state["_pin_streaks"]["motivation"] == 3
    # relax below the margin → streak clears, accelerator releases
    core["motivation"] = setpoint("motivation") + hom.PIN_MARGIN - 0.05
    hom.update_pin_streaks(state, core)
    assert "motivation" not in state["_pin_streaks"]
    assert hom.pin_multiplier(state, "motivation") == 1.0


def test_multiplier_grows_with_time_at_ceiling_and_caps():
    state = {"_pin_streaks": {"motivation": int(hom.PIN_ACCEL_WINDOW)}}
    assert hom.pin_multiplier(state, "motivation") == pytest.approx(2.0)
    state["_pin_streaks"]["motivation"] = 10_000
    assert hom.pin_multiplier(state, "motivation") == pytest.approx(hom.PIN_ACCEL_MAX)


def test_ablation_flag(monkeypatch):
    monkeypatch.delenv("ORRIN_SIGNAL_DECAY", raising=False)
    assert hom.signal_decay_enabled() is True
    monkeypatch.setenv("ORRIN_SIGNAL_DECAY", "0")
    assert hom.signal_decay_enabled() is False


# ── the wired behavior: pinned drives relax over idle cycles ────────────────────

def test_pinned_drive_relaxes_over_idle_cycles(monkeypatch, tmp_path):
    """Regression on the wired per-call pull: a drive seeded in the 07-01 run's
    pinned band (0.84) must leave it over idle cycles, and the accelerator's
    streaks must be engaged along the way."""
    monkeypatch.delenv("ORRIN_SIGNAL_DECAY", raising=False)
    affect_file = _isolate(monkeypatch, tmp_path, {"motivation": 0.84, "confidence": 0.82})

    saved = _run_idle_cycles(affect_file, 30)

    core = saved["core_signals"]
    assert core["motivation"] < 0.70, (
        f"motivation stayed pinned at {core['motivation']} — restoring pull broken")
    assert core["confidence"] < 0.70


def test_ablation_off_reproduces_hot_and_flat(monkeypatch, tmp_path):
    """With the per-call pull ablated, the same seed must stay pinned — the
    'hot and flat' failure the panel needs to demonstrate."""
    monkeypatch.setenv("ORRIN_SIGNAL_DECAY", "0")
    affect_file = _isolate(monkeypatch, tmp_path, {"motivation": 0.84})

    saved = _run_idle_cycles(affect_file, 30)

    assert saved["core_signals"]["motivation"] > 0.78, (
        "ablation flag off should preserve the plateau (only the hours-based decay "
        "runs, which is ~0 per cycle)")


def test_pin_streaks_persist_in_state_file(monkeypatch, tmp_path):
    monkeypatch.delenv("ORRIN_SIGNAL_DECAY", raising=False)
    affect_file = _isolate(monkeypatch, tmp_path, {"motivation": 0.84})

    saved = _run_idle_cycles(affect_file, 2)

    streaks = saved.get("_pin_streaks") or {}
    assert streaks.get("motivation", 0) >= 1


# ── the repetition guard ─────────────────────────────────────────────────────────

def test_repetition_penalty_suppresses_recent_tokens():
    torch = pytest.importorskip("torch")
    from brain.cognition.language.native_lm import _apply_repetition_penalty

    logits = torch.tensor([2.0, 2.0, -1.0, 2.0])
    _apply_repetition_penalty(logits, [1, 2], penalty=2.0)
    assert float(logits[0]) == pytest.approx(2.0)      # unseen token untouched
    assert float(logits[1]) == pytest.approx(1.0)      # positive logit divided
    assert float(logits[2]) == pytest.approx(-2.0)     # negative logit multiplied
    assert float(logits[3]) == pytest.approx(2.0)


def test_repetition_penalty_noop_at_one():
    torch = pytest.importorskip("torch")
    from brain.cognition.language.native_lm import _apply_repetition_penalty

    logits = torch.tensor([1.5, -0.5])
    _apply_repetition_penalty(logits, [0, 1], penalty=1.0)
    assert float(logits[0]) == pytest.approx(1.5)
    assert float(logits[1]) == pytest.approx(-0.5)
