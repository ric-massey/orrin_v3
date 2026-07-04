# Run 4 fix B3 (RUN4_FIX_PLAN_2026-07-04 §B3): unblock satiety closures. A
# read-heavy "understand X" goal records no ledger effect, so it could never
# satiety-close (19 refusals, 0 closures, three runs). Now the first refusal
# writes a "what I learned" note through the effect ledger; the note is the
# qualifying effect, so the close then completes legitimately. A goal that
# learned nothing writes no note and the refusal still stands.

import brain.agency.effect_ledger as el
import brain.cognition.planning.goal_outcomes as go


def _fresh_ledger(monkeypatch, tmp_path):
    monkeypatch.setattr(el, "EFFECT_LEDGER_FILE", tmp_path / "effect_ledger.jsonl",
                        raising=False)
    el.reset_for_tests()


def test_first_refusal_writes_note_and_closes(monkeypatch, tmp_path):
    _fresh_ledger(monkeypatch, tmp_path)

    goal = {
        "id": "g-understand-evo",
        "title": "Understand evolutionary biology",
        "name": "Understand evolutionary biology",
        "status": "in_progress",
        "milestones": [],
    }
    ctx = {
        "working_memory": [
            {"content": "Evolutionary biology: natural selection acts on heritable "
                        "variation across generations, the core mechanism."},
            {"content": "In evolutionary biology genetic drift dominates small "
                        "populations while gene flow homogenizes diverging lineages."},
            {"content": "Speciation in evolutionary biology follows reproductive "
                        "isolation, allopatric or sympatric."},
        ],
    }
    # Avoid the archive/continuity side effects firing on the real close path.
    monkeypatch.setattr(go, "save_goals", lambda *a, **k: None)
    monkeypatch.setattr(go, "load_goals", lambda: [])

    go.mark_goal_completed(goal, ctx, satiety_close=True)

    # A note was written for the goal and it satisfies the artifact gate now.
    assert el.has_qualifying_effect("g-understand-evo")
    assert goal.get("_learned_note_attempted") is True
    assert goal["status"] == "completed"


def test_goal_that_learned_nothing_still_refuses(monkeypatch, tmp_path):
    _fresh_ledger(monkeypatch, tmp_path)
    goal = {
        "id": "g-empty",
        "title": "Understand something nobody mentioned",
        "name": "Understand something nobody mentioned",
        "status": "in_progress",
        "milestones": [],
    }
    ctx = {"working_memory": []}   # nothing learned
    go.mark_goal_completed(goal, ctx, satiety_close=True)
    assert not el.has_qualifying_effect("g-empty")
    assert goal["status"] == "in_progress"   # refusal stood
    assert goal.get("_learned_note_attempted") is True
