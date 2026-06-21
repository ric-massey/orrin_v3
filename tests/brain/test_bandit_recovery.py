# tests/brain/test_bandit_recovery.py
# Verifies the bucketed contextual bandit coerces corrupt/legacy state without
# crashing and that bucketing + update()/choose() behave correctly per affect bucket.

from __future__ import annotations

import json
import sys
from pathlib import Path

# Ensure brain/ is on the path
BRAIN_DIR = Path(__file__).resolve().parent.parent.parent / "brain"
if str(BRAIN_DIR) not in sys.path:
    sys.path.insert(0, str(BRAIN_DIR))

from brain.think.bandit.contextual_bandit import (
    _validate_state, _context_bucket, update, choose, expected_reward,
)


# ---------- helpers ----------

def _write_state(tmp_path: Path, state: dict) -> Path:
    p = tmp_path / "bandit_state.json"
    p.write_text(json.dumps(state), encoding="utf-8")
    return p


def _patch_path(monkeypatch, new_path: Path):
    import brain.think.bandit.contextual_bandit as _cb
    monkeypatch.setattr(_cb, "BANDIT_STATE_PATH", new_path)


# ---------- bucketing ----------

def test_bucketing_from_emotion_onehot():
    assert _context_bucket({"emo_exploration_drive": 1.0}) == "exploration_drive"
    assert _context_bucket({"emo_impasse_signal": 1.0}) == "impasse_signal"
    assert _context_bucket({"emo_social_deficit": 1.0}) == "social_deficit"


def test_bucketing_defaults_to_stable():
    assert _context_bucket({"emo_positive_valence": 1.0}) == "stable"
    assert _context_bucket({}) == "stable"
    assert _context_bucket(None) == "stable"


# ---------- recovery / migration ----------

def test_corrupt_bucket_stat_coerced(tmp_path, monkeypatch):
    """A non-dict action stat must be coerced; update() must not raise."""
    p = _write_state(tmp_path, {"buckets": {"exploration_drive": {"look_outward": 0.0}}, "counts": {}})
    _patch_path(monkeypatch, p)
    update("look_outward", {"emo_exploration_drive": 1.0}, reward=0.5)  # must not raise
    s = json.loads(p.read_text())["buckets"]["exploration_drive"]["look_outward"]
    assert isinstance(s, dict) and "n" in s and "q" in s


def test_legacy_linear_state_migrates(tmp_path, monkeypatch):
    """Old weights/alpha/beta/traces are dropped; counts + suppression survive."""
    p = _write_state(tmp_path, {
        "weights": {"x": {"__bias__": 0.5}}, "alpha": {"x": 2.0}, "traces": {"x": {}},
        "counts": {"x": 7}, "suppressed": {"y": 3},
    })
    _patch_path(monkeypatch, p)
    update("x", {"emo_impasse_signal": 1.0}, reward=0.4)
    state = json.loads(p.read_text())
    assert "weights" not in state and "alpha" not in state and "traces" not in state
    assert state["counts"]["x"] >= 8                      # preserved + incremented
    assert state["suppressed"].get("y") == 3              # suppression preserved
    assert "x" in state["buckets"]["impasse_signal"]      # update landed in the bucket


def test_valid_state_unchanged(tmp_path, monkeypatch):
    """A valid bucketed state must not be mutated by _validate_state."""
    st = {"buckets": {"stable": {"reflect": {"n": 4, "q": 0.3}}}, "counts": {"reflect": 4}, "suppressed": {}}
    _validate_state(st)
    assert st["buckets"]["stable"]["reflect"] == {"n": 4, "q": 0.3}
    assert st["counts"]["reflect"] == 4


# ---------- behaviour ----------

def test_reward_moves_value_in_bucket(tmp_path, monkeypatch):
    p = _write_state(tmp_path, {"buckets": {}, "counts": {}})
    _patch_path(monkeypatch, p)
    feats = {"emo_exploration_drive": 1.0}
    update("seek_novelty", feats, reward=1.0)
    assert expected_reward("seek_novelty", feats) > 0.0
    # different bucket has no value for the same action
    assert expected_reward("seek_novelty", {"emo_social_deficit": 1.0}) == 0.0


def test_choose_returns_valid_action_and_scores(tmp_path, monkeypatch):
    p = _write_state(tmp_path, {"buckets": {}, "counts": {}})
    _patch_path(monkeypatch, p)
    picked = choose(["a", "b", "c"], {"emo_stable": 1.0}, epsilon=0.0)
    assert picked in {"a", "b", "c"}
    picked2, info = choose(["a", "b", "c"], {"emo_stable": 1.0}, epsilon=0.0, return_scores=True)
    assert picked2 in {"a", "b", "c"}
    assert info["bucket"] == "stable" and isinstance(info["scores"], dict)
