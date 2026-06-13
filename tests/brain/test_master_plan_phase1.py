# Phase 1 regression tests (docs/archive/ORRIN_MASTER_PLAN.md — the second checker).
#
# Inner (affect) predictions must carry a behavioral receipt, resolve through
# two channels (felt_true from self-report, behaved_true from cognition_log),
# feed the per-domain introspection-trust ledger, and surface sharp felt/behaved
# disagreement as an introspection_miss working-memory event.
import pytest

import cognition.prediction as pred_mod
import cognition.calibration as cal


@pytest.fixture(autouse=True)
def _isolated_trust(monkeypatch, tmp_path):
    monkeypatch.setattr(cal, "_TRUST_PATH", tmp_path / "introspection_trust.json")
    yield


def _ctx_with_picks(picks):
    return {"cognition_log": [{"choice": p} for p in picks]}


# ── 1.1 receipts attach at generation ────────────────────────────────────────

def test_affect_trend_prediction_carries_receipt(monkeypatch, tmp_path):
    # Seed WM snapshots with a rising motivation trend (3+ readings, Δ ≥ 0.10).
    wm = [
        {"event_type": "thought", "content": "a", "emotional_context": {"motivation": 0.2}},
        {"event_type": "thought", "content": "b", "emotional_context": {"motivation": 0.35}},
        {"event_type": "thought", "content": "c", "emotional_context": {"motivation": 0.5}},
    ]
    wm_file = tmp_path / "wm.json"
    import json
    wm_file.write_text(json.dumps(wm))
    monkeypatch.setattr(pred_mod, "WORKING_MEMORY_FILE", wm_file)

    context = {"affect_state": {"core_signals": {"motivation": 0.5}}}
    preds = pred_mod.generate_predictions(context, [])

    inner = [p for p in preds if p.get("basis") == "affect_trend"
             and p["source_data"].get("signal") == "motivation"]
    assert inner, "rising motivation trend should produce an affect_trend prediction"
    receipt = inner[0]["source_data"].get("receipt")
    assert receipt and receipt["kind"] == "pursue_pick"
    assert receipt["window"] == pred_mod._RECEIPT_WINDOW


# ── 1.2 receipt verdicts ─────────────────────────────────────────────────────

def test_receipt_verdict_pursue_pick():
    receipt = {"kind": "pursue_pick", "window": 8}
    yes = _ctx_with_picks(["look_outward", "assess_goal_progress", "reflection"])
    no = _ctx_with_picks(["look_outward", "seek_novelty", "reflection"])
    assert pred_mod._receipt_verdict(receipt, yes) is True
    assert pred_mod._receipt_verdict(receipt, no) is False


def test_receipt_verdict_needs_enough_behavior():
    receipt = {"kind": "pursue_pick", "window": 8}
    sparse = _ctx_with_picks(["assess_goal_progress"])
    assert pred_mod._receipt_verdict(receipt, sparse) is None


def test_receipt_verdict_switch_rate():
    receipt = {"kind": "switch_rate_up", "window": 8}
    thrash = _ctx_with_picks(["a", "b", "c", "d", "e", "f", "g", "h"])
    rut = _ctx_with_picks(["a", "a", "a", "a", "a", "a", "b", "a"])
    assert pred_mod._receipt_verdict(receipt, thrash) is True
    assert pred_mod._receipt_verdict(receipt, rut) is False


# ── 1.2/1.3 two-channel resolution ───────────────────────────────────────────

def test_resolve_inner_correct_only_when_receipt_agrees():
    ctx = _ctx_with_picks(["assess_goal_progress", "plan_next_step", "reflection"])
    pred = {"source_data": {"receipt": {"kind": "pursue_pick", "window": 8}}}
    came_true, mismatch = pred_mod._resolve_inner(pred, True, 0.0, ctx)
    assert came_true is True
    assert pred["felt_true"] is True and pred["behaved_true"] is True

    # felt yes, behaved no → not correct, mismatch raised
    ctx_no = _ctx_with_picks(["look_outward", "seek_novelty", "reflection"])
    pred2 = {"source_data": {"receipt": {"kind": "pursue_pick", "window": 8}}}
    came_true2, mismatch2 = pred_mod._resolve_inner(pred2, True, 0.0, ctx_no)
    assert came_true2 is False
    assert mismatch2 >= 0.6
    assert pred2["felt_true"] is True and pred2["behaved_true"] is False


def test_resolve_inner_without_receipt_keeps_felt_verdict():
    pred = {"source_data": {}}
    came_true, mismatch = pred_mod._resolve_inner(pred, True, 0.1, {})
    assert came_true is True and mismatch == 0.1
    assert pred["behaved_true"] is None


# ── 1.3 trust ledger ─────────────────────────────────────────────────────────

def test_introspection_trust_moves_with_agreement():
    assert cal.get_introspection_trust("INTERNAL") == 0.5
    for _ in range(5):
        cal.update_introspection_trust("INTERNAL", True)
    high = cal.get_introspection_trust("INTERNAL")
    assert high > 0.5
    for _ in range(10):
        cal.update_introspection_trust("INTERNAL", False)
    assert cal.get_introspection_trust("INTERNAL") < high


def test_trust_scales_affect_trend_confidence(monkeypatch, tmp_path):
    import json
    wm = [
        {"event_type": "thought", "content": "a", "emotional_context": {"motivation": 0.2}},
        {"event_type": "thought", "content": "b", "emotional_context": {"motivation": 0.35}},
        {"event_type": "thought", "content": "c", "emotional_context": {"motivation": 0.5}},
    ]
    wm_file = tmp_path / "wm.json"
    wm_file.write_text(json.dumps(wm))
    monkeypatch.setattr(pred_mod, "WORKING_MEMORY_FILE", wm_file)

    context = {"affect_state": {"core_signals": {"motivation": 0.5}}}

    # Neutral trust → 0.60 prior.
    preds = pred_mod.generate_predictions(context, [])
    inner = [p for p in preds if p.get("basis") == "affect_trend"][0]
    assert inner["confidence"] == pytest.approx(0.60, abs=0.01)

    # Low earned trust → prior drops.
    for _ in range(30):
        cal.update_introspection_trust("INTERNAL", False)
    preds_low = pred_mod.generate_predictions(context, [])
    inner_low = [p for p in preds_low if p.get("basis") == "affect_trend"][0]
    assert inner_low["confidence"] < inner["confidence"]


# ── 1.4 disagreement is an event ─────────────────────────────────────────────

def test_introspection_miss_writes_wm_event(monkeypatch):
    import cog_memory.working_memory as wm_mod
    captured = []
    monkeypatch.setattr(wm_mod, "update_working_memory",
                        lambda entry, *a, **k: captured.append(entry))
    monkeypatch.setattr(pred_mod, "log_private", lambda *a, **k: None)

    pred = {
        "prediction": "Affect signal 'motivation' will rise",
        "source_data": {"receipt": {"kind": "pursue_pick", "window": 8,
                                    "expected": "a goal-pursuit action is selected"}},
    }
    context = {"affect_state": {"core_signals": {}}}
    pred_mod._fire_introspection_miss(pred, context)

    assert captured and captured[0]["event_type"] == "introspection_miss"
    # The surprise spike went through the arbiter as proposals.
    assert context.get("_affect_proposals")
