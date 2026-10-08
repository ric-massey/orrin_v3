"""Phase B cluster 4 — reward honesty (B8+B21, B16, B15, B17, B23, B24).

Fixtures are Run 13 artifacts: 20 of the 75 credited native-LM tracked-work
sections and the 5 auto-promoted exemplars (3 junk, 2 good).
"""
from __future__ import annotations

import json
from pathlib import Path


FIX = Path(__file__).resolve().parents[1] / "fixtures" / "run13"
_JUNK_EXEMPLARS = {"a-similar-situation-suggests-a-similar-situation-4543c9a7.md",
                   "research-memo-the-world-more-deeply-e79808b2.md",
                   "section-2-dd738409.md"}


# ── B8 + B21: the impossible action is marked and earns zero ─────────────────

def test_code_writer_bailout_marks_impossible_and_zeroes_reward(monkeypatch):
    from brain.agency import code_writer
    from brain.control_signals.reward_signals import impossibility as imp
    from brain.loop.invoke import _invoke_cognition
    monkeypatch.setattr("brain.cognition.tools.ask_llm.ask_llm",
                        lambda *a, **k: "ask_llm: LLM tool unavailable (no provider configured)")
    imp.note_possible("decide_to_write_code")
    out = _invoke_cognition(code_writer.decide_to_write_code, "decide_to_write_code", {})
    assert out.get("impossible") is True and out.get("changed") is False
    assert imp.is_impossible("decide_to_write_code")
    assert imp.realized_reward_with_prejudice("decide_to_write_code", 0.54) == 0.0
    assert "decide_to_write_code" in imp.impossible_actions()
    imp.note_possible("decide_to_write_code")


# ── B16: native-LM babble is not production ──────────────────────────────────

def _material():
    return [("memo", "Evolutionary biology is a subfield of biology. " * 6, "m1"),
            ("memo", "Cooperation evolves through kin selection and reciprocity. " * 6, "m2")]


def test_native_draft_needs_the_fluency_gate(monkeypatch):
    from brain.agency import compose_section as cs
    monkeypatch.setattr(cs, "llm_callable_by", lambda caller: False)
    monkeypatch.setattr("brain.cognition.language.voice.lm_ready", lambda: True)
    monkeypatch.setattr("brain.cognition.language.conditional_render.organ_fluent", lambda: False)
    monkeypatch.setattr("brain.cognition.language.native_lm.generate",
                        lambda *a, **k: "A clean paragraph about cooperation. " * 20)
    assert cs._draft({"title": "Make things"}, "Section 2", _material()) == ""


def test_run13_babble_refused_even_past_the_gate(monkeypatch):
    from brain.agency import compose_section as cs
    sections = json.loads((FIX / "credited_babble_sections.json").read_text())
    monkeypatch.setattr(cs, "llm_callable_by", lambda caller: False)
    monkeypatch.setattr("brain.cognition.language.voice.lm_ready", lambda: True)
    monkeypatch.setattr("brain.cognition.language.conditional_render.organ_fluent", lambda: True)
    credited = 0
    for sec in sections:
        monkeypatch.setattr("brain.cognition.language.native_lm.generate",
                            lambda *a, _s=sec, **k: _s)
        if cs._draft({"title": "Make things"}, "Section 2", _material()):
            credited += 1
    assert credited == 0, f"{credited} of {len(sections)} Run-13 babble sections still drafted"


def test_status_lines_never_train_the_organ():
    from brain.cognition.language.acquisition_noise import _is_log_noise
    assert _is_log_noise("[world_model] I've been running for 2h 0m. It's afternoon on Wednesday.")
    assert _is_log_noise("[I_model] memory used. disk full. network up.")
    assert _is_log_noise("[intrinsic_goal] 'Understand history more deeply' (driven by world_knowledge)")
    assert not _is_log_noise("The tide rose over the stones and the gulls went quiet.")


# ── B15: the exemplar gate's self-talk / garble / verbatim checks ────────────

def test_run13_promoted_exemplars_three_junk_two_good():
    from brain.cognition.quality_standard import originality
    from brain.utils.text_sanity import looks_garbled
    rejected = set()
    for f in (FIX / "promoted_exemplars").glob("*.md"):
        t = f.read_text()
        if (originality.is_self_talk(t)[0] or looks_garbled(t)
                or originality.is_verbatim_research_memo(t)):
            rejected.add(f.name)
    assert rejected == _JUNK_EXEMPLARS


# ── B17: value headroom ──────────────────────────────────────────────────────

def test_aspiration_value_cannot_pin_at_one():
    from brain.cognition.planning.commitment_value import _VALUE_ALPHA, _headroom
    v = 0.5
    for _ in range(1000):
        v += _VALUE_ALPHA * _headroom(v, 1.0) * (1.0 - v)
    assert v < 0.99
    assert _headroom(0.9, 0.2) == 1.0   # losing value is never slowed


# ── B23: growth counts dedupe by question ────────────────────────────────────

def test_ladder_credits_a_question_once():
    from brain.cognition import growth_ladder as gl
    if gl._STATE_FILE.exists():
        gl._STATE_FILE.unlink()
    for _ in range(6):
        gl.note_verified_success("answered_question", "What actually is world a world?")
    assert gl._state().get("streak") == 1
    gl.note_verified_success("answered_question", "What is phylogeny?")
    gl.note_verified_success("answered_question", "What is Sisu?")
    assert gl.rung() == 1


def test_citation_counts_once_per_decision_window():
    from brain.cognition import answer_citation as ac
    ac._FILE.write_text("[]")
    ac.note_answered("What is there about emergence in complex systems?",
                     "emergence is…", "g1")
    ctx = {"bound_goal": "Understand emergence in complex systems more deeply"}
    for _ in range(50):
        ac.annotate_reason({}, ctx, "research_topic")
    assert ac.cited_rows()[0]["cited"] == 1
    ac.annotate_reason({}, {"bound_goal": "Write about emergence in complex systems"},
                       "compose_section")
    assert ac.cited_rows()[0]["cited"] == 2


# ── B24: rule hits are once per cycle on every path ──────────────────────────

def test_reinforce_rule_hits_once_per_cycle(monkeypatch):
    from brain.symbolic import rule_engine as re_
    monkeypatch.setattr("brain.utils.get_cycle_count.get_cycle_count", lambda: 4242)
    rule = re_.add_rule(["reflection", "no_action"],
                        "Sustained reflection without goal-directed action predicts B24 test",
                        source="knowledge_formation")
    start = rule.get("hits", 0)
    for _ in range(7):
        re_.reinforce_rule(rule["id"], confidence=0.9)
    re_.apply(dict(re_.reinforce_rule(rule["id"]) or rule), log=False)
    hits = next(r for r in re_.get_all_rules() if r["id"] == rule["id"])["hits"]
    assert hits == start + 1
