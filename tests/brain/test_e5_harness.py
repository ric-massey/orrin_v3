"""E5 harness (brain/eval/e5_answer_use.py) — tests of the TEST, not of Orrin.

Orrin's own result is what scripts/run_e5.py reports; it is not asserted here,
so the day something lets an answer change a selection this suite stays green
and the script's verdict changes. What is asserted: a decider that applies the
answer passes, one that ignores it or reacts only to an answer being on file
fails, and every problem keeps the topic constant across conditions."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from brain.eval import e5_answer_use as e5


@pytest.mark.parametrize("split", ["dev", "heldout"])
def test_oracle_passes(split):
    assert e5.run(e5.oracle_decider, seeds=5, split=split).passed


@pytest.mark.parametrize("decider", [e5.blind_decider, e5.topic_decider])
def test_deciders_that_do_not_read_the_answer_fail(decider):
    r = e5.run(decider, seeds=5, split="all")
    assert not r.passed
    assert r.flip_rate == 0.0


def test_topic_is_constant_across_conditions():
    from brain.cognition.epistemic_closeout import _subject_terms
    from brain.utils.subject_terms import matched_terms
    for p in e5.PROBLEMS:
        terms = _subject_terms(p.question)
        assert terms, p.pid
        need = min(2, len(terms))
        for text in (*p.answers.values(), p.irrelevant):
            assert len(matched_terms(terms, text.lower())) >= need, (p.pid, text)
        # the deciding context carries the topic too, as annotate_reason requires
        assert len(matched_terms(terms, p.goal.lower())) >= need, p.pid


def test_answers_describe_actions_rather_than_name_them():
    for p in e5.PROBLEMS:
        for text in (*p.answers.values(), p.irrelevant):
            for fn in p.candidates:
                assert fn not in text, (p.pid, fn)


def test_candidates_are_real_registered_functions():
    import brain
    reg = json.loads((Path(brain.__file__).parent / "data" / "cognitive_functions.json").read_text())
    names = {e.get("name") for e in reg if isinstance(e, dict)}
    for p in e5.PROBLEMS:
        assert set(p.candidates) <= names, p.pid


def test_both_splits_are_populated():
    assert {p.split for p in e5.PROBLEMS} == {"dev", "heldout"}
    assert sum(p.split == "heldout" for p in e5.PROBLEMS) >= 5


@pytest.fixture
def restore_session_data(tmp_path):
    """The adapter wipes DATA_DIR on every call; give the rest of the session its
    shared data dir back afterwards."""
    import shutil
    from brain.paths import DATA_DIR
    keep = tmp_path / "data_snapshot"
    if Path(DATA_DIR).exists():
        shutil.copytree(DATA_DIR, keep)
    yield
    shutil.rmtree(DATA_DIR, ignore_errors=True)
    if keep.exists():
        shutil.copytree(keep, DATA_DIR)


def test_selector_adapter_runs_and_files_the_answer(restore_session_data):
    from brain.cognition import answer_citation
    p = e5.PROBLEMS[0]
    pick = e5.orrin_selector_decider(p, p.answers[p.candidates[1]], 0)
    assert pick in p.candidates
    rows = answer_citation._rows()
    assert rows and rows[0]["answer"].startswith(p.answers[p.candidates[1]][:40])
    e5.orrin_selector_decider(p, None, 0)
    assert answer_citation._rows() == []
