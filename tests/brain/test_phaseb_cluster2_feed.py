"""Phase B cluster 2 — the feed (B13, B6, B7, B5, B4).

Fixtures are Run 13 artifacts: the knowledge graph's 26 concept names and eight
research claims.json files (tests/fixtures/run13/).
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "run13"

# Run 13's junk concepts (verdict §4 / brief B4) and the real ones beside them.
_JUNK = {"world a world", "See More Results Suggestions", "this game-playing ai",
         "but what if there", "round the sun", "Make things",
         "Is AI the End of Math As We Know It? | Quanta Magazine"}


# ── B4: one cleaner for chrome, fragments and own titles ─────────────────────

def test_run13_junk_concepts_rejected_real_ones_kept():
    from brain.utils.topic_clean import is_junk_topic, own_titles
    names = json.loads((FIX / "kg_concept_names.json").read_text())
    rejected = {n for n in names if is_junk_topic(n, own_titles())}
    assert _JUNK <= rejected
    for real in ("evolutionary biology", "philosophy of mathematics", "The Daily Stoic",
                 "history of written language", "emergence in complex systems"):
        assert real not in rejected


def test_kg_gate_refuses_junk_concepts():
    from brain.cognition.knowledge_graph_extract import _validate_candidate
    for junk in _JUNK:
        ok, _c, reason = _validate_candidate(junk, "concept", 0.8, "definition")
        assert not ok, junk
    ok, _c, _r = _validate_candidate("evolutionary biology", "concept", 0.8, "definition")
    assert ok


def test_encyclopedia_hatnote_is_not_an_answer():
    from brain.utils.topic_clean import strip_chrome
    s = ("From Wikipedia, the free encyclopedia This article is about the history of "
         "evolutionary thought in biology.")
    assert strip_chrome(s) == ""


# ── B6: his own research feeds the pool its next topics ──────────────────────

@pytest.fixture()
def run13_claims(tmp_path, monkeypatch):
    for i, f in enumerate(sorted((FIX / "claims").glob("*.json"))):
        d = tmp_path / "artifacts" / f"g{i}"
        d.mkdir(parents=True)
        shutil.copy(f, d / "claims.json")
    monkeypatch.setattr("brain.paths.GOALS_DIR", tmp_path)
    return tmp_path


def test_neighbour_topics_from_run13_claims(run13_claims):
    from brain.cognition import intrinsic_generators as ig
    topics = ig._neighbour_topics()
    assert "Sisu" in topics and "phylogeny" in topics
    # Never the topic the claim already asked about, never a common-noun fragment.
    for bad in ("The Daily Stoic", "Evolutionary biology", "The field", "One major obstacle",
                "the other curves", "episodes List of episodes This"):
        assert bad not in topics
    goals = ig._neighbour_topic_goals(limit=3)
    assert goals and all(g["kind"] == "research" for g in goals)
    assert all(g["spec"]["queries"][0] in topics for g in goals)


def test_empty_research_lane_pulls_generation(monkeypatch):
    import brain.goal_io as gio
    from brain.think.think_utils.selection import score_actions as sa
    from goals.model import Status

    def api(kinds):
        return SimpleNamespace(list_goals=lambda **k: [
            SimpleNamespace(kind=kd, status=Status.RUNNING) for kd in kinds])

    monkeypatch.setattr(gio, "_api_ref", api([]))
    assert sa._research_lane_pull({}, 1) == pytest.approx(0.30)
    monkeypatch.setattr(gio, "_api_ref", api(["research", "characterize"]))
    assert sa._research_lane_pull({}, 2) == pytest.approx(0.12)
    monkeypatch.setattr(gio, "_api_ref", api(["research", "research"]))
    assert sa._research_lane_pull({}, 3) == 0.0


# ── B13: one unacted cycle no longer blocks origination ──────────────────────

def test_generation_runs_with_open_action_debt(monkeypatch):
    from brain.cognition import intrinsic_goals as ig
    goal = {"title": "Understand tides more deeply", "kind": "research",
            "driven_by": "world_knowledge", "description": "tides"}
    monkeypatch.setattr(ig, "_LAST_INTRINSIC_TS", 0.0)
    monkeypatch.setattr(ig, "_under_load", lambda ctx: (False, ""))
    monkeypatch.setattr(ig, "llm_callable_by", lambda caller: False)
    monkeypatch.setattr(ig, "_ensure_aspirations", lambda: None)
    monkeypatch.setattr(ig, "_varied_symbolic_goals", lambda ctx, lm: [dict(goal)])
    monkeypatch.setattr(ig, "_enrich_goal_zone", lambda g: g)
    ctx = {"action_debt": 40,
           "committed_goal": {"title": "Something else", "id": "g1", "status": "in_progress"}}
    out = ig.generate_intrinsic_goals(ctx)
    assert [g["title"] for g in out] == [goal["title"]]
    assert ctx["proposed_goals"][-1]["title"] == goal["title"]


# ── B7: a no-op instrument is not goal service ───────────────────────────────

def test_breaker_stops_sparing_a_noop_instrument(monkeypatch):
    from brain.cognition import metacog_analyze as ma
    from brain.cognition import action_accounting
    monkeypatch.setattr(action_accounting, "cycle_produced_goal_action", lambda ctx: False)
    monkeypatch.setattr(ma.random, "random", lambda: 0.99)
    # Keep the mute out of the process-wide bandit (it would leak into the
    # selector goldens); the selection-level cooldown on context is asserted.
    monkeypatch.setattr("brain.think.bandit.contextual_bandit.suppress_action",
                        lambda *a, **k: None)
    picks = ["research_topic", "reflection", "research_topic", "self_review",
             "detect_tensions", "narrative_update", "introspective_planning", "associative_recall"]

    def ctx(streak):
        return {"recent_picks": list(picks), "action_debt": 12,
                "committed_goal": {"title": "understand tides", "id": "g1"},
                "cycle_count": {"count": 100}, "affect_state": {"core_signals": {}},
                "_fn_noop_streak": {"research_topic": streak}}

    working = ctx(0)
    ma.metacog_analyze(working)
    assert "research_topic" not in (working.get("_fn_suppression") or {})
    idle = ctx(5)
    ma.metacog_analyze(idle)
    assert "research_topic" in (idle.get("_fn_suppression") or {})


# ── B5: rounds stop at the angles' end ───────────────────────────────────────

def test_research_rounds_stop_at_max(monkeypatch):
    import brain.goal_io as gio
    base = "Understand The Daily Stoic more deeply"
    finished = [SimpleNamespace(id=f"g{i}", title=base if i == 0 else f"{base} — round {i + 1}",
                                kind="research", status="DONE") for i in range(gio.MAX_ROUND)]
    created: list = []
    api = SimpleNamespace(list_goals=lambda **k: finished,
                          create_goal=lambda **k: created.append(k) or SimpleNamespace(id="gx"))
    monkeypatch.setattr(gio, "_load_v1_tree", lambda: [])
    ctx = {"proposed_goals": [{"title": base, "kind": "research",
                               "milestones": ["m"], "spec": {"queries": ["The Daily Stoic"]}}]}
    gio.sync_proposed_goals(api, ctx)
    assert created == []
    assert gio.MAX_ROUND <= 4

    monkeypatch.setattr(gio, "_api_ref", api)
    gio._finished_rounds_cache["ts"] = 0.0
    assert gio.rounds_exhausted(base)
    assert gio.rounds_exhausted(f"{base} — round 3")


def test_round_angles_never_repeat():
    import brain.goal_io as gio
    seen = []
    for k in range(2, gio.MAX_ROUND + 1):
        gd = {"title": "Understand X more deeply", "kind": "research", "spec": {}}
        gio._make_followon(gd, dict(gd), gd["title"], [f"p{i}" for i in range(k - 1)])
        seen.append(tuple(gd["spec"]["queries"]))
    assert len(seen) == len(set(seen))


# ── Smoke life 2026-10-08 follow-ups ─────────────────────────────────────────

def test_direct_commit_never_picks_a_daemon_only_goal():
    from brain.cognition.commitment_competition import _select_commit_proposal
    char = {"title": "Characterize what makes my CPU load climb", "kind": "characterize",
            "driven_by": "self_exploration"}
    assert _select_commit_proposal([char], {}) is None
    other = {"title": "Understand tides more deeply", "kind": "research",
             "driven_by": "world_knowledge"}
    assert _select_commit_proposal([char, other], {}) is other


def test_newborn_pool_still_offers_research(monkeypatch, tmp_path):
    """The smoke life's KG held 2 concepts and no claims: the pool offered no
    research and the daemon lane was silent all life."""
    from brain.cognition import intrinsic_generators as ig
    monkeypatch.setattr("brain.paths.GOALS_DIR", tmp_path)
    monkeypatch.setattr("brain.cognition.knowledge_graph._load_graph",
                        lambda: {"entities": {}, "relations": []})
    pool = ig._build_symbolic_pool({}, [])
    research = [g for g in pool if g.get("kind") == "research"]
    assert research
    from brain.cognition.web_research import _INTERESTING_FALLBACKS
    assert any(g["spec"]["queries"][0] in _INTERESTING_FALLBACKS for g in research)


def test_throttle_is_flagged_not_a_noop(monkeypatch):
    import time
    from brain.cognition import web_research as wr
    monkeypatch.setattr(wr, "_last_research", time.time())
    out = wr.research_topic({})
    assert out.get("throttled") is True and out.get("changed") is False


def test_noop_rule_spares_throttles():
    """B7 as fixed after smoke life 1: {"changed": False} is a no-op; a throttle
    is the action resting; anything else is a real result."""
    from brain.cognition.action_accounting import is_noop_result
    assert is_noop_result({"changed": False, "reason": "no fresh topic — everything tried recently"})
    assert is_noop_result({"changed": False, "reason": "No URL found to read right now."})
    assert not is_noop_result({"changed": False, "throttled": True, "reason": "research throttled"})
    assert not is_noop_result({"changed": True})
    assert not is_noop_result("Researched 'tides': …")
    assert not is_noop_result([])



def test_continuity_batch_without_context_reaches_the_handoff(monkeypatch):
    """Smoke life 2: closes with no live context generated into a throwaway dict
    and the batch was lost while the cooldown still started."""
    import brain.goal_io as gio
    import brain.cognition.intrinsic_goals as ig
    from brain.cognition.planning.goal_outcomes import mark_goal_completed
    gio._drain_pending_proposals({})
    seed = {"title": "Understand Robertson more deeply", "kind": "research",
            "driven_by": "world_knowledge", "description": "d"}
    monkeypatch.setattr(ig, "generate_intrinsic_goals", lambda ctx: [dict(seed)])
    goal = {"title": "Strengthen EMOTIONAL symbolic reasoning", "name": "Strengthen EMOTIONAL symbolic reasoning",
            "id": "g_sym", "status": "in_progress", "tier": "short_term",
            "milestones": [{"text": "done", "met": True}]}
    mark_goal_completed(goal)          # no context — the sweep path
    queued: dict = {}
    gio._drain_pending_proposals(queued)
    assert [g["title"] for g in queued.get("proposed_goals", [])] == [seed["title"]]


def test_preposition_led_fragment_is_not_a_topic():
    from brain.utils.topic_clean import clean_topic
    assert clean_topic("Within each papilla", strict=True) is None
    assert clean_topic("Taste", strict=True) == "Taste"
