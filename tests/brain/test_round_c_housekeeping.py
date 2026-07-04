# Run 4 fix Round C (RUN4_FIX_PLAN_2026-07-04 §3): housekeeping sweep. Focused
# assertions for the behavioural items (the rotation/cap/slim items are exercised
# by their own writers; these pin the ones with observable behaviour).


def test_3_1_social_penalty_registered_in_signal_vocabulary():
    """§3.1 — social_penalty (and loss_signal) must be in CORE_BASELINES so they
    seed into `core` and the emotion buffer stops dropping them as 'unknown'."""
    from brain.control_signals.setpoints import CORE_BASELINES
    assert "social_penalty" in CORE_BASELINES
    assert "loss_signal" in CORE_BASELINES


def test_3_1_buffer_no_longer_drops_social_penalty():
    from brain.control_signals.signal_buffer import drain_signal_queue
    core = {"social_penalty": 0.0}
    state = {"_emotion_queue": [
        {"emotion": "social_penalty", "per_cycle": 0.1, "cycles_left": 2, "source": "t"},
    ]}
    drain_signal_queue(state, core)
    assert core["social_penalty"] > 0.0   # applied, not dropped


def test_3_3_attention_weights_floored(tmp_path, monkeypatch):
    import brain.think.attention_weights as aw
    monkeypatch.setattr(aw, "_WEIGHTS_PATH", tmp_path / "aw.json", raising=False)
    # Drive s1 down with repeated negative reward; it must never hit 0.0.
    for _ in range(200):
        aw.update_attention_weights({"attention_sources": ["s1"]}, reward=0.0)
    assert aw.get_source_weight("s1") >= 0.01


def test_3_9_window_summary_sums_midnight_straddle(tmp_path, monkeypatch):
    import brain.cognition.planning.outcome_metrics as om
    monkeypatch.setattr(om, "OUTCOME_METRICS_FILE", tmp_path / "om.json", raising=False)
    # Two daily rows from one straddling run.
    from brain.utils.json_utils import save_json
    save_json(om.OUTCOME_METRICS_FILE, [
        {"date": "2026-07-03", "goals_completed": 4, "goals_failed": 1, "active_goals": 5},
        {"date": "2026-07-04", "goals_completed": 6, "goals_failed": 2, "active_goals": 3},
    ])
    monkeypatch.setattr(om, "flush", lambda: {})   # don't re-flush a live session over the fixture
    out = om.window_summary(dates=["2026-07-03", "2026-07-04"])
    assert out["goals_completed"] == 10   # summed, not one half-run
    assert out["goals_failed"] == 3
    assert out["active_goals"] == 3       # _LATEST takes newest row


def test_3_8_library_offline_starter_stocks_shelf(tmp_path, monkeypatch):
    import brain.cognition.language.library as lib
    monkeypatch.setattr(lib, "_LIB", tmp_path / "library", raising=False)
    # _READS_FILE is derived from _LIB at import — repoint it too so read_book's
    # book_reads write stays in tmp (else it breaches live-state isolation).
    monkeypatch.setattr(lib, "_READS_FILE", tmp_path / "library" / "book_reads.json",
                        raising=False)
    # Network fetch returns nothing (offline); starter must still stock the shelf.
    monkeypatch.setattr(lib, "fetch_books", lambda ids: 0)
    got = lib.populate_starter(3)
    assert got >= 1
    assert lib.size_chars() > 0
    title, text = lib.read_book()
    assert text and len(text) > 100
