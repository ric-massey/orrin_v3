# brain/cognition/answer_use.py
#
# Answers inform selection (2026-11-02, Ric: "Let answers inform selection").
#
# Until now an answered question could not change what Orrin did next: the
# selector read no answer, and the "citation" that claimed otherwise was topic
# overlap counted after the pick (F4). E5 (brain/eval/e5_answer_use.py) measured
# it: 0 of 200 decisions moved with the answer.
#
# This is the read. Before scoring, find the answered question whose subject is
# in the deciding context (the same subject match annotate_reason uses). Take
# what the answer says BEYOND its subject — its predicate — and compare it with
# each candidate's own registry definition and name, stemmed. If one candidate
# is clearly what the answer describes (at least _MIN_MATCH shared stems, and a
# lead over every other candidate of at least _MIN_LEAD of the predicate), it
# gets a selection term equal to that lead. Nothing else is touched: an
# answer that says nothing about any candidate — most answers about the world —
# moves nothing.
#
# The selector then asks the counterfactual: would the pick have been different
# without this term? That, not topic overlap, is what `decisions_changed` on the
# answer's row counts.
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set, Tuple

from brain.utils.failure_counter import record_failure

_MIN_MATCH = 2           # shared predicate stems a candidate needs
# ...and the winner's lead over the runner-up must be this share of the
# answer's predicate. A recommendation is mostly ABOUT the one action it
# recommends; a fact that shares generic words with a definition shares them
# with many definitions, so over the real pool no candidate leads by much. Set
# 2026-11-02 between E5's dev answers (lowest lead 0.43) and Run 13's 17 real
# answers, 4 of which matched some function on generic words ("structure",
# "after", "one", "part") with leads of 0.11–0.14. A share-of-predicate floor
# alone (coverage) still let 2 of those 4 through.
_MIN_LEAD = 0.25
_TOKEN = re.compile(r"[a-zA-Z]{3,}")
# Words in every definition (signatures, docstring boilerplate) or in the
# shape of every answer — they would match anything and so say nothing.
_STOP = frozenset("""
the and for with that this from into when what which while where there their them they
then than have has had was were are is be been being its it's i'm my me myself our you your
does did doing done can could should would will shall may might must not no yes
any all some each every other more most less much many few such only own same very also just
about over under again further once here how why who whom whose both either neither
context dict str int float bool none optional list tuple any return returns returned args kwargs
self cls true false default value values function cognition cognitive fn
""".split())
_SUFFIXES = ("ations", "ation", "ness", "ments", "ment", "ings", "ing", "ives", "ive",
             "ions", "ion", "ies", "ied", "ers", "er", "ed", "es", "ly", "al", "s")


def _stem(w: str) -> str:
    w = w.lower()
    changed = True
    while changed:
        changed = False
        for suf in _SUFFIXES:
            if w.endswith(suf) and len(w) - len(suf) >= 4:
                w = w[: -len(suf)]
                changed = True
                break
    return w


def _stems(text: str) -> Set[str]:
    return {_stem(t) for t in _TOKEN.findall(text or "") if t.lower() not in _STOP}


def _candidate_stems(name: str, definition: str) -> Set[str]:
    return _stems(name.replace("_", " ")) | _stems(definition)


def _find_relevant_answer(context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The answered question whose subject is most present in the deciding
    context (ties → the most recent), or None."""
    try:
        from brain.cognition.answer_citation import _rows, _deciding_text, _MIN_TERM_OVERLAP
        from brain.cognition.epistemic_closeout import _subject_terms
        from brain.utils.subject_terms import matched_terms
        deciding = _deciding_text(context)
        if len(deciding) < 8:
            return None
        best: Optional[Tuple[int, float, Dict[str, Any]]] = None
        for r in _rows():
            if not r.get("answer"):
                continue
            terms = _subject_terms(str(r.get("question", "")))
            if not terms:
                continue
            overlap = len(matched_terms(terms, deciding))
            if overlap < min(_MIN_TERM_OVERLAP, len(terms)):
                continue
            key = (overlap, float(r.get("ts", 0) or 0), r)
            if best is None or key[:2] > best[:2]:
                best = key
        return best[2] if best else None
    except Exception as exc:
        record_failure("answer_use._find_relevant_answer", exc)
        return None


def _implications(row: Dict[str, Any], defs: Dict[str, Any], actions: List[str]) -> Dict[str, float]:
    """{candidate: strength in (0, 1]} for the one candidate the answer's
    predicate describes, or {} when it describes none of them clearly."""
    predicate = _stems(str(row.get("answer", ""))) - _stems(str(row.get("question", "")))
    if not predicate:
        return {}
    hits = sorted(
        ((len(predicate & _candidate_stems(a, str(defs.get(a, a)))), a) for a in actions),
        reverse=True)
    if not hits or hits[0][0] < _MIN_MATCH:
        return {}
    if len(hits) > 1 and hits[1][0] >= hits[0][0]:
        return {}  # the answer fits two candidates equally — it decides nothing
    runner_up = hits[1][0] if len(hits) > 1 else 0
    lead = (hits[0][0] - runner_up) / len(predicate)
    if lead < _MIN_LEAD:
        return {}  # no candidate is clearly what the answer describes
    return {hits[0][1]: min(1.0, lead)}


def _answer_terms(context: Dict[str, Any], defs: Dict[str, Any],
                 actions: List[str]) -> Tuple[Optional[Dict[str, Any]], Dict[str, float]]:
    """(row, {candidate: strength}) for this selection; ({}, {}) when no
    answered question bears on it."""
    row = _find_relevant_answer(context)
    if row is None:
        return None, {}
    try:
        return row, _implications(row, defs, actions)
    except Exception as exc:
        record_failure("answer_use._implications", exc)
        return row, {}


def _note_decision(row: Dict[str, Any], changed: bool) -> None:
    """Count, on the answer's own row, that it informed a selection and whether
    it changed the pick (the counterfactual select_function computed)."""
    try:
        from brain.cognition.answer_citation import _FILE, _rows, _MAX_ROWS
        from brain.utils.json_utils import save_json
        rows = _rows()
        for r in rows:
            if r.get("question") == row.get("question"):
                r["informed"] = int(r.get("informed", 0) or 0) + 1
                if changed:
                    r["decisions_changed"] = int(r.get("decisions_changed", 0) or 0) + 1
                break
        save_json(_FILE, rows[-_MAX_ROWS:])
    except Exception as exc:
        record_failure("answer_use._note_decision", exc)
