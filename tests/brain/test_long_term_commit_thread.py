"""P4 — let long-term goals actually drive.

A directional long_term goal is committable-but-non-terminal (goal_io gate + the
mark_goal_completed guard), and the long_term_driver threads a `frontier` across
sessions: session N's failed check becomes session N+1's sub-task target. The parent
never files DONE.
"""

import brain.goal_io as gio
import brain.cognition.planning.long_term_driver as ltd
import brain.cognition.planning.goal_outcomes as go


# ── goal_io gate: directional long_term is committable, capped to one ────────────

def _tree():
    return [
        {"name": "Immediate Actions", "status": "pending", "subgoals": []},
        {"name": "drive A", "title": "drive A", "tier": "long_term", "status": "pending",
         "directional": True, "priority": "HIGH"},
        {"name": "drive B", "title": "drive B", "tier": "long_term", "status": "pending",
         "directional": True, "priority": "NORMAL"},
        {"name": "signpost", "title": "signpost", "tier": "long_term", "status": "pending"},
        {"name": "ordinary", "title": "ordinary", "tier": "core", "status": "pending"},
        {"name": "aspire", "title": "aspire", "tier": "aspiration", "status": "pending"},
    ]


def test_directional_long_term_is_committable_capped(monkeypatch):
    monkeypatch.setattr(gio, "_load_v1_tree", lambda: _tree())
    names = {g.get("name") for g in gio._committable_from_v1_tree(limit=10)}
    assert "ordinary" in names                 # ordinary goals still commit
    assert "aspire" not in names               # aspirations never commit
    assert "signpost" not in names             # non-directional long_term stays a signpost
    directional = names & {"drive A", "drive B"}
    assert len(directional) == 1               # cap: exactly one directional driver
    assert "drive A" in directional            # the higher-priority one wins


# ── mark_goal_completed guard: a directional driver never files DONE ─────────────

def test_directional_goal_never_completes(monkeypatch):
    monkeypatch.setattr(go, "log_activity", lambda *a, **k: None)
    goal = {"id": "d1", "title": "drive", "tier": "long_term",
            "directional": True, "status": "in_progress"}
    go.mark_goal_completed(goal, context={}, satiety_close=True)
    assert goal["status"] != "completed"
    # even a plain long_term (no explicit flag) is protected
    goal2 = {"id": "d2", "title": "roadmap", "tier": "long_term", "status": "in_progress"}
    go.mark_goal_completed(goal2, context={})
    assert goal2["status"] != "completed"


# ── the frontier thread across sessions ──────────────────────────────────────────

def _fail_live_child(driver, gap):
    """Simulate the live sub-task failing its check (Phase 3 writes _last_check_gap)."""
    child = ltd._live_child(driver)
    assert child is not None
    child["status"] = "failed"
    child["_last_check_gap"] = gap
    return child


def test_frontier_threads_across_three_sessions():
    driver = {"id": "understand_time", "title": "Understand time more deeply",
              "tier": "long_term", "status": "in_progress", "priority": "HIGH"}
    goals = [driver]

    # Session 1: promote, seed frontier from the subject, spawn sub-task S1
    s1 = ltd.drive_long_term(goals)
    assert s1["driver"] == "understand_time"
    assert driver.get("directional") is True
    kids = ltd._frontier_children(driver)
    assert len(kids) == 1
    assert kids[0]["frontier_target"] == driver["frontier"]        # S1 targets the seed frontier
    seed_frontier = driver["frontier"]

    # S1 fails its check with a specific gap
    _fail_live_child(driver, "the block-universe vs presentism distinction")

    # Session 2: absorb the gap into the frontier, spawn S2 aimed at it
    s2 = ltd.drive_long_term(goals)
    assert s2["absorbed"] == "the block-universe vs presentism distinction"
    assert driver["frontier"] == "the block-universe vs presentism distinction"
    kids = ltd._frontier_children(driver)
    assert len(kids) == 2
    assert kids[1]["frontier_target"] == "the block-universe vs presentism distinction"
    assert kids[1]["frontier_target"] != seed_frontier            # a NEW target, not a repeat

    # S2 fails with a further gap
    _fail_live_child(driver, "how entropy defines the arrow")

    # Session 3: thread advances again
    s3 = ltd.drive_long_term(goals)
    assert s3["absorbed"] == "how entropy defines the arrow"
    kids = ltd._frontier_children(driver)
    assert len(kids) == 3
    assert kids[2]["frontier_target"] == "how entropy defines the arrow"

    # exactly one live sub-task at any time; parent never terminal; thread recorded
    live = [c for c in kids if c["status"] not in ltd._TERMINAL]
    assert len(live) == 1
    assert driver["status"] != "completed"
    assert len(driver.get("frontier_thread", [])) == 2            # two absorptions


def test_no_double_spawn_while_subtask_live():
    driver = {"id": "g", "title": "Understand minds", "tier": "long_term",
              "status": "in_progress"}
    goals = [driver]
    ltd.drive_long_term(goals)
    n_after_first = len(ltd._frontier_children(driver))
    # driving again while the sub-task is still live must NOT spawn another
    ltd.drive_long_term(goals)
    assert len(ltd._frontier_children(driver)) == n_after_first == 1


def test_cap_one_directional_among_many():
    goals = [
        {"id": "a", "tier": "long_term", "status": "in_progress", "priority": "NORMAL"},
        {"id": "b", "tier": "long_term", "status": "in_progress", "priority": "HIGH"},
        {"id": "c", "tier": "long_term", "status": "in_progress", "priority": "LOW"},
    ]
    driver = ltd.promote_one_directional(goals)
    assert driver["id"] == "b"                                    # highest priority drives
    directional = [g for g in goals if g.get("directional")]
    assert len(directional) == 1 and directional[0]["id"] == "b"


def test_run_long_term_driver_persists(monkeypatch):
    tree = [{"id": "lt", "title": "Understand X", "tier": "long_term", "status": "in_progress"}]
    saved = {}
    monkeypatch.setattr("brain.cognition.planning.goal_store.load_goals", lambda: tree)
    monkeypatch.setattr("brain.cognition.planning.goal_store.save_goals",
                        lambda g: saved.setdefault("tree", g))
    summary = ltd.run_long_term_driver(context={})
    assert summary.get("driver") == "lt"
    assert saved.get("tree") is tree
    assert tree[0].get("directional") is True
