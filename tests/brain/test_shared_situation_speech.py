# tests/brain/test_shared_situation_speech.py
#
# P3 (Companion & Presence plan): the shared-situation speech kernels. The
# person coming back after an absence and the pinned/crowded machine become
# nameable, referent-bearing intents — composed through the one expression
# door, never scraped. A reunion outranks any artifact (the moment matters);
# host pressure sits just above the express_state last resort.

from __future__ import annotations

from brain.behavior import speech_content as sc


def _arrival_signal(from_pattern: str = "absent", silence_s: float = 900.0) -> dict:
    return {
        "source": "social_presence",
        "content": "[social_boundary] User presence crossed the threshold: absent -> present.",
        "signal_strength": 0.62,
        "tags": ["social", "presence", "door", "threshold_crossing", "arrival"],
        "from_pattern": from_pattern,
        "to_pattern": "present",
        "direction": "arrival",
        "silence_s": silence_s,
    }


def test_reunion_kernel_fires_on_arrival_after_absence():
    ctx = {"raw_signals": [_arrival_signal("absent", 900.0)]}
    kernel = sc.choose_content_kernel(ctx)
    assert kernel["intent"] == "greet_return"
    assert "15 minutes" in kernel["seed"]
    assert kernel["referent"]["type"] == "presence"


def test_reunion_kernel_names_hours_after_distant():
    ctx = {"raw_signals": [_arrival_signal("distant", 2 * 3600.0)]}
    kernel = sc.choose_content_kernel(ctx)
    assert kernel["intent"] == "greet_return"
    assert "2 hours" in kernel["seed"]


def test_reunion_outranks_artifact():
    ctx = {
        "raw_signals": [_arrival_signal()],
        "_effect_rows_this_cycle": [{"kind": "note_novel", "content_hash": "zz", "dedupe": False}],
    }
    assert sc.choose_content_kernel(ctx)["intent"] == "greet_return"


def test_nearby_pause_is_not_a_reunion(tmp_path, monkeypatch):
    import brain.paths as paths
    lm = tmp_path / "long_memory.json"
    lm.write_text("[]")
    monkeypatch.setattr(paths, "LONG_MEMORY_FILE", lm)
    ctx = {"raw_signals": [_arrival_signal("nearby", 90.0)]}
    assert sc.choose_content_kernel(ctx)["intent"] == "express_state"


def test_host_pressure_kernel_names_the_concrete_metric(tmp_path, monkeypatch):
    import brain.paths as paths
    lm = tmp_path / "long_memory.json"
    lm.write_text("[]")
    monkeypatch.setattr(paths, "LONG_MEMORY_FILE", lm)
    ctx = {"raw_signals": [{
        "source": "sensory_stream",
        "content": "The disk is 94% full — my den is getting cramped.",
        "signal_strength": 0.69,
        "tags": ["environment", "host", "den_crowded", "home", "internal"],
        "host_metric": {"name": "disk_percent", "value": 94.0},
    }]}
    kernel = sc.choose_content_kernel(ctx)
    assert kernel["intent"] == "name_shared_situation"
    assert "94% full" in kernel["seed"]  # the cause, not just the feeling
    assert kernel["referent"]["handle"] == "disk_percent=94.0"


def test_departure_never_greets(tmp_path, monkeypatch):
    import brain.paths as paths
    lm = tmp_path / "long_memory.json"
    lm.write_text("[]")
    monkeypatch.setattr(paths, "LONG_MEMORY_FILE", lm)
    sig = _arrival_signal()
    sig["direction"] = "departure"
    sig["tags"] = ["social", "presence", "door", "threshold_crossing", "departure"]
    ctx = {"raw_signals": [sig]}
    assert sc.choose_content_kernel(ctx)["intent"] == "express_state"
