# Benchmark realignment (docs/benchmark_realignment.md F1–F5): the suite must
# match the dual-process, multi-goal architecture — sample both lanes, commit
# scenario goals, time per-goal pursuit, and measure concurrent progress (B6).
import benchmarks as bm


# ── F1: B2 counts BOTH lanes ──────────────────────────────────────────────────

def _samples_b2(n=40, exec_novelty=False):
    out = []
    for i in range(n):
        stag = 0.8 if i % 2 else 0.1
        if exec_novelty:
            # deliberate lane is introspective; novelty happens in the Executive
            fn, fx = "assess_goal_progress", (["seek_novelty"] if stag > 0.6 else ["leave_note"])
        else:
            fn, fx = ("seek_novelty" if stag > 0.6 else "assess_goal_progress"), []
        rec = {"cycle": i, "stag": stag, "fn": fn}
        if fx:
            rec["fx"] = fx
        out.append(rec)
    return out


def test_b2_passes_on_deliberate_lane_novelty():
    res = bm._eval_b2(_samples_b2(exec_novelty=False))
    assert res["status"] == "pass"


def test_b2_sees_executive_lane_novelty():
    # Same behavior moved entirely into the Executive lane — pre-F1 this was
    # invisible and the benchmark failed spuriously.
    res = bm._eval_b2(_samples_b2(exec_novelty=True))
    assert res["status"] == "pass"
    assert res["lanes"].startswith("both")


# ── F2: not_committed is a distinct, honest state ────────────────────────────

def test_uncommitted_goal_reports_not_committed(monkeypatch):
    monkeypatch.setattr(bm, "_current_cycle", lambda: 200)
    g = {"status": "active", "plan": [], "subgoals": [], "seeded_at_cycle": 10}
    res = bm._commitment_state(g)
    assert res and res["status"] == "not_committed"
    assert res["cycles_waiting"] == 190


def test_planned_goal_is_not_flagged(monkeypatch):
    monkeypatch.setattr(bm, "_current_cycle", lambda: 200)
    g = {"status": "active", "plan": [{"step": "x", "status": "pending"}],
         "seeded_at_cycle": 10}
    assert bm._commitment_state(g) is None


def test_recently_seeded_goal_is_not_flagged(monkeypatch):
    monkeypatch.setattr(bm, "_current_cycle", lambda: 30)
    g = {"status": "active", "plan": [], "subgoals": [], "seeded_at_cycle": 10}
    assert bm._commitment_state(g) is None


# ── F3: per-goal pursuit ticks ────────────────────────────────────────────────

def test_pursuit_ticks_counts_only_that_goal():
    samples = [
        {"cycle": 1, "gx": ["a", "b"]},
        {"cycle": 2, "gx": ["b"]},
        {"cycle": 3, "gx": ["a"]},
        {"cycle": 4},
    ]
    assert bm._pursuit_ticks("a", samples) == 2
    assert bm._pursuit_ticks("b", samples) == 2
    assert bm._pursuit_ticks("c", samples) == 0


# ── F5: B6 concurrent goal progress ──────────────────────────────────────────

def test_b6_passes_when_two_goals_advance_in_one_tick():
    samples = [{"cycle": 5, "fn": "reflect", "gx": ["a", "b", "c"]}]
    res = bm._eval_b6(samples)
    assert res["status"] == "pass"
    assert res["max_goals_single_tick"] == 3


def test_b6_passes_within_window():
    samples = [{"cycle": 1, "fn": "x", "gx": ["a"]},
               {"cycle": 8, "fn": "y", "gx": ["b"]}]
    assert bm._eval_b6(samples)["status"] == "pass"


def test_b6_fails_on_single_goal_monoculture():
    samples = [{"cycle": i, "fn": "x", "gx": ["a"]} for i in range(0, 100, 7)]
    assert bm._eval_b6(samples)["status"] == "fail"


def test_b6_honest_when_no_executive_data():
    assert bm._eval_b6([{"cycle": 1, "fn": "x"}])["status"] == "insufficient_data"


# ── F4: search-shaped goals get search-shaped plans ──────────────────────────

def test_b3_goal_decomposes_to_search_template():
    from cognition.planning.goals import _rule_based_decompose
    subs = _rule_based_decompose({"name": bm._SCENARIO_GOALS["B3"]["title"]})
    names = " ".join(s["name"].lower() for s in subs)
    assert "search_own_files" in names and "grep_files" in names


def test_b3_symbolic_plan_maps_to_executable_fns():
    from cognition.planning.pursue_goal import _symbolic_plan
    from cognition.planning.step_execution import recognise_step_action
    plan = _symbolic_plan(bm._SCENARIO_GOALS["B3"]["title"], {})
    fns = [recognise_step_action(s) for s in plan]
    assert fns[0] == "search_own_files"
    assert fns[1] == "grep_files"
    assert all(f is not None for f in fns)


def test_research_goals_still_hit_research_template():
    from cognition.planning.pursue_goal import _symbolic_plan
    plan = _symbolic_plan("Find out about black holes", {})
    assert "research_topic" in plan[0]


# ── F2: seed_scenario writes one id across both representations ──────────────

def test_seed_scenario_commits_with_shared_id(monkeypatch, tmp_path):
    goals_file = tmp_path / "goals_mem.json"
    monkeypatch.setattr(bm, "GOALS_FILE", goals_file)

    created = {}

    class _FakeGoal:
        id = "api-goal-123"

    class _FakeAPI:
        def create_goal(self, **kw):
            created.update(kw)
            return _FakeGoal()

    monkeypatch.setattr(bm, "_goals_api", lambda: _FakeAPI())
    assert bm.seed_scenario("B3") is True

    from utils.json_utils import load_json
    goals = load_json(goals_file, default_type=list)
    assert goals and goals[0]["id"] == "api-goal-123"     # one id, both stores
    assert goals[0]["benchmark"] == "B3"
    assert "seeded_at_cycle" in goals[0]
    assert created["priority"] == "CRITICAL"               # ranks into committed head
    assert created["spec"]["benchmark"] == "B3"
    # idempotent
    assert bm.seed_scenario("B3") is True
    assert len(load_json(goals_file, default_type=list)) == 1


def test_seed_scenario_falls_back_without_api(monkeypatch, tmp_path):
    goals_file = tmp_path / "goals_mem.json"
    monkeypatch.setattr(bm, "GOALS_FILE", goals_file)
    monkeypatch.setattr(bm, "_goals_api", lambda: (_ for _ in ()).throw(RuntimeError("no store")))
    assert bm.seed_scenario("B5") is True
    from utils.json_utils import load_json
    goals = load_json(goals_file, default_type=list)
    assert goals and goals[0]["benchmark"] == "B5"
