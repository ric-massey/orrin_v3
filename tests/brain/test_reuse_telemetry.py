# R9-F6 (RUN9_DEEP_ANALYSIS_2026-07-15 Finding 4): mark_reused hard-coded
# cycle=0 and recorded no path, so every reuse row in a run capture was
# time-blind and referent-less — the Run 8 "reuse↔failure time-lock" took a
# hash join against the WAL to resolve. Rows now stamp the real cycle and the
# reused artifact's owning path.

import json

import pytest

import brain.agency.effect_ledger as el
import brain.utils.get_cycle_count as gcc

_BODY = ("Convection cells transport heat through bulk fluid motion; the memo "
         "records Rayleigh number thresholds, boundary-layer behavior, and how "
         "laminar rolls transition to turbulent plumes as heating intensifies.")


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(el, "EFFECT_LEDGER_FILE", tmp_path / "effect_ledger.jsonl",
                        raising=False)
    el.reset_for_tests()
    yield
    el.reset_for_tests()


def _rows():
    return [json.loads(line) for line in
            el.EFFECT_LEDGER_FILE.read_text(encoding="utf-8").splitlines() if line]


def test_mark_reused_stamps_real_cycle_and_owning_path(tmp_path, monkeypatch):
    monkeypatch.setattr(gcc, "get_cycle_count", lambda: 4242)
    memo = tmp_path / "research_memo.md"
    memo.write_text(_BODY, encoding="utf-8")
    el.record_effect("file_write", _BODY, goal_id="g1",
                     metadata={"path": str(memo)})

    assert el.mark_reused_path(memo) == 1

    reuse = [r for r in _rows() if r["kind"] == "reuse"]
    assert len(reuse) == 1
    assert reuse[0]["cycle"] == 4242            # was hard-coded 0
    assert reuse[0]["metadata"]["path"] == el._norm_path(memo)
    assert reuse[0]["goal_id"] == "g1"


def test_mark_reused_by_hash_resolves_path_from_index(tmp_path, monkeypatch):
    monkeypatch.setattr(gcc, "get_cycle_count", lambda: 7)
    memo = tmp_path / "memo.md"
    memo.write_text(_BODY, encoding="utf-8")
    el.record_effect("file_write", _BODY, goal_id="g1",
                     metadata={"path": str(memo)})
    h = el.hash_for_path(memo)
    assert h

    el.mark_reused(h)  # hash-only caller (compose_section) still gets a path

    reuse = [r for r in _rows() if r["kind"] == "reuse"][-1]
    assert reuse["metadata"]["path"] == el._norm_path(memo)
    assert reuse["cycle"] == 7


def test_reuse_rows_do_not_burn_the_per_path_write_credit_budget(tmp_path):
    memo = tmp_path / "memo.md"
    memo.write_text(_BODY, encoding="utf-8")
    el.record_effect("file_write", _BODY, goal_id="g1",
                     metadata={"path": str(memo)})
    el.mark_reused_path(memo)
    el.mark_reused_path(memo)

    # Rehydrate from the ledger file: reuse rows carry metadata.path now, but
    # they are citations, not writes — F2c's repeat-credit decay must count 1.
    el.reset_for_tests()
    assert el.hash_for_path(memo) is not None  # forces _hydrate
    assert el._path_credit_counts.get(el._norm_path(memo), 0) == 1
