# brain/cognition/epistemic_closeout.py
#
# R10-12 — epistemic close-out on understanding goals (first rung of the
# Finding-7 difficulty ladder; B18 in embryo).
#
# THE PROBLEM (Run 9 skeptic pass, item 14)
# "Understand X more deeply" closed on quenched drive (satiety) — a metabolic
# event, not an epistemic one. Nothing tested whether Orrin could answer anything
# he couldn't before; a goal could complete having produced an artifact that
# never addressed its own gap.
#
# THE FIX
# At creation the goal carries a concrete `question` derived from the gap that
# spawned it (intrinsic_generators does this). At close, the produced artifact is
# scored AGAINST that question — not against effort — and the goal is stamped
# with `question` + `answered: true/false` + a short `answer` excerpt. Scoring is
# symbolic (no LLM): the answer must name the question's subject AND carry
# substantive new prose, not merely restate the title.
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from brain.utils.failure_counter import record_failure

_STOP = {
    "what", "is", "are", "the", "a", "an", "of", "about", "not", "obvious",
    "how", "why", "does", "do", "more", "deeply", "understand", "to", "and",
    "in", "on", "for", "with", "that", "this", "it", "its", "explained",
    "something", "new", "learn", "know",
}

# An artifact must carry at least this much prose to count as a real answer —
# guards against a one-line restatement of the title closing the goal.
_MIN_ANSWER_CHARS = 200


def _is_understanding_goal(goal: Dict[str, Any]) -> bool:
    driver = str(goal.get("driven_by") or "").lower()
    title = str(goal.get("title") or goal.get("name") or "").lower()
    return (driver == "world_knowledge"
            or title.startswith("understand")
            or bool(goal.get("question")))


# A question already written INTO the goal's own prose (description/DoD) — the
# most content-faithful derivation there is.
_EMBEDDED_QUESTION_RE = re.compile(
    r"((?:What|How|Why|When|Where|Who|Which)\b[^.?!]{6,120}\?)"
)


def question_for(goal: Dict[str, Any]) -> str:
    """The concrete question this goal must answer. Prefers the stored question;
    otherwise derives one from the goal's OWN content (description, DoD,
    milestones) — F-LN4c: all 10 Run-10 stamps were the same 'What is not
    obvious about X?' template because this fallback ignored the goal body."""
    q = str(goal.get("question") or "").strip()
    if q:
        return q
    spec = goal.get("spec")
    if isinstance(spec, dict):
        for cand in spec.get("queries", []) or []:
            if "?" in str(cand):
                return str(cand).strip()
    # A question sentence the goal itself carries is the real gap.
    for field in (goal.get("description"),
                  (spec or {}).get("definition_of_done") if isinstance(spec, dict) else None):
        m = _EMBEDDED_QUESTION_RE.search(str(field or ""))
        if m:
            return m.group(1).strip()
    title = str(goal.get("title") or goal.get("name") or "").strip()
    subj = re.sub(r"(?i)^understand\s+|\s+more deeply\s*$", "", title).strip()
    if not subj:
        return ""
    # Last resort: interrogate the goal's own success criterion, not a fixed shape.
    ms = [m for m in (goal.get("milestones") or []) if isinstance(m, dict)]
    ms_text = str(ms[0].get("text") or "").strip(" .") if ms else ""
    if ms_text:
        return f"What did I find about {subj} that makes '{ms_text[:70]}' true?"
    return f"What do I now know about {subj} that I could not have said before?"


def _subject_terms(question: str) -> List[str]:
    words = re.findall(r"[a-z0-9]+", question.lower())
    return [w for w in words if w not in _STOP and len(w) > 2]


def _gather_artifact_text(goal: Dict[str, Any]) -> str:
    """Concatenate the memo artifacts this goal produced (R10-3 files them under
    the goal's own dir). Best-effort; empty string if none found."""
    gid = str(goal.get("id") or "")
    if not gid:
        return ""
    try:
        from brain.paths import GOALS_DIR
        import re as _re
        dir_name = _re.sub(r"[^A-Za-z0-9_-]+", "-", gid)[:64]
        memo_dir = GOALS_DIR / "artifacts" / dir_name
        if not memo_dir.exists():
            return ""
        parts: List[str] = []
        for p in sorted(memo_dir.glob("*.md")):
            try:
                parts.append(p.read_text(encoding="utf-8", errors="replace"))
            except Exception as _pe:
                record_failure("epistemic_closeout._gather_artifact_text.read", _pe)
                continue
        return "\n\n".join(parts)
    except Exception as exc:
        record_failure("epistemic_closeout._gather_artifact_text", exc)
        return ""


def score_answer(question: str, artifact_text: str) -> Tuple[bool, str]:
    """Symbolic score of whether `artifact_text` answers `question`.

    Answered iff: the subject term(s) of the question appear in the artifact AND
    the artifact carries substantive prose beyond the title. Returns
    (answered, answer_excerpt)."""
    text = str(artifact_text or "")
    body = text.strip()
    if len(body) < _MIN_ANSWER_CHARS:
        return (False, "")
    terms = _subject_terms(question)
    low = body.lower()
    if terms and not any(t in low for t in terms):
        return (False, "")
    # First substantive sentence mentioning a subject term is the answer excerpt.
    for sent in re.split(r"(?<=[.!?])\s+", body):
        s = sent.strip()
        if len(s) >= 40 and (not terms or any(t in s.lower() for t in terms)):
            return (True, s[:280])
    return (True, body[:280])


def spawn_followup_goal(goal: Dict[str, Any]) -> bool:
    """F-LN4b: when an understanding goal finally closes with its question NOT
    answered, the question survives as a NEW goal instead of being eaten by the
    satiety close. Returns True if a follow-up was actually added (add_goal's
    live-title-twin dedup may absorb it into an existing node). Never raises."""
    try:
        question = str(goal.get("question") or "").strip()
        if not question:
            return False
        from brain.cognition.intrinsic_helpers import _mk_goal
        from brain.cognition.planning.goal_store import add_goal
        kind = str(goal.get("kind") or "generic")
        is_research = kind == "research"
        followup = _mk_goal(
            f"Answer: {question[:90]}",
            f"My goal '{str(goal.get('title') or '?')[:60]}' closed without answering "
            f"its own question: '{question}'. Answer THAT question specifically — not "
            f"the topic in general — and write the answer to long memory.",
            driven_by=str(goal.get("driven_by") or "world_knowledge"),
            milestones=[f"An answer to '{question[:60]}' was found.",
                        "The answer was written to long memory."],
            kind=kind if is_research else "generic",
            requires_artifact=bool(is_research),
            spec={"queries": [question], "synth_kind": "memo"} if is_research else None,
            question=question,
        )
        # Lineage for G2's answer-changed-a-decision tracing.
        if goal.get("id"):
            followup["parent_question_goal"] = str(goal["id"])
        added = add_goal(followup)
        try:
            from brain.utils.log import log_activity
            log_activity(f"[epistemic] question survived the close — follow-up goal "
                         f"'{str(added.get('title') or '?')[:70]}' carries it.")
        except Exception as _le:
            record_failure("epistemic_closeout.spawn_followup.log", _le)
        return True
    except Exception as exc:
        record_failure("epistemic_closeout.spawn_followup_goal", exc)
        return False


def stamp_closeout(goal: Dict[str, Any]) -> Optional[bool]:
    """Stamp an understanding goal with its question + whether the produced
    artifact answered it. Mutates `goal` in place. Returns the `answered` bool,
    or None for non-understanding goals / on error. Never raises."""
    try:
        if not _is_understanding_goal(goal):
            return None
        question = question_for(goal)
        if not question:
            return None
        answered, answer = score_answer(question, _gather_artifact_text(goal))
        goal["question"] = question
        goal["answered"] = bool(answered)
        if answer:
            goal["answer"] = answer
        if answered:
            # G2: file the answer so a later decision can consume and cite it —
            # the grounded-consequence loop close-out only STARTS here.
            from brain.cognition.answer_citation import note_answered
            note_answered(question, answer, goal.get("id"))
            # G1: an ANSWERED question is a verified success — ladder fuel.
            from brain.cognition.growth_ladder import note_verified_success
            note_verified_success("answered_question", question)
        if not answered:
            try:
                from brain.utils.log import log_activity
                log_activity(f"[epistemic] '{str(goal.get('title'))[:50]}' closed but its "
                             f"question was NOT answered by the artifact: {question[:80]}")
            except Exception as _le:
                record_failure("epistemic_closeout.stamp_closeout.log", _le)
        return bool(answered)
    except Exception as exc:
        record_failure("epistemic_closeout.stamp_closeout", exc)
        return None
