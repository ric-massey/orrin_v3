# T1 (Run 11 §4) — the Thought Object as working-memory currency. One
# canonical provenance/addressee/researchability classifier replaces twelve
# drifting prefix lists; content becomes display-only. The structural win over
# F-LN1's string skips: a typed entry needs NO magic marker to be handled right.

from brain.cognition import thought as th


def test_mk_thought_carries_typed_fields_through_working_memory():
    from brain.cog_memory.working_memory import update_working_memory
    from brain.utils.json_utils import load_json
    from brain.paths import WORKING_MEMORY_FILE

    entry = th.mk_thought("What is noise, really — beyond randomness?",
                          provenance="self_thought", kind="reflection",
                          importance=3)
    update_working_memory(entry)
    wm = load_json(WORKING_MEMORY_FILE, default_type=list) or []
    stored = next(e for e in wm if e.get("id") == entry["id"])
    assert stored["provenance"] == "self_thought"
    assert stored["researchability"] == "world"
    assert stored["addressee"] == "none"


def test_typed_field_wins_over_legacy_inference():
    e = {"content": "🧠 Chose: reflect", "provenance": "self_thought"}
    assert th.provenance_of(e) == "self_thought"   # explicit stamp is authority


def test_legacy_inference_covers_the_established_markers():
    assert th.provenance_of({"content": "x", "agent": "user"}) == "user"
    assert th.provenance_of({"content": "x", "event_type": "user_input"}) == "user"
    assert th.provenance_of(
        {"content": "I asked 'What do you think?'",
         "event_type": "unanswered_question"}) == "self_speech"
    assert th.provenance_of({"content": "[unanswered_question] I asked..."}) == "self_speech"
    assert th.provenance_of({"content": "[input/ user said hello"}) == "user"
    assert th.provenance_of({"content": "🧠 Chose: reflect — scored 0.4"}) == "instrumentation"
    assert th.provenance_of({"content": "A quiet thought about tides."}) == "self_thought"


def test_minable_predicate_is_the_one_rule():
    assert th.is_minable_as_own_gap({"content": "What makes glass transparent?"})
    assert not th.is_minable_as_own_gap({"content": "x", "agent": "user"})
    assert not th.is_minable_as_own_gap(
        {"content": "anything", "event_type": "unanswered_question"})
    assert not th.is_minable_as_own_gap({"content": "🧠 Chose: ponder"})
    # The structural case F-LN1's string-skips could never reach: a typed
    # self_speech entry with NO legacy marker in its content.
    assert not th.is_minable_as_own_gap(
        {"content": "What do you think stands out most?", "provenance": "self_speech"})


def test_researchability_routes_self_vs_world_vs_none():
    assert th.researchability_of({"content": "Why do I keep abandoning threads?"}) == "self"
    assert th.researchability_of({"content": "Why is the sky blue at noon?"}) == "world"
    assert th.researchability_of(
        {"content": "Why is the sky blue?", "agent": "user"}) == "none"


def test_miner_respects_typed_provenance_without_markers():
    from brain.cognition.intrinsic_generators import _open_question_goals
    long_mem = [
        # His own outbound question, typed — no [unanswered_question] marker.
        {"content": "What would you build first, given a week?",
         "provenance": "self_speech"},
        # A genuine world gap from his own thinking.
        {"content": "A thought: What limits how small a transistor can get?",
         "event_type": "reflection"},
    ]
    goals = _open_question_goals({"working_memory": []}, long_mem)
    titles = " | ".join(g.get("title", "") for g in goals)
    assert "What would you build first" not in titles
    assert any("transistor" in t.lower() for t in titles.split(" | "))
