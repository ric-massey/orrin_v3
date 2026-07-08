"""2026-07-08 addendum (F10–F22) — verification tests.

F10 gather-first long-form plans + material-gated compose boost; F11 research
milestones need research evidence; F12 the completion sweeper respects the
guard's verdict; F13 recursive satiety walk; F14 stable goal ids at load;
F15 chronology/grounding-gated delayed reward; F16 per-goal pursuit cooldown +
unrewarded cooldown skips; F17 instrumentation out of episodic memory; F18
memory-graph truth compaction; F19 typed speech content kernel; F20 corpus
diversity floor; F21 opinion/relationship store hygiene; F22 the felt lifespan
lurches with experience.
"""

import json
import time

import pytest


# ── F10 — long-form plans gather before they compose ──────────────────────────

def test_long_form_fallback_plan_gathers_first():
    from brain.cognition.planning.goal_comprehension import _fallback
    model = _fallback({"title": "Write a book about my own memory system"})
    assert model["tracked_work"] is True
    fns = [(s.get("action") or {}).get("function") for s in model["plan"]]
    assert fns[0] == "research_topic"
    assert fns[1] == "fetch_and_read"
    assert "compose_section" in fns[2:]
    # never all composes, and no compose before the gathers
    assert fns[:2].count("compose_section") == 0


def test_ensure_production_actions_converts_leading_steps_to_gathers():
    from brain.cognition.planning.goal_comprehension import _ensure_production_actions
    model = {
        "tracked_work": True,
        "plan": [{"step": f"Establish part {i}"} for i in range(4)],
    }
    _ensure_production_actions(model)
    fns = [(s.get("action") or {}).get("function") for s in model["plan"]]
    assert fns[0] == "research_topic" and fns[1] == "fetch_and_read"
    assert fns[2] == fns[3] == "compose_section"


def test_goal_lens_compose_boost_gated_on_material():
    from brain.cognition.goal_lens import action_prior
    starving = {"active": True, "tokens": ["memory", "synthesis"],
                "tracked_work": True, "requires_artifact": True,
                "material_ready": False}
    fed = dict(starving, material_ready=True)
    # with no material the gather functions outrank the composer
    assert action_prior(starving, "research_topic") > action_prior(starving, "compose_section")
    # with material the composer gets its boost back
    assert action_prior(fed, "compose_section") > action_prior(starving, "compose_section")


# ── F11 — research milestones tick only on research evidence ──────────────────

def test_lm_research_total_ignores_instrumentation(tmp_path, monkeypatch):
    import brain.paths as paths
    from brain.cognition.planning.env_snapshot import _lm_research_total
    lm = tmp_path / "long_memory.json"
    lm.write_text(json.dumps([
        {"event_type": "goal_progress", "content": "pursued"},
        {"event_type": "metacog_pattern", "content": "pattern"},
        {"event_type": "world_perception", "content": "a real finding"},
        {"event_type": "chunk", "content": "chunk"},
    ]))
    monkeypatch.setattr(paths, "LONG_MEMORY_FILE", lm)
    assert _lm_research_total({}) == 1


def test_research_milestone_needs_research_growth(tmp_path, monkeypatch):
    import brain.paths as paths
    from brain.cognition.planning import env_snapshot as es
    lm = tmp_path / "long_memory.json"
    lm.write_text(json.dumps([{"event_type": "world_perception", "content": "x"}]))
    monkeypatch.setattr(paths, "LONG_MEMORY_FILE", lm)
    goal = {"id": "g1", "milestones": [
        {"text": "A summary of findings was written to long memory", "met": False},
    ]}
    ctx = {"committed_goal": goal, "working_memory": []}
    monkeypatch.setattr(
        "brain.agency.effect_ledger.has_qualifying_effect", lambda gid, g=None: False)
    assert es.apply_milestone_updates(ctx) == 0   # baseline pass, nothing new

    # instrumentation growth only → still unmet
    lm.write_text(json.dumps([
        {"event_type": "world_perception", "content": "x"},
        {"event_type": "goal_progress", "content": "cycle 5 progress"},
        {"event_type": "goal_progress", "content": "cycle 10 progress"},
    ]))
    assert es.apply_milestone_updates(ctx) == 0
    assert goal["milestones"][0]["met"] is False

    # a genuine research entry lands → met, stamped with its evidence source
    lm.write_text(json.dumps([
        {"event_type": "world_perception", "content": "x"},
        {"event_type": "goal_progress", "content": "cycle 5 progress"},
        {"event_type": "world_perception", "content": "a new finding"},
    ]))
    assert es.apply_milestone_updates(ctx) == 1
    assert goal["milestones"][0]["evidence_source"] == "research_lm_growth"


# ── F12 — the sweeper trusts the guard's RESULT, not its call ─────────────────

def test_maybe_complete_goals_respects_guard_refusal(tmp_path, monkeypatch):
    from brain.cognition.planning import goals as G
    completed_file = tmp_path / "comp_goals.json"
    tree = [{"name": "hollow", "status": "in_progress",
             "plan": [{"step": "s1", "status": "completed"}]}]
    monkeypatch.setattr(G, "COMPLETED_GOALS_FILE", completed_file)
    monkeypatch.setattr(G, "load_goals", lambda: tree)
    monkeypatch.setattr(G, "save_goals", lambda goals: None)
    monkeypatch.setattr(G, "update_working_memory", lambda *a, **k: None)
    # the guard REFUSES: status never flips
    monkeypatch.setattr(G, "mark_goal_completed", lambda goal, **k: None)
    changed = G.maybe_complete_goals()
    assert changed is False
    stored = json.loads(completed_file.read_text()) if completed_file.exists() else []
    assert stored == []          # a refusal is never laundered into a completion


def test_maybe_complete_goals_records_real_completions(tmp_path, monkeypatch):
    from brain.cognition.planning import goals as G
    completed_file = tmp_path / "comp_goals.json"
    tree = [{"name": "real", "status": "in_progress",
             "plan": [{"step": "s1", "status": "completed"}]}]
    monkeypatch.setattr(G, "COMPLETED_GOALS_FILE", completed_file)
    monkeypatch.setattr(G, "load_goals", lambda: tree)
    monkeypatch.setattr(G, "save_goals", lambda goals: None)
    monkeypatch.setattr(G, "update_working_memory", lambda *a, **k: None)

    def _accepting_guard(goal, **k):
        goal["status"] = "completed"
    monkeypatch.setattr(G, "mark_goal_completed", _accepting_guard)
    assert G.maybe_complete_goals() is True
    stored = json.loads(completed_file.read_text())
    assert [g["name"] for g in stored] == ["real"]


# ── F13 — the satiety sweep sees nested nodes ──────────────────────────────────

def test_flat_goal_nodes_recurses():
    from brain.loop.maintenance import _flat_goal_nodes
    tree = [{"name": "root", "subgoals": [
        {"name": "child", "subgoals": [{"name": "grandchild"}]},
        {"name": "child2"},
    ]}]
    names = [n["name"] for n in _flat_goal_nodes(tree)]
    assert names == ["root", "child", "grandchild", "child2"]


# ── F14 — stable ids at load and ingress ──────────────────────────────────────

def test_load_goals_stamps_deterministic_ids(tmp_path, monkeypatch):
    from brain.cognition.planning import goal_store as gs
    goals_file = tmp_path / "goals_mem.json"
    goals_file.write_text(json.dumps([
        {"name": "root goal", "timestamp": "2026-07-08T00:00:00Z",
         "subgoals": [{"name": "nested child", "timestamp": "2026-07-08T01:00:00Z"}]},
    ]))
    monkeypatch.setattr(gs, "GOALS_FILE", goals_file)
    first = gs.load_goals()
    second = gs.load_goals()
    assert first[0]["id"] and first[0]["subgoals"][0]["id"]
    # deterministic: the same node resolves to the SAME id on every load,
    # even though the stamp was never persisted
    assert first[0]["id"] == second[0]["id"]
    assert first[0]["subgoals"][0]["id"] == second[0]["subgoals"][0]["id"]
    assert first[0]["id"] != first[0]["subgoals"][0]["id"]


# ── F15 — delayed reward pays for causing a grounded completion ───────────────

@pytest.fixture
def _closure(tmp_path, monkeypatch):
    from brain.eval import evaluator_daemon as ed
    completed = tmp_path / "comp_goals.json"
    monkeypatch.setattr(ed, "COMPLETED_GOALS_FILE", completed)
    return ed, completed


def test_closure_reward_refused_when_completion_predates_decision(_closure, monkeypatch):
    ed, completed = _closure
    completed.write_text(json.dumps([
        {"id": "g1", "title": "old goal",
         "completed_timestamp": "2026-07-08T00:00:00+00:00"},
    ]))
    monkeypatch.setattr("brain.agency.effect_ledger.has_qualifying_effect",
                        lambda gid, g=None: True)
    daemon = ed.EvaluatorDaemon()
    origin_ts = time.time()   # decision made NOW, long after the completion
    assert daemon._check_goal_closure({}, "g1", 0, 10, origin_ts=origin_ts) is None


def test_closure_reward_refused_without_qualifying_effect(_closure, monkeypatch):
    from datetime import datetime, timezone
    ed, completed = _closure
    completed.write_text(json.dumps([
        {"id": "g1", "title": "hollow goal",
         "completed_timestamp": datetime.now(timezone.utc).isoformat()},
    ]))
    monkeypatch.setattr("brain.agency.effect_ledger.has_qualifying_effect",
                        lambda gid, g=None: False)
    daemon = ed.EvaluatorDaemon()
    assert daemon._check_goal_closure({}, "g1", 0, 10, origin_ts=time.time() - 3600) is None


def test_closure_reward_scales_with_significance(_closure, monkeypatch):
    from datetime import datetime, timezone
    ed, completed = _closure
    now_iso = datetime.now(timezone.utc).isoformat()
    completed.write_text(json.dumps([
        {"id": "g-hard", "title": "hard goal", "tier": "core",
         "milestones": [{"text": "m", "met": True}] * 5,
         "plan": [{"step": "s"}] * 6, "_completion_attempts": 3,
         "completed_timestamp": now_iso},
    ]))
    monkeypatch.setattr("brain.agency.effect_ledger.has_qualifying_effect",
                        lambda gid, g=None: True)
    daemon = ed.EvaluatorDaemon()
    reward = daemon._check_goal_closure({}, "g-hard", 0, 10, origin_ts=time.time() - 3600)
    assert reward is not None
    assert reward != pytest.approx(ed.GOAL_CLOSURE_REWARD)   # not the flat 0.55
    assert reward > ed.GOAL_CLOSURE_REWARD                   # hard goal pays more


# ── F16 — the pursuit cooldown is per goal ─────────────────────────────────────

def test_pursuit_cooldown_does_not_leak_across_goals(monkeypatch):
    from brain.cognition.planning import goal_execution as gex
    monkeypatch.setattr(gex, "_last_pursuit_by_goal", {"A": time.time()})
    # goal A is inside ITS window → cooldown (checked before status release)
    ctx_a = {"committed_goal": {"id": "A", "title": "a", "status": "completed"}}
    assert gex.pursue_committed_goal(ctx_a)["reason"] == "cooldown"
    # goal B is not blocked by A's advance — it reaches the status-release gate
    ctx_b = {"committed_goal": {"id": "B", "title": "b", "status": "completed"}}
    assert gex.pursue_committed_goal(ctx_b)["reason"] == "goal_already_done"


def test_executive_cooldown_skip_posts_no_reward(monkeypatch):
    from brain.cognition.planning import executive as ex
    import brain.cognition.planning.pursue_goal as pg
    import brain.control_signals.reward_signals.reward_engine as re_mod
    monkeypatch.setattr(pg, "pursue_committed_goal",
                        lambda ctx=None: {"status": "ok", "skipped": True,
                                          "reason": "cooldown"})
    rewards = []
    monkeypatch.setattr(re_mod, "submit_reward",
                        lambda *a, **k: rewards.append(k.get("action_type")))
    monkeypatch.setattr(ex, "recognise_step_action", lambda step: "compose_section")
    ctx = {"committed_goals": [
        {"id": "g1", "title": "write it", "status": "in_progress",
         "plan": [{"step": "compose the section", "status": "pending"}]},
    ]}
    summary = ex.executive_tick(ctx)
    assert summary["cooldown_skipped"] >= 1
    assert summary["advanced"][0]["status"] == "cooldown_skipped"
    assert rewards == []           # recognized ≠ ran: no learning event


# ── F17 — instrumentation is telemetry, not episodic memory ───────────────────

def test_goal_progress_writes_to_log_not_long_memory(tmp_path, monkeypatch):
    import brain.goal_io as gio
    import brain.paths as paths
    monkeypatch.setattr(paths, "LOGS_DIR", tmp_path)
    calls = []
    monkeypatch.setattr("brain.cog_memory.long_memory.update_long_memory",
                        lambda *a, **k: calls.append(a))
    ctx = {"committed_goal": {"id": "g1", "title": "the goal"},
           "cycle_count": {"count": 5}, "recent_picks": ["reflect"],
           "working_memory": [{"content": "a thought"}]}
    gio.record_goal_progress(ctx)
    log_file = tmp_path / "goal_progress_log.jsonl"
    assert log_file.exists()
    row = json.loads(log_file.read_text().splitlines()[0])
    assert row["goal_id"] == "g1" and row["cycle"] == 5
    assert calls == []             # long memory untouched


def test_instrumentation_entries_get_no_importance_bump(tmp_path, monkeypatch):
    from brain.cog_memory import long_memory as lm_mod
    lm_file = tmp_path / "long_memory.json"
    monkeypatch.setattr(lm_mod, "LONG_MEMORY_FILE", lm_file)
    lm_mod.update_long_memory(
        "a metacog pattern noticed during the run, repeated wording here",
        event_type="metacog_pattern", importance=4,
        context={"affect_state": {"core_signals": {"threat_level": 0.9}}},
    )
    stored = json.loads(lm_file.read_text())
    assert stored[0]["importance"] == 1    # capped; no affect bump


def test_prune_caps_instrumentation_share(tmp_path, monkeypatch):
    from brain.cog_memory import long_memory as lm_mod
    lm_file = tmp_path / "long_memory.json"
    monkeypatch.setattr(lm_mod, "LONG_MEMORY_FILE", lm_file)
    monkeypatch.setattr(lm_mod, "PRIVATE_THOUGHTS_FILE", tmp_path / "pt.txt")
    monkeypatch.setattr(
        "brain.cognition.self_state.ethics.update_values_with_lessons",
        lambda kept: None)
    entries = []
    for i in range(30):
        entries.append({"id": f"i{i}", "event_type": "goal_progress",
                        "content": f"[Goal progress | cycle {i}] pursued goal {i}",
                        "importance": 1, "timestamp": f"2026-07-08T10:{i:02d}:00+00:00"})
    for i in range(10):
        entries.append({"id": f"r{i}", "event_type": "world_perception",
                        "content": f"real finding number {i} with substance",
                        "importance": 3, "timestamp": f"2026-07-08T11:{i:02d}:00+00:00"})
    lm_file.write_text(json.dumps(entries))
    lm_mod.prune_long_memory(max_total=20)
    kept = json.loads(lm_file.read_text())
    instr = [m for m in kept if m.get("event_type") == "goal_progress"]
    real = [m for m in kept if m.get("event_type") == "world_perception"]
    assert len(instr) <= int(20 * lm_mod._INSTRUMENTATION_MAX_SHARE)
    assert len(real) == 10        # every real finding survived


# ── F18 — the memory graph tracks live memories, not ghosts ───────────────────

def test_no_edges_for_instrumentation(tmp_path, monkeypatch):
    from brain.utils import memory_graph as mg
    graph = tmp_path / "graph.jsonl"
    monkeypatch.setattr(mg, "MEMORY_GRAPH_FILE", graph)
    telemetry = {"id": "t1", "event_type": "goal_progress",
                 "content": "recent cognitive actions research reflect assess progress"}
    peer = {"id": "p1", "event_type": "summary",
            "content": "recent cognitive actions research reflect assess progress"}
    mg.add_edges(telemetry, [peer])
    assert not graph.exists() or graph.read_text().strip() == ""


def test_compact_against_live_drops_orphans(tmp_path, monkeypatch):
    from brain.utils import memory_graph as mg
    graph = tmp_path / "graph.jsonl"
    rows = [
        {"source": "a", "target": "b", "weight": 0.5, "ts": "t"},
        {"source": "a", "target": "ghost", "weight": 0.5, "ts": "t"},
        {"source": "ghost", "target": "ghost2", "weight": 0.5, "ts": "t"},
    ]
    graph.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    monkeypatch.setattr(mg, "MEMORY_GRAPH_FILE", graph)
    dropped = mg.compact_against_live({"a", "b"})
    assert dropped == 2
    kept = [json.loads(x) for x in graph.read_text().splitlines() if x.strip()]
    assert kept == [rows[0]]


# ── F19 — the mouth speaks about something ─────────────────────────────────────

def test_content_kernel_prefers_produced_artifact(monkeypatch):
    from brain.behavior import speech_content as sc
    monkeypatch.setattr("brain.agency.effect_artifacts.load",
                        lambda h: "a research memo about attention I just wrote")
    ctx = {"_effect_rows_this_cycle": [
        {"kind": "note_novel", "content_hash": "abc123", "dedupe": False},
    ]}
    kernel = sc.choose_content_kernel(ctx)
    assert kernel["intent"] == "share_artifact"
    assert "memo about attention" in kernel["seed"]


def test_content_kernel_states_blockers(tmp_path, monkeypatch):
    import brain.paths as paths
    from brain.behavior import speech_content as sc
    lm = tmp_path / "long_memory.json"
    lm.write_text("[]")
    monkeypatch.setattr(paths, "LONG_MEMORY_FILE", lm)
    ctx = {"committed_goal": {"id": "g1", "title": "compose the manuscript",
                              "_needs_deliberate_action": "decide_to_write_code"}}
    kernel = sc.choose_content_kernel(ctx)
    assert kernel["intent"] == "state_blocker"
    assert "compose the manuscript" in kernel["seed"]


def test_content_kernel_express_state_is_last_resort(tmp_path, monkeypatch):
    import brain.paths as paths
    from brain.behavior import speech_content as sc
    lm = tmp_path / "long_memory.json"
    lm.write_text("[]")
    monkeypatch.setattr(paths, "LONG_MEMORY_FILE", lm)
    kernel = sc.choose_content_kernel({})
    assert kernel["intent"] == "express_state" and kernel["seed"] is None


# ── F20 — the training corpora keep a diversity floor ─────────────────────────

def test_diversity_cap_bounds_repeats():
    from brain.cognition.language.acquisition_noise import diversity_cap_lines
    lines = ["something present but hard to name."] * 100 + ["a genuinely new sentence."]
    capped = diversity_cap_lines(lines)
    assert capped.count("something present but hard to name.") == 4
    assert "a genuinely new sentence." in capped


def test_replay_corpus_is_diversity_capped(tmp_path, monkeypatch):
    from brain.cognition.language import acquisition as acq
    replay = tmp_path / "replay_corpus.txt"
    monkeypatch.setattr(acq, "_REPLAY_FILE", replay)
    stuck = "There is something present but hard to name in this moment."
    acq._update_replay("\n".join([stuck] * 50 + ["The library was quiet that evening."]))
    text = replay.read_text()
    assert text.count(stuck) <= 4
    assert "library was quiet" in text


def test_narration_pairs_stop_absorbing_the_stuck_phrase(tmp_path, monkeypatch):
    from brain.cognition.language import acquisition as acq
    pairs = tmp_path / "narration_pairs.jsonl"
    monkeypatch.setattr(acq, "_NARRATION_PAIRS_FILE", pairs)
    thought = {"intent": "narrate_experience", "affect": {"felt": "being stuck"}}
    for _ in range(10):
        acq._append_narration_pair(thought, "Feeling stuck, I looked through my own files.")
    stored = pairs.read_text().strip().splitlines()
    assert len(stored) == 4


# ── F21 — store hygiene ────────────────────────────────────────────────────────

def test_opinion_hygiene_drops_junk_and_compacts_orphan_refs(tmp_path, monkeypatch):
    import brain.paths as paths
    from brain.cognition import opinions_store as store
    monkeypatch.setattr(store, "OPINIONS_FILE", tmp_path / "opinions.json")
    monkeypatch.setattr(paths, "LONG_MEMORY_FILE", tmp_path / "lm.json")
    monkeypatch.setattr(paths, "WORKING_MEMORY_FILE", tmp_path / "wm.json")
    (tmp_path / "lm.json").write_text(json.dumps([{"id": "live-1", "content": "x"}]))
    (tmp_path / "wm.json").write_text("[]")
    monkeypatch.setattr(store, "_migration_done", True)
    monkeypatch.setattr(store, "_hygiene_done", False)
    data = [
        # ledger-format junk topic — the legacy migration never touched these
        {"id": "j1", "topic": "objective unmet", "view": "?", "evidence": []},
        {"id": "k1", "topic": "recursive self improvement", "view": "underestimated",
         "alpha": 3.0, "beta": 1.0, "confidence": 0.75,
         "evidence": [
             {"kind": "observation", "ref_id": "live-1", "direction": "for", "weight": 0.25},
             {"kind": "observation", "ref_id": "pruned-9", "direction": "for", "weight": 0.25},
             {"kind": "experiment_verdict", "ref_id": "exp-1", "direction": "for", "weight": 1.0},
         ]},
    ]
    out = store._hygiene_pass(data)
    assert [op["id"] for op in out] == ["k1"]
    kept = out[0]
    refs = [(e["kind"], e["ref_id"]) for e in kept["evidence"]]
    assert ("observation", "live-1") in refs
    assert ("observation", "pruned-9") not in refs
    assert ("experiment_verdict", "exp-1") in refs     # non-memory refs untouched
    assert kept["evidence_compacted"] == 1
    assert kept["confidence"] == 0.75                  # alpha/beta already absorbed it


def test_relationship_history_dedupes_identical_exchanges(tmp_path, monkeypatch):
    from brain.cognition.self_state import relationships as rel
    monkeypatch.setattr(rel, "RELATIONSHIPS_FILE", tmp_path / "relationships.json")
    ctx = {"person_id": "ric", "latest_user_input": "how are you",
           "latest_response": "Something present but hard to name.",
           "affect_state": {"core_signals": {}}}
    for _ in range(5):
        rel.update_relationship_model(dict(ctx))
    stored = json.loads((tmp_path / "relationships.json").read_text())
    hist = stored["ric"]["interaction_history"]
    assert len(hist) == 1
    assert hist[0]["repeats"] == 5


# ── F22 — the felt lifespan lurches ────────────────────────────────────────────

@pytest.fixture
def _lifespan(tmp_path, monkeypatch):
    from brain.cognition import felt_lifespan as fl
    monkeypatch.setattr(fl, "LIFESPAN_FILE", tmp_path / "runtime_lifetime.json")
    monkeypatch.setattr(fl, "_live_bias", None)
    monkeypatch.setattr(fl, "_last_saved_bias", 0.0)
    data = {"start_time": "2026-07-01T00:00:00+00:00", "lifespan_days": 400.0,
            "noise_days": 2.0, "slept_seconds": 0.0, "felt_bias_days": 0.0}
    return fl, data


def test_distress_compresses_and_reward_relaxes_the_felt_lifespan(_lifespan):
    fl, data = _lifespan
    hard = {"affect_state": {"core_signals": {"threat_level": 0.9}}}
    for _ in range(20):
        fl.recalibrate_felt_lifespan(hard, data)
    compressed = data["felt_bias_days"]
    assert compressed > 0
    good = {"affect_state": {"core_signals": {"threat_level": 0.0,
                                              "reward_positive": 0.8}}}
    for _ in range(20):
        fl.recalibrate_felt_lifespan(good, data)
    assert data["felt_bias_days"] < compressed


def test_felt_bias_is_bounded_and_never_touches_the_true_clock(_lifespan):
    from brain.cognition import runtime_lifetime as rl
    fl, data = _lifespan
    hard = {"affect_state": {"core_signals": {"threat_level": 1.0,
                                              "loss_signal": 1.0}}}
    for _ in range(5000):
        fl.recalibrate_felt_lifespan(hard, data)
    assert data["felt_bias_days"] <= fl._FELT_BIAS_MAX_DAYS
    # the REAL fraction reads only lifespan_days — the bias moves the felt view only
    real_before = rl._life_fraction(dict(data, felt_bias_days=0.0))
    assert rl._life_fraction(data) == pytest.approx(real_before)
    # ...while the FELT view is genuinely compressed
    assert rl._days_remaining_felt(data) < rl._days_remaining_felt(dict(data, felt_bias_days=0.0))


def test_shock_lands_once_and_registers(_lifespan):
    fl, data = _lifespan
    ctx = {"affect_state": {"core_signals": {}},
           "_felt_lifespan_shock": 1.0}
    fl.recalibrate_felt_lifespan(ctx, data)
    assert data["felt_bias_days"] == pytest.approx(1.0, abs=0.01)
    assert "_felt_lifespan_shock" not in ctx      # consumed, one-shot
    # register_lifespan_shock persists through the file
    fl.save_json(fl.LIFESPAN_FILE, data)
    fl.register_lifespan_shock(1.0, "silent_death")
    stored = json.loads(fl.LIFESPAN_FILE.read_text())
    assert stored["felt_bias_days"] == pytest.approx(2.0, abs=0.02)
