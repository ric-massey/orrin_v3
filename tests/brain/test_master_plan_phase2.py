# Phase 2 regression tests (docs/archive/ORRIN_MASTER_PLAN.md — from records to a life).
#
# 2.1 session_epilogue: ordinary shutdown appends a session_close entry without
#     closing the chapter, never raises, never empty.
# 2.2 review_failures: ≥3 new goal_failure memories cluster into a
#     failure_pattern memory whose related_memory_ids point at the failures;
#     the trigger gate holds below the threshold.
# 2.3 _eval_b7: the restart-retrieval benchmark resolves failure-pattern links.
import json

import pytest

import brain.cognition.selfhood.autobiography as auto_mod
import brain.cognition.reflection.review_failures as rvf


@pytest.fixture
def _iso_autobio(monkeypatch, tmp_path):
    monkeypatch.setattr(auto_mod, "AUTOBIOGRAPHY", tmp_path / "autobiography.json")
    monkeypatch.setattr(auto_mod, "NARRATIVE_PRESSURE_FILE", tmp_path / "pressure.json")
    monkeypatch.setattr(auto_mod, "log_activity", lambda *a, **k: None)
    monkeypatch.setattr(auto_mod, "log_private", lambda *a, **k: None)
    return tmp_path


def _failure_entry(i, reason="wikipedia fetch timed out"):
    return {
        "id": f"fail-{i}",
        "timestamp": f"2026-06-11T0{i}:00:00+00:00",
        "content": f"Failed goal: research topic {i}. Reason: {reason}.",
        "event_type": "goal_failure",
        "importance": 3,
    }


# ── 2.1 session epilogue ─────────────────────────────────────────────────────

def test_session_epilogue_appends_without_closing_chapter(_iso_autobio, monkeypatch):
    auto_mod.save_autobiography({
        "chapters": [{"number": 1, "title": "T", "started_ts": "x",
                      "narrative": "n", "entries": []}],
    })
    # Force the rule-based path.
    monkeypatch.setattr(rvf, "load_json", rvf.load_json)  # no-op; keep imports honest
    import brain.utils.llm_gate as gate
    monkeypatch.setattr(gate, "llm_available", lambda: False)

    auto_mod.session_epilogue({"cycle_count": 42})

    saved = auto_mod.load_autobiography()
    ch = saved["chapters"][-1]
    entries = [e for e in ch.get("entries", []) if e.get("type") == "session_close"]
    assert entries, "session_close entry missing"
    assert len(entries[0]["text"]) > 20, "reflection must never be empty"
    assert "closed_ts" not in ch, "epilogue must not close the chapter (death's job)"
    assert saved.get("last_session_close")
    assert saved.get("last_updated") != saved.get("last_session_close")


def test_session_epilogue_never_raises(_iso_autobio, monkeypatch):
    # Even with a poisoned autobiography store, shutdown must not be blocked.
    monkeypatch.setattr(auto_mod, "load_autobiography",
                        lambda: (_ for _ in ()).throw(RuntimeError("disk gone")))
    auto_mod.session_epilogue({})  # must not raise


# ── 2.2 failure ledger ───────────────────────────────────────────────────────

@pytest.fixture
def _iso_review(monkeypatch, tmp_path):
    lm_file = tmp_path / "long_memory.json"
    monkeypatch.setattr(rvf, "LONG_MEMORY_FILE", lm_file)
    monkeypatch.setattr(rvf, "_REVIEW_STATE_FILE", tmp_path / "review_state.json")
    monkeypatch.setattr(rvf, "log_activity", lambda *a, **k: None)
    return lm_file


def test_review_failures_gate_holds_below_threshold(_iso_review):
    _iso_review.write_text(json.dumps([_failure_entry(1), _failure_entry(2)]))
    msg = rvf.review_failures({})
    assert "nothing to consolidate" in msg


def test_review_failures_emits_pattern_with_links(_iso_review, monkeypatch):
    import brain.cog_memory.long_memory as lm_mod
    written = []
    monkeypatch.setattr(lm_mod, "update_long_memory",
                        lambda content, **k: written.append((content, k)))
    pressure = []
    monkeypatch.setattr(auto_mod, "add_narrative_pressure",
                        lambda amt, why="": pressure.append(amt))

    _iso_review.write_text(json.dumps(
        [_failure_entry(i) for i in range(1, 5)]   # 4 similar failures
    ))
    msg = rvf.review_failures({})

    assert written, "no failure_pattern memory emitted"
    content, kwargs = written[0]
    assert kwargs["event_type"] == "failure_pattern"
    assert kwargs["importance"] == 4
    assert set(kwargs["related_memory_ids"]) >= {"fail-1", "fail-2", "fail-3"}
    assert "pattern" in content.lower()
    assert pressure == [0.25], "patterns must feed narrative pressure at thread-pivot scale"
    assert "consolidated" in msg

    # Second run: nothing new → gate holds again.
    msg2 = rvf.review_failures({})
    assert "nothing to consolidate" in msg2


def test_failure_pattern_discount(_iso_review):
    entries = [_failure_entry(i) for i in range(1, 4)]
    entries.append({
        "id": "pat-1",
        "content": "Failure pattern: 3 similar goal failures — recurring theme: "
                   "research, topic, wikipedia, timed. This is the kind of thing I keep getting wrong.",
        "event_type": "failure_pattern",
        "related_memory_ids": ["fail-1", "fail-2", "fail-3"],
    })
    _iso_review.write_text(json.dumps(entries))
    hit = rvf.failure_pattern_discount("research a wikipedia topic about timed fetching")
    miss = rvf.failure_pattern_discount("compose a short poem about gardens")
    assert hit > 0.0
    assert miss == 0.0


# ── 2.3 restart-retrieval benchmark ──────────────────────────────────────────

def test_eval_b7_resolves_links(monkeypatch, tmp_path):
    import brain.benchmarks as bm  # noqa: F401 — module path is `benchmarks` on sys.path
    import brain.benchmarks as bench

    auto_file = tmp_path / "autobiography.json"
    pressure_file = tmp_path / "pressure.json"
    lm_file = tmp_path / "long_memory.json"
    auto_file.write_text(json.dumps(
        {"chapters": [{"number": 1, "entries": [{"text": "x"}]}]}))
    pressure_file.write_text(json.dumps({"running_total": 0.4, "last_check_ts": "t"}))
    lm_file.write_text(json.dumps([
        _failure_entry(1), _failure_entry(2),
        {"id": "pat-1", "event_type": "failure_pattern", "content": "p",
         "related_memory_ids": ["fail-1", "fail-2"]},
    ]))

    monkeypatch.setattr(bench, "AUTOBIOGRAPHY", auto_file)
    monkeypatch.setattr(bench, "NARRATIVE_PRESSURE_FILE", pressure_file)
    monkeypatch.setattr(bench, "LONG_MEMORY_FILE", lm_file)

    res = bench._eval_b7()
    assert res["status"] == "pass", res
    assert res["links_resolve"] is True

    # A dangling link must fail the benchmark.
    lm_file.write_text(json.dumps([
        {"id": "pat-1", "event_type": "failure_pattern", "content": "p",
         "related_memory_ids": ["fail-GONE"]},
    ]))
    res2 = bench._eval_b7()
    assert res2["status"] == "fail"
    assert "fail-GONE" in res2.get("dangling_ids", [])
