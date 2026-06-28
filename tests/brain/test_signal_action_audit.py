"""R1 from SIGNAL_TO_ACTION_AUDIT_2026-06-18: the signal→action follow-through
audit — the action-class classifier + the deferred "did it land / did the signal
relieve?" outcome."""
import brain.cognition.signal_action_audit as sa


def _reset():
    with sa._lock:
        sa._window.clear()
        sa._pending.clear()


# ── classifier ──────────────────────────────────────────────────────────────

def test_classifier_covers_seven_classes():
    assert sa.classify_action("leave_note") == sa.PRODUCTIVE          # _OUTWARD_HIGH
    assert sa.classify_action("seek_novelty") == sa.ORIENTING         # _OUTWARD_MED
    assert sa.classify_action("survey_environment") == sa.ORIENTING   # _OUTWARD_LOW
    assert sa.classify_action("speak") == sa.COMMUNICATIVE
    assert sa.classify_action("notify_user") == sa.COMMUNICATIVE      # over outward_artifact
    assert sa.classify_action("attempt_regulation") == sa.REGULATORY
    assert sa.classify_action("metacog_flush") == sa.MAINTENANCE
    assert sa.classify_action("threat_response") == sa.REFLEX
    assert sa.classify_action("leave_note", blocked=True) == sa.FAILED_BLOCKED
    assert sa.classify_action("totally_unknown_fn") == sa.MAINTENANCE  # never over-credit
    assert sa.classify_action("") == sa.MAINTENANCE


# ── follow-through: relief + class-rise ──────────────────────────────────────

def test_unaudited_pattern_returns_no_stub():
    _reset()
    assert sa.note_armed("id1", "some_unmapped_pattern") is None


def test_landed_when_class_rose_and_signal_fell(monkeypatch):
    _reset()
    # impasse 0.80 at arm → 0.50 at resolve (fell → relieved).
    seq = iter([0.80, 0.50])
    monkeypatch.setattr(sa, "_read_signal", lambda k: next(seq))
    written = {}
    monkeypatch.setattr(sa, "_write_outcome", lambda aid, oc: written.update({aid: oc}))

    stub = sa.note_armed("idA", "goal_avoidance", cycle=10)
    assert stub["status"] == "pending" and stub["expected_class"] == sa.PRODUCTIVE

    # Window: no productive before arm; productive fires after.
    monkeypatch.setattr(sa, "get_cycle_count", lambda: 0, raising=False)
    for c, fn in [(11, "leave_note"), (12, "metacog_flush"), (14, "write_tool")]:
        monkeypatch.setattr(sa, "get_cycle_count", lambda c=c: c)
        sa.tick({}, fn)
    # Tick at arm+k (18) → triggers resolution.
    monkeypatch.setattr(sa, "get_cycle_count", lambda: 18)
    sa.tick({}, "metacog_flush")

    oc = written["idA"]
    assert oc["status"] == "resolved"
    assert oc["expected_class_after"] == 2 and oc["expected_class_before"] == 0
    assert oc["expected_class_rose"] is True
    assert oc["signal_delta"] == -0.30 and oc["relieved"] is True
    assert oc["landed"] is True


def test_not_landed_when_signal_rose(monkeypatch):
    _reset()
    seq = iter([0.40, 0.70])   # impasse climbed → not relieved
    monkeypatch.setattr(sa, "_read_signal", lambda k: next(seq))
    written = {}
    monkeypatch.setattr(sa, "_write_outcome", lambda aid, oc: written.update({aid: oc}))

    sa.note_armed("idB", "goal_avoidance", cycle=100)
    monkeypatch.setattr(sa, "get_cycle_count", lambda: 108)
    sa.tick({}, "leave_note")   # productive fired, but signal worsened

    oc = written["idB"]
    assert oc["relieved"] is False
    assert oc["landed"] is False   # right class, but no relief → did not land


def test_resolves_only_after_k_cycles(monkeypatch):
    _reset()
    monkeypatch.setattr(sa, "_read_signal", lambda k: 0.5)
    written = {}
    monkeypatch.setattr(sa, "_write_outcome", lambda aid, oc: written.update({aid: oc}))
    sa.note_armed("idC", "rut", cycle=50)
    # Before the window elapses, nothing resolves.
    monkeypatch.setattr(sa, "get_cycle_count", lambda: 55)
    sa.tick({}, "seek_novelty")
    assert "idC" not in written
    assert len(sa._pending) == 1
    # At arm + K it resolves and is removed from pending.
    monkeypatch.setattr(sa, "get_cycle_count", lambda: 58)
    sa.tick({}, "seek_novelty")
    assert "idC" in written and len(sa._pending) == 0
