"""Run 13 gate-passers 1+2 (DEMO_RUN_2026-08-19 §3): Run 12's Growth was hollow.

Subject terms kept the question template's scaffolding ("What did I GET WRONG or
OVERSIMPLIFY about X?") and matched it by substring, so any claims file "answered"
any question and every goal "built on" the newest claims file regardless of topic.
These tests run against REAL claims.json files captured from that life
(tests/fixtures/run12_claims/), not synthetic stand-ins.
"""
import json
import os
from pathlib import Path

from brain.cognition.epistemic_closeout import score_answer_structured
from brain.utils.subject_terms import matched_terms, subject_terms
from goals.handlers.research import _find_prior_claims
from goals.model import Goal

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "run12_claims"


def _load(gid):
    return json.loads((FIX / f"{gid}.json").read_text(encoding="utf-8"))


MATH = "g_24136ed3db"            # "...about mathematics?"
NATURE_OF_MATH = "g_1265f806a8"  # "...about the nature of mathematics?"
EVO_BIO = "g_40fe7f09e0"         # "...about evolutionary biology?"
BIO_EVO_BIO = "g_c7a4e8421d"     # "...about biology evolutionary biology?" (same pages)
QUANTUM = "g_b15f5c2b37"         # "...about quantum mechanics foundations?"
NOW = "g_dd89aa2324"             # "What is concrete and true right now?"


def test_scaffold_words_are_not_subject():
    assert subject_terms("What did I get wrong or oversimplify about evolutionary biology?") \
        == ["evolutionary", "biology"]
    assert subject_terms("What is concrete and true right now?") == []


def test_whole_token_matching_not_substring():
    assert matched_terms(["get"], "a set together with two operations") == []
    assert matched_terms(["now"], "what is known as the yield point") == []
    assert matched_terms(["system"], "complex systems are") == ["system"]


def test_off_topic_claims_do_not_answer():
    # The Run 12 proof case: mathematics claims "answered" a medieval-cooking question.
    q = "What did I get wrong or oversimplify about medieval cooking?"
    assert score_answer_structured(q, _load(MATH)) == (False, "")


def test_subjectless_question_is_not_answerable_by_claims():
    # Run 12: answered by "This linear region terminates at what is known as the
    # yield point" (now ⊂ known).
    c = _load(NOW)
    assert score_answer_structured(c["question"], c) == (False, "")


def test_definition_does_not_answer_what_did_i_get_wrong():
    c = _load(MATH)
    assert score_answer_structured(c["question"], c) == (False, "")


def test_definition_answers_what_is_with_no_prior():
    answered, excerpt = score_answer_structured(
        "What actually is mathematics, beyond the mentions I keep seeing?", _load(MATH))
    assert answered is True and "mathematics" in excerpt.lower()


def test_refetching_known_relations_answers_nothing():
    # Same Wikipedia pages fetched twice: every relation is already in the prior.
    q = "What is there about evolutionary biology that my earlier notes on it are missing?"
    assert score_answer_structured(q, _load(BIO_EVO_BIO), prior=[_load(EVO_BIO)]) == (False, "")


def test_single_term_does_not_name_a_multiword_subject():
    # 'nature' alone ("abstractions from nature...") is not "the nature of mathematics".
    c = _load(NATURE_OF_MATH)
    q = "What is there about the nature of mathematics that my earlier notes on it are missing?"
    assert score_answer_structured(q, c, prior=[_load(MATH)]) == (False, "")


def test_revision_needs_a_real_contradiction():
    prior = {"relations": [{"subject": "Entropy", "predicate": "is",
                            "object": "always decreasing in isolated systems"}]}
    other_fact = {"relations": [{"subject": "Entropy", "predicate": "is",
                                 "object": "a measure of disorder"}]}
    flipped = {"relations": [{"subject": "Entropy", "predicate": "is",
                              "object": "not decreasing in isolated systems"}]}
    q = "What did I get wrong or oversimplify about entropy?"
    assert score_answer_structured(q, other_fact, prior=[prior]) == (False, "")
    answered, excerpt = score_answer_structured(q, flipped, prior=[prior])
    assert answered is True and excerpt.startswith("revised:")
    # No prior belief → nothing to have gotten wrong.
    assert score_answer_structured(q, flipped) == (False, "")


def _art_base(tmp_path, gids):
    base = tmp_path / "artifacts"
    for i, gid in enumerate(gids):
        d = base / gid
        d.mkdir(parents=True)
        p = d / "claims.json"
        p.write_text((FIX / f"{gid}.json").read_text(encoding="utf-8"), encoding="utf-8")
        os.utime(p, (1_000_000 + i, 1_000_000 + i))   # later in list = newer
    return base


def test_prior_claims_reuse_is_topical(tmp_path):
    # Newest file is off-topic (quantum); Run 12 picked the newest regardless.
    base = _art_base(tmp_path, [EVO_BIO, MATH, QUANTUM])
    goal = Goal(id="g_new", title="Understand evolutionary biology more deeply", kind="research",
                spec={"question": "What is there about evolutionary biology that my earlier "
                                  "notes on it are missing?"})
    hit = _find_prior_claims(base, goal, base / "g_new")
    assert hit is not None and hit[0].parent.name == EVO_BIO


def test_prior_claims_reuse_none_when_no_topic_overlap(tmp_path):
    base = _art_base(tmp_path, [EVO_BIO, MATH, QUANTUM])
    goal = Goal(id="g_new", title="Understand medieval cooking more deeply", kind="research",
                spec={"question": "What did I get wrong or oversimplify about medieval cooking?"})
    assert _find_prior_claims(base, goal, base / "g_new") is None
