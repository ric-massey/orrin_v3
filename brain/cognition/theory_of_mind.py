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
#     → Added `_infer_cognitive_state()` (mental agenda) alongside `_infer_signal_state()`
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
from brain.core.runtime_log import get_logger

from typing import Any, Dict, Optional

from brain.utils.log import log_private
from brain.utils.timeutils import now_iso_z
from brain.utils.failure_counter import record_failure
# Linguistic-signal inference + intention prediction, extracted to
# theory_of_mind_infer.py (Phase 4.5C). Re-imported so the simulate() pipeline
# below + _extract_keywords' _STOPWORDS keep their references.
from brain.cognition.theory_of_mind_infer import (  # noqa: F401
    _STOPWORDS, _ling_signals, _infer_cognitive_state, _infer_signal_state,
    _infer_intention, _detect_shift, _predict_next_intention, _family_of,
    _predict_next_family,
)
# Surface-text framing (states → mentalizing summary), extracted to
# theory_of_mind_surface.py (Phase 4.5C).
from brain.cognition.theory_of_mind_surface import (  # noqa: F401
    _AFFECTIVE_FRAMING, _COGNITIVE_FRAMING, _INTENTION_FRAMING, _NEXT_FRAMING,
    _build_surface_text,
)
_log = get_logger(__name__)


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
    orrin_pos = float(core.get("reward_positive", 0) or 0) + float(core.get("exploration_drive", 0) or 0)
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
        from brain.utils.json_utils import load_json
        from brain.paths import RELATIONSHIPS_FILE
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
        from brain.utils.json_utils import load_json
        from brain.paths import RELATIONSHIPS_FILE
        rels = load_json(RELATIONSHIPS_FILE, default_type=dict) or {}
        return (rels.get(person_id) or {}).get("tom_state") or {}
    except Exception as exc:  # relationships unreadable — record, no ToM state
        record_failure("theory_of_mind._load_tom_state", exc)
        return {}


def _save_tom_state(person_id: str, state: Dict[str, Any]) -> None:
    if not person_id:
        return
    try:
        from brain.utils.json_utils import load_json, save_json
        from brain.paths import RELATIONSHIPS_FILE
        rels = load_json(RELATIONSHIPS_FILE, default_type=dict) or {}
        if person_id not in rels or not isinstance(rels.get(person_id), dict):
            rels[person_id] = {}
        rels[person_id]["tom_state"] = state
        save_json(RELATIONSHIPS_FILE, rels)
    except Exception as _e:
        record_failure("theory_of_mind._save_tom_state", _e)


def _person_model_for(person_id: str) -> Dict[str, Any]:
    try:
        from brain.utils.json_utils import load_json
        from brain.paths import RELATIONSHIPS_FILE
        rels = load_json(RELATIONSHIPS_FILE, default_type=dict) or {}
        return (rels.get(person_id) or {}).get("person_model") or {}
    except Exception as exc:  # relationships unreadable — record, no person model
        record_failure("theory_of_mind._person_model_for", exc)
        return {}


# ── Surface text ───────────────────────────────────────────────────────────────



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
    affective_state = _infer_signal_state(sig, person_model)
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


