"""Answers inform selection (brain/cognition/answer_use.py, 2026-11-02).

E5 (scripts/run_e5.py) is the behavioural test; these pin the mechanism: an
answer moves only the candidate it clearly describes, real answers about the
world move nothing, and the selector records the counterfactual on the row."""
from __future__ import annotations

import inspect
import json
from pathlib import Path



from brain.cognition import answer_use as au

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "run13"
DEFS = {
    "look_outward": "look_outward(context) Cognition function: generate a web search and queue it.",
    "narrative_update": "narrative_update(context) Event-driven autobiography update.",
}


def _row(answer, question="What relieves impasse pressure in my planning?"):
    return {"question": question, "answer": answer}


def test_the_described_candidate_and_only_it():
    imp = au._implications(_row("Impasse pressure eases when I generate a web search."), DEFS, list(DEFS))
    assert set(imp) == {"look_outward"} and imp["look_outward"] >= au._MIN_LEAD


def test_an_answer_that_describes_nothing_moves_nothing():
    assert au._implications(_row("Impasse pressure was first named in my ninth life."), DEFS, list(DEFS)) == {}


def test_a_tie_decides_nothing():
    defs = {"a": "a() search the web", "b": "b() search the web"}
    assert au._implications(_row("It eases when I search the web."), defs, list(defs)) == {}


def test_run13_answers_move_nothing_across_the_real_pool(restore_session_data):
    import shutil
    import brain
    import brain.registry.cognition_registry  # noqa: F401 — persists the registry list first
    from brain.paths import COGNITIVE_FUNCTIONS_LIST_FILE
    from brain.think.think_utils.selection.candidates import _load_action_defs
    shutil.copy(Path(brain.__file__).parent / "data" / "cognitive_functions.json",
                COGNITIVE_FUNCTIONS_LIST_FILE)
    pool, defs = _load_action_defs()
    rows = json.loads((FIX / "answered_questions.json").read_text())
    fired = {r["question"]: au._implications(r, defs, pool) for r in rows}
    assert not any(fired.values()), {q: v for q, v in fired.items() if v}


def test_selector_records_the_counterfactual(restore_session_data):
    from brain.cognition import answer_citation
    from brain.eval import e5_answer_use as e5
    p = next(x for x in e5.PROBLEMS if x.pid == "drift")
    truth = "narrative_update"
    assert e5.orrin_selector_decider(p, None, 0) != truth        # chosen otherwise without it
    assert e5.orrin_selector_decider(p, p.answers[truth], 0) == truth
    row = answer_citation._rows()[0]
    assert row["informed"] == 1 and row["decisions_changed"] == 1


def test_helpers_are_not_selectable_cognitive_functions():
    # every public function in a brain.cognition module becomes a selectable
    # "cognitive function" (cognition_registry.discover_cognitive_functions)
    public = [n for n, f in inspect.getmembers(au, inspect.isfunction)
              if f.__module__ == au.__name__ and not n.startswith("_")]
    assert public == []
