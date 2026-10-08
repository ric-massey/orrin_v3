"""Phase B cluster 6 — instruments and hygiene (B14, B18, B19, B22, B27; B28 in
test_production_telemetry, B15 in cluster 4)."""
from __future__ import annotations

import gzip
import json
from types import SimpleNamespace


# ── B14: every reuse names its reader ────────────────────────────────────────

def test_spec_artifact_reuse_cites_the_new_goal(monkeypatch):
    import brain.goal_io as gio
    calls: list = []
    monkeypatch.setattr("brain.agency.effect_ledger.mark_reused_path",
                        lambda p, citing_goal_id=None: calls.append((p, citing_goal_id)))
    api = SimpleNamespace(list_goals=lambda **k: [],
                          create_goal=lambda **k: SimpleNamespace(id="g_new"))
    monkeypatch.setattr(gio, "_load_v1_tree", lambda: [])
    ctx = {"proposed_goals": [{
        "title": "Build on the tides memo", "kind": "research", "milestones": ["m"],
        "spec": {"prior": "data/goals/artifacts/g_old/research_memo.md"}}]}
    gio.sync_proposed_goals(api, ctx)
    assert calls and all(c == "g_new" for _p, c in calls)


def test_fetch_and_read_reuse_names_a_citer(monkeypatch):
    from brain.cognition import web_research as wr
    calls: list = []
    monkeypatch.setattr("brain.agency.effect_ledger.mark_reused_path",
                        lambda p, citing_goal_id=None: calls.append((p, citing_goal_id)))
    monkeypatch.setattr(wr, "_pick_url", lambda ctx: "file:///tmp/memo.md")
    monkeypatch.setattr(wr, "_get", lambda url, timeout=12: None)   # no I/O
    monkeypatch.setattr(wr, "_last_fetch", 0.0, raising=False)
    wr.fetch_and_read({})
    monkeypatch.setattr(wr, "_last_fetch", 0.0, raising=False)
    wr.fetch_and_read({"committed_goal": {"id": "g_tides", "title": "Understand tides"}})
    assert calls == [("/tmp/memo.md", "fn:fetch_and_read"), ("/tmp/memo.md", "g_tides")]


def test_library_read_names_its_reader(monkeypatch, tmp_path):
    from brain.cognition.language import library
    book = tmp_path / "pg1.txt"
    book.write_text("A short book about tides. " * 40)
    monkeypatch.setattr(library, "_LIB", tmp_path)
    calls: list = []
    monkeypatch.setattr("brain.agency.effect_ledger.mark_reused_path",
                        lambda p, citing_goal_id=None: calls.append(citing_goal_id))
    library.read_book(book)
    assert calls == ["fn:language_acquisition"]


# ── B18: a natural death keeps its own final words ───────────────────────────

def test_natural_death_is_not_relabelled_operator_stop(monkeypatch):
    from brain.cognition import runtime_lifetime as rl
    from brain.loop import services
    from brain.paths import FINAL_THOUGHTS
    death_note = [{"death_reason": "lifespan", "reflection": "I tried to be genuine."}]
    FINAL_THOUGHTS.write_text(json.dumps(death_note))
    rl.LIFESPAN_FILE.write_text(json.dumps({"final_thoughts_written": True}))
    monkeypatch.setattr("brain.cognition.self_state.autobiography.session_epilogue",
                        lambda ctx: None)
    services.shutdown_loop({}, None)
    assert json.loads(FINAL_THOUGHTS.read_text()) == death_note
    rl.LIFESPAN_FILE.write_text(json.dumps({}))
    services.shutdown_loop({}, None)
    assert json.loads(FINAL_THOUGHTS.read_text())["death_reason"] == "operator_stop"


# ── B19: ToM runs once per cycle, on this turn's input ───────────────────────

def test_theory_of_mind_runs_once_per_cycle(monkeypatch):
    import brain.cognition.theory_of_mind as tom
    calls: list = []
    monkeypatch.setattr(tom, "simulate", lambda ctx: calls.append(1) or {"surface_text": "x"})
    cycle = {"n": 10}
    monkeypatch.setattr("brain.utils.get_cycle_count.get_cycle_count", lambda: cycle["n"])
    ctx: dict = {}
    tom.run_theory_of_mind(ctx)    # sense
    tom.run_theory_of_mind(ctx)    # think fallback
    assert calls == [1] and ctx["theory_of_mind"] == {"surface_text": "x"}
    cycle["n"] = 11                # the same context dict, next cycle
    tom.run_theory_of_mind(ctx)
    assert calls == [1, 1]


# ── B22: rotated log segments are kept for a whole life ──────────────────────

def test_rotation_gzips_and_keeps_far_more_than_twenty(tmp_path, monkeypatch):
    from brain.utils import log as lg
    monkeypatch.setattr(lg, "_LOG_MAX_BYTES", 2000)
    monkeypatch.setattr(lg, "_LOG_KEEP_BYTES", 500)
    p = tmp_path / "private_thoughts.txt"
    stamps = iter(f"2026-10-07T{h:02d}:{m:02d}:00Z" for h in range(24) for m in range(60))
    monkeypatch.setattr(lg, "now_iso_z", lambda: next(stamps))
    for i in range(60):
        p.write_text(f"[segment {i}] " + "x" * 2500 + "\n")
        lg._maybe_rotate(p)
    segs = sorted((tmp_path / "rotated").glob("private_thoughts.*.txt.gz"))
    assert len(segs) == 60
    with gzip.open(segs[0], "rt") as fh:
        assert fh.read().startswith("[segment 0]")


# ── B27: every speech row carries a typed intent ─────────────────────────────

def test_self_initiated_speech_logs_its_typed_intent():
    from brain.think.speech_log import typed_intent
    # Run 13's row: self speech, plan from the composer, nothing comprehended.
    assert typed_intent({"response_type": "express_state", "source": "composed"}, {}) \
        == "express_state"
    assert typed_intent({"response_type": "express_state",
                         "motive": {"intent": "share_finding"}}, {}) == "share_finding"
    assert typed_intent({"response_type": "answer"}, {"intent": "question"}) == "question"
