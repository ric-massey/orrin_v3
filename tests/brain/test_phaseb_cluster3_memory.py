"""Phase B cluster 3 — memory about his world (B1, B3, B2).

Fixtures are Run 13 artifacts: a stratified 204-row sample of long memory at death
(72 % "📝 Working memory summary: 🧠 Chose: …") and working memory at death.
"""
from __future__ import annotations

import json
from pathlib import Path

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "run13"


# ── B1: telemetry stays out of working memory ────────────────────────────────

def test_finalize_writes_no_selection_log_to_working_memory():
    from brain.paths import WORKING_MEMORY_FILE
    from brain.think.think_utils.finalize import finalize_cycle

    class _Speaker:
        def speak_final(self, *a, **k):
            return None

    WORKING_MEMORY_FILE.write_text("[]")
    ctx = {"affect_state": {"core_signals": {}}, "cycle_count": {"count": 5},
           "last_function_chosen": "reflection"}
    finalize_cycle(ctx, "", "reflection", {"via": "multi-factor"}, _Speaker())
    wm = json.loads(WORKING_MEMORY_FILE.read_text() or "[]")
    texts = [str(e.get("content", "")) for e in wm if isinstance(e, dict)]
    for marker in ("🧠 Chose:", "⏳ Last active", "✅ Rewarded", "↔ Intake", "⚠️ Cognition"):
        assert not any(marker in t for t in texts), marker


def test_metacog_alarms_go_to_trace_not_working_memory(monkeypatch):
    from brain.cognition import metacog
    from brain.paths import WORKING_MEMORY_FILE
    WORKING_MEMORY_FILE.write_text("[]")
    monkeypatch.setattr(metacog, "metacog_analyze",
                        lambda ctx: ["Goal avoidance: 21 consecutive cycles without taking action."])
    monkeypatch.setattr("brain.cognition.behavioral_adaptation.apply_behavioral_adaptations",
                        lambda *a, **k: None)
    monkeypatch.setattr("brain.cognition.knowledge_formation.form_from_observations",
                        lambda *a, **k: None)
    ctx = {"metacog": {"entries": [{"phase": "select", "note": "picked reflection"}]},
           "cycle_count": {"count": 1}}
    metacog.metacog_flush(ctx)
    wm = json.loads(WORKING_MEMORY_FILE.read_text() or "[]")
    assert not any("[metacog" in str(e.get("content", "")) for e in wm if isinstance(e, dict))


# ── B3: long memory keeps his world ──────────────────────────────────────────

def test_prune_keeps_world_findings_and_bounds_self_logs(tmp_path, monkeypatch):
    from brain.cog_memory import long_memory as lm
    f = tmp_path / "long_memory.json"
    monkeypatch.setattr(lm, "LONG_MEMORY_FILE", f)
    monkeypatch.setattr("brain.cognition.self_state.ethics.update_values_with_lessons",
                        lambda kept: None)
    rows = json.loads((FIX / "long_memory_sample.json").read_text())
    world_before = [r["id"] for r in rows if lm.is_world_finding(r)]
    assert world_before   # Run 13's research / rss / web reads are in the sample
    f.write_text(json.dumps(rows))
    lm.prune_long_memory(max_total=100)
    kept = json.loads(f.read_text())
    kept_ids = {r.get("id") for r in kept}
    assert set(world_before) <= kept_ids, "a world finding was evicted"
    self_logs = [r for r in kept if r.get("event_type") in lm._SELF_LOG_EVENT_TYPES]
    assert len(self_logs) <= int(100 * lm._SELF_LOG_MAX_SHARE) + 1   # + the prune summary


def test_own_state_files_are_not_world_perception(tmp_path, monkeypatch):
    from brain.cognition.perception import look_around as la
    from brain.paths import DATA_DIR
    assert la._is_own_state(DATA_DIR.parent, f"{DATA_DIR.name}/cycle_count.json")
    assert la._is_own_state(tmp_path, "brain/data/cycle_count.json.lock")
    assert not la._is_own_state(tmp_path, "inbox/letter_from_ric.txt")


# ── B2: appraisal reads structured events, not his own alarms ────────────────

_HIGH_COPING = {"core_signals": {"confidence": 0.9, "motivation": 0.9}, "resource_deficit": 0.0}


def test_working_memory_at_death_moves_no_affect():
    from brain.control_signals.appraisal import appraise_working_memory
    wm = json.loads((FIX / "working_memory_at_death.json").read_text())
    goals = ["Understand evolutionary biology more deeply",
             "Characterize what makes my memory use (RSS) climb"]
    assert appraise_working_memory(wm, goals, _HIGH_COPING, lookback=len(wm), mood=0.3) == []


def test_world_failure_is_circumstance_not_self():
    from brain.control_signals import appraisal as ap
    ap.drain_appraisal_events()
    import brain.goal_io as gio
    from types import SimpleNamespace
    title = "Understand The Daily Stoic more deeply — round 21"
    gio._queue_outcome_appraisal(
        {"title": title, "goal": SimpleNamespace(last_error="no URLs to fetch")}, "failed")
    gio._queue_outcome_appraisal(
        {"title": "Write the tides memo", "goal": SimpleNamespace(last_error=None)}, "done")
    events = ap.drain_appraisal_events()
    assert events[0]["agency"] == "circumstance" and events[0]["outcome"] == "block"
    assert events[0]["repeated"] is True
    assert events[1]["agency"] == "self" and events[1]["outcome"] == "help"

    rows = ap.appraise_structured(events, [title], _HIGH_COPING, mood=0.0)
    by = {}
    for r in rows:
        by.setdefault(r["about"], {}).setdefault(r["emotion"], 0.0)
        by[r["about"]][r["emotion"]] += r["delta"]
    # A repeated world failure is an impasse, not his social penalty / a reward.
    assert by[title].get("impasse_signal", 0) > 0
    assert "social_penalty" not in by[title] and by[title].get("motivation", 0) <= 0
    assert by["Write the tides memo"].get("reward_positive", 0) > 0


def test_a_persons_words_still_appraised():
    from brain.control_signals.appraisal import appraise_working_memory
    wm = [{"event_type": "user_input",
           "content": "You finally solved the parser bug and the build is working now."}]
    rows = appraise_working_memory(wm, ["fix the parser bug"], _HIGH_COPING, mood=0.2)
    assert any(r["emotion"] == "reward_positive" for r in rows)
