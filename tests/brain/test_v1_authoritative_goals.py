# Part II of GOALS_MASTER_PLAN_2026-06-23 (Option D, D2 lifecycle inversion).
#
# The committed goal is chosen from the v1 cognitive tree (tier-then-priority
# ordered) — the single source of truth for what's committed; v2 still executes.
# These tests pin: the tree selection + ordering, the bucket/directional/terminal
# exclusions, and the v2→v1 reconcile that keeps v2-only goals from being stranded.
import brain.goal_io as goal_io
from brain.cognition.planning.goals import load_goals, save_goals


def _restore():
    save_goals([])


# ── tree selection + ordering ──────────────────────────────────────────────────

def test_committable_orders_by_tier_then_priority(monkeypatch):
    save_goals([
        {"name": "Immediate Actions", "tier": "short_term", "status": "active",
         "subgoals": [
             {"id": "g-grow", "name": "grow", "title": "grow", "tier": "growth",
              "status": "in_progress", "priority": 3},
             {"id": "g-surv", "name": "surv", "title": "surv", "tier": "survival",
              "status": "in_progress", "priority": 3},
         ]},
        {"id": "g-core", "name": "core", "title": "core", "tier": "core",
         "status": "proposed", "priority": 5},
    ])
    try:
        out = goal_io._committable_from_v1_tree(limit=3)
    finally:
        _restore()
    ids = [g["id"] for g in out]
    assert ids[0] == "g-surv"            # survival tier wins (weight 4)
    assert ids[1] == "g-core"            # then core (weight 3)
    assert ids[2] == "g-grow"            # then growth (weight 2)


def test_excludes_bucket_directional_and_terminal(monkeypatch):
    save_goals([
        {"name": "Immediate Actions", "tier": "short_term", "status": "active",
         "subgoals": [
             {"id": "ok", "name": "real goal", "title": "real goal",
              "tier": "core", "status": "in_progress"},
             {"id": "done", "name": "finished", "title": "finished",
              "tier": "core", "status": "completed"},
         ]},
        {"id": "asp", "name": "an aspiration", "title": "an aspiration",
         "tier": "aspiration", "status": "in_progress"},
    ])
    try:
        out = goal_io._committable_from_v1_tree(limit=10)
    finally:
        _restore()
    ids = {g["id"] for g in out}
    assert ids == {"ok"}                  # bucket, completed, aspiration all excluded
    assert "Immediate Actions" not in {g.get("name") for g in out}


# ── v2 → v1 reconcile (absorb) ───────────────────────────────────────────────────────────

class _FakePriority:
    name = "NORMAL"


class _FakeGoal:
    def __init__(self, gid, title, kind, spec):
        self.id = gid
        self.title = title
        self.kind = kind
        self.spec = spec
        self.tags = []
        self.priority = _FakePriority()
        self.deadline = None


def test_backfill_absorbs_v2_only_goals(monkeypatch):
    save_goals([])   # v1 empty; goal lives only in v2

    class _Api:
        def list_goals(self, **_kw):
            return [_FakeGoal("v2only", "a v2 goal", "generic",
                              spec={"tier": "survival", "driven_by": "resource_deficit"})]

    try:
        out = goal_io.committed_goals_v1(_Api(), {}, limit=3)
        # it was absorbed into v1 AND selected, with tier restored from spec
        assert any(g["id"] == "v2only" and g["tier"] == "survival" for g in out)
        # and it now exists in the v1 tree (not stranded in v2)
        tree_ids = {n.get("id") for n in load_goals()
                    for n in ([n] + (n.get("subgoals") or []))}
        assert "v2only" in tree_ids
    finally:
        _restore()


def test_backfill_is_idempotent(monkeypatch):
    save_goals([])

    class _Api:
        def list_goals(self, **_kw):
            return [_FakeGoal("g1", "dup goal", "generic", spec={"tier": "core"})]

    api = _Api()
    try:
        goal_io.committed_goals_v1(api, {}, limit=3)
        goal_io.committed_goals_v1(api, {}, limit=3)  # second pass
        # only one node for g1 — backfill didn't duplicate it
        count = sum(1 for top in load_goals()
                    for n in ([top] + (top.get("subgoals") or []))
                    if n.get("id") == "g1")
        assert count == 1
    finally:
        _restore()
