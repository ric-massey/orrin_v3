# Master plan Phase 3 regression tests: opinions move from a provenance-typed
# evidence ledger, not from repetition; stakes gate flips; LLM reflection is
# the weakest voice and can never flip a view on its own.
import pytest

import brain.cognition.opinions as O


@pytest.fixture(autouse=True)
def _isolate_opinion_files(monkeypatch, tmp_path):
    monkeypatch.setattr(O, "OPINIONS_FILE", tmp_path / "opinions.json")
    monkeypatch.setattr(O, "WORKING_MEMORY_FILE", tmp_path / "wm.json")
    monkeypatch.setattr(O, "LONG_MEMORY_FILE", tmp_path / "lm.json")
    # Reversal records must not touch the live long memory in tests.
    written = []
    monkeypatch.setattr(O, "update_long_memory",
                        lambda *a, **k: written.append((a, k)))
    monkeypatch.setattr(O, "update_working_memory", lambda *a, **k: None)
    yield written


def _seed(topic="recursion", view="recursion is being underestimated",
          alpha=7.0, beta=3.0, **extra):
    op = {
        "id": O._topic_id(topic), "topic": topic, "view": view,
        "confidence": round(alpha / (alpha + beta), 2),
        "alpha": alpha, "beta": beta, "evidence_count": 3,
    }
    op.update(extra)
    ops = O._load()
    ops.append(op)
    O._save(ops)
    return op["id"]


def test_mention_moves_salience_not_confidence():
    oid = _seed()
    before = O._load()[0]["confidence"]
    assert O.add_evidence(oid, "mention", "wm-1", "for")
    op = O._load()[0]
    assert op["confidence"] == before
    assert op["salience"] > 0.3
    # deduped on (kind, ref_id)
    assert not O.add_evidence(oid, "mention", "wm-1", "for")


def test_contrary_experiment_verdicts_drop_high_mention_opinion(_isolate_opinion_files):
    """The Phase 3 observable sign: a seeded contrary experiment verdict
    visibly drops a high-mention opinion."""
    _seed(alpha=7.0, beta=3.0)   # conf 0.70 — the old code only ever raised this
    for i in range(6):
        O.ingest_experiment_verdict(
            "recursion is not underestimated", "confirmed", f"e{i}")
        if not O._load():
            break
    assert O._load() == [], "opinion survived repeated contrary experiment verdicts"
    # the reversal was recorded durably with the evidence that did it
    reversal = [k for a, k in _isolate_opinion_files
                if k.get("event_type") == "opinion_reversal"]
    assert reversal and reversal[0].get("related_memory_ids")


def test_llm_reflection_can_never_flip_alone():
    oid = _seed(alpha=1.8, beta=2.2)   # already weak
    for i in range(40):
        O.add_evidence(oid, "llm_reflection", f"r{i}", "against")
    assert O._load(), "LLM reflections alone flipped an opinion"
    assert O._against_mass(O._load()[0]) == 0.0   # llm weight excluded from mass


def test_stake_grows_on_survived_challenge_and_use():
    oid = _seed(alpha=12.0, beta=2.0)   # strong enough to survive
    O.add_evidence(oid, "prediction_outcome", "p1", "against")
    op = O._load()[0]
    assert op["stake"] > O._INIT_STAKE
    before = op["stake"]
    O.mark_opinion_used(oid)
    assert O._load()[0]["stake"] > before


def test_flip_threshold_scales_with_stake():
    assert O._flip_threshold(1.0) > O._flip_threshold(0.1)


def test_inconclusive_verdicts_carry_no_weight():
    _seed()
    assert O.ingest_experiment_verdict("recursion stuff", "inconclusive", "e9") == 0


def test_neighbor_disturbance_marks_needs_review(monkeypatch):
    a = _seed("recursion depth", "recursion depth handling is fragile")
    b = _seed("recursion limits", "recursion limits need careful handling")
    ops = O._load()
    op_a = next(o for o in ops if o["id"] == a)
    O._ensure_ledger_fields(op_a)
    op_a["linked_opinion_ids"] = [b]
    O._mark_neighbors_for_review(op_a, ops)
    op_b = next(o for o in ops if o["id"] == b)
    assert op_b["needs_review"] is True
    # and the review picker prefers it
    assert O._pick_review_candidate(ops)["id"] == b


def test_roots_haircut_when_seed_memories_pruned(tmp_path):
    from brain.utils.json_utils import save_json
    save_json(tmp_path / "wm.json", [])
    save_json(tmp_path / "lm.json", [])
    _seed(root_memory_ids=["gone-1", "gone-2"])
    ops = O._load()
    op = ops[0]
    O._ensure_ledger_fields(op)
    beta_before = op["beta"]
    assert O._check_roots(op) is True
    assert op["beta"] > beta_before and op["roots_lost"] is True
    # one-time only
    assert O._check_roots(op) is False
