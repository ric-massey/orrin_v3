# Part II of GOALS_MASTER_PLAN_2026-06-23 (Option D) — projection invariants.
#
# The v1 cognitive goal is authoritative for the rich layering (tier/origin) that
# v2's flat Goal model can't hold; the v2 record is a PROJECTION (carried in spec),
# not a competing original. These tests lock the seam-drift bug as an invariant:
#   • a v2 round-trip must NOT strip the v1-authoritative cognitive fields
#     (the bug: _goal_to_v1 defaulted tier=kind, dropping a survival goal's tier);
#   • the projection must be reconstructible (project→read preserves the fields);
#   • legacy goals (no contract fields in spec) still fall back to kind, no crash;
#   • the live v1 node wins over the spec snapshot (v1 node → spec → kind).
import brain.goal_io as goal_io
from brain.cognition.planning.goals import save_goals


class _FakePriority:
    name = "NORMAL"


class _FakeGoal:
    """Mimics goals.model.Goal's flat shape for _goal_to_v1 / committed_goals_v1."""
    def __init__(self, gid, title, kind, spec, status_name="NEW"):
        self.id = gid
        self.title = title
        self.kind = kind
        self.spec = spec
        self.tags = []
        self.priority = _FakePriority()
        self.deadline = None
        self.status = status_name


# ── round-trip preservation (the core fix) ─────────────────────────────────────

def test_survival_tier_survives_v2_roundtrip():
    # A recruited survival goal projected to v2 carries kind="generic"; its tier and
    # origin live in spec. The read must restore them, not collapse tier→kind.
    g = _FakeGoal(
        "g1", "Restore: rest needed", "generic",
        spec={"tier": "survival", "driven_by": "resource_deficit",
              "recruit_aid": "resource_deficit_critical", "plan": [{"step": "rest"}]},
    )
    d = goal_io._goal_to_v1(g)
    assert d["tier"] == "survival"               # NOT "generic"
    assert d["driven_by"] == "resource_deficit"
    assert d["recruit_aid"] == "resource_deficit_critical"
    assert d["kind"] == "generic"                # kind itself is unchanged


def test_legacy_goal_without_contract_fields_falls_back_to_kind():
    g = _FakeGoal("g2", "research birds", "research", spec={"plan": [{"step": "x"}]})
    d = goal_io._goal_to_v1(g)
    assert d["tier"] == "research"               # legacy fallback, no crash
    assert "driven_by" not in d or d.get("driven_by") is None


# ── projection stashes the authoritative fields into spec ──────────────────────

def test_sync_projects_cognitive_fields_into_spec(monkeypatch):
    captured = {}

    class _Api:
        def list_goals(self, **_kw):
            return []                            # nothing exists → not a dup
        def create_goal(self, **kw):
            captured.update(kw)
            return _FakeGoal("new", kw["title"], kw["kind"], kw.get("spec") or {})

    ctx = {"proposed_goals": [{
        "title": "Restore: rest needed", "kind": "generic", "tier": "survival",
        "driven_by": "resource_deficit", "recruit_aid": "resource_deficit_critical",
        "milestones": [{"text": "restored", "met": False}],
    }]}
    goal_io.sync_proposed_goals(_Api(), ctx)
    spec = captured.get("spec") or {}
    assert spec.get("tier") == "survival"
    assert spec.get("driven_by") == "resource_deficit"
    assert spec.get("recruit_aid") == "resource_deficit_critical"


def test_project_then_read_reconstructs_the_goal(monkeypatch):
    # The end-to-end invariant: project a goal, then read it back from a v2 Goal
    # built from the projected spec — the authoritative fields must reappear.
    captured = {}

    class _Api:
        def list_goals(self, **_kw):
            return []
        def create_goal(self, **kw):
            captured.update(kw)
            return None

    ctx = {"proposed_goals": [{
        "title": "Turn X into a synthesis", "kind": "generic", "tier": "core",
        "driven_by": "output_producing", "serves": "make_things",
        "milestones": [{"text": "made", "met": False}],
    }]}
    goal_io.sync_proposed_goals(_Api(), ctx)
    projected = _FakeGoal("g3", captured["title"], captured["kind"], captured["spec"])
    d = goal_io._goal_to_v1(projected)
    assert d["tier"] == "core" and d["driven_by"] == "output_producing"
    assert d["serves"] == "make_things"


# ── live v1 node wins over the spec snapshot ───────────────────────────────────

def test_live_v1_node_overrides_spec(monkeypatch):
    # v2 spec says tier=growth (stale projection); the live v1 node says survival.
    # committed_goals_v1 must surface the node's value (v1 node → spec → kind).
    save_goals([{"id": "g4", "name": "Restore: rest", "title": "Restore: rest",
                 "status": "in_progress", "tier": "survival",
                 "driven_by": "resource_deficit"}])
    g = _FakeGoal("g4", "Restore: rest", "generic",
                  spec={"tier": "growth", "driven_by": "curiosity"})

    class _Api:
        def list_goals(self, **_kw):
            return [g]

    try:
        out = goal_io.committed_goals_v1(_Api(), limit=3)
    finally:
        save_goals([])                           # don't leak fixture state
    assert out and out[0]["tier"] == "survival"  # node wins, not the stale spec
    assert out[0]["driven_by"] == "resource_deficit"
