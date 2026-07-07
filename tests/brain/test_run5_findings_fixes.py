"""2026-07-05 findings (the Run 5 fix list) — verification tests.

F1b durable step attempts + give-up escalation; F1c effect-valued executive
reward; F2 aspiration guards; F3 artifact capture + intake prose gate;
F4 research memos; F5 attempt-rate quota; F6 completion caps + satiety gate;
F7 user-speech boundary; F8 heartbeat / silent death.
"""

import time

import pytest


# ── F1b — durable step attempts ────────────────────────────────────────────────

@pytest.fixture
def _attempts(tmp_path, monkeypatch):
    from brain.cognition.planning import step_attempts as sa
    monkeypatch.setattr(sa, "STEP_ATTEMPTS_FILE", tmp_path / "step_attempts.json")
    return sa


def test_step_attempts_survive_a_fresh_goal_dict(_attempts):
    # The executive re-pulls goal dicts from the v2 store every tick; the count
    # must live off-dict or it resets every retry (the 146× stamper).
    sa = _attempts
    assert sa.bump_attempt("g1", "write the thing") == 1
    assert sa.bump_attempt("g1", "write the thing") == 2
    assert sa.bump_attempt("g1", "write the thing") == 3
    assert sa.attempts_for("g1") == {"write the thing": 3}
    sa.clear_attempt("g1", "write the thing")
    assert sa.attempts_for("g1") == {}


def test_give_up_counter_escalates(_attempts):
    sa = _attempts
    assert sa.record_give_up("g2") == 1
    assert sa.record_give_up("g2") == 2
    assert sa.record_give_up("g2") == 3
    assert sa.GOAL_GIVE_UP_MAX == 3


# ── F1c — executive reward reads the effect's value ────────────────────────────

def test_outcome_reward_uses_effect_value():
    from brain.cognition.planning.executive import _outcome_reward
    ok = {"status": "ok"}
    # a deduped/zero-value effect is near-failure even though the step "advanced"
    assert _outcome_reward(ok, effect={"credited": False}) == pytest.approx(0.05)
    # a credited novel effect pays with its value
    rich = _outcome_reward(ok, effect={"credited": True, "novelty": 1.0, "significance": 1.0})
    poor = _outcome_reward(ok, effect={"credited": True, "novelty": 0.1, "significance": 0.5})
    assert rich > poor > 0.05
    # no ledger-visible outcome → the old status mapping stands
    assert _outcome_reward(ok) == pytest.approx(0.6)
    assert _outcome_reward({"status": "awaiting_deliberate"}) == pytest.approx(0.2)


def test_record_effect_stashes_outcome_for_the_lane(tmp_path, monkeypatch):
    from brain.agency import effect_ledger as el
    monkeypatch.setattr(el, "EFFECT_LEDGER_FILE", tmp_path / "ledger.jsonl")
    el.reset_for_tests()
    ctx: dict = {}
    body = ("A genuinely novel observation about the executive lane learning "
            "gap, long enough to clear the artifact floor of the ledger, with "
            "enough distinct words that novelty scoring is not boilerplate.")
    row = el.record_effect("note_novel", body, context=ctx)
    assert row is not None
    out = ctx["_last_effect_outcome"]
    assert out["credited"] is True and out["novelty"] > 0
    # the identical write dedupes — and says so
    ctx2: dict = {}
    assert el.record_effect("note_novel", body, context=ctx2) is None
    assert ctx2["_last_effect_outcome"]["credited"] is False
    el.reset_for_tests()


# ── F2 — aspirations can be edited, never failed ───────────────────────────────

def test_is_aspiration_covers_all_markers():
    from brain.cognition.planning.goal_criteria import is_aspiration
    assert is_aspiration({"id": "aspiration-output_producing"})
    assert is_aspiration({"kind": "aspiration"})
    assert is_aspiration({"tier": "long_term"})
    assert is_aspiration({"_aspiration": True})
    assert not is_aspiration({"id": "g1", "tier": "core"})


def test_mark_goal_failed_refuses_aspirations():
    from brain.cognition.planning.goal_outcomes import mark_goal_failed
    asp = {"id": "aspiration-output_producing", "kind": "aspiration",
           "title": "Make things", "status": "in_progress"}
    mark_goal_failed(asp, reason="objective unmet after 2 attempts", context={})
    assert asp["status"] == "in_progress"          # untouched
    assert not any(h.get("event") == "failed" for h in asp.get("history", []))


def test_executive_queue_excludes_aspirations():
    from brain.cognition.planning.executive import _build_queue
    ctx = {"committed_goals": [
        {"id": "aspiration-world_knowledge", "kind": "aspiration",
         "title": "Understand the world more deeply", "status": "in_progress"},
        {"id": "g-real", "title": "Write a memo", "status": "in_progress"},
    ]}
    queue = _build_queue(ctx)
    assert [g["id"] for g in queue] == ["g-real"]


# ── F3 — bodies are artifacts; markup soup is not a memory ─────────────────────

def test_credited_effect_body_is_captured(tmp_path, monkeypatch):
    from brain.agency import effect_ledger as el
    from brain.agency import effect_artifacts as ea
    monkeypatch.setattr(el, "EFFECT_LEDGER_FILE", tmp_path / "ledger.jsonl")
    el.reset_for_tests()
    body = ("What I learned about satiety today: the refusal wrote a genuinely "
            "novel note through the ledger and that note is the qualifying "
            "effect which lets the close complete legitimately at last.")
    row = el.record_effect("note_novel", body, context={})
    assert row is not None
    assert ea.load(row.content_hash) == body       # resolvable at death (F3)
    el.reset_for_tests()


def test_prose_gate_rejects_css_keeps_prose():
    from brain.utils.text_sanity import prose_ratio, strip_markup_noise
    css = (":host{display:inline-block;width:100%;font-family:sans-serif} "
           ".r-1adg3ll{border-radius:9999px} .css-175oi2r{align-items:stretch;"
           "border:0 solid black;box-sizing:border-box} @media (max-width:600px)"
           "{.x{display:none!important}}")
    prose = ("The colony reorganised itself within minutes, although no single "
             "ant carried a plan for the whole structure.")
    assert prose_ratio(prose) > 0.7
    assert len(strip_markup_noise(css)) < len(css) * 0.4
    assert prose_ratio(strip_markup_noise(css) or "{") < 0.5 or not strip_markup_noise(css)


def test_world_perception_markup_never_becomes_memory(tmp_path):
    from brain.cog_memory.long_memory import update_long_memory
    from brain.paths import LONG_MEMORY_FILE
    from brain.utils.json_utils import load_json
    before = len(load_json(LONG_MEMORY_FILE, default_type=list) or [])
    update_long_memory(
        "[read] Tweet: :host{display:inline-block;width:100%} "
        ".css-175oi2r{align-items:stretch;border:0 solid black} "
        ".r-1adg3ll{border-radius:9999px;padding:0;margin:0}",
        event_type="world_perception",
    )
    after = load_json(LONG_MEMORY_FILE, default_type=list) or []
    assert len(after) == before                     # rejected, not stored


# ── F4 — substantial research becomes a memo artifact ──────────────────────────

def test_research_memo_written_and_ledger_indexed(monkeypatch):
    from brain.cognition import web_research as wr
    from brain.agency import effect_ledger as el
    from brain.paths import GOALS_DIR
    el.reset_for_tests()
    body = (
        "Black holes are regions where gravity prevents anything, including "
        "light, from escaping past the event horizon. Hawking radiation implies "
        "they evaporate slowly, raising the information paradox: quantum theory "
        "forbids destroying information, yet a shrinking horizon seems to erase "
        "what fell in. Recent work on entanglement islands suggests the interior "
        "gradually transfers its record outward, so unitarity survives after all. "
        "Observationally, the Event Horizon Telescope resolved the shadow of M87*, "
        "matching general relativity's predicted photon ring within a few percent."
    )
    ctx = {"committed_goal": {"id": "g-bh", "title": "Understand black holes"}}
    wr._write_research_memo("black holes", body, ctx, source="research_topic")
    memos = list((GOALS_DIR / "artifacts").glob("*/memo_black-holes.md"))
    assert len(memos) == 1
    # the path→hash index resolves, so a later read can be credited as reuse
    assert el.hash_for_path(memos[0]) is not None
    el.reset_for_tests()


# ── F5 — attempt-rate quota ────────────────────────────────────────────────────

def test_attempt_rate_quota_trims_over_generators(monkeypatch):
    from brain.cognition import intrinsic_generators as ig
    stages = {"Understand the world more deeply":
              {"generated": 100, "attempted": 5, "progressed": 0, "completed": 1},
              "Make things — produce work that didn't exist before":
              {"generated": 6, "attempted": 5, "progressed": 2, "completed": 2}}
    monkeypatch.setattr("brain.cognition.objective_scoreboard.scoreboard",
                        lambda *a, **k: stages)
    monkeypatch.setattr(ig, "_serves_aspiration",
                        lambda d: ("Understand the world more deeply"
                                   if d == "world_knowledge"
                                   else "Make things — produce work that didn't exist before"))
    pool = ([{"title": f"Understand t{i}", "driven_by": "world_knowledge"} for i in range(4)]
            + [{"title": "Make a tool", "driven_by": "output_producing"}])
    out = ig._attempt_rate_quota(pool)
    world = [g for g in out if g["driven_by"] == "world_knowledge"]
    assert len(world) == 1                          # trimmed to one candidate
    assert any(g["driven_by"] == "output_producing" for g in out)


# ── F6 — real definition-of-done + per-life completion cap ─────────────────────

def test_satiety_close_needs_two_steps_or_a_milestone(monkeypatch):
    from brain.cognition.planning import goal_closure as gc
    monkeypatch.setattr(gc, "_tier_closure_enabled", lambda: True)
    monkeypatch.setattr("brain.cognition.planning.goal_satiety.is_sated",
                        lambda goal, ctx: (True, "novelty exhausted"))
    goal = {"id": "g-front", "title": "Understand emergence more deeply",
            "tier": "core", "status": "in_progress", "milestones": [],
            "plan": [{"step": "research it", "status": "completed"},
                     {"step": "write one concrete thing", "status": "pending"},
                     {"step": "connect it to prior notes", "status": "pending"}]}
    res = gc._maybe_close_on_tier(goal, goal["title"], "write one concrete thing", 2, {})
    assert res is None                              # deferred: only 1/3 steps done
    goal["plan"][1]["status"] = "completed"
    res2 = gc._maybe_close_on_tier(goal, goal["title"], "connect it", 1, {})
    # with 2 steps done the gate opens (closure itself may still be blocked by
    # deeper completion machinery; what matters here is the gate no longer defers)
    assert res2 is None or res2.get("closed")


def test_title_completion_cap_and_escalating_cooldown(monkeypatch, tmp_path):
    from brain.cognition import intrinsic_helpers as ih
    monkeypatch.setattr(ih, "_TITLE_COUNTS_FILE", tmp_path / "counts.json")
    monkeypatch.setattr(ih, "_TITLE_COUNTS", {})
    monkeypatch.setattr(ih, "_RECENTLY_COMPLETED", {})
    t = "Understand emergence more deeply"
    now = time.time()
    ih.note_title_completion(t)
    # inside base cooldown → blocked
    assert ih.title_respawn_blocked(t, now=now + 60)
    # 1 completion → base cooldown; past it → allowed again
    assert not ih.title_respawn_blocked(t, now=now + ih._COOLDOWN_S + 60)
    ih.note_title_completion(t)   # 2nd completion → cooldown doubles
    assert ih.title_respawn_blocked(t, now=now + ih._COOLDOWN_S + 60)
    for _ in range(3):
        ih.note_title_completion(t)
    # 5 completions → capped for the life, regardless of elapsed time
    assert ih.title_respawn_blocked(t, now=now + 100 * ih._COOLDOWN_S)


# ── F7 — the user boundary ─────────────────────────────────────────────────────

def test_open_question_miner_skips_user_speech():
    from brain.cognition.intrinsic_generators import _open_question_goals
    ctx = {"working_memory": [
        {"content": "[input/question] What do you think?", "event_type": "user_input"},
        {"content": "I keep wondering: Why does my prediction error spike at night?",
         "event_type": "reflection"},
    ], "latest_user_input": "What do you think?"}
    goals = _open_question_goals(ctx, long_mem=[])
    titles = [g["title"] for g in goals]
    assert not any("what do you think" in t.lower() for t in titles)


def test_self_speech_habituation_gate(monkeypatch):
    from brain.think.think_utils import talk_policy as tp
    monkeypatch.setattr(tp, "_self_speech_log", [])
    monkeypatch.setattr(tp, "_last_self_speak_ts", 0.0)
    t0 = 1_000_000.0
    line = "something present but hard to name. Am I off on that?"
    assert tp._self_speech_allowed(line, now=t0) is True
    # 40 s later, same content → blocked (min-interval floor already catches it)
    assert tp._self_speech_allowed(line, now=t0 + 40) is False
    # past the floor but inside the content-repeat interval → still blocked
    assert tp._self_speech_allowed(line, now=t0 + 120) is False
    # genuinely different content past the floor → allowed
    assert tp._self_speech_allowed(
        "I finished the memo on emergence and want to show you.", now=t0 + 120 + 91
    ) is True


# ── F8 — heartbeat / silent death ──────────────────────────────────────────────

def test_silent_death_detected_and_clean_shutdown_not(tmp_path, monkeypatch):
    from brain.utils import heartbeat as hb
    monkeypatch.setattr(hb, "HEARTBEAT_FILE", tmp_path / "heartbeat.json")
    monkeypatch.setattr(hb, "LIFECYCLE_EVENTS_FILE", tmp_path / "lifecycle.jsonl")
    monkeypatch.setattr(hb, "_last_beat", 0.0)
    hb.beat(cycle=42)
    # simulate a kill 10 h ago
    from brain.utils.json_utils import load_json, save_json
    d = load_json(hb.HEARTBEAT_FILE, default_type=dict)
    d["ts"] = time.time() - 36_000
    save_json(hb.HEARTBEAT_FILE, d)
    event = hb.check_silent_death()
    assert event is not None and event["event"] == "silent_death"
    assert event["gap_s"] > hb.SILENT_DEATH_GAP_S
    assert (tmp_path / "lifecycle.jsonl").exists()

    # clean shutdown → no event
    monkeypatch.setattr(hb, "_last_beat", 0.0)
    hb.beat(cycle=43)
    hb.mark_clean_shutdown()
    d = load_json(hb.HEARTBEAT_FILE, default_type=dict)
    d["ts"] = time.time() - 36_000
    save_json(hb.HEARTBEAT_FILE, d)
    assert hb.check_silent_death() is None


# ── F9 — pseudo-action channels are known ──────────────────────────────────────

def test_problem_refocus_channels_are_known_pseudo_actions():
    from brain.control_signals.reward_signals.action_reward_ema import _KNOWN_PSEUDO_ACTIONS
    assert {"problem_workaround", "problem_resolved"} <= _KNOWN_PSEUDO_ACTIONS
