# AR6 (CODEBASE_AUDIT_2026-07-01 M1): long-memory self-pollution. A periodic
# instrumentation event recurring with only its numbers changed (mismatch=0.42
# vs 0.43) slipped the prefix dedup and piled up 34–39 copies each, evicting
# real findings. The dedup key now digit-normalizes periodic event types, and
# per-cycle prediction errors no longer write to long memory at all (they go to
# a capped metrics log).
import json

import pytest

from brain.cog_memory import long_memory as lm


def test_periodic_event_with_fresh_numbers_is_deduped(tmp_path, monkeypatch):
    monkeypatch.setattr(lm, "LONG_MEMORY_FILE", tmp_path / "long_memory.json")
    lm.update_long_memory(
        "[prediction error] 'motivation rises' did not materialise (mismatch=0.42). Updating internal model.",
        event_type="prediction_error",
    )
    for m in (0.43, 0.57, 0.91):
        lm.update_long_memory(
            f"[prediction error] 'motivation rises' did not materialise (mismatch={m:.2f}). Updating internal model.",
            event_type="prediction_error",
        )
    entries = json.loads((tmp_path / "long_memory.json").read_text())
    assert len(entries) == 1, "same periodic event with fresh numbers must collapse"


def test_distinct_periodic_events_both_store(tmp_path, monkeypatch):
    monkeypatch.setattr(lm, "LONG_MEMORY_FILE", tmp_path / "long_memory.json")
    lm.update_long_memory(
        "[prediction error] 'motivation rises' did not materialise (mismatch=0.42).",
        event_type="prediction_error",
    )
    lm.update_long_memory(
        "[prediction error] 'exploration falls after impasse' did not materialise (mismatch=0.42).",
        event_type="prediction_error",
    )
    entries = json.loads((tmp_path / "long_memory.json").read_text())
    assert len(entries) == 2


def test_normal_events_keep_exact_match_dedup(tmp_path, monkeypatch):
    monkeypatch.setattr(lm, "LONG_MEMORY_FILE", tmp_path / "long_memory.json")
    lm.update_long_memory("I found that Rayleigh number 1708 governs onset.",
                          event_type="summary")
    lm.update_long_memory("I found that Rayleigh number 2000 governs nothing similar.",
                          event_type="summary")
    entries = json.loads((tmp_path / "long_memory.json").read_text())
    # non-periodic types are NOT digit-normalized — different content both store
    assert len(entries) == 2


def test_fire_surprise_writes_metrics_not_long_memory(tmp_path, monkeypatch):
    import brain.cognition.prediction_helpers as ph
    import brain.paths as paths
    monkeypatch.setattr(lm, "LONG_MEMORY_FILE", tmp_path / "long_memory.json")
    monkeypatch.setattr(paths, "DATA_DIR", tmp_path)

    ctx = {"affect_state": {"core_signals": {}}}
    ph._fire_surprise("motivation rises within two cycles", 0.8, ctx)

    metrics = tmp_path / "prediction_metrics.jsonl"
    assert metrics.exists(), "prediction error must land in the metrics log"
    row = json.loads(metrics.read_text().splitlines()[0])
    assert row["mismatch"] == pytest.approx(0.8)
    assert not (tmp_path / "long_memory.json").exists(), \
        "per-cycle prediction errors must not write long memory"
