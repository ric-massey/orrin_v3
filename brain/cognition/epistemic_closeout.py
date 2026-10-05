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
from brain.utils.subject_terms import matched_terms, mentions, subject_terms, tokens

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
    # Run 12 §3: the shared definition (scaffold-stopped, matched on whole tokens);
    # _STOP adds this module's legacy extras on top.
    return [w for w in subject_terms(question) if w not in _STOP]


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


def _gather_claims(goal: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Slice 1C.2: load the structured research product (claims.json) the daemon
    wrote beside the memo, from the goal's own artifacts dir. None if absent."""
    gid = str(goal.get("id") or "")
    if not gid:
        return None
    try:
        import json as _json
        from brain.paths import GOALS_DIR
        dir_name = re.sub(r"[^A-Za-z0-9_-]+", "-", gid)[:64]
        p = GOALS_DIR / "artifacts" / dir_name / "claims.json"
        if not p.exists():
            return None
        data = _json.loads(p.read_text(encoding="utf-8", errors="replace"))
        return data if isinstance(data, dict) else None
    except Exception as exc:
        record_failure("epistemic_closeout._gather_claims", exc)
        return None


def _gather_prior_claims(goal: Dict[str, Any], question: str) -> List[Dict[str, Any]]:
    """Orrin's EARLIER claims on the same subject: every other goal's claims.json
    older than this goal's, whose own question shares a whole-token subject term.
    The baseline a new answer must improve on. Best-effort; [] on any error."""
    terms = _subject_terms(question)
    gid = str(goal.get("id") or "")
    if not terms or not gid:
        return []
    try:
        import json as _json
        from brain.paths import GOALS_DIR
        base = GOALS_DIR / "artifacts"
        own = base / re.sub(r"[^A-Za-z0-9_-]+", "-", gid)[:64] / "claims.json"
        cutoff = own.stat().st_mtime if own.exists() else float("inf")
        out: List[Dict[str, Any]] = []
        for p in base.glob("*/claims.json"):
            if p == own:
                continue
            try:
                if p.stat().st_mtime >= cutoff:
                    continue
                data = _json.loads(p.read_text(encoding="utf-8", errors="replace"))
            except (OSError, ValueError):
                continue
            if isinstance(data, dict) and mentions(terms, str(data.get("question") or "")):
                out.append(data)
        return out
    except Exception as exc:
        record_failure("epistemic_closeout._gather_prior_claims", exc)
        return []


# Questions that ask what Orrin got WRONG can only be answered by a claim that
# contradicts something he previously claimed — a definition sentence fetched
# about the topic does not answer them (Run 12: every stamp was a definition).
_REVISION_RE = re.compile(r"\b(wrong|oversimplif\w*|mistaken|misunderst\w*|mis-?read)\b", re.I)

_PRED_NORM = {"is a": "is", "is an": "is", "is the": "is", "are": "is", "was": "is",
              "were": "is", "is defined as": "is", "refers to": "is", "means": "is",
              "is called": "is", "is a type of": "is"}


def _rel_key(r: Dict[str, Any]) -> Tuple[str, str, str]:
    pred = " ".join(str(r.get("predicate") or "").lower().split())
    return (" ".join(tokens(str(r.get("subject") or ""))),
            _PRED_NORM.get(pred, pred),
            " ".join(tokens(str(r.get("object") or ""))))


_NEG = frozenset({"not", "no", "never", "neither", "nor", "cannot", "isn", "aren",
                  "wasn", "weren", "doesn", "don", "didn", "without"})
# A claim that announces its own correction of a common belief.
_MISCONCEPTION_RE = re.compile(
    r"\b(misconception|myth|contrary to|commonly (?:believed|thought|assumed)|"
    r"mistakenly|incorrectly|not actually|oversimplif\w*)\b", re.I)


def _names_subject(terms: List[str], text: str) -> bool:
    """A multi-word subject must be named as a whole: at least two of its terms
    (one when the subject is a single word) — 'nature' alone does not name 'the
    nature of mathematics'."""
    return len(matched_terms(terms, text)) >= min(2, len(terms))


def _differs(new: Tuple[str, str, str], old: Tuple[str, str, str], terms: List[str]) -> bool:
    """`new` CONTRADICTS `old`: both subjects name the question's subject, the
    predicate matches, the objects make the same claim (token overlap >= 0.5 once
    negations are set aside) and exactly one of them is negated. Two different
    true facts about X are not a correction."""
    if new[1] != old[1] or new == old:
        return False
    if not (_names_subject(terms, new[0]) and _names_subject(terms, old[0])):
        return False
    a, b = set(new[2].split()), set(old[2].split())
    if bool(a & _NEG) == bool(b & _NEG):
        return False
    a, b = a - _NEG, b - _NEG
    if not a or not b:
        return False
    return len(a & b) / len(a | b) >= 0.5


def score_answer_structured(question: str, claims: Dict[str, Any],
                            prior: Optional[List[Dict[str, Any]]] = None) -> Tuple[bool, str]:
    """Slice 1C.2 — the STRUCTURED answer scorer (growth's currency is structured
    knowledge, not prose). Returns (answered, answer_excerpt).

    - A telemetry-checkable prediction, if present, must have RESOLVED correctly.
    - Otherwise the question needs a subject (a question with no subject terms
      cannot be answered by claims) and a relation that names it as a whole token.
    - That relation must be NEW relative to `prior` (Orrin's earlier claims on the
      same subject): re-fetching what he already held answers nothing.
    - A revision-shaped question ("what did I get wrong…") additionally needs the
      new relation to CONTRADICT a prior claim (or announce a misconception) — you
      cannot have gotten wrong something you never claimed (Run 12 §5 item 2)."""
    if not isinstance(claims, dict):
        return (False, "")
    terms = _subject_terms(question)
    relations = [r for r in (claims.get("relations") or []) if isinstance(r, dict)]

    pred = claims.get("prediction")
    if isinstance(pred, dict) and pred.get("checkable_against"):
        if not (pred.get("resolved") and pred.get("correct")):
            return (False, "")
        claim_txt = str(pred.get("claim") or "")
        if not terms or mentions(terms, claim_txt):
            return (True, f"prediction confirmed: {claim_txt[:240]}")

    if not terms:
        return (False, "")
    prior_rels = [r for c in (prior or []) if isinstance(c, dict)
                  for r in (c.get("relations") or []) if isinstance(r, dict)]
    prior_keys = {_rel_key(r) for r in prior_rels}
    revision = bool(_REVISION_RE.search(question))

    for r in relations:
        blob = f"{r.get('subject','')} {r.get('predicate','')} {r.get('object','')}".strip()
        if not _names_subject(terms, blob):
            continue
        key = _rel_key(r)
        if key in prior_keys:
            continue
        if not revision:
            return (True, blob[:280])
        if _MISCONCEPTION_RE.search(blob):
            return (True, f"corrects a common belief: {blob[:250]}")
        for old in prior_rels:
            if _differs(key, _rel_key(old), terms):
                old_blob = f"{old.get('subject','')} {old.get('predicate','')} {old.get('object','')}".strip()
                return (True, f"revised: '{old_blob[:120]}' -> '{blob[:140]}'")
    return (False, "")


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
    if not terms or not mentions(terms, body):
        return (False, "")
    # First substantive sentence mentioning a subject term is the answer excerpt.
    for sent in re.split(r"(?<=[.!?])\s+", body):
        s = sent.strip()
        if len(s) >= 40 and mentions(terms, s):
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
        # Slice 1C.2: score the STRUCTURED product first (growth's currency). The
        # memo-prose scorer is now only the rendering-layer fallback for goals that
        # produced no claims.json (e.g. a non-research understanding goal).
        claims = _gather_claims(goal)
        if claims is not None:
            answered, answer = score_answer_structured(
                question, claims, prior=_gather_prior_claims(goal, question))
        else:
            answered, answer = score_answer(question, _gather_artifact_text(goal))
        goal["question"] = question
        goal["answered"] = bool(answered)
        if answer:
            goal["answer"] = answer
        # The transcript (voice.py): closing a question — answered or honestly not —
        # is him reporting on his own work, in the question's and the scorer's own
        # words. No phrasing is invented here beyond the verdict word.
        try:
            from brain.cognition.voice import utter as _utter
            _utter("closeout",
                   f"{'Answered' if answered else 'Not answered'}: {question}"
                   + (f" — {answer}" if answer else ""))
        except Exception as _ve:
            record_failure("epistemic_closeout.voice", _ve)
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
