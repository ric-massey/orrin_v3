"""Run-12 Slice 1B regression: the daemon research feed must not be starved.

1B.1/1B.2 — one symbolic generation pass emits the coverage-floor PRIMARY pick AND,
in addition, the research subset of the pool, so a `kind:"research"` goal is proposed
whenever one exists (independent of which aspiration the floor picked).

1B.3 — a research-feed heartbeat keeps the daemon fed on a ≤ 20-min cadence even
while a conscious goal holds the committed slot (Run 11: ~12 h daemon silence).
"""
import brain.cognition.intrinsic_generators as ig


def _make(monkeypatch, concept_goals, making_goals):
    monkeypatch.setattr(ig, "_goal_from_recent_research", lambda lm: None)
    monkeypatch.setattr(ig, "_concept_deepening_goals", lambda *a, **k: list(concept_goals))
    monkeypatch.setattr(ig, "_open_question_goals", lambda *a, **k: [])
    monkeypatch.setattr(ig, "_causal_frontier_goals", lambda *a, **k: [])
    monkeypatch.setattr(ig, "_tension_goals", lambda *a, **k: [])
    monkeypatch.setattr(ig, "_autobiographical_continuity_goals", lambda *a, **k: [])
    monkeypatch.setattr(ig, "_making_goals", lambda *a, **k: list(making_goals))
    monkeypatch.setattr(ig, "_contact_goals", lambda *a, **k: [])
    monkeypatch.setattr(ig, "_active_goal_titles", lambda: set())
    monkeypatch.setattr(ig, "_acceptable_goal_subject", lambda t: True)
    monkeypatch.setattr(ig, "_title_respawn_blocked", lambda t, now: False)


def test_batch_emits_research_alongside_make_primary(monkeypatch):
    """The coverage floor picks the starved MAKE goal; the research candidate must
    STILL be emitted in the same pass (previously it was starved out)."""
    research = {"title": "Understand entropy more deeply", "driven_by": "world_knowledge",
                "description": "learn", "kind": "research"}
    make = {"title": "Build a thing", "driven_by": "output_producing", "description": "make"}
    _make(monkeypatch, [research], [make])
    # MAKE is starved → coverage floor picks it as primary.
    monkeypatch.setattr(ig, "objective_pressure", lambda ctx: {"make": 0.9, "world": 0.1})
    monkeypatch.setattr(ig, "_serves_aspiration",
                        lambda d: "make" if d == "output_producing" else "world")

    batch = ig._varied_symbolic_goals({}, [])
    kinds = [g.get("kind") for g in batch]
    drivers = [g.get("driven_by") for g in batch]
    assert "output_producing" in drivers          # coverage-floor primary present
    assert "research" in kinds                     # research feed NOT starved
    assert batch[0]["driven_by"] == "output_producing"


def test_research_only_skips_primary(monkeypatch):
    research = {"title": "Understand X", "driven_by": "world_knowledge",
                "description": "d", "kind": "research"}
    make = {"title": "Build Y", "driven_by": "output_producing", "description": "d"}
    _make(monkeypatch, [research], [make])
    monkeypatch.setattr(ig, "objective_pressure", lambda ctx: {"make": 0.9})
    monkeypatch.setattr(ig, "_serves_aspiration",
                        lambda d: "make" if d == "output_producing" else "world")

    batch = ig._varied_symbolic_goals({}, [], research_only=True)
    assert batch  # something emitted
    assert all(g.get("kind") == "research" for g in batch)  # no conscious primary


def test_singular_wrapper_returns_primary(monkeypatch):
    research = {"title": "Understand X", "driven_by": "world_knowledge",
                "description": "d", "kind": "research"}
    _make(monkeypatch, [research], [])
    monkeypatch.setattr(ig, "objective_pressure", lambda ctx: {"world": 0.1})
    monkeypatch.setattr(ig, "_serves_aspiration", lambda d: "world")
    picked = ig._varied_symbolic_goal({}, [])
    assert picked is not None and picked["title"] == "Understand X"


import brain.cognition.intrinsic_goals as igoals


def _stub_heartbeat_deps(monkeypatch, batch):
    monkeypatch.setattr(igoals, "_ensure_aspirations", lambda: None)
    monkeypatch.setattr(igoals, "load_json", lambda *a, **k: [])
    monkeypatch.setattr(igoals, "_varied_symbolic_goals",
                        lambda ctx, lm, **kw: [dict(g) for g in batch])
    monkeypatch.setattr(igoals, "_enrich_goal_zone", lambda g: g)
    monkeypatch.setattr(igoals, "_under_load", lambda ctx: (False, ""))


def test_heartbeat_fires_when_cadence_elapsed(monkeypatch):
    monkeypatch.setattr(igoals, "_LAST_RESEARCH_FEED_TS", 0.0)
    r = {"title": "Understand Z", "driven_by": "world_knowledge",
         "description": "d", "kind": "research"}
    _stub_heartbeat_deps(monkeypatch, [r])
    ctx = {"_seed": 1}  # non-empty: `context or {}` would otherwise swap an empty dict
    out = igoals.research_feed_heartbeat(ctx)
    assert out and out[0]["kind"] == "research"
    assert ctx["proposed_goals"][0]["title"] == "Understand Z"


def test_heartbeat_noops_before_cadence(monkeypatch):
    import time
    monkeypatch.setattr(igoals, "_LAST_RESEARCH_FEED_TS", time.time())  # just fired
    _stub_heartbeat_deps(monkeypatch, [{"title": "x", "driven_by": "world_knowledge",
                                        "description": "d", "kind": "research"}])
    assert igoals.research_feed_heartbeat({}) == []


def test_heartbeat_respects_load(monkeypatch):
    monkeypatch.setattr(igoals, "_LAST_RESEARCH_FEED_TS", 0.0)
    _stub_heartbeat_deps(monkeypatch, [{"title": "x", "driven_by": "world_knowledge",
                                        "description": "d", "kind": "research"}])
    monkeypatch.setattr(igoals, "_under_load", lambda ctx: (True, "resource_deficit"))
    assert igoals.research_feed_heartbeat({}) == []
