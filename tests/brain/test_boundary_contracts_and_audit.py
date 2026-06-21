# Master plan Phase 5 regression tests: boundary contracts at module seams,
# failure-summary triage as a cognition act, and the map-territory audit.
import json

import pytest

from brain.symbolic.meta_rules import resolve_conflict
from brain.utils.failure_counter import ContractViolation, strict_should_reraise


def test_resolve_conflict_contract_fires_on_bare_dicts():
    """The Problem-4 crash shape: a bare rule-dict list instead of pairs must
    raise a NAMED error, not a swallowable ValueError."""
    with pytest.raises(ContractViolation):
        resolve_conflict([{"id": "r1", "conclusion": "x", "confidence": 0.9}])


def test_resolve_conflict_still_accepts_valid_pairs():
    res = resolve_conflict([({"id": "r1", "conclusion": "x", "confidence": 0.9}, 0.8)])
    assert res["winner"]["id"] == "r1"
    res2 = resolve_conflict([])
    assert res2["action"] == "no_match"


def test_contract_violation_reraised_under_any_strict_mode(monkeypatch):
    import brain.utils.failure_counter as FC
    monkeypatch.setattr(FC, "_STRICT", "1")
    assert strict_should_reraise(ContractViolation("seam broke"))
    # ...even though it isn't a programmer-error type
    assert not isinstance(ContractViolation("x"), FC._PROGRAMMER_ERRORS)


def test_review_failures_internal_surfaces_growing_sites(monkeypatch, tmp_path):
    import brain.cognition.health_monitor as HM
    import brain.utils.failure_counter as FC

    monkeypatch.setattr(HM, "_state_path", lambda: tmp_path / "health_state.json")
    monkeypatch.setattr(FC, "_counters", {
        "hot.site": {"count": 25, "first_seen": "t", "last_seen": "t",
                     "last_error": "ValueError: boom"},
        "cold.site": {"count": 3, "first_seen": "t", "last_seen": "t",
                      "last_error": "IOError: meh"},
    })
    captured = []
    import brain.cog_memory.working_memory as wm_mod
    monkeypatch.setattr(wm_mod, "update_working_memory",
                        lambda e, **k: captured.append(e))

    assert HM.review_failures_internal({}) == 1
    assert captured[0]["event_type"] == "internal_fault"
    assert "hot.site" in captured[0]["content"]
    # no growth since baseline → silence
    captured.clear()
    assert HM.review_failures_internal({}) == 0
    assert captured == []


def test_map_territory_audit_writes_findings_log(monkeypatch, tmp_path):
    import brain.cognition.maintenance.map_territory_audit as MA

    monkeypatch.setattr(MA, "_FINDINGS_LOG", tmp_path / "audit.jsonl")
    monkeypatch.setattr(MA, "_STATE_FILE", tmp_path / "audit_state.json")
    import brain.cog_memory.working_memory as wm_mod
    monkeypatch.setattr(wm_mod, "update_working_memory", lambda *a, **k: None)

    msg = MA.audit_map_territory({})
    assert "audit" in msg.lower()
    lines = (tmp_path / "audit.jsonl").read_text().strip().splitlines()
    rec = json.loads(lines[-1])
    assert "findings" in rec and "ts" in rec
    # the monthly gate now holds
    assert MA.audit_if_due({}) is None


def test_audit_comment_constant_mismatch_detection(monkeypatch, tmp_path):
    import brain.cognition.maintenance.map_territory_audit as MA

    bad = tmp_path / "drifty.py"
    bad.write_text("_RETRY_HOURS = 24  # retry after 36 hours\n")
    good = tmp_path / "fine.py"
    good.write_text("_WAIT_S = 60  # one minute (60 s) between polls\n")
    monkeypatch.setattr(MA, "_source_files", lambda: [bad, good])
    monkeypatch.setattr(MA, "ROOT_DIR", tmp_path)

    findings = MA._audit_comment_constants()
    assert len(findings) == 1
    assert "_RETRY_HOURS" in findings[0] and "36" in findings[0]
