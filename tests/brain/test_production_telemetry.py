"""F6 — durable production-loop telemetry (PRODUCTION_LOOP_CLOSURE).

Acceptance: commitment + lens coverage are computable from a run archive without
reading transient process memory. These verify finalize writes one bounded line
per cycle with the named fields, and that the effect-rejection reason is derived
from the ledger rows.
"""

import json

import brain.loop.finalize as fin


def test_effect_rejection_reason_from_rows():
    assert fin._effect_rejection_reason([{"significance": 0.6}]) is None
    assert fin._effect_rejection_reason([{"significance": 0.0, "dedupe": True}]) == "duplicate"
    assert fin._effect_rejection_reason(
        [{"significance": 0.0, "novelty": 0.0}]) == "low_novelty_or_boilerplate"
    assert fin._effect_rejection_reason(
        [{"significance": 0.0, "novelty": 0.5}]) == "low_significance"
    assert fin._effect_rejection_reason([]) is None


def _read_lines(path):
    return [json.loads(ln) for ln in path.read_text().splitlines() if ln.strip()]


def test_emit_writes_durable_record_with_named_fields(tmp_path, monkeypatch):
    log = tmp_path / "production_loop.jsonl"
    monkeypatch.setattr(fin, "PRODUCTION_LOOP_LOG", log)
    monkeypatch.setattr(fin, "get_cycle_count", lambda: 7)
    monkeypatch.setattr(fin, "_handoff_total", 0, raising=False)
    monkeypatch.setattr(fin, "_attempt_total", 0, raising=False)
    monkeypatch.setattr(fin, "_success_total", 0, raising=False)

    ctx = {
        "committed_goal": {
            "id": "g1", "title": "Write a synthesis",
            "grounded_parts": ["a", "b"],
            "definition_of_done": [{"criterion": "x", "met": False}],
            "_needs_deliberate_action": "compose_section",
        },
        "goal_lens": {"terms": ["synthesis"]},
        "_goal_lens_telemetry": {"top_signal_relevance": 0.8, "retrieval_mean_relevance": 0.4},
        "_production_effect_this_cycle": True,
        "_effect_rows_this_cycle": [{"significance": 0.6, "novelty": 0.7}],
    }
    fin._emit_production_telemetry(ctx)

    rows = _read_lines(log)
    assert len(rows) == 1
    r = rows[0]
    for field in (
        "committed_goal_present", "committed_goal_id", "goal_model_hydrated",
        "goal_lens_active", "goal_lens_top_signal_relevance",
        "goal_lens_retrieval_mean_relevance", "pending_production_action",
        "production_attempt", "production_success", "effect_rejection",
        "production_handoff_count", "production_attempt_count", "production_success_count",
    ):
        assert field in r, f"missing telemetry field {field}"
    assert r["committed_goal_present"] is True
    assert r["committed_goal_id"] == "g1"
    assert r["goal_model_hydrated"] is True
    assert r["goal_lens_active"] is True
    assert r["pending_production_action"] == "compose_section"
    assert r["production_success"] is True
    assert r["effect_rejection"] is None
    assert r["production_handoff_count"] == 1
    assert r["production_success_count"] == 1


def test_rejected_effect_is_recorded_and_counts_accumulate(tmp_path, monkeypatch):
    log = tmp_path / "production_loop.jsonl"
    monkeypatch.setattr(fin, "PRODUCTION_LOOP_LOG", log)
    monkeypatch.setattr(fin, "get_cycle_count", lambda: 1)
    monkeypatch.setattr(fin, "_handoff_total", 0, raising=False)
    monkeypatch.setattr(fin, "_attempt_total", 0, raising=False)
    monkeypatch.setattr(fin, "_success_total", 0, raising=False)

    # a duplicate effect: attempt yes, success no, reason duplicate
    fin._emit_production_telemetry({
        "_effect_rows_this_cycle": [{"significance": 0.0, "dedupe": True}],
    })
    # an empty cycle: no attempt
    fin._emit_production_telemetry({})

    rows = _read_lines(log)
    assert rows[0]["production_attempt"] is True
    assert rows[0]["production_success"] is False
    assert rows[0]["effect_rejection"] == "duplicate"
    assert rows[0]["committed_goal_present"] is False
    # counts are cumulative across cycles
    assert rows[1]["production_attempt_count"] == 1
    assert rows[1]["production_success_count"] == 0
