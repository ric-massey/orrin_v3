# Run 4 fix A2 (RUN4_FIX_PLAN_2026-07-04 §A2): the path→hash index + read-path
# reuse crediting. Before A2, mark_reused existed but nothing that READS ever
# called it, and no path could resolve back to a content hash — so the ledger's
# ungameable tier-3 signal was dead. These assert the primitive and one arc.

import brain.agency.effect_ledger as el


def _isolate(monkeypatch, tmp_path):
    """Each test gets its own ledger file so on-disk dedup can't bleed across
    cases (conftest points DATA_DIR at one shared session tmp dir)."""
    monkeypatch.setattr(el, "EFFECT_LEDGER_FILE", tmp_path / "effect_ledger.jsonl",
                        raising=False)
    el.reset_for_tests()


_MEMO = ("Evolution shapes organisms through natural selection acting on "
         "heritable variation; drift, migration, mutation and recombination "
         "each contribute distinct dynamics across populations and deep time.")


def test_hash_for_path_resolves_written_file(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    p = tmp_path / "memo.md"
    p.write_text("x", encoding="utf-8")
    row = el.record_effect("file_write", _MEMO, goal_id="g1",
                           metadata={"path": str(p)})
    assert row is not None
    h = el.hash_for_path(str(p))
    assert h == row.content_hash
    # unnormalized / Path forms resolve to the same hash
    assert el.hash_for_path(p) == row.content_hash
    assert el.hash_for_path(tmp_path / "nope.md") is None


def test_mark_reused_path_credits_reuse_and_lifts_significance(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    p = tmp_path / "memo.md"
    row = el.record_effect("file_write", _MEMO, goal_id="g1",
                           metadata={"path": str(p)})
    assert row is not None
    before = el.significance_for_goal("g1")

    n = el.mark_reused_path(str(p))
    assert n == 1
    assert el.reuse_count(row.content_hash) == 1
    assert el.significance_for_goal("g1") >= before

    # a path the ledger never produced credits nothing
    assert el.mark_reused_path(tmp_path / "unknown.md") is None


def test_path_index_survives_hydrate(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    p = tmp_path / "memo.md"
    row = el.record_effect("file_write", _MEMO, goal_id="g1",
                           metadata={"path": str(p)})
    assert row is not None

    # simulate a fresh process: drop in-memory state, re-hydrate from disk
    el._hydrated = False
    el._path_hash.clear()
    el._seen_hashes.clear()
    assert el.hash_for_path(str(p)) == row.content_hash
