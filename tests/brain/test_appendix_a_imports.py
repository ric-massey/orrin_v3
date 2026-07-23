# RUN12 Appendix A — the Athena-Class imports (A.1.1 inference tax,
# A.1.2 convergence-spiral metric, A.1.3 stochastic contradiction surfacing).
# Each organ is individually ablatable (A.1.4 practice); the ablated paths are
# pinned here alongside the live ones.
from datetime import datetime, timedelta, timezone

import pytest

import brain.run_config as run_config
import brain.symbolic.rule_engine as re_mod
import brain.symbolic.rule_forgetting as rf_mod
from brain.utils.json_utils import save_json


@pytest.fixture()
def rules_file(tmp_path, monkeypatch):
    """Isolated rule store + a clean cache on both sides — a poisoned
    module-level rules cache must not leak into other tests' selections."""
    path = tmp_path / "symbolic_rules.json"
    monkeypatch.setattr(re_mod, "SYMBOLIC_RULES_FILE", path)
    monkeypatch.setattr(rf_mod, "_WAL_FILE", tmp_path / "rule_firings.jsonl")
    re_mod._rules_cache = []
    yield path
    re_mod._rules_cache = []


def _old_iso(days: int = 100) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


# ─── A.1.1 — inference distance stamped at birth ───────────────────────────────

def test_confirmed_prediction_is_distance_zero(rules_file):
    r = re_mod.add_rule(
        conditions=["cpu high"], conclusion="load causes cpu spikes",
        source="confirmed_prediction",
    )
    assert r["inference_distance"] == 0


def test_reflection_sources_default_distance_one(rules_file):
    r = re_mod.add_rule(
        conditions=["pattern"], conclusion="i tend to avoid hard steps",
        source="metacog",
    )
    assert r["inference_distance"] == 1


def test_derived_rule_sits_one_hop_past_cited_parent(rules_file):
    base = re_mod.add_rule(
        conditions=["obs"], conclusion="reading pages yields memos",
        source="confirmed_prediction",
    )
    d1 = re_mod.add_rule(
        conditions=["obs"], conclusion="research activity produces artifacts",
        source="abstraction", evidence_ids=[base["id"]],
    )
    d2 = re_mod.add_rule(
        conditions=["obs"], conclusion="production follows engagement generally",
        source="abstraction", evidence_ids=[d1["id"]],
    )
    assert d1["inference_distance"] == 1
    assert d2["inference_distance"] == 2


def test_legacy_rule_distance_derived_not_defaulted(rules_file):
    # Rules born before the field existed derive distance from provenance.
    legacy_exp = {"id": "aa", "conclusion": "x", "source": "confirmed_prediction"}
    legacy_ref = {"id": "bb", "conclusion": "y", "source": "metacog"}
    by_id = {"aa": legacy_exp, "bb": legacy_ref}
    assert re_mod.rule_inference_distance(legacy_exp, by_id) == 0
    assert re_mod.rule_inference_distance(legacy_ref, by_id) == 1


def test_distance_cycle_is_safe(rules_file):
    a = {"id": "a1", "conclusion": "x", "source": "abstraction", "evidence_ids": ["b1"]}
    b = {"id": "b1", "conclusion": "y", "source": "abstraction", "evidence_ids": ["a1"]}
    by_id = {"a1": a, "b1": b}
    assert re_mod.rule_inference_distance(a, by_id) >= 1  # terminates, no recursion blowup


# ─── A.1.1 — the tax at decay time ─────────────────────────────────────────────

def _seed_idle_pair(path):
    rules = [
        {"id": "exp1", "conditions": ["c"], "conclusion": "experience-born rule",
         "source": "confirmed_prediction", "confidence": 0.8, "hits": 0,
         "created_at": _old_iso()},
        {"id": "ref1", "conditions": ["c"], "conclusion": "reflection-born rule",
         "source": "metacog", "confidence": 0.8, "hits": 0,
         "created_at": _old_iso()},
    ]
    save_json(path, rules)
    re_mod._rules_cache = []
    return rules


def test_reflection_born_rule_decays_faster(rules_file):
    _seed_idle_pair(rules_file)
    decayed = rf_mod.decay_idle_rules()
    assert decayed == 2
    by_id = {r["id"]: r for r in re_mod.get_all_rules()}
    assert by_id["ref1"]["confidence"] < by_id["exp1"]["confidence"]
    assert rf_mod._last_taxed_count == 1  # only the distance>=1 rule was taxed


def test_tax_ablation_restores_flat_decay(rules_file, monkeypatch):
    monkeypatch.setattr(run_config, "_cached", frozenset({"inference_tax"}))
    _seed_idle_pair(rules_file)
    decayed = rf_mod.decay_idle_rules()
    assert decayed == 2
    by_id = {r["id"]: r for r in re_mod.get_all_rules()}
    assert by_id["ref1"]["confidence"] == by_id["exp1"]["confidence"]
    assert rf_mod._last_taxed_count == 0


# ─── A.1.2 — convergence-spiral metric ─────────────────────────────────────────

def test_spiral_ratio_counts_edge_classes(rules_file):
    base = re_mod.add_rule(conditions=["c"], conclusion="observed effect one",
                           source="confirmed_prediction")
    d1 = re_mod.add_rule(conditions=["c"], conclusion="derived pattern one",
                         source="abstraction", evidence_ids=[base["id"]])
    re_mod.add_rule(conditions=["c"], conclusion="derived principle one",
                    source="abstraction", evidence_ids=[d1["id"]])

    from brain.cognition.convergence_metric import convergence_spiral_report
    report = convergence_spiral_report()
    assert report["available"] is True
    assert report["reflection_on_experience_edges"] == 1   # d1 → base
    assert report["reflection_on_reflection_edges"] == 1   # d2 → d1
    assert report["spiral_ratio"] == 1.0
    assert report["mean_inference_distance"] == 1.0        # (0 + 1 + 2) / 3


def test_spiral_ratio_zero_when_no_edges(rules_file):
    re_mod.add_rule(conditions=["c"], conclusion="lone grounded rule",
                    source="confirmed_prediction")
    from brain.cognition.convergence_metric import convergence_spiral_report
    report = convergence_spiral_report()
    assert report["spiral_ratio"] == 0.0
    assert report["reflection_on_reflection_edges"] == 0


# ─── A.1.3 — stochastic contradiction surfacing ────────────────────────────────

_POSITION = "the web research approach is working well and produces good memos"
_CONFLICT = "the web research approach is not working well and produces no good memos"


@pytest.fixture()
def surfacing(rules_file, tmp_path, monkeypatch):
    import brain.cognition.contradiction_surfacing as cs
    monkeypatch.setattr(cs, "_SURFACING_LOG", tmp_path / "contradiction_surfacing.json")
    re_mod.add_rule(conditions=["c"], conclusion=_CONFLICT,
                    source="crystallization", confidence=0.7)
    return cs


def test_surfaces_conflicting_rule_as_workspace_offer(surfacing, monkeypatch):
    monkeypatch.setattr(surfacing.random, "random", lambda: 0.0)
    ctx = {"global_workspace": {"content": _POSITION}}
    rid = surfacing.maybe_surface_contradiction(ctx)
    assert rid
    offers = ctx.get("_workspace_offers") or []
    assert any(o["source"] == "contradiction_surfacing" for o in offers)
    # It competes at modest salience — never a guaranteed winner.
    offered = next(o for o in offers if o["source"] == "contradiction_surfacing")
    assert offered["salience"] < 0.9


def test_no_roll_no_offer(surfacing, monkeypatch):
    monkeypatch.setattr(surfacing.random, "random", lambda: 0.99)
    ctx = {"global_workspace": {"content": _POSITION}}
    assert surfacing.maybe_surface_contradiction(ctx) is None
    assert not ctx.get("_workspace_offers")


def test_ablated_never_surfaces(surfacing, monkeypatch):
    monkeypatch.setattr(run_config, "_cached", frozenset({"contradiction_surfacing"}))
    monkeypatch.setattr(surfacing.random, "random", lambda: 0.0)
    ctx = {"global_workspace": {"content": _POSITION}}
    assert surfacing.maybe_surface_contradiction(ctx) is None
    assert not ctx.get("_workspace_offers")


def test_no_conscious_position_no_offer(surfacing, monkeypatch):
    monkeypatch.setattr(surfacing.random, "random", lambda: 0.0)
    ctx = {}
    assert surfacing.maybe_surface_contradiction(ctx) is None


def test_coherent_position_finds_no_conflict(surfacing, monkeypatch):
    monkeypatch.setattr(surfacing.random, "random", lambda: 0.0)
    ctx = {"global_workspace": {"content": "thinking about lunch options today"}}
    assert surfacing.maybe_surface_contradiction(ctx) is None
