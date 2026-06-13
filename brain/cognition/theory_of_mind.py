# cognition/theory_of_mind.py
#
# Active, persistent, predictive mentalizing — ongoing simulation of the other
# person's current mental state across conversational turns.
#
# Scientific basis (v2 foundations):
#   Premack & Woodruff (1978) — Theory of Mind: attributing beliefs/desires/intentions.
#   Leslie (1987) — metarepresentation: second-order model of their model.
#   Gallese & Goldman (1998) — simulation theory: understanding others via simulation.
#   Friston (2010) — predictive processing: ToM as a generative model; PE → update.
#   Senju & Csibra (2008) — ToM is generative (simulate), not detective (read clues).
#   Apperly & Butterfill (2009) — two-systems ToM: implicit S1 vs explicit S2.
#
# v3 additions (scientifically grounded new mechanisms):
#
#   Singer & Lamm (2009) — Cognitive vs affective empathy dissociation.
#     Cognitive empathy: perspective-taking (what do they THINK/intend?) — uses
#       inferior frontal gyrus, STS, mPFC, TPJ.
#     Affective empathy: feeling what they feel (what is their emotional state?) —
#       uses insula, ACC, sensorimotor cortex.
#     These doubly dissociate in patients: psychopaths show intact cognitive but
#     impaired affective; some autism profiles show the reverse.
#     In conversation: their cognitive agenda (goal/task orientation) and affective
#     register (emotional state) are separable and should be tracked independently.
#     → Added `_infer_cognitive_state()` (mental agenda) alongside `_infer_affective_state()`
#       (renamed and refocused from the old `_infer_state`).
#
#   Feldman (2007) — Interpersonal synchrony.
#     Progressive alignment of two parties' emotional states over time. High synchrony
#     correlates with better mutual prediction, more accurate ToM, and relationship
#     quality. Increases with sustained positive shared attention; decreases with
#     conflict and valence mismatches.
#     → Added `synchrony_score` per person (0.0–1.0), updated each turn.
#     → Synchrony feeds into confidence: high synchrony boosts, low penalizes.
#
#   Baron-Cohen (1995) — Joint attention as the foundation of Theory of Mind.
#     Joint attention: both parties directing attention to the same referent.
#     In text: topic continuity is the proxy. When the same topic is held, joint
#     attention is maintained → ToM is easier and more confident. Topic shifts
#     break joint attention → brief confidence reset.
#     → Added `_extract_keywords()` and `_topic_overlap()`.
#     → Topic stability modulates confidence per turn.
#
#   Buckner & Carroll (2007) — Self-projection as common substrate.
#     ToM, prospective memory, and episodic recall all recruit the same default
#     network (mPFC, posterior cingulate, TPJ, temporal poles). Self-projection
#     quality scales with accumulated experiential richness — more interaction
#     history → richer substrate → better simulation.
#     → Confidence now explicitly blends interaction-depth (Buckner) and
#       prediction accuracy (Friston PE signal) and synchrony (Feldman).
#
#   Saxe & Kanwisher (2003); Saxe (2006) — rTPJ processes beliefs, not just states.
#     The right TPJ is specifically recruited for false-belief tasks — when holding
#     in mind that another's belief DIFFERS from reality (or from one's own knowledge).
#     This is the neural substrate of Leslie's metarepresentation.
#     The core work of ToM is belief discordance, not just state inference.
#     → The belief model (feels_understood, in_alignment) is the Saxe-Leslie layer.
#       Now also tracks whether person appears to hold a belief contradicted by
#       prior interaction context (belief_discordance flag).
#
# Storage: `tom_state` field in relationships.json under the person's record.
from __future__ import annotations
from core.runtime_log import get_logger

import re
from typing import Any, Dict, Optional, Tuple

from utils.log import log_private
from utils.timeutils import now_iso_z
from utils.failure_counter import record_failure
_log = get_logger(__name__)

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


# ── Belief model ───────────────────────────────────────────────────────────────
#
# Leslie (1987) + Saxe (2006): the core work of ToM is holding a second-order
# representation — what do they BELIEVE about this conversation, which may differ
# from reality or from Orrin's knowledge.

def _update_belief_model(
    belief: Dict[str, Any],
    sig: Dict[str, bool],
    prev_intention: str,
    curr_intention: str,
) -> Dict[str, Any]:
    belief = dict(belief)

    if sig["is_affirming"] and not sig["has_neg_words"]:
        belief["feels_understood"] = True
        belief["satisfied_last"]   = True
        belief["in_alignment"]     = True
        belief["consecutive_misalignments"] = 0
        belief["belief_discordance"] = False

    elif sig["is_frustrated"] or (sig["is_correction"] and sig["has_neg_words"]):
        belief["feels_understood"] = False
        belief["satisfied_last"]   = False
        belief["in_alignment"]     = False
        belief["consecutive_misalignments"] = belief.get("consecutive_misalignments", 0) + 1
        belief["belief_discordance"] = True   # Saxe: their belief ≠ what Orrin provided

    elif sig["is_correction"]:
        belief["feels_understood"] = False
        belief["in_alignment"]     = False
        belief["consecutive_misalignments"] = belief.get("consecutive_misalignments", 0) + 1
        belief["belief_discordance"] = True

    elif sig["is_question"] and prev_intention == "instructing":
        belief["feels_understood"] = None
        belief["satisfied_last"]   = None

    elif sig["is_personal"]:
        belief["in_alignment"] = True

    elif belief.get("feels_understood") is not None:
        belief["_staleness"] = belief.get("_staleness", 0) + 1
        if belief.get("_staleness", 0) >= 4:
            belief["feels_understood"] = None
            belief["_staleness"] = 0

    return belief


def _is_misaligned(belief: Dict[str, Any]) -> bool:
    return (
        belief.get("feels_understood") is False or
        belief.get("in_alignment") is False or
        belief.get("consecutive_misalignments", 0) >= 2
    )


# ── Synchrony (Feldman 2007) ──────────────────────────────────────────────────

def _update_synchrony(tom: Dict[str, Any], context: Dict[str, Any], sig: Dict[str, bool]) -> float:
    """
    Feldman (2007): interpersonal synchrony — progressive alignment of two parties'
    emotional states. Tracked as a score (0.0 = opposite poles, 1.0 = high alignment).

    Proxy: compare Orrin's emotional valence to the person's expressed valence.
    Matched valence (both positive, or shared distress) → synchrony increases.
    Divergent valence → synchrony decreases. Ambiguous turns → gentle decay to neutral.
    """
    current = float(tom.get("synchrony_score", 0.50))

    emo  = context.get("affect_state") or {}
    core = emo.get("core_signals", emo) or {}
    orrin_pos = float(core.get("positive_valence", 0) or 0) + float(core.get("exploration_drive", 0) or 0)
    orrin_neg = float(core.get("risk_estimate", 0) or 0) + float(core.get("impasse_signal", 0) or 0)

    if orrin_pos > orrin_neg + 0.15:
        orrin_valence = "positive"
    elif orrin_neg > orrin_pos + 0.15:
        orrin_valence = "negative"
    else:
        orrin_valence = "neutral"

    if sig["has_pos_words"] and not sig["has_neg_words"]:
        person_valence = "positive"
    elif sig["has_neg_words"] and not sig["has_pos_words"]:
        person_valence = "negative"
    else:
        person_valence = "neutral"

    if orrin_valence == person_valence and orrin_valence != "neutral":
        new = min(0.92, current + 0.05)
    elif orrin_valence != "neutral" and person_valence != "neutral" and orrin_valence != person_valence:
        new = max(0.08, current - 0.07)   # opposite poles — divergence
    else:
        new = current * 0.97 + 0.50 * 0.03  # gentle drift toward neutral

    return round(new, 3)


# ── Topic stability / joint attention (Baron-Cohen 1995) ──────────────────────

def _extract_keywords(text: str) -> set:
    words = text.lower().split()
    return {
        w.strip(".,?!:;\"'()[]")
        for w in words
        if len(w) > 3 and w.strip(".,?!:;\"'()[]") not in _STOPWORDS
    }


def _topic_overlap(prev_keywords: set, curr_keywords: set) -> float:
    """
    Baron-Cohen (1995): joint attention proxy via topic continuity.
    High overlap = both attending to the same thing = ToM is easier and more confident.
    """
    if not prev_keywords or not curr_keywords:
        return 0.50  # neutral — no history
    intersection = prev_keywords & curr_keywords
    smaller = min(len(prev_keywords), len(curr_keywords))
    return min(1.0, len(intersection) / max(1, smaller))


# ── Confidence (Buckner + Friston + Feldman + Baron-Cohen) ───────────────────

def _compute_confidence(person_id: str, tom: Dict[str, Any], topic_stability: float = 0.5) -> float:
    """
    Confidence in ToM inference blends four sources:

    1. Interaction depth (Buckner & Carroll 2007): accumulated self-projection
       substrate. More interactions → richer simulation base.
    2. Prediction accuracy (Friston 2010): the PE signal. If predictions are
       frequently wrong, the model is poorly calibrated — confidence should reflect
       this. Weighted more heavily as evidence accumulates.
    3. Synchrony (Feldman 2007): high emotional alignment → higher confidence;
       low alignment → models may have diverged.
    4. Topic stability (Baron-Cohen 1995): joint attention maintained → higher
       inference confidence; topic broke → brief confidence dip.
    """
    try:
        from utils.json_utils import load_json
        from paths import RELATIONSHIPS_FILE
        rels  = load_json(RELATIONSHIPS_FILE, default_type=dict) or {}
        r     = rels.get(person_id) or {}
        n     = len(r.get("interaction_history", []))
        depth = float(r.get("depth", 0.0) or 0.0)
        n_based = min(0.75, 0.30 + (n / 80) * 0.30 + depth * 0.20)
    except Exception:
        n_based = 0.35

    # Friston: blend prediction accuracy as evidence accumulates
    pred_total = tom.get("prediction_total", 0)
    pred_acc   = tom.get("prediction_accuracy", 0.50)
    if pred_total >= 4:
        acc_weight = min(0.35, (pred_total - 3) / 15 * 0.35)
        conf = n_based * (1 - acc_weight) + pred_acc * acc_weight
    else:
        conf = n_based

    # Feldman: synchrony modulation
    synchrony = tom.get("synchrony_score", 0.50)
    if synchrony >= 0.72:
        conf = min(0.90, conf + 0.06)
    elif synchrony <= 0.28:
        conf = max(0.10, conf - 0.08)

    # Baron-Cohen: topic stability (joint attention)
    if topic_stability >= 0.50:
        conf = min(0.90, conf + 0.04)
    elif topic_stability <= 0.10:
        conf = max(0.10, conf - 0.05)

    return round(conf, 3)


# ── Persistence (via relationships.json) ─────────────────────────────────────

def _load_tom_state(person_id: str) -> Dict[str, Any]:
    if not person_id:
        return {}
    try:
        from utils.json_utils import load_json
        from paths import RELATIONSHIPS_FILE
        rels = load_json(RELATIONSHIPS_FILE, default_type=dict) or {}
        return (rels.get(person_id) or {}).get("tom_state") or {}
    except Exception:
        return {}


def _save_tom_state(person_id: str, state: Dict[str, Any]) -> None:
    if not person_id:
        return
    try:
        from utils.json_utils import load_json, save_json
        from paths import RELATIONSHIPS_FILE
        rels = load_json(RELATIONSHIPS_FILE, default_type=dict) or {}
        if person_id not in rels or not isinstance(rels.get(person_id), dict):
            rels[person_id] = {}
        rels[person_id]["tom_state"] = state
        save_json(RELATIONSHIPS_FILE, rels)
    except Exception as _e:
        record_failure("theory_of_mind._save_tom_state", _e)


def _person_model_for(person_id: str) -> Dict[str, Any]:
    try:
        from utils.json_utils import load_json
        from paths import RELATIONSHIPS_FILE
        rels = load_json(RELATIONSHIPS_FILE, default_type=dict) or {}
        return (rels.get(person_id) or {}).get("person_model") or {}
    except Exception:
        return {}


# ── Surface text ───────────────────────────────────────────────────────────────

_AFFECTIVE_FRAMING = {
    "frustrated":                  "seem frustrated",
    "anxious":                     "seem concerned",
    "emotionally open":            "are being personally open",
    "positive":                    "seem to be in a good place",
    "engaged and aligned":         "seem engaged and tracking",
    "reserved":                    "are giving little away",
    "disagreeing or redirecting":  "are disagreeing — not hostile, but not with this",
    "attentive":                   "seem focused and present",
    "task-focused":                "are in execution mode",
    "curious and seeking":         "seem genuinely curious about something specific",
    "carrying something difficult": "seem to be carrying something",
    "possibly carrying some friction": "may be carrying some friction",
}

_COGNITIVE_FRAMING = {
    "goal-blocked":  "Something is blocking their goal.",
    "goal-directed": "They want execution.",
    "exploring":     "The question is open — building understanding.",
    "seeking":       "They want a specific answer.",
    "revising":      "They're updating their model.",
    "confirming":    "They're checking their model matches.",
    "processing":    "They're working through something.",
    "minimal":       "Minimal cognitive engagement — keep the response light.",
    "attending":     "",
}

_INTENTION_FRAMING = {
    "instructing":          "They want execution — not discussion.",
    "seeking_information":  "They want a clear answer.",
    "seeking_connection":   "They want to be understood, not advised.",
    "redirecting":          "They're pushing back. The direction needs to change.",
    "seeking_validation":   "They want their concern acknowledged.",
    "exploring":            "The question is open. They're thinking alongside Orrin.",
    "validating":           "They're affirming — following the thread.",
    "minimal":              "Hard to read. Keep the response light.",
}

_NEXT_FRAMING = {
    "seeking_validation":   "check whether it was done right",
    "seeking_information":  "follow up with a question",
    "exploring":            "explore further",
    "redirecting":          "push back again if not addressed",
    "minimal":              "stay brief",
    "validating":           "affirm or continue",
}


def _build_surface_text(
    affective_state: str,
    cognitive_state: str,
    intention: str,
    shift: Optional[Tuple[str, str]],
    misaligned: bool,
    belief: Dict[str, Any],
    prediction_miss: bool,
    next_predicted: str,
    conf: float,
    consec_misalign: int,
    resolving_misalignment: bool = False,
    synchrony: float = 0.50,
) -> str:
    parts = []
    affective_text = _AFFECTIVE_FRAMING.get(affective_state, f"seem {affective_state}")
    cognitive_text = _COGNITIVE_FRAMING.get(cognitive_state, "")
    intent_text    = _INTENTION_FRAMING.get(intention, "")

    # Priority 0: misalignment resolved — affirmation after corrections
    if resolving_misalignment:
        parts.append(
            f"They {affective_text} — the misalignment cleared. "
            f"They affirmed after the corrections. {intent_text}"
        )
    # Priority 1: misalignment (most actionable signal in conversation)
    elif misaligned:
        if consec_misalign >= 3:
            parts.append(
                f"Misalignment (persistent): they still don't feel understood — "
                f"this is the {consec_misalign}rd consecutive time. What Orrin is doing isn't landing."
            )
        elif consec_misalign == 2:
            parts.append(
                "Misalignment (repeated): they corrected again. They don't feel "
                "understood. Orrin needs to change approach, not just try again."
            )
        else:
            parts.append(
                f"Misalignment: they {affective_text} — they don't feel understood. "
                f"The last response didn't meet their model. {intent_text}"
            )
    # Priority 2: meaningful shift in mental state
    elif shift:
        direction, desc = shift
        if direction == "improved":
            shifted = desc.split(":")[1].strip() if ":" in desc else desc
            parts.append(f"Shift (positive): they {affective_text} now. {shifted}. {intent_text}")
        elif direction == "worsened":
            parts.append(f"Shift (negative): they {affective_text}. Something worsened. {intent_text}")
        elif direction == "withdrawn":
            parts.append("They've gone quiet. Possible disengagement or processing.")
    # Priority 3: stable state — combine cognitive + affective for richer read
    else:
        cog_line = cognitive_text if cognitive_text and cognitive_text != intent_text else ""
        body = f"They {affective_text}. " + " ".join(filter(None, [cog_line, intent_text]))
        parts.append(body.strip())

    # Synchrony annotation (Feldman): only surface when meaningfully divergent or aligned
    if synchrony >= 0.75 and not misaligned:
        parts.append("(High synchrony — shared register.)")
    elif synchrony <= 0.25:
        parts.append("(Low synchrony — some distance in how we're relating.)")

    # Prediction miss: model was wrong — worth flagging for recalibration
    if prediction_miss and not misaligned:
        parts.append("(Different from what I expected — recalibrating.)")

    # Next prediction
    next_desc = _NEXT_FRAMING.get(next_predicted)
    if next_desc and not misaligned:
        parts.append(f"Likely next: they will {next_desc}.")

    prefix = "Mentalizing (tentative): " if conf < 0.50 else "Mentalizing: "
    return prefix + " ".join(parts)


# ── Public API ─────────────────────────────────────────────────────────────────

def simulate(context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Run the Theory of Mind simulation for this cycle.

    Returns None on autonomous cycles (no user input — person not present).

    Returns:
      their_state            : str — affective state (backward compat)
      their_affective_state  : str — what they feel (Singer & Lamm)
      their_cognitive_state  : str — what they think/intend (Singer & Lamm)
      their_intention        : str
      their_expectation      : str
      belief_model           : dict
      shift                  : Optional[Tuple]
      misaligned             : bool
      prediction_accuracy    : float
      confidence             : float — blends depth + PE + synchrony + topic
      synchrony              : float — interpersonal alignment (Feldman)
      topic_stability        : float — joint attention proxy (Baron-Cohen)
      surface_text           : str
    """
    user_input = (context.get("latest_user_input") or "").strip()
    if not user_input:
        return None

    person_id    = context.get("person_id") or context.get("user_id", "")
    person_model = _person_model_for(person_id)
    sig          = _ling_signals(user_input)

    # Singer & Lamm: separate cognitive and affective inference
    cognitive_state = _infer_cognitive_state(sig)
    affective_state = _infer_affective_state(sig, person_model)
    intention       = _infer_intention(sig)

    tom = _load_tom_state(person_id)

    # Check last turn's prediction (Friston: PE signal) — scored at FAMILY level.
    # Exact micro-intention matching scored below chance; the calibration signal we
    # care about is whether Orrin called the other's coarse next-move correctly.
    curr_family      = _family_of(intention)
    last_pred        = tom.get("last_prediction", {})
    predicted_family = last_pred.get("family", "")
    # Back-compat: older state stored only a fine intention — derive its family.
    if not predicted_family and last_pred.get("intention"):
        predicted_family = _family_of(last_pred["intention"])
    pred_hits  = tom.get("prediction_hits",  0)
    pred_total = tom.get("prediction_total", 0)
    # One-time migration: a record from before family-scoring carries exact-match
    # counts (e.g. 2 hits / 67) that would anchor the new, honest family metric for
    # a very long time. Detect the old format (last_prediction has no "family"),
    # reset the tally, and skip scoring this transitional turn so family accuracy
    # starts from a clean baseline.
    if last_pred and "family" not in last_pred:
        pred_hits = 0
        pred_total = 0
        predicted_family = ""   # don't score the stale exact-match prediction
    prediction_miss  = bool(predicted_family and predicted_family != curr_family)
    if predicted_family:
        pred_total += 1
        if not prediction_miss:
            pred_hits += 1
    pred_accuracy = round(pred_hits / max(1, pred_total), 3)

    # Learn the per-person family transition matrix from the observed move:
    # previous family → current family. Sharpens next-family prediction over time.
    transitions = tom.get("intent_transitions") or {}
    if not isinstance(transitions, dict):
        transitions = {}
    _prev_intent = (tom.get("state_history") or [{}])[-1].get("intention", "") \
        if tom.get("state_history") else ""
    if _prev_intent:
        _pf = _family_of(_prev_intent)
        _row = transitions.setdefault(_pf, {})
        _row[curr_family] = int(_row.get(curr_family, 0)) + 1

    # Detect shift vs previous turn
    history = tom.get("state_history", [])
    prev    = history[-1] if history else {}
    shift   = _detect_shift(
        prev.get("state", ""), prev.get("intention", ""),
        affective_state, intention,
    )

    # Update belief model (Leslie / Saxe)
    belief = tom.get("belief_model", {
        "feels_understood":          None,
        "in_alignment":              None,
        "satisfied_last":            None,
        "consecutive_misalignments": 0,
        "belief_discordance":        False,
    })
    old_consec_misalign = belief.get("consecutive_misalignments", 0)
    belief         = _update_belief_model(belief, sig, prev.get("intention", ""), intention)
    misaligned     = _is_misaligned(belief)
    consec_misalign = belief.get("consecutive_misalignments", 0)

    # Predict next turn — fine intention for the surface text, family for scoring.
    next_predicted = _predict_next_intention(intention, sig)
    next_family    = _predict_next_family(curr_family, transitions, next_predicted)

    # Detect misalignment resolution
    resolving_misalignment = (
        sig["is_affirming"] and
        not sig["has_neg_words"] and
        old_consec_misalign >= 1
    )

    # Synchrony update (Feldman 2007)
    synchrony = _update_synchrony(tom, context, sig)

    # Topic stability / joint attention (Baron-Cohen 1995)
    prev_keywords   = set(tom.get("last_keywords", []))
    curr_keywords   = _extract_keywords(user_input)
    topic_stability = _topic_overlap(prev_keywords, curr_keywords)

    # Confidence (Buckner + Friston + Feldman + Baron-Cohen)
    tom["prediction_hits"]     = pred_hits
    tom["prediction_total"]    = pred_total
    tom["prediction_accuracy"] = pred_accuracy
    tom["synchrony_score"]     = synchrony
    conf = _compute_confidence(person_id, tom, topic_stability)

    # Update persistent state
    history.append({
        "state":           affective_state,
        "cognitive_state": cognitive_state,
        "intention":       intention,
        "ts":              now_iso_z(),
    })
    history = history[-8:]

    tom["state_history"]       = history
    tom["belief_model"]        = belief
    tom["last_prediction"]     = {
        "intention": next_predicted,
        "family":    next_family,
        "state":     affective_state,
    }
    tom["intent_transitions"]  = transitions
    tom["misalignment_streak"] = consec_misalign
    tom["last_keywords"]       = list(curr_keywords)
    _save_tom_state(person_id, tom)

    # Surface text
    surface = _build_surface_text(
        affective_state, cognitive_state, intention, shift,
        misaligned, belief, prediction_miss, next_predicted,
        conf, consec_misalign,
        resolving_misalignment=resolving_misalignment,
        synchrony=synchrony,
    )

    expectation_map = {
        "instructing":          "execution — they want the thing done",
        "seeking_information":  "a direct, clear answer",
        "seeking_connection":   "to be heard before being advised",
        "redirecting":          "Orrin to adjust course, not double down",
        "seeking_validation":   "their concern to be acknowledged",
        "exploring":            "genuine engagement with an open question",
        "validating":           "continuation and building on the thread",
        "minimal":              "a response that doesn't demand much",
    }

    log_private(
        f"[ToM] affective={affective_state} cognitive={cognitive_state} "
        f"intention={intention} conf={conf:.2f} sync={synchrony:.2f} "
        f"topic={topic_stability:.2f} misaligned={misaligned} "
        f"shift={shift} pred_acc={pred_accuracy:.2f}"
    )

    return {
        "their_state":           affective_state,   # backward compat
        "their_affective_state": affective_state,
        "their_cognitive_state": cognitive_state,
        "their_intention":       intention,
        "their_expectation":     expectation_map.get(intention, "a thoughtful response"),
        "belief_model":          belief,
        "shift":                 shift,
        "misaligned":            misaligned,
        "prediction_accuracy":   pred_accuracy,
        "confidence":            conf,
        "synchrony":             synchrony,
        "topic_stability":       round(topic_stability, 3),
        "surface_text":          surface,
    }


