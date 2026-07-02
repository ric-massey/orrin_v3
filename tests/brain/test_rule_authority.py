# Tests for T1.2 — outcome-based rule authority + revision-queue drain
# (brain/symbolic/rule_verifier.py).
#
# Pins the Master-Plan done-when: a rule that mispredicts N times in a row (above
# the min-sample gate) loses priority with no human action; a proposed revision
# reaches applied/rejected within a bounded window; no domain is left with zero
# usable rules purely by retirement.

import pytest


@pytest.fixture()
def rv(tmp_path, monkeypatch):
    """rule_verifier + rule_engine pointed at temp data files (isolated)."""
    import brain.symbolic.rule_engine as re_mod
    import brain.symbolic.rule_verifier as rv_mod
    rules_file = tmp_path / "symbolic_rules.json"
    revs_file = tmp_path / "rule_revisions.json"
    monkeypatch.setattr(re_mod, "SYMBOLIC_RULES_FILE", rules_file)
    monkeypatch.setattr(rv_mod, "REVISIONS_FILE", revs_file)
    re_mod._rules_cache = []
    # Many distinct keyword-rich conclusions classify to the same domain, so give
    # each test rule its own domain control by stubbing _rule_domain per-test.
    return rv_mod, re_mod, rules_file, revs_file


def _mk(re_mod, conclusion, conf=0.30, **extra):
    r = re_mod.add_rule(["c1", "c2"], conclusion, confidence=conf)
    r.update(extra)
    # persist the extra fields
    rules = re_mod.get_all_rules()
    for i, x in enumerate(rules):
        if x["id"] == r["id"]:
            rules[i] = r
    from brain.utils.json_utils import save_json
    save_json(re_mod.SYMBOLIC_RULES_FILE, rules)
    re_mod._rules_cache = []
    return r


def _conf(re_mod, rid):
    for r in re_mod.get_all_rules():
        if r["id"] == rid:
            return r
    return None


# 1. Sustained misprediction strips authority toward the floor, not to zero.
def test_sustained_misprediction_strips_authority(rv, monkeypatch):
    rv_mod, re_mod, _, _ = rv
    # Two usable rules in the same domain so the over-retirement guard allows it.
    monkeypatch.setattr(rv_mod, "_rule_domain", lambda rule: "PLANNING")
    keep = _mk(re_mod, "a planning sibling rule", conf=0.80)
    bad = _mk(re_mod, "the chronically wrong planning rule", conf=0.30)

    for _ in range(rv_mod._MIN_SAMPLE + 2):
        rv_mod._adjust_confidence(bad["id"], rv_mod._PENALTY, "penalty",
                                  {"query_head": ""}, 0.0)
    r = _conf(re_mod, bad["id"])
    assert r["consecutive_misses"] >= rv_mod._MISS_STREAK_N
    # Authority stripped, but never below the floor (no collapse to zero).
    assert r["confidence"] >= rv_mod._AUTHORITY_FLOOR - 1e-9
    assert r["confidence"] <= rv_mod._TOMBSTONE_THRESH + 1e-9
    # Sibling untouched → domain still has a usable rule.
    assert _conf(re_mod, keep["id"])["confidence"] > rv_mod._TOMBSTONE_THRESH


# 2. A reward clears the miss streak.
def test_reward_resets_streak(rv, monkeypatch):
    rv_mod, re_mod, _, _ = rv
    monkeypatch.setattr(rv_mod, "_rule_domain", lambda rule: "PLANNING")
    r = _mk(re_mod, "a wobbly rule", conf=0.50)
    for _ in range(3):
        rv_mod._adjust_confidence(r["id"], rv_mod._PENALTY, "penalty", {"query_head": ""}, 0.0)
    assert _conf(re_mod, r["id"])["consecutive_misses"] == 3
    rv_mod._adjust_confidence(r["id"], rv_mod._REWARD, "reward", {"query_head": ""}, 0.9)
    assert _conf(re_mod, r["id"])["consecutive_misses"] == 0


# 3. Over-retirement guard: the last usable rule in a domain is floored, not tombstoned.
def test_last_in_domain_not_tombstoned(rv, monkeypatch):
    rv_mod, re_mod, _, _ = rv
    monkeypatch.setattr(rv_mod, "_rule_domain", lambda rule: "SOCIAL")
    only = _mk(re_mod, "the only social rule", conf=0.30)
    for _ in range(rv_mod._MIN_SAMPLE + 6):
        rv_mod._adjust_confidence(only["id"], rv_mod._PENALTY, "penalty", {"query_head": ""}, 0.0)
    r = _conf(re_mod, only["id"])
    assert r.get("source") != "tombstoned"          # never retired the last one
    assert r["confidence"] >= rv_mod._AUTHORITY_FLOOR - 1e-9


# 4. Under-learned rules are exempt from retirement (need acquisition, not deletion).
def test_low_sample_exempt(rv, monkeypatch):
    rv_mod, re_mod, _, _ = rv
    monkeypatch.setattr(rv_mod, "_rule_domain", lambda rule: "PLANNING")
    _mk(re_mod, "a planning sibling", conf=0.80)
    fresh = _mk(re_mod, "a brand new planning rule", conf=0.22)
    # Two penalties — below MIN_SAMPLE — even though confidence dips under tombstone.
    rv_mod._adjust_confidence(fresh["id"], -0.10, "penalty", {"query_head": ""}, 0.0)
    r = _conf(re_mod, fresh["id"])
    assert r["outcome_count"] < rv_mod._MIN_SAMPLE
    assert r.get("source") != "tombstoned"


# 5. drain_revisions resolves every pending revision (bounded window = one call).
def test_drain_resolves_pending(rv, monkeypatch):
    rv_mod, re_mod, _, _ = rv
    monkeypatch.setattr(rv_mod, "_rule_domain", lambda rule: "PLANNING")
    sib = _mk(re_mod, "a healthy planning sibling", conf=0.80)
    recovered = _mk(re_mod, "a rule that recovered", conf=0.60)
    persistent = _mk(re_mod, "a persistently wrong rule", conf=0.12,
                     outcome_count=20)
    # Flag all three for revision.
    for r in (sib, recovered, persistent):
        rv_mod._flag_for_revision(_conf(re_mod, r["id"]), 0.1, {"query_head": ""})
    assert len(rv_mod.get_pending_revisions()) == 3

    tally = rv_mod.drain_revisions()
    assert rv_mod.get_pending_revisions() == []        # nothing left pending
    assert tally["kept"] >= 2                            # sib + recovered earned their keep
    assert tally["retired"] >= 1                         # persistent + low-conf retired
    assert _conf(re_mod, persistent["id"]).get("source") == "tombstoned"


# 6. Fail-safe — draining an empty/missing queue is a no-op, never raises.
def test_drain_empty_safe(rv):
    rv_mod, _, _, _ = rv
    assert rv_mod.drain_revisions() == {"kept": 0, "weakened": 0, "retired": 0}
