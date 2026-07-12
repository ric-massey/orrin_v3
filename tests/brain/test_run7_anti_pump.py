# RUN7_FIX_PLAN_2026-07-11 — make credit un-pumpable.
#
# Run 6 ended in a 92 % committed-goal monopoly because the learned value signal
# was poisoned: one memo body re-recorded 387× under hash-fresh timestamp
# footers pumped a goal's value EMA to 0.8142. These tests pin the anti-pump
# credit substrate (F2), content-keyed credit (F3), the re-commit cooldown (F4),
# diversity weighting (F5), the problem-refocus wiring (F7), and the small
# verified fixes (F8) — plus the QuadRF-shaped characterization replay.
import json

import pytest

import brain.cognition.planning.commitment_value as cv
import brain.cognition.planning.diagnosis as diag
import brain.cognition.planning.problem_refocus as pr
from brain.agency import effect_ledger as el

_BODY = ("Superconducting qubits rely on Josephson junctions to create the "
         "anharmonic oscillator behavior needed for a controllable two-level "
         "system; coherence times depend on materials, shielding, and filtering "
         "of stray radiation across the whole control chain and readout path.")


def _distinct_body(prefix: str) -> str:
    # Fully distinct word sets so novelty stays high between bodies.
    return " ".join(f"{prefix}{i}" for i in range(40))


@pytest.fixture(autouse=True)
def _isolate(tmp_path):
    cv._SIGNALS_FILE = tmp_path / "commitment_signals.json"
    el.EFFECT_LEDGER_FILE = tmp_path / "effect_ledger.jsonl"
    diag._RECURRENCE_FILE = tmp_path / "problem_recurrence.json"
    el.reset_for_tests()
    yield
    el.reset_for_tests()


# ── F2a: volatile stamps can't mint a fresh hash ─────────────────────────────────

def test_volatile_stamp_stripped_before_hashing():
    a = el._normalize(f"{_BODY}\n---\nsource: fetch_and_read · 2026-07-11 18:30Z")
    b = el._normalize(f"{_BODY}\n---\nsource: fetch_and_read · 2026-07-12 09:01Z")
    assert a == b


def test_timestamp_footer_no_longer_mints_fresh_credit():
    r1 = el.record_effect("file_write", _BODY + "\n---\nsource: x · 2026-07-11 18:30Z")
    r2 = el.record_effect("file_write", _BODY + "\n---\nsource: x · 2026-07-11 18:31Z")
    assert r1 is not None
    assert r2 is None  # same body ± stamp → exact-dup, no credit


# ── F2b: novelty gates credit (floor + proportional ramp) ────────────────────────

def test_novelty_below_floor_is_recorded_but_uncredited():
    assert el.record_effect("file_write", _BODY, novelty=0.02) is None
    rows = el.drain_recent_rows()
    assert rows, "the row must still be recorded for the record"
    assert rows[-1]["dedupe"] is True
    assert rows[-1]["significance"] == 0.0


def test_novelty_ramp_pays_proportionally():
    row = el.record_effect("file_write", _BODY, novelty=0.15)
    assert row is not None
    # file_write structural sig 0.4, ramped by nov/0.30
    assert row.significance == pytest.approx(0.4 * (0.15 / 0.30))


def test_verified_check_is_exempt_from_the_floor_but_not_the_ramp():
    # A sandbox-verified check (tool_run_effect) below the floor still earns a
    # ramped credit — produce_and_check's per-goal closure contract — while an
    # exact repeat (novelty 0) stays uncredited.
    row = el.record_effect("tool_run_effect", _BODY, novelty=0.04, goal_id="vg")
    assert row is not None
    assert row.significance == pytest.approx(0.6 * (0.04 / 0.30))
    assert el.has_effect_kind("vg", "tool_run_effect")
    assert el.record_effect("tool_run_effect", _BODY, novelty=0.04, goal_id="vg") is None


# ── F2c: per-path repeat-credit decay (×1 / ×0.5 / ×0.25 / nothing) ──────────────

def test_per_path_repeat_credit_decays_then_stops(tmp_path):
    p = str(tmp_path / "memo.md")
    sigs = []
    for prefix in ("alpha", "bravo", "carol", "delta"):
        row = el.record_effect("file_write", _distinct_body(prefix),
                               metadata={"path": p})
        sigs.append(None if row is None else row.significance)
    assert sigs[0] == pytest.approx(0.4)
    assert sigs[1] == pytest.approx(0.2)
    assert sigs[2] == pytest.approx(0.1)
    assert sigs[3] is None  # n ≥ 3 → no credit at all


# ── F3a: alignment weights the value-EMA sample, and gates avoid relief ──────────

def test_alignment_weights_value_ema_sample():
    cv.note_goal_credit("g", 0.4, alignment=0.14, content_hash="h1")
    row = cv.signals_snapshot()["g"]
    expected = 0.75 * 0.5 + 0.25 * (0.5 + 0.4 * 0.14)
    assert row["value_ema"] == pytest.approx(expected, abs=1e-3)


def test_low_alignment_credit_does_not_relieve_avoidance():
    for _ in range(10):
        cv.note_avoidance("g")
    before = cv.signals_snapshot()["g"]["avoid_streak"]
    cv.note_goal_credit("g", 0.4, alignment=0.1, content_hash="h2")
    assert cv.signals_snapshot()["g"]["avoid_streak"] == pytest.approx(before)
    cv.note_goal_credit("g", 0.4, alignment=0.5, content_hash="h3")
    assert cv.signals_snapshot()["g"]["avoid_streak"] == pytest.approx(before * 0.5)


# ── F5: distinct-hash diversity dampens a single content family ──────────────────

def test_single_hash_family_earns_less_than_diverse_credit():
    for i in range(20):
        cv.note_goal_credit("mono", 0.4, content_hash="same-hash")
        cv.note_goal_credit("diverse", 0.4, content_hash=f"hash-{i}")
    snap = cv.signals_snapshot()
    assert snap["mono"]["value_ema"] < snap["diverse"]["value_ema"]


# ── F4: re-commit cooldown — a temporal exit, not a rubber band ──────────────────

def test_recommit_block_set_decrement_and_driver_skip():
    cv.note_driver_selected("a", ["a"])
    for _ in range(16):
        cv.note_avoidance("a")
    # a loses the slot while its streak is still ≥ 15 → displaced by avoidance.
    cv.note_driver_selected("b", ["a", "b"])
    assert cv.signals_snapshot()["a"]["recommit_block_pulls"] == 300

    # Credit does NOT clear the block.
    cv.note_goal_credit("a", 0.9)
    assert cv.signals_snapshot()["a"]["recommit_block_pulls"] == 300

    # Each pull pays one.
    cv.note_driver_selected("b", ["a", "b"])
    assert cv.signals_snapshot()["a"]["recommit_block_pulls"] == 299

    # A blocked directional is ineligible for the driver slot: the next-best
    # directional drives.
    found = [
        {"id": "a", "tier": "long_term", "directional": True, "priority": "HIGH"},
        {"id": "b", "tier": "long_term", "directional": True, "priority": "HIGH"},
    ]
    out = cv.order_committable(found, tier_weight_fn=lambda t: 1,
                               priority_rank_fn=lambda p: 1, limit=3)
    ids = [g["id"] for g in out]
    assert "a" not in ids
    assert "b" in ids


def test_ordinary_rotation_does_not_stamp_a_block():
    cv.note_driver_selected("a", ["a"])       # low/no avoidance
    cv.note_driver_selected("b", ["a", "b"])  # ordinary rotation
    assert float(cv.signals_snapshot()["a"].get("recommit_block_pulls", 0) or 0) == 0


# ── F3b: aspiration credit routes by content ─────────────────────────────────────

def test_router_classifies_by_artifact_content():
    from brain.cognition.intrinsic_objectives import route_artifact_drive
    world = ("research notes from a wikipedia article about the history of "
             "science: knowledge about the world, its causes and observations")
    assert route_artifact_drive(world) == "world_knowledge"
    selfish = ("an audit of my own mind: introspect the cognition, memory and "
               "architecture in my internal source code machinery")
    assert route_artifact_drive(selfish) == "self_understanding"
    assert route_artifact_drive("too short") is None


# ── F3c: genuine_contact earns, rate-capped ──────────────────────────────────────

def test_genuine_contact_credit_is_rate_capped(monkeypatch):
    import brain.think.speech_evaluator as se
    import brain.cognition.intrinsic_objectives as io_mod
    calls = []
    monkeypatch.setattr(io_mod, "mark_objective_contribution",
                        lambda drive: calls.append(drive))
    monkeypatch.setattr(se, "_last_genuine_contact_ts", 0.0)

    se._maybe_credit_genuine_contact({"response_type": "share_finding"}, 0.7)
    assert calls == ["genuine_contact"]
    # Within the hour → capped, no second contribution.
    se._maybe_credit_genuine_contact({"response_type": "answer"}, 0.9)
    assert calls == ["genuine_contact"]


def test_genuine_contact_requires_type_and_quality(monkeypatch):
    import brain.think.speech_evaluator as se
    import brain.cognition.intrinsic_objectives as io_mod
    calls = []
    monkeypatch.setattr(io_mod, "mark_objective_contribution",
                        lambda drive: calls.append(drive))
    monkeypatch.setattr(se, "_last_genuine_contact_ts", 0.0)

    se._maybe_credit_genuine_contact({"response_type": "express_state"}, 0.9)
    se._maybe_credit_genuine_contact({"response_type": "answer"}, 0.3)
    assert calls == []


# ── F7 C2: recovery requires a verified re-attempt ───────────────────────────────

def test_generic_recovery_requires_verified_probe(monkeypatch):
    ap = {"detect_total": 0}
    # No probe → recovery is unverifiable → never "working again".
    assert pr._capability_healthy("quality.thing.site", ap) is False
    monkeypatch.setitem(diag.RECOVERY_PROBES, "quality.thing.site", lambda: True)
    assert pr._capability_healthy("quality.thing.site", ap) is True
    monkeypatch.setitem(diag.RECOVERY_PROBES, "quality.thing.site", lambda: False)
    assert pr._capability_healthy("quality.thing.site", ap) is False


# ── F7 C3: recurrence refutes "transient" at 3 ───────────────────────────────────

def test_recurrence_counter_persists():
    assert diag.bump_recurrence("some.site.key") == 1
    assert diag.bump_recurrence("some.site.key") == 2
    assert diag.bump_recurrence("other.site") == 1
    assert diag.bump_recurrence("some.site.key") == 3


def test_third_recurrence_escalates_to_workaround():
    ctx = {}
    ap = {"capability": "some.site.key", "parked_goal": {}, "parked_title": None,
          "background": True, "fix_goal": {"title": "fix it"},
          "phase": "diagnosing", "attempts": 0, "hypotheses": [],
          "hyp_idx": 0, "hyp_tries": 0, "detect_total": 0, "recurrences": 3}
    ctx["_active_problem"] = ap
    out = pr._advance_fix(ctx, ap)
    assert out["status"] == "problem_workaround"
    assert "_active_problem" not in ctx


# ── F7 C1: internal failures route inward, never to the web ──────────────────────

def test_internal_failure_key_detected():
    assert pr._is_internal_failure("quality_standard.gate.write_exemplar")
    assert not pr._is_internal_failure("llm")
    assert not pr._is_internal_failure("some website")


def test_internal_failure_fix_goal_looks_inward():
    goal = pr._build_fix_goal("quality_standard.gate.write_exemplar", "it broke", {})
    assert goal["driven_by"] == "self_understanding"
    assert "search_own_files" in json.dumps(goal)


def test_internal_module_path_never_a_web_query():
    from brain.cognition.web_research import _is_external_subject
    assert not _is_external_subject(
        "Figure out why quality_standard.gate.write_exemplar isn't working")


# ── F8a: a missing manifest on a fresh life is not a failure ─────────────────────

def test_load_manifest_missing_file_is_not_a_failure(monkeypatch, tmp_path):
    from brain.agency import self_code
    from brain.utils.failure_counter import get_summary
    monkeypatch.setattr(self_code, "MANIFEST_FILE", tmp_path / "manifest.json")
    before = (get_summary().get("self_code.load_manifest") or {}).get("count", 0)
    assert self_code.load_manifest() == []
    after = (get_summary().get("self_code.load_manifest") or {}).get("count", 0)
    assert after == before


# ── F8c: person-facing seeds cut at word/sentence boundaries ─────────────────────

def test_cut_never_ends_mid_word():
    from brain.behavior.speech_content import _cut
    assert _cut("QuadRF can supply a full radio front end", 15) == "QuadRF can…"
    assert _cut("short", 140) == "short"
    assert _cut("One sentence. Another that goes on and on", 25) == "One sentence."


# ── Characterization: the QuadRF-shaped replay ───────────────────────────────────

def test_quadrf_shaped_replay_credit_is_bounded(tmp_path):
    """Same body, fresh timestamp footers, one committed goal — Run 6's exact
    pump shape. Total credit must stay ≤ 3 rows and the goal's value EMA must
    stay under 0.6 (it reached 0.8142 in the run)."""
    gid = "self_understanding-goal"
    # A lens with modest overlap (~0.2 alignment): "shielding" and "filtering"
    # appear in the body, the rest don't — the run's memos aligned ≈ 0.14.
    ctx = {"goal_lens": {"active": True, "goal_id": gid, "tokens": [
        "cognition", "introspection", "shielding", "filtering", "arbiter",
        "workspace", "binding", "ledger", "selector", "metacognition"]}}
    credited = 0
    for minute in range(10):
        content = (f"# Research memo: quadrf\n\n{_BODY}\n\n---\n"
                   f"source: fetch_and_read · 2026-07-11 18:{minute:02d}Z\n")
        row = el.record_effect("file_write", content, goal_id=gid, context=ctx,
                               metadata={"path": str(tmp_path / "memo_quadrf.md")})
        if row is not None and row.significance > 0:
            credited += 1
    assert credited <= 3
    ema = float(cv.signals_snapshot()[gid]["value_ema"])
    assert ema < 0.6
