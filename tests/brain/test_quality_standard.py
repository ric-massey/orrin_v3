# Quality-standard evolution (T0.5 adaptation layer) — the guardrail contract.
#
# Implements QUALITY_STANDARD_EVOLUTION_IMPLEMENTATION_PLAN_2026-06-28.md §3 map.
# Every test here pins one row of the guardrail → mechanism table: evidence-keyed
# promotion, direction asymmetry (raise auto, loosen human), provenance/reversibility,
# indirection (not callable from selection), regression invariant, signal_prior
# ordering-only.
from pathlib import Path

import pytest

from brain import paths
from brain.agency import effect_artifacts, effect_ledger
from brain.cognition.quality_standard import revisions, proposer, gate, ratify


# A real, predicate-passing exemplar body (mirrors the starter golden exemplar).
_GOOD_PROSE = (
    "# Emergence: a working synthesis\n\n"
    "Local feedback coupling between many simple units and a shared field produces a "
    "measurable global polarization pattern that no individual unit represents or intends, "
    "as in convection cells, starling flocks, and market price formation. The coupling is "
    "the mechanism and the lever: change the coupling and the global pattern shifts even "
    "with the units untouched. Weak emergence remains derivable by simulating the parts "
    "forward, which keeps the idea honest and bounded against stronger, contested claims."
)

_GOOD_CODE = (
    "def summarize_window(values, window):\n"
    "    '''Rolling mean over a fixed window — a real, parseable authored helper.'''\n"
    "    out = []\n"
    "    for i in range(len(values)):\n"
    "        lo = max(0, i - window + 1)\n"
    "        chunk = values[lo:i + 1]\n"
    "        out.append(sum(chunk) / len(chunk))\n"
    "    return out\n"
)


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    """Redirect the golden set to a tmp dir and reset all stores between tests so
    nothing touches the live tests/fixtures/quality_golden tree."""
    ex = tmp_path / "exemplars"
    anti = tmp_path / "anti_exemplars"
    ex.mkdir()
    anti.mkdir()
    monkeypatch.setattr(paths, "QUALITY_EXEMPLARS_DIR", ex)
    monkeypatch.setattr(paths, "QUALITY_ANTI_EXEMPLARS_DIR", anti)
    revisions.save([])              # empty candidate store
    effect_ledger.reset_for_tests()
    yield ex, anti


# ── P0: candidate store + schema + signal_prior ordering-only ──────────────────

def test_store_round_trip_and_cap():
    c = revisions.make_candidate(kind="promote", direction="raise",
                                 artifact_ref={"content_hash": "abc"}, signal_prior=0.5)
    revisions.append(c)
    assert revisions.get(c["id"])["evidence"]["signal_prior"] == 0.5
    # cap: pushing far more than the cap keeps only the most recent.
    for i in range(revisions._MAX_ROWS + 50):
        revisions.append(revisions.make_candidate(
            kind="promote", direction="raise",
            artifact_ref={"content_hash": f"h{i}"}, signal_prior=None))
    assert len(revisions.load()) <= revisions._MAX_ROWS


def test_schema_rejects_bad_kind_and_missing_signal_prior():
    with pytest.raises(ValueError):
        revisions.make_candidate(kind="bogus", direction="raise")
    # signal_prior must be PRESENT (ordering-only, may be null) — guardrail.
    bad = {"kind": "promote", "direction": "raise", "status": "pending",
           "evidence": {"goals": []}}  # no signal_prior key
    with pytest.raises(ValueError):
        revisions._validate(bad)


def test_signal_prior_is_ordering_only_not_evidence():
    """signal_prior orders the review queue but is never summed into evidence."""
    lo = revisions.make_candidate(kind="suspect", direction="lower",
                                  artifact_ref={"artifact_path": "/x/a.md"}, signal_prior=0.1)
    hi = revisions.make_candidate(kind="suspect", direction="lower",
                                  artifact_ref={"artifact_path": "/x/b.md"}, signal_prior=0.9)
    revisions.append(lo)
    revisions.append(hi)
    q = ratify.review_queue()
    assert [r["id"] for r in q][:2] == [hi["id"], lo["id"]]  # high prior first
    # And it lives under evidence, never as a standalone evidence count.
    assert "significance" in hi["evidence"] and hi["evidence"]["signal_prior"] == 0.9


# ── P1a: artifact-text capture ─────────────────────────────────────────────────

def test_capture_round_trip_and_floor():
    h = effect_artifacts.capture(_GOOD_PROSE)
    assert h and effect_artifacts.load(h) == _GOOD_PROSE
    assert effect_artifacts.capture("too short") is None  # below MIN_ARTIFACT_CHARS


# ── P1b: promotion proposer — evidence-keyed, kind-aware ───────────────────────

def test_code_promotion_requires_reuse():
    ctx = {"cycle_count": {"count": 1}}
    row = effect_ledger.record_effect("tool_written", _GOOD_CODE, goal_id="g1",
                                      context=ctx, metadata={"name": "summarize_window"})
    assert row is not None
    effect_artifacts.capture(_GOOD_CODE, content_hash=row.content_hash)

    # No reuse yet → no promotion (structural significance is never enough alone).
    assert proposer.propose_promotions(ctx) == []

    # Future self invokes it by name → tier-3 reuse credit → now promotable.
    assert effect_ledger.note_artifact_use("summarize_window") == 1
    out = proposer.propose_promotions(ctx)
    assert len(out) == 1
    assert out[0]["kind"] == "promote" and out[0]["direction"] == "raise"
    assert out[0]["evidence"]["reuse_count"] >= 1


def test_prose_promotion_requires_long_memory_persistence(tmp_path):
    ctx = {"cycle_count": {"count": 1}}
    row = effect_ledger.record_effect("note_novel", _GOOD_PROSE, goal_id="g2", context=ctx)
    assert row is not None
    effect_artifacts.capture(_GOOD_PROSE, content_hash=row.content_hash)

    # No persisted memory → no promotion (prose can never earn reuse credit).
    assert proposer.propose_promotions(ctx) == []

    # An important, persisted long_memory entry matching the prose = the anchor.
    from brain.utils.json_utils import save_json
    save_json(paths.LONG_MEMORY_FILE,
              [{"id": "m1", "content": _GOOD_PROSE, "importance": 6}])
    out = proposer.propose_promotions(ctx)
    assert len(out) == 1 and out[0]["evidence"]["memory_refs"] == ["m1"]


# ── P2: promotion gate — add-only, predicate-conforming, the only auto-apply ───

def test_gate_applies_predicate_passing_exemplar(_isolate):
    ex, _anti = _isolate
    h = effect_artifacts.capture(_GOOD_PROSE)
    revisions.append(revisions.make_candidate(
        kind="promote", direction="raise",
        artifact_ref={"goal_id": "g", "content_hash": h}, signal_prior=None))
    changed = gate.apply_pending_promotions()
    assert len(changed) == 1 and changed[0]["status"] == "applied"
    written = list(ex.glob("*.md"))
    assert len(written) == 1
    assert gate.regression_smoke()[0]  # invariant still green


def test_gate_routes_predicate_reject_to_human(_isolate):
    ex, _anti = _isolate
    stub = "x" * 200  # long enough to capture, but low-information → predicate rejects
    h = effect_artifacts.capture(stub)
    revisions.append(revisions.make_candidate(
        kind="promote", direction="raise",
        artifact_ref={"content_hash": h}, signal_prior=None))
    changed = gate.apply_pending_promotions()
    assert changed and changed[0]["status"] == "pending"
    assert changed[0]["needs_rule_review"] is True
    assert not list(ex.glob("*.md"))  # NOTHING auto-written on a reject


def test_gate_skips_near_duplicate_exemplar(_isolate):
    ex, _anti = _isolate
    (ex / "existing.md").write_text(_GOOD_PROSE, encoding="utf-8")
    h = effect_artifacts.capture(_GOOD_PROSE)
    revisions.append(revisions.make_candidate(
        kind="promote", direction="raise",
        artifact_ref={"content_hash": h}, signal_prior=None))
    changed = gate.apply_pending_promotions()
    assert changed and changed[0]["status"] == "rejected"
    assert "near_duplicate" in changed[0]["reason"]
    assert len(list(ex.glob("*.md"))) == 1  # no second copy added


# ── P3: suspect proposer ───────────────────────────────────────────────────────

def test_suspect_flags_exemplar_matching_anti_exemplar(_isolate):
    ex, anti = _isolate
    (ex / "good.md").write_text(_GOOD_PROSE, encoding="utf-8")
    (anti / "bad.md").write_text(_GOOD_PROSE, encoding="utf-8")  # contradiction!
    out = proposer.propose_suspects(None)
    assert len(out) == 1
    assert out[0]["kind"] == "suspect" and out[0]["direction"] == "lower"
    assert out[0]["reason"] == "near_duplicate_of_anti_exemplar"


def test_suspect_flags_now_rejected_exemplar(_isolate):
    ex, _anti = _isolate
    (ex / "stale.md").write_text("too short and trivial", encoding="utf-8")
    out = proposer.propose_suspects(None)
    assert len(out) == 1 and out[0]["reason"].startswith("predicate_now_rejects")


# ── P4: human ratify — the only loosening path, reversible, regression-gated ───

def test_approve_removes_suspect_exemplar_and_is_reversible(_isolate):
    ex, _anti = _isolate
    # A stale exemplar the CURRENT predicate now rejects — a genuine suspect whose
    # removal leaves the golden set consistent (regression green after removal).
    stale = "x " * 120
    f = ex / "stale.md"
    f.write_text(stale, encoding="utf-8")
    cand = proposer.propose_suspects(None)[0]
    assert cand["reason"].startswith("predicate_now_rejects")

    applied, msg = ratify.approve(cand["id"])
    assert applied and not f.exists()                     # exemplar removed
    row = revisions.get(cand["id"])
    assert row["status"] == "applied" and row["removed_text"] == stale  # provenance kept

    ok, _ = ratify.restore(cand["id"])                    # reversible from the row
    assert ok and f.exists() and f.read_text() == stale


def test_approve_needs_rule_review_refuses_until_rule_edited(_isolate):
    h = effect_artifacts.capture("x" * 200)
    revisions.append(revisions.make_candidate(
        kind="promote", direction="raise",
        artifact_ref={"content_hash": h}, signal_prior=None))
    cid = gate.apply_pending_promotions()[0]["id"]
    # The predicate still rejects it → approve must refuse, not force it through.
    applied, msg = ratify.approve(cid)
    assert not applied and "still rejects" in msg


def test_reject_marks_candidate_without_touching_golden_set(_isolate):
    ex, _anti = _isolate
    (ex / "good.md").write_text(_GOOD_PROSE, encoding="utf-8")
    revisions.append(revisions.make_candidate(
        kind="suspect", direction="lower",
        artifact_ref={"artifact_path": str(ex / "good.md")}))
    cid = ratify.review_queue()[0]["id"]
    ratify.reject(cid, reason="seed exemplar, keep")
    assert revisions.get(cid)["status"] == "rejected"
    assert (ex / "good.md").exists()  # untouched


# ── Guardrail: indirection — not callable from selection ───────────────────────

def test_quality_standard_not_imported_by_selection():
    """Orrin must have NO path to the bar: nothing under brain/think (selection /
    candidates / scoring) may import the quality_standard package."""
    think = Path(__file__).resolve().parent.parent.parent / "brain" / "think"
    offenders = []
    for p in think.rglob("*.py"):
        if "quality_standard" in p.read_text(encoding="utf-8", errors="replace"):
            offenders.append(str(p))
    assert not offenders, f"quality_standard reachable from selection: {offenders}"
