# Run 11 Slice 1A — harness proofs for the Run 10 fix set (F-LN1..F-LN8),
# per RUN11_IMPLEMENTATION_PLAN_2026-07-19.md. Each test drives the REAL
# mechanism and scores its real store (the R9-F7 forced-fire pattern), so a
# green here is evidence, not inference.

import json

import pytest


# ── F-LN1: question-miner provenance skip ────────────────────────────────────

def test_miner_skips_own_unanswered_question_records():
    from brain.cognition.intrinsic_generators import _open_question_goals
    own_question = "What do you think stands out most about that?"
    long_mem = [
        {"content": f"I reached out and asked: {own_question}",
         "event_type": "unanswered_question"},
        {"content": f"[unanswered_question] {own_question}"},
    ]
    goals = _open_question_goals({"working_memory": []}, long_mem)
    titles = " | ".join(g.get("title", "") for g in goals)
    assert own_question not in titles, (
        "LN-1: Orrin's own outbound question was mined back as an open question")


def test_miner_still_mines_genuine_questions():
    from brain.cognition.intrinsic_generators import _open_question_goals
    long_mem = [{"content": "A thought: What makes copper conduct electricity so well?",
                 "event_type": "reflection"}]
    goals = _open_question_goals({"working_memory": []}, long_mem)
    assert goals, "a genuine well-formed question must still originate a goal"
    assert goals[0].get("kind") == "research"
    # F-LN4a: the mined question is stamped at creation.
    assert goals[0].get("question", "").startswith("What makes copper")


# ── F-LN3: researchability routing ───────────────────────────────────────────

def test_self_referential_question_routes_to_introspection_not_research():
    from brain.cognition.intrinsic_generators import _open_question_goals
    long_mem = [{"content": "It lingers: Why do I keep abandoning threads halfway?",
                 "event_type": "reflection"}]
    goals = _open_question_goals({"working_memory": []}, long_mem)
    assert goals, "a self-referential question is a real gap — routed, not filtered"
    g = goals[0]
    assert g.get("kind") != "research", "self-referential questions must never plan web queries"
    assert not g.get("requires_artifact")
    assert g.get("driven_by") == "self_exploration"
    assert g.get("question", "").startswith("Why do I keep")


# ── F-LN2: failure persisted into the tree at the failure site ───────────────

def test_failed_goal_is_merged_into_tree_no_double_failure():
    from brain.cognition.planning.goal_store import add_goal
    from brain.cognition.planning.goals import load_goals
    from brain.cognition.planning import step_attempts as sa

    goal = add_goal({
        "title": "Research the history of bit software",
        "name": "Research the history of bit software",
        "status": "in_progress", "tier": "growth", "kind": "research",
    })
    gid = goal["id"]
    # Drive the real give-up escalation: each step abandoned at the cap.
    ctx: dict = {"committed_goal": goal}
    result = None
    for i in range(sa.GOAL_GIVE_UP_MAX):
        step = f"step-{i}"
        for _ in range(3):
            result = sa.handle_unexecuted_step(goal, goal["title"], step, ctx, max_attempts=3)
    assert result is not None and result.get("status") == "failed"

    def _find(nodes):
        for n in nodes or []:
            if isinstance(n, dict):
                if n.get("id") == gid:
                    return n
                got = _find(n.get("subgoals"))
                if got:
                    return got
        return None

    node = _find(load_goals())
    assert node is not None, "goal vanished from the tree"
    # THE F-LN2 assertion: the tree copy is terminal at the failure site, so a
    # later pull cannot resurrect-and-refail it (Run 10: 4 of 5 double-failed).
    assert node.get("status") == "failed"


# ── F-LN4a/4b: stamp-before-archive + the unanswered-question wall ───────────

def _understanding_goal(add_goal, title="Understand chalk more deeply"):
    return add_goal({
        "title": title, "name": title,
        "status": "in_progress", "tier": "growth",
        "driven_by": "world_knowledge",
        "question": f"What about {title.split()[1]} do I still not understand?",
        "milestones": [{"text": "A new fact was written to long memory.",
                        "met": True, "met_at": "2026-07-19T00:00:00Z"}],
    })


@pytest.fixture()
def _clear_finalized_ids():
    from brain.cognition.planning import goal_closure
    goal_closure._FINALIZED_IDS.clear()
    yield
    goal_closure._FINALIZED_IDS.clear()


def test_completed_understanding_goal_archives_with_stamps(_clear_finalized_ids):
    from brain.cognition.planning.goal_store import add_goal
    from brain.cognition.planning.goal_closure import _finalize_goal_completion
    from brain.paths import DATA_DIR

    goal = _understanding_goal(add_goal, "Understand basalt more deeply")
    _finalize_goal_completion(goal, goal["title"], {"committed_goal": goal},
                              reason="plan complete")
    assert goal.get("status") == "completed"

    comp = json.loads((DATA_DIR / "comp_goals.json").read_text() or "[]")
    rec = next((r for r in comp if isinstance(r, dict) and r.get("id") == goal["id"]), None)
    assert rec is not None, "completed goal missing from the scored store"
    # F-LN4a: the ARCHIVED record carries the stamps (Run 10: stamped after the
    # archive append, so all 10 scored records were stampless).
    assert rec.get("question"), "archived record lost its question"
    assert "answered" in rec, "archived record lost its answered verdict"


def test_unanswered_question_blocks_satiety_close_then_spawns_followup(_clear_finalized_ids):
    from brain.cognition.planning.goal_store import add_goal
    from brain.cognition.planning.goals import load_goals
    from brain.cognition.planning import goal_closure
    from brain.cognition.planning.goal_closure import (
        _finalize_goal_completion, _EPISTEMIC_BLOCK_MAX)

    goal = _understanding_goal(add_goal, "Understand gneiss more deeply")
    ctx = {"committed_goal": goal}

    # No artifact exists → answered=False → the wall blocks the satiety close.
    for i in range(_EPISTEMIC_BLOCK_MAX):
        _finalize_goal_completion(goal, goal["title"], ctx, reason="satiety:test")
        assert goal.get("status") != "completed", f"block {i + 1} did not hold"
        assert int(goal.get("_epistemic_blocks", 0)) == i + 1
        assert goal["id"] not in goal_closure._FINALIZED_IDS, (
            "a blocked close must stay closeable")

    # Past the block budget the close proceeds — and the question SURVIVES as a
    # follow-up goal instead of being eaten by satiety.
    _finalize_goal_completion(goal, goal["title"], ctx, reason="satiety:test")
    assert goal.get("status") == "completed"

    def _titles(nodes, acc):
        for n in nodes or []:
            if isinstance(n, dict):
                acc.append(str(n.get("title") or ""))
                _titles(n.get("subgoals"), acc)
        return acc

    titles = _titles(load_goals(), [])
    q = goal["question"]
    assert any(t.startswith("Answer: ") and q[:40] in t for t in titles), (
        "NOT-answered close must spawn a follow-up goal carrying the question")


# ── F-LN4c: questions derive from goal content, not one template ─────────────

def test_question_for_derives_from_goal_content():
    from brain.cognition.epistemic_closeout import question_for

    stored = question_for({"question": "Why is basalt dark?"})
    embedded = question_for({
        "title": "Understand tides more deeply",
        "description": "I keep wondering: How do tides couple to the moon's orbit? Find out.",
    })
    milestoned = question_for({
        "title": "Understand chert more deeply",
        "milestones": [{"text": "A new fact about chert was written to long memory.",
                        "met": False}],
    })
    bare = question_for({"title": "Understand slate more deeply"})

    shapes = {stored, embedded, milestoned, bare}
    assert len(shapes) == 4, "fallback shapes collapsed back into one template"
    assert stored == "Why is basalt dark?"
    assert embedded.startswith("How do tides")
    assert "not obvious" not in (milestoned + bare), (
        "the Run-10 template is retired from the fallback")


# ── F-LN5: saturation tripwire fires on the wobble pattern ───────────────────

def test_saturation_fraction_arm_fires_on_run10_wobble_series():
    from brain.control_signals.homeostasis import (
        saturation_tripwire, SATURATION_MAX_CYCLES)

    state: dict = {}
    fired_at = None
    # Run 10's drive_mastery shape: welded at 1.00 with periodic brief dips
    # (0.84–0.96) that reset any CONSECUTIVE streak — ~95% time-at-bound.
    for cycle in range(SATURATION_MAX_CYCLES + 10):
        v = 0.90 if cycle % 20 == 19 else 1.0
        signals = {"drive_mastery": v}
        if saturation_tripwire(state, signals, cycle=cycle):
            fired_at = cycle
            break
    assert fired_at is not None, (
        "F-LN5: the tripwire is still wobble-blind — the fraction arm must fire "
        "where the consecutive streak provably cannot (max streak 19 here)")
    # And the recalibration really moved the signal off the bound.
    assert signals["drive_mastery"] < 1.0 - 0.005


def test_saturation_ignores_signal_resting_at_its_setpoint():
    from brain.control_signals.homeostasis import (
        saturation_tripwire, SATURATION_MAX_CYCLES)

    state: dict = {}
    for cycle in range(SATURATION_MAX_CYCLES + 10):
        # loss_signal resting at 0.0 IS its setpoint — correct rest, never a trip.
        assert saturation_tripwire(state, {"loss_signal": 0.0}, cycle=cycle) == []


# ── F-LN6: the handoff-decision log ──────────────────────────────────────────

def test_handoff_log_writes_once_per_decision_change():
    from brain.utils import handoff_log as hl

    hl._last.clear()
    if hl.HANDOFF_LOG.exists():
        hl.HANDOFF_LOG.unlink()
    hl.log_handoff("sync_proposed_goals", "Open question: why is the sky blue?",
                   "research", "queued", "v2 created g_1")
    hl.log_handoff("sync_proposed_goals", "Open question: why is the sky blue?",
                   "research", "queued", "v2 created g_1")   # repeat → suppressed
    hl.log_handoff("sync_proposed_goals", "Open question: why is the sky blue?",
                   "research", "deferred", "v2 API down")    # change → logged
    lines = [json.loads(l) for l in hl.HANDOFF_LOG.read_text().splitlines()]
    assert [l["decision"] for l in lines] == ["queued", "deferred"]
    assert all(l["site"] == "sync_proposed_goals" for l in lines)


# ── F-LN8: zero-with-prejudice proven at the account seam ────────────────────

def test_blocked_action_pays_zero_and_ema_decays_below_default():
    from brain.think.think_utils.finalize import realized_reward_with_prejudice
    from brain.control_signals.reward_signals import impossibility as imp
    from brain.control_signals.reward_signals.reward_engine import submit_reward
    from brain.control_signals.reward_signals import action_reward_ema as ema

    action = "decide_to_write_code"
    for a in list(imp._load().keys()):
        imp.note_possible(a)

    ctx: dict = {}
    # Seed a HIGH learned expectation (the Run 9 pathology: EMA 0.618 while
    # blocked 369/369).
    ema.update_expected(ctx, action, 0.62)
    assert ema.get_expected(ctx, action) > ema._DEFAULT

    imp.mark_impossible(action, "tool unavailable: llm (tool-only)")
    # The PRODUCTION seam forces the realized reward to zero...
    assert realized_reward_with_prejudice(action, 0.9) == 0.0
    # ...and feeding that through the real engine decays the EMA below the
    # selection default within one life's worth of blocked cycles.
    for _ in range(60):
        submit_reward(ctx, actual=realized_reward_with_prejudice(action, 0.9),
                      action_type=action, kind="reward_signal", source="env_delta")
    assert ema.get_expected(ctx, action) < ema._DEFAULT, (
        "zero-with-prejudice must drag a blocked action's EMA below the default")

    # And while blocked it leaves the selectable set (selection seam).
    from brain.think.think_utils.selection import candidates as cand
    assert action in cand._impossible_now()

    imp.note_possible(action)
    # A recovered action passes rewards through untouched.
    assert realized_reward_with_prejudice(action, 0.9) == 0.9
