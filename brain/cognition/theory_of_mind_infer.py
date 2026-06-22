# brain/cognition/theory_of_mind_infer.py
#
# Linguistic-signal inference + intention prediction for theory_of_mind.py
# (CODEBASE_CLEANUP_PLAN 4.5C), lifted verbatim to bring that module under the
# 600-line soft limit. Pure text->state logic (no I/O, no brain deps): detect
# linguistic signals in an utterance, infer the speaker's cognitive/affective
# state and intention, detect state shifts, and predict the next intention /
# intention-family. theory_of_mind.py re-imports these (the simulate() pipeline
# + _STOPWORDS for _extract_keywords) so call sites are unchanged.
from __future__ import annotations

import re
from typing import Any, Dict, Optional, Tuple

# ── Linguistic signal detectors ───────────────────────────────────────────────

_QUESTION_RE   = re.compile(r'\b(what|how|why|when|where|who|can you|could you|would you|is it|are you|do you)\b', re.I)
_CORRECTION_RE = re.compile(r'^(actually[,.]?|no[,.]?|wait[,.]?|but |not really|i don\'t think|that\'s not|wrong[,.])', re.I)
_PERSONAL_RE   = re.compile(r'\b(i feel|i\'m feeling|i am feeling|i\'ve been|i\'m worried|i\'m scared|for me[,])\b', re.I)
_AFFIRM_RE     = re.compile(r'^(yes[.,]?|yeah[.,]?|exactly|right[.,]?|true|agreed|absolutely|totally|correct|yep|precisely|that makes sense)', re.I)
_INSTRUCT_RE   = re.compile(r'\b(do this|make (this|it|that|a|the)|change|fix|update|add|remove|implement|create|write|build|refactor|delete)\b', re.I)
_FRUSTRAT_RE   = re.compile(
    r'\b(not what i|that\'s wrong|no no|still not|still wrong|why (is it|are you|does it|won\'t)|'
    r'doesn\'t work|broken|missing the point|you don\'t (get|understand)|'
    r'you\'re not getting|that\'s not (what|right|it)|you missed|completely wrong)\b', re.I)
_CONCERN_RE    = re.compile(r'\b(worried|concern|careful|are you sure|double.check|might break|are we sure|make sure)\b', re.I)

_NEG_WORDS = {"anxious", "worried", "frustrated", "angry", "upset", "confused",
              "scared", "lost", "overwhelmed", "sad", "annoyed", "stuck", "wrong"}
_POS_WORDS = {"happy", "excited", "grateful", "glad", "great", "good",
              "love", "perfect", "excellent", "wonderful", "nice", "thanks"}

_STOPWORDS = {
    "this", "that", "they", "with", "have", "from", "what", "when", "will",
    "been", "also", "just", "some", "there", "their", "about", "would",
    "could", "should", "like", "make", "does", "into", "more", "your",
    "then", "than", "which", "were", "here", "said", "each",
}


def _ling_signals(text: str) -> Dict[str, bool]:
    t     = text.strip()
    lower = t.lower()
    words = lower.split()
    wc    = len(words)
    return {
        "is_question":    bool(_QUESTION_RE.search(t)) and "?" in t,
        "is_correction":  bool(_CORRECTION_RE.match(t)),
        "is_affirming":   bool(_AFFIRM_RE.match(t)) and wc < 20,
        "is_personal":    bool(_PERSONAL_RE.search(t)),
        "is_instruction": bool(_INSTRUCT_RE.search(t)),
        "is_frustrated":  bool(_FRUSTRAT_RE.search(t)),
        "is_concerned":   bool(_CONCERN_RE.search(t)),
        "is_brief":       wc <= 6,
        "is_long":        wc >= 35,
        "has_neg_words":  any(w in lower for w in _NEG_WORDS),
        "has_pos_words":  any(w in lower for w in _POS_WORDS),
    }


# ── Cognitive vs affective state inference ────────────────────────────────────
#
# Singer & Lamm (2009): cognitive empathy (what they THINK/intend) and affective
# empathy (what they FEEL) dissociate neurologically and behaviorally.
# Track them separately.

def _infer_cognitive_state(sig: Dict[str, bool]) -> str:
    """
    What is their mental AGENDA — their goal/task orientation this turn?
    Cognitive empathy: perspective-taking on their current intent (mPFC, STS, TPJ).
    """
    if sig["is_frustrated"] and sig["is_instruction"]:
        return "goal-blocked"     # clear goal; progress is impeded
    if sig["is_instruction"]:
        return "goal-directed"    # clear procedural intent
    if sig["is_question"] and sig["is_long"]:
        return "exploring"        # open inquiry; building understanding
    if sig["is_question"]:
        return "seeking"          # specific informational goal
    if sig["is_correction"]:
        return "revising"         # updating their model of the situation
    if sig["is_affirming"]:
        return "confirming"       # verifying their model aligns
    if sig["is_personal"]:
        return "processing"       # working through something internally
    if sig["is_brief"]:
        return "minimal"          # low cognitive engagement
    return "attending"            # present but not specifically goal-directed


def _infer_affective_state(sig: Dict[str, bool], person_model: Dict[str, Any]) -> str:
    """
    What do they FEEL — their emotional register this turn?
    Affective empathy: insula/ACC route; distinct from cognitive state.
    """
    if sig["is_frustrated"]:
        return "frustrated"
    if sig["is_concerned"]:
        return "anxious"
    if sig["is_correction"] and sig["has_neg_words"]:
        return "frustrated"
    if sig["is_personal"]:
        return "emotionally open"
    if sig["has_neg_words"] and not sig["has_pos_words"]:
        return "carrying something difficult"
    if sig["has_pos_words"] and not sig["has_neg_words"]:
        return "positive"
    if sig["is_affirming"]:
        return "engaged and aligned"
    if sig["is_correction"]:
        return "disagreeing or redirecting"
    if sig["is_instruction"] and not sig["has_neg_words"]:
        return "task-focused"
    if sig["is_question"] and not sig["has_neg_words"]:
        return "curious and seeking"
    if sig["is_brief"]:
        return "reserved"
    em = person_model.get("emotional_patterns", "")
    if em and "impasse_signal" in em.lower():
        return "possibly carrying some friction"
    return "attentive"


def _infer_intention(sig: Dict[str, bool]) -> str:
    if sig["is_frustrated"] or sig["is_correction"]:
        return "redirecting"
    if sig["is_instruction"]:
        return "instructing"
    if sig["is_question"]:
        return "seeking_information"
    if sig["is_personal"]:
        return "seeking_connection"
    if sig["is_affirming"]:
        return "validating"
    if sig["is_concerned"]:
        return "seeking_validation"
    if sig["is_brief"]:
        return "minimal"
    if sig["is_long"]:
        return "exploring"
    return "exploring"


# ── Shift detection ───────────────────────────────────────────────────────────

_POSITIVE_INTENTS = {"seeking_information", "exploring", "validating", "seeking_connection"}
_NEGATIVE_INTENTS = {"redirecting", "challenging"}
_NEGATIVE_STATES  = {"frustrated", "anxious", "carrying something difficult",
                     "emotionally open", "disagreeing or redirecting"}
_POSITIVE_STATES  = {"positive", "engaged and aligned", "curious and seeking",
                     "attentive", "task-focused"}


def _detect_shift(
    prev_state: str, prev_intention: str,
    curr_state: str, curr_intention: str,
) -> Optional[Tuple[str, str]]:
    if not prev_state:
        return None
    prev_neg_intent = prev_intention in _NEGATIVE_INTENTS
    curr_neg_intent = curr_intention in _NEGATIVE_INTENTS
    prev_neg_state  = prev_state in _NEGATIVE_STATES
    curr_neg_state  = curr_state in _NEGATIVE_STATES

    if prev_neg_intent and not curr_neg_intent:
        return ("improved",  f"de-escalated: {prev_intention} → {curr_intention}")
    if not prev_neg_intent and curr_neg_intent:
        return ("worsened",  f"escalated: {prev_intention} → {curr_intention}")
    if prev_neg_state and not curr_neg_state:
        return ("improved",  f"state shift: {prev_state} → {curr_state}")
    if not prev_neg_state and curr_neg_state:
        return ("worsened",  f"state shift: {prev_state} → {curr_state}")
    if prev_intention != curr_intention and curr_intention == "minimal":
        return ("withdrawn", f"went quiet: {prev_intention} → minimal")
    return None


# ── Prediction ─────────────────────────────────────────────────────────────────
#
# Friston (2010): ToM is a generative model. Commit to a prediction; check next
# cycle; accumulate prediction error as a model-calibration signal.

def _predict_next_intention(intention: str, sig: Dict[str, bool]) -> str:
    if intention == "instructing":
        return "seeking_validation"
    if intention == "redirecting":
        return "seeking_information" if not sig["has_neg_words"] else "redirecting"
    if intention == "seeking_information":
        return "exploring"
    if intention == "validating":
        return "exploring"
    if intention == "seeking_connection":
        return "exploring"
    if intention == "minimal":
        return "minimal"
    if intention == "exploring":
        return "seeking_information"
    return intention


# ── Intention families (ToM scoring granularity) ─────────────────────────────
#
# Scoring an exact micro-intention match was below chance (3%): human turn-taking
# is noisy at the sub-category level. People predict the OTHER's coarse next-move
# (are they going to push, ask, connect, or disengage?), not which exact phrasing
# they'll use. So predict and score at the family level — honest *and* faithful.

_INTENTION_FAMILY: Dict[str, str] = {
    "instructing":         "directive",
    "redirecting":         "directive",
    "seeking_validation":  "directive",
    "seeking_information": "inquiry",
    "exploring":           "inquiry",
    "seeking_connection":  "social",
    "validating":          "social",
    "minimal":             "low",
}


def _family_of(intention: str) -> str:
    return _INTENTION_FAMILY.get(intention, "inquiry")


def _predict_next_family(curr_family: str, transitions: Dict[str, Any],
                         fallback_intention: str) -> str:
    """
    Predict the next intention FAMILY from a learned per-person transition matrix
    (argmax of observed from→to counts). Falls back to the family of the hardcoded
    `_predict_next_intention` guess until enough transitions are observed, so the
    model is useful from turn one and sharpens with experience.
    """
    row = transitions.get(curr_family) if isinstance(transitions, dict) else None
    if isinstance(row, dict) and row:
        try:
            return max(row.items(), key=lambda kv: kv[1])[0]
        except Exception:
            pass
    return _family_of(fallback_intention)

