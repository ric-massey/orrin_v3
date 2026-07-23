"""Run-12 Slice 1C keystone: growth's currency is STRUCTURED knowledge, not prose.

1C.0 — a research goal writes a claims.json (entities / relations / prediction /
sources) extracted symbolically from the fetched docs.
1C.2 — score_answer is re-keyed to the structured product: answered iff a claim
names the question's subject (0 prose required); a subject-less stitch stamps
answered=False; a checkable prediction must be resolved-correct.
"""
from goals.handlers.research import _extract_claims
from goals.model import Goal
from brain.cognition import epistemic_closeout as ec


def _goal(**kw):
    base = dict(id="g", title="Understand entropy more deeply", kind="research",
                spec={"question": "What actually is entropy?"})
    base.update(kw)
    return Goal(**base)


def test_extract_claims_pulls_subject_relation():
    g = _goal()
    snips = [("https://x/entropy",
              "Entropy is a measure of disorder in a system. The weather is nice today.")]
    claims = _extract_claims(g, snips)
    assert claims["relations"], "a subject-naming relation must be extracted"
    r = claims["relations"][0]
    assert "entropy" in (r["subject"] + r["object"]).lower()
    assert claims["sources"] == [{"src": "https://x/entropy"}]


def test_structured_answer_true_when_subject_named():
    g = _goal()
    claims = _extract_claims(g, [("s", "Entropy is a measure of disorder in a system.")])
    answered, excerpt = ec.score_answer_structured(claims["question"], claims)
    assert answered is True
    assert "entropy" in excerpt.lower()


def test_structured_answer_false_when_subject_absent():
    g = _goal(id="g2", title="Understand mitochondria more deeply",
              spec={"question": "What is a mitochondrion?"})
    claims = _extract_claims(g, [("s", "The sky is blue. Cats are mammals.")])
    assert claims["relations"] == []
    assert ec.score_answer_structured(claims["question"], claims) == (False, "")


def test_checkable_prediction_must_resolve_correct():
    q = "What makes RSS climb?"
    # Unresolved checkable prediction → not yet answered even if relations exist.
    claims = {
        "relations": [{"subject": "RSS", "predicate": "is driven by", "object": "consolidation"}],
        "prediction": {"claim": "RSS climbs with consolidation events",
                       "checkable_against": "rss_series", "resolved": False, "correct": None},
    }
    assert ec.score_answer_structured(q, claims) == (False, "")
    # Resolved-correct → answered.
    claims["prediction"]["resolved"] = True
    claims["prediction"]["correct"] = True
    answered, excerpt = ec.score_answer_structured(q, claims)
    assert answered is True and "confirmed" in excerpt.lower()


def test_stamp_prefers_structured_over_prose(tmp_path, monkeypatch):
    """stamp_closeout scores claims.json when present; a subject-naming claim stamps
    answered=True with ZERO memo prose (the currency change)."""
    from brain.paths import GOALS_DIR
    import json
    gid = "gstamp"
    d = GOALS_DIR / "artifacts" / gid
    d.mkdir(parents=True, exist_ok=True)
    claims = {"question": "What is entropy?",
              "relations": [{"subject": "Entropy", "predicate": "is a",
                             "object": "measure of disorder"}],
              "prediction": None}
    (d / "claims.json").write_text(json.dumps(claims), encoding="utf-8")
    goal = {"id": gid, "title": "Understand entropy more deeply",
            "driven_by": "world_knowledge", "question": "What is entropy?", "kind": "research"}
    answered = ec.stamp_closeout(goal)
    assert answered is True
    assert goal["answered"] is True
    assert goal["question"] == "What is entropy?"
