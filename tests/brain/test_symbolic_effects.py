# AR1 (CODEBASE_AUDIT_2026-07-01 D7): the symbolic engine's productions —
# synthesized rules, crystallized skills, resolved experiments, established
# causal edges — must record credited effects on the ledger, bound to the
# committed goal when one exists, with duplicates deduped and a rate cap so a
# synthesis storm can't farm credit.
import pytest

from brain.agency import effect_ledger as el
from brain.symbolic.symbolic_effects import record_symbolic_effect

_RULE_TEXT = (
    "[synthesized L3 principle] conditions: uncertainty, confidence, avoidance, "
    "planning; conclusion: high uncertainty suppresses action across domains and "
    "shrinking the task restores initiation; causal: uncertainty exceeds confidence "
    "-> action initiation drops (task decomposition restores a tractable next step); "
    "generalised from 3 L2 rules"
)


@pytest.fixture(autouse=True)
def _isolate(tmp_path):
    from brain.cognition.global_workspace import reset_bound_goal_mirror_for_tests
    el.EFFECT_LEDGER_FILE = tmp_path / "effect_ledger.jsonl"
    el.reset_for_tests()
    reset_bound_goal_mirror_for_tests()
    yield
    el.reset_for_tests()
    reset_bound_goal_mirror_for_tests()


def test_symbolic_artifact_is_a_valid_kind():
    assert "symbolic_artifact" in el.EFFECT_KINDS


def test_rule_effect_credits_and_binds_to_committed_goal():
    ctx = {"committed_goal": {"id": "goal-77", "title": "understand avoidance"}}
    row = record_symbolic_effect("rule", _RULE_TEXT, context=ctx)
    assert row is not None
    assert row.kind == "symbolic_artifact"
    assert row.goal_id == "goal-77"
    assert row.significance == pytest.approx(0.5)
    assert (row.metadata or {}).get("kind") == "rule"
    assert el.has_qualifying_effect("goal-77")
    assert el.has_effect_kind("goal-77", "symbolic_artifact")


def test_ungoaled_when_no_committed_goal():
    # No committed goal anywhere (context empty, mirror empty) → ungoaled.
    row = record_symbolic_effect("rule", _RULE_TEXT, context={})
    assert row is not None
    assert row.goal_id is None


def test_mirror_attributes_contextless_effects():
    # 2026-07-02 fix: a contextless producer (edge establishment,
    # crystallization) still binds to the recently committed goal via the
    # workspace mirror — anonymous effects starved aspiration crediting.
    from brain.cognition.global_workspace import bound_goal
    bound_goal({"committed_goal": {"id": "goal-88", "title": "make a thing"}})
    row = record_symbolic_effect("rule", _RULE_TEXT, context=None)
    assert row is not None
    assert row.goal_id == "goal-88"


def test_duplicate_rule_dedupes_no_double_credit():
    assert record_symbolic_effect("rule", _RULE_TEXT) is not None
    assert record_symbolic_effect("rule", _RULE_TEXT) is None


def test_experiment_outranks_rule_significance():
    exp_text = (
        "[experiment resolved] goal: does symbolic coverage extend to planning; "
        "domain: planning; probe: rule_coverage; hypothesis: existing rules cover "
        "the planning query space; outcome: hit_rate=0.75 over 8 queries, "
        "success=True, rules_fired=5, domain_error=0.12"
    )
    row = record_symbolic_effect("experiment", exp_text)
    assert row is not None
    assert row.significance == pytest.approx(0.6)


def test_short_symbolic_content_earns_nothing():
    # a bare edge/rule string under MIN_ARTIFACT_CHARS is a hypothesis, not a production
    assert record_symbolic_effect("causal_edge", "curiosity -> exploration") is None


def test_rate_cap_stops_a_synthesis_storm():
    credited = 0
    for i in range(el._SYMBOLIC_CAP + 4):
        text = (
            f"[synthesized L3 principle number {i}] conditions: cluster{i}, tokens{i}, "
            f"observation{i}, pattern{i}; conclusion: distinct principle body {i} about "
            f"how repeated structure {i} in different surface contexts reveals a shared "
            f"mechanism worth acting on when planning the next investigation step; "
            f"generalised from {i + 2} instances"
        )
        if record_symbolic_effect("rule", text) is not None:
            credited += 1
    assert credited == el._SYMBOLIC_CAP


def test_synthesise_rules_records_effect(monkeypatch, tmp_path):
    # End-to-end through rule_synthesis: a synthesized principle lands on the ledger.
    from brain.symbolic import rule_synthesis as rs

    monkeypatch.setattr(rs, "SYNTHESIS_FILE", tmp_path / "rule_synthesis.json")
    monkeypatch.setattr(rs, "_last_run", 0.0)

    base = {
        "confidence": 0.8, "source": "observation", "abstraction_level": 2,
        "causal_claim": {
            "cause": "uncertainty exceeds confidence during planning",
            "effect": "action initiation drops for the whole session",
            "mechanism": "large ambiguous tasks give no tractable first step",
        },
    }
    rules = [
        {**base, "id": "r1",
         "conditions": ["uncertainty", "planning", "avoidance"],
         "conclusion": "when uncertainty exceeds confidence the goal is avoided",
         "prediction": "smaller task restores initiation",
         "recommended_action": "decompose the task"},
        {**base, "id": "r2",
         "conditions": ["uncertainty", "planning", "hesitation"],
         "conclusion": "when uncertainty is high planning stalls before the first step",
         "prediction": "smaller task restores initiation",
         "recommended_action": "decompose the task"},
    ]
    added = {}

    def fake_add_rule(**fields):
        added.update(fields)
        return {"id": "parent-1", **fields}

    monkeypatch.setattr(rs, "load_json", lambda *a, **k: [])
    import brain.symbolic.rule_engine as re_mod
    monkeypatch.setattr(re_mod, "get_all_rules", lambda: rules)
    monkeypatch.setattr(re_mod, "add_rule", fake_add_rule)

    out = rs.synthesise_rules(force=True)
    assert out.get("principles_added", 0) >= 1

    import json
    rows = [json.loads(ln) for ln in
            el.EFFECT_LEDGER_FILE.read_text(encoding="utf-8").splitlines() if ln]
    credited = [r for r in rows
                if r["kind"] == "symbolic_artifact" and not r["dedupe"]]
    assert credited, f"no credited symbolic_artifact row in {rows}"
    assert (credited[0].get("metadata") or {}).get("kind") == "rule"
