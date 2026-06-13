# Tests for reactive problem refocus (cognition/planning/problem_refocus.py).
#
# Two regimes (BEHAVIOR_FIX_PLAN 0.3 — the LLM is only a tool):
#
#   * Registry-TOOL capabilities (llm): an outage is a normal fact. The fix
#     goal runs in the BACKGROUND as an ordinary curiosity goal with a capped
#     motivational weight — the committed goal is never parked, the focus slot
#     is never seized, and affect gets a wonder nudge, not an impasse spike.
#
#   * Non-tool capabilities: the original human reflex — park the current goal,
#     refocus on a fix micro-goal, resume once fixed or work around it.
#
# Failure detection and capability health are seam-injected via monkeypatch so
# no real LLM/network is touched.
import cognition.planning.problem_refocus as pr


def _ctx(goal_title="Research black holes", **extra):
    ctx = {
        "committed_goal": {
            "title": goal_title, "name": goal_title,
            "kind": "cognitive", "milestones": [],
        },
        "working_memory": [],
        "affect_state": {"core_signals": {}},
        "cycle_count": {"count": 1},
    }
    ctx.update(extra)
    return ctx


def _seed_baseline(ctx, monkeypatch, llm=0, sites=None):
    """Run one cycle that just seeds the failure baseline (no problem yet)."""
    monkeypatch.setattr(pr, "_fingerprint", lambda: {"llm": llm, "sites": dict(sites or {})})
    # healthy by default during seeding
    monkeypatch.setattr(pr, "_capability_healthy", lambda cap, ap=None: True)
    out = pr.handle_problem_refocus(ctx)
    assert out["status"] == "baseline_init"


def _no_goal_tree_writes(monkeypatch):
    """Keep the background path off the live goals_mem.json file."""
    import cognition.planning.goals as goals_mod
    monkeypatch.setattr(goals_mod, "add_goal", lambda g, parent_name=None: g)
    monkeypatch.setattr(goals_mod, "mark_goal_status_by_name", lambda n, s: True)


# ── detection / no-trigger ──────────────────────────────────────────────────────

def test_no_trigger_without_failures(monkeypatch):
    ctx = _ctx()
    _seed_baseline(ctx, monkeypatch)
    out = pr.handle_problem_refocus(ctx)
    assert out["status"] == "ok"
    assert "_active_problem" not in ctx
    # original goal untouched
    assert ctx["committed_goal"]["title"] == "Research black holes"


def test_llm_outage_without_goal_starts_background(monkeypatch):
    # A tool outage needs no goal to park — the curiosity investigation starts
    # in the background regardless.
    _no_goal_tree_writes(monkeypatch)
    ctx = _ctx()
    ctx["committed_goal"] = None
    _seed_baseline(ctx, monkeypatch)
    monkeypatch.setattr(pr, "_fingerprint", lambda: {"llm": 2, "sites": {}})
    out = pr.handle_problem_refocus(ctx)
    assert out["status"] == "started_background"
    assert ctx["_active_problem"]["background"] is True
    # the focus slot is untouched
    assert ctx["committed_goal"] is None


def test_site_failure_without_goal_does_not_park(monkeypatch):
    # Non-tool capabilities keep the old guard: nothing to park → no refocus.
    ctx = _ctx()
    ctx["committed_goal"] = None
    _seed_baseline(ctx, monkeypatch)
    monkeypatch.setattr(
        pr, "_fingerprint",
        lambda: {"llm": 0, "sites": {"goal_planner": 5}})
    out = pr.handle_problem_refocus(ctx)
    assert out["status"] == "no_goal_to_park"
    assert "_active_problem" not in ctx


# ── LLM outage: background curiosity, never a crisis ────────────────────────────

def test_llm_failure_is_background_curiosity_not_crisis(monkeypatch):
    _no_goal_tree_writes(monkeypatch)
    ctx = _ctx()
    _seed_baseline(ctx, monkeypatch, llm=0)
    # now the LLM starts failing, and it stays unhealthy
    monkeypatch.setattr(pr, "_fingerprint", lambda: {"llm": 2, "sites": {}})
    monkeypatch.setattr(pr, "_capability_healthy", lambda cap, ap=None: False)

    out = pr.handle_problem_refocus(ctx)
    assert out["status"] == "started_background"
    assert out["capability"] == "llm"

    ap = ctx["_active_problem"]
    assert ap["capability"] == "llm"
    assert ap["background"] is True
    # the committed goal was NOT parked — focus stays on the real goal
    assert ctx["committed_goal"]["title"] == "Research black holes"
    assert not ctx["committed_goal"].get("_is_fix_goal")
    # the investigation goal is bounded: capped weight, refocus-exempt
    fg = ap["fix_goal"]
    assert fg["_is_fix_goal"] is True
    assert fg["motivational_weight"] <= 0.4
    assert fg["_no_refocus_boost"] is True
    assert fg["driven_by"] == "curiosity"
    assert fg["plan"]            # has a symbolic diagnostic plan
    # curiosity-grade affect: wonder, not an impasse spike
    core = ctx["affect_state"]["core_signals"]
    assert core.get("wonder", 0) > 0
    assert core.get("impasse_signal", 0) == 0


def test_background_fix_never_seizes_focus_slot(monkeypatch):
    _no_goal_tree_writes(monkeypatch)
    ctx = _ctx()
    _seed_baseline(ctx, monkeypatch)
    monkeypatch.setattr(pr, "_fingerprint", lambda: {"llm": 2, "sites": {}})
    monkeypatch.setattr(pr, "_capability_healthy", lambda cap, ap=None: False)
    pr.handle_problem_refocus(ctx)

    # advance several cycles: committed_goal must never be replaced
    for _ in range(3):
        pr.handle_problem_refocus(ctx)
        assert ctx["committed_goal"]["title"] == "Research black holes"


def test_fix_goal_cannot_nest(monkeypatch):
    ctx = _ctx()
    _seed_baseline(ctx, monkeypatch)
    # already focused on a fix goal, and no active-problem record (edge case)
    ctx["committed_goal"] = {"title": "Figure out why the language model isn't working",
                             "name": "x", "_is_fix_goal": True}
    monkeypatch.setattr(pr, "_fingerprint", lambda: {"llm": 9, "sites": {}})
    out = pr.handle_problem_refocus(ctx)
    assert out["status"] == "already_fixing"
    assert "_active_problem" not in ctx


# ── resolution path: capability recovers → investigation completes ───────────────

def test_background_completes_when_capability_recovers(monkeypatch):
    _no_goal_tree_writes(monkeypatch)
    ctx = _ctx()
    _seed_baseline(ctx, monkeypatch)
    monkeypatch.setattr(pr, "_fingerprint", lambda: {"llm": 2, "sites": {}})

    # cycle 1: detect (background, unhealthy)
    monkeypatch.setattr(pr, "_capability_healthy", lambda cap, ap=None: False)
    pr.handle_problem_refocus(ctx)
    assert ctx["_active_problem"]["phase"] == "diagnosing"

    # cycle 2: LLM healthy again → episode ends, focus untouched throughout
    monkeypatch.setattr(pr, "_capability_healthy", lambda cap, ap=None: True)
    out = pr.handle_problem_refocus(ctx)
    assert out["status"] == "problem_resolved"
    assert "_active_problem" not in ctx
    assert ctx["committed_goal"]["title"] == "Research black holes"
    assert "_avoid_capability" not in ctx["committed_goal"]


# ── workaround path: can't fix → note it and move on ─────────────────────────────

def test_workaround_when_no_fixable_cause(monkeypatch):
    # Abduction finds only an unfixable cause → the honest decision is "work
    # around it and note it for the operator"; the goal completes like any other.
    _no_goal_tree_writes(monkeypatch)
    import cognition.planning.diagnosis as diag
    monkeypatch.setattr(diag, "abduce", lambda cap, ctx, description="": [
        {"key": "persistent_outage", "cause": "a persistent outage", "fixable": False,
         "cost": 0.9, "confirmed": True, "source": "fault_model"},
    ])
    ctx = _ctx()
    _seed_baseline(ctx, monkeypatch)
    monkeypatch.setattr(pr, "_fingerprint", lambda: {"llm": 2, "sites": {}})
    monkeypatch.setattr(pr, "_capability_healthy", lambda cap, ap=None: False)

    pr.handle_problem_refocus(ctx)          # detect (background)
    out = pr.handle_problem_refocus(ctx)    # first advance → straight to workaround
    assert out["status"] == "problem_workaround"
    assert "_active_problem" not in ctx

    # the committed goal was never touched; the capability is globally avoided
    assert ctx["committed_goal"]["title"] == "Research black holes"
    assert "llm" in ctx["_unhealthy_capabilities"]
    # the investigation completed terminally
    assert pr is not None  # episode cleared above


def test_transient_cause_is_repaired_then_resolves(monkeypatch):
    # A confirmed FIXABLE cause is repaired; when the capability heals, the
    # episode ends. This is the abductive repair loop, run in the background.
    _no_goal_tree_writes(monkeypatch)
    import cognition.planning.diagnosis as diag
    monkeypatch.setattr(diag, "abduce", lambda cap, ctx, description="": [
        {"key": "transient_network", "cause": "a transient network problem",
         "fixable": True, "cost": 0.2, "confirmed": True, "source": "fault_model"},
    ])
    monkeypatch.setattr(diag, "check_cause", lambda cap, key, ctx: True)
    applied = {"n": 0}
    monkeypatch.setattr(diag, "apply_fix",
                        lambda cap, key, ctx: applied.__setitem__("n", applied["n"] + 1) or True)

    ctx = _ctx()
    _seed_baseline(ctx, monkeypatch)
    monkeypatch.setattr(pr, "_fingerprint", lambda: {"llm": 2, "sites": {}})

    monkeypatch.setattr(pr, "_capability_healthy", lambda cap, ap=None: False)
    pr.handle_problem_refocus(ctx)          # detect (background)
    out = pr.handle_problem_refocus(ctx)    # advance → repair attempt
    assert out["status"] == "repairing"
    assert applied["n"] == 1
    assert ctx["committed_goal"]["title"] == "Research black holes"

    monkeypatch.setattr(pr, "_capability_healthy", lambda cap, ap=None: True)
    out = pr.handle_problem_refocus(ctx)    # healed → episode ends
    assert out["status"] == "problem_resolved"
    assert ctx["committed_goal"]["title"] == "Research black holes"
    assert "_active_problem" not in ctx


# ── non-tool capabilities keep the park/refocus reflex ───────────────────────────

def test_site_failure_parks_goal_and_refocuses(monkeypatch):
    ctx = _ctx()
    _seed_baseline(ctx, monkeypatch)
    monkeypatch.setattr(
        pr, "_fingerprint",
        lambda: {"llm": 0, "sites": {"goal_planner": 5}})
    monkeypatch.setattr(pr, "_capability_healthy", lambda cap, ap=None: False)

    out = pr.handle_problem_refocus(ctx)
    assert out["status"] == "started"
    assert out["capability"] == "goal_planner"

    ap = ctx["_active_problem"]
    assert not ap.get("background")
    assert ap["parked_title"] == "Research black holes"
    # focus has switched to the fix micro-goal
    cg = ctx["committed_goal"]
    assert cg["_is_fix_goal"] is True
    assert "isn't working" in cg["title"]
    # real stress was registered for a non-tool blocker
    assert ctx["affect_state"]["core_signals"]["impasse_signal"] > 0


# ── health reconciliation drives the global avoid-set ────────────────────────────

def test_reconcile_adds_and_clears_unhealthy_llm(monkeypatch):
    ctx = _ctx()
    monkeypatch.setattr(pr, "_fingerprint", lambda: {"llm": 0, "sites": {}})

    # llm down → added to the avoid-set
    monkeypatch.setattr(pr, "_capability_healthy", lambda cap, ap=None: False)
    pr.handle_problem_refocus(ctx)  # baseline_init still reconciles first
    assert "llm" in ctx["_unhealthy_capabilities"]

    # llm back → cleared
    monkeypatch.setattr(pr, "_capability_healthy", lambda cap, ap=None: True)
    pr.handle_problem_refocus(ctx)
    assert "llm" not in ctx["_unhealthy_capabilities"]
