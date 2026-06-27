"""Selection scoring / priors (Phase 4D, from select_function.py).

The policy layer turning candidate actions into bias scores: emotion-prefs from
persisted state, the static semantic-emotion prior table (emotion drives
selection from cycle 1), outcome-devaluation of stale priors, recency/frequency
novelty, and the contextual-bandit pick + UCB hint scores. Imports its inputs
downward (constants, state, config, bandit) so there's no cycle back to the core
selector, which re-imports these names.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from brain.config import tuning as _tuning
from brain.think.bandit import contextual_bandit as bandit
from brain.utils.json_utils import load_json
from brain.utils.failure_counter import record_failure
from brain.paths import AFFECT_STATE_FILE, EMOTION_FUNCTION_MAP_FILE
from brain.think.think_utils.selection.constants import FALLBACK_ACTIONS
from brain.think.think_utils.selection.state import _dominant_emotion
from brain.think.think_utils.selection.catalog import _tag_weights


_SEMANTIC_PRIORS: Dict[str, Dict[str, float]] = {
    "stagnation_signal":     {"seek_novelty": 0.9, "search_own_files": 0.82, "look_outward": 0.75,
                    "read_a_book": 0.78, "look_around": 0.70, "grep_files": 0.65,
                    "wikipedia_search": 0.62, "research_topic": 0.60,
                    "search_files": 0.60, "idle_consolidation_cycle": 0.60, "generate_intrinsic_goals": 0.55},
    # Prior realignment (LEARNING_DIAGNOSIS_2026-06-16 §5.1): the curiosity urge was
    # wired to the cheap diversive scanners (look_outward/look_around, learned q≈0.11–0.14)
    # over the epistemic explorers (seek_novelty/research_topic/wikipedia_search, q≈0.34–0.59).
    # The static prior's lift was the entire margin keeping the low-reward arms on top, so
    # learning could never dig out. Point the prior at what he is actually rewarded for and
    # demote the scanners below them — turns diversive curiosity into epistemic.
    "exploration_drive":   {"seek_novelty": 0.85, "research_topic": 0.80,
                    "wikipedia_search": 0.78, "read_a_book": 0.70,
                    "grep_files": 0.62, "reflect_on_internal_agents": 0.55,
                    "generate_intrinsic_goals": 0.55, "search_own_files": 0.50,
                    "search_files": 0.50, "look_outward": 0.45, "look_around": 0.40},
    "impasse_signal": {"attempt_regulation": 0.88, "reflect_on_affect": 0.82,
                    "investigate_unexplained_emotions": 0.76, "reflection": 0.72,
                    "reflect_on_emotion_model": 0.68, "propose_value_revision": 0.65,
                    "self_review": 0.62, "detect_memory_contradictions": 0.60, "plan_self_evolution": 0.52},
    "risk_estimate":     {"attempt_regulation": 0.90, "reflect_on_affect": 0.84,
                    "investigate_unexplained_emotions": 0.78, "check_affect_drift": 0.72,
                    "reflect_on_emotion_model": 0.66, "self_review": 0.62,
                    "reflection": 0.58, "narrative_update": 0.52},
    "threat_level":        {"attempt_regulation": 0.85, "reflect_on_affect": 0.80,
                    "investigate_unexplained_emotions": 0.74, "reflection": 0.70,
                    "reflect_on_emotion_model": 0.64, "propose_value_revision": 0.60,
                    "self_review": 0.56},
    "negative_valence":     {"reflect_on_affect": 0.85, "attempt_regulation": 0.78,
                    "narrative_update": 0.75, "reflection": 0.68,
                    "reflect_on_emotion_model": 0.64, "apply_affective_feedback": 0.60},
    "conflict_signal":       {"attempt_regulation": 0.88, "reflect_on_affect": 0.80,
                    "detect_memory_contradictions": 0.72, "reflection": 0.68,
                    "reflect_on_emotion_model": 0.64, "investigate_unexplained_emotions": 0.62},
    # Phase 4 / E6 cleanup: dead pursue_committed_goal entries removed from the
    # priors below (never scored — the name is excluded from the pool).
    "confidence":  {"plan_self_evolution": 0.7, "generate_intrinsic_goals": 0.6},
    "motivation":  {"assess_goal_progress": 0.8, "adapt_subgoals": 0.6, "plan_self_evolution": 0.6},
    "positive_valence":         {"narrative_update": 0.65, "leave_note": 0.62, "generate_intrinsic_goals": 0.6,
                    "look_outward": 0.55, "search_own_files": 0.50},
    "uncertainty": {"search_own_files": 0.78, "self_review": 0.75, "reflection": 0.72,
                    "attempt_regulation": 0.65, "look_around": 0.60, "adapt_subgoals": 0.55,
                    "propose_value_revision": 0.50},
    "social_penalty":       {"attempt_regulation": 0.88, "reflect_on_affect": 0.82,
                    "investigate_unexplained_emotions": 0.72, "reflection": 0.68,
                    "reflect_on_emotion_model": 0.62, "narrative_update": 0.55},
    "overwhelm":   {"attempt_regulation": 0.90, "reflect_on_affect": 0.82,
                    "self_review": 0.72, "reflection": 0.65,
                    "investigate_unexplained_emotions": 0.60},
    "expected_gain":        {"plan_self_evolution": 0.7, "generate_intrinsic_goals": 0.6},
    # §5.1: same realignment as exploration_drive — lead with epistemic explorers,
    # demote look_outward/look_around so the prior stops over-privileging the scanners.
    "wonder":      {"seek_novelty": 0.82, "research_topic": 0.78, "wikipedia_search": 0.74,
                    "search_own_files": 0.62, "reflect_on_internal_agents": 0.60,
                    "leave_note": 0.58, "look_outward": 0.50, "look_around": 0.48},
}


def _emotion_pref_scores_for_dominant(actions: List[str]) -> Dict[str, float]:
    """
    Use *only existing state* to bias functions by emotion:
    - First look inside AFFECT_STATE_FILE:
        - emotion_function_map[dominant] / function_preferences[dominant] / emotion_function_weights[dominant]
    - Then (fallback) look inside EMOTION_FUNCTION_MAP_FILE if present.
    Normalizes to [0..1] with a floor, and handles singletons.
    """
    emo_state: Dict[str, Any] = load_json(AFFECT_STATE_FILE, default_type=dict) or {}
    dom = _dominant_emotion()
    candidates = (
        (emo_state.get("emotion_function_map") or {}),
        (emo_state.get("function_preferences") or {}),
        (emo_state.get("emotion_function_weights") or {}),
    )
    pref: Dict[str, float] = {}
    for block in candidates:
        if isinstance(block, dict) and isinstance(block.get(dom), dict):
            for fn, wt in block[dom].items():
                if fn in actions and isinstance(wt, (int, float)):
                    pref[fn] = float(wt)
            break

    # 🔁 fallback: dedicated map file produced by update_affect_function_map(...)
    if not pref and EMOTION_FUNCTION_MAP_FILE:
        try:
            external_map: Dict[str, Any] = load_json(EMOTION_FUNCTION_MAP_FILE, default_type=dict) or {}
            block = external_map.get(dom)
            if isinstance(block, dict):
                for fn, wt in block.items():
                    if fn in actions and isinstance(wt, (int, float)):
                        pref[fn] = float(wt)
        except Exception as _e:
            record_failure("select_function._emotion_pref_scores_for_dominant", _e)

    if not pref:
        return {}

    vals = list(pref.values())
    if len(vals) == 1:               # singleton → full weight
        k = next(iter(pref))
        return {k: 1.0}

    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1.0
    return {k: 0.15 + 0.85 * ((v - lo) / span) for k, v in pref.items()}  # small floor so emo signal shows up




def _semantic_emotion_prior(actions: List[str], dominant: str) -> Dict[str, float]:
    """
    Return semantic prior scores [0..1] for actions based on dominant emotion.
    Uses the hard-coded _SEMANTIC_PRIORS table so emotion drives selection from
    cycle 1, before the learned map has accumulated evidence.
    """
    priors = _SEMANTIC_PRIORS.get(dominant.lower(), {})
    return {name: priors[name] for name in actions if name in priors}


def _devalue_prior(
    prior: float,
    name: str,
    stats: Dict[str, Dict[str, float]],
    pool_median: float | None,
) -> float:
    """
    Decay a static emotion prior by how far this fn's learned avg_reward sits
    below the candidate-pool median (LEARNING_DIAGNOSIS_2026-06-16 §5.2).

    Only applies once the fn has >= SELECTOR_DEVAL_MIN_PULLS of evidence, and is
    floored at SELECTOR_DEVAL_FLOOR so a prior can never be killed outright (cold
    re-sampling must stay possible). Restores outcome-devaluation sensitivity:
    a prior cannot keep boosting an arm the agent has proven is worse than peers.
    """
    if prior <= 0.0 or pool_median is None:
        return prior
    st = stats.get(name) or {}
    if int(st.get("count", 0) or 0) < int(_tuning.SELECTOR_DEVAL_MIN_PULLS):
        return prior
    gap = pool_median - float(st.get("avg_reward", 0.5) or 0.5)
    count = int(st.get("count", 0) or 0)
    avg = float(st.get("avg_reward", 0.5) or 0.5)
    # A heavily sampled neutral outcome is itself evidence: the action is
    # predictably boring even when the pool median is also flat.
    # P4 — give self-knowledge MORE authority over a heavily-sampled, proven-neutral
    # action. Calibration was near-perfect (Brier 0.010) yet had ~zero authority
    # over action: generate_intrinsic_goals learned `neutral` and was STILL picked
    # #1. The neutral-penalty ceiling now rises with evidence (0.20 → 0.40 once an
    # arm is deeply sampled), and for such an arm the demotion floor drops, so "I
    # know this is empty" can finally become "so I'll pick it less" — while the
    # SELECTOR_DEVAL_MIN_PULLS count gate above still protects cold re-sampling of
    # lightly-sampled arms.
    neutral_cap = 0.40 if count >= 50 else 0.20
    neutral_penalty = min(neutral_cap, 0.03 * (count ** 0.5)) if abs(avg - 0.5) <= 0.05 else 0.0
    if gap <= 0.0 and neutral_penalty <= 0.0:
        return prior
    floor = float(_tuning.SELECTOR_DEVAL_FLOOR)
    if count >= 50 and neutral_penalty >= 0.30:
        floor = floor * 0.5   # proven-empty AND heavily sampled → demotable further
    return prior * max(
        floor,
        1.0 - float(_tuning.SELECTOR_DEVAL_K) * max(0.0, gap) - neutral_penalty,
    )


def _novelty_score(name: str, recent: List[str]) -> float:
    """
    High if not used recently or rarely used.
    Combines recency distance and inverse frequency within a window.
    """
    if not recent:
        return 1.0
    try:
        idx = len(recent) - 1 - recent[::-1].index(name)
        distance = len(recent) - 1 - idx
    except ValueError:
        distance = len(recent)  # never seen → maximum novelty

    window = recent[-32:]
    freq = window.count(name)
    # recency: farther back → higher
    r = min(1.0, distance / max(4.0, len(window) / 4.0))
    # frequency: fewer occurrences → higher
    f = 1.0 - min(1.0, (freq - 0.0) / max(1.0, len(window) / 3.0))
    return max(0.0, min(1.0, 0.6 * r + 0.4 * f))


def _bandit_pick_with_info(actions: List[str], feats: Dict[str, float]) -> Tuple[str, Dict[str, Any]]:
    """
    Try to get (picked, info) from the bandit; degrade gracefully to just a choice.
    `info` may contain 'scores', 'epsilon', etc., if supported by the bandit.
    """
    if hasattr(bandit, "choose"):
        # Prefer newer signature that can return scores
        try:
            picked, info = bandit.choose(actions, feats, return_scores=True)
            if not isinstance(info, dict):
                info = {"_info": info}
            return picked, info
        except TypeError:
            res = bandit.choose(actions, feats)
            if isinstance(res, tuple) and len(res) >= 2:
                return res[0], {"scores": res[1]}
            return res, {}
    if hasattr(bandit, "pick"):
        return bandit.pick(actions, feats), {}
    return (actions[0] if actions else ""), {}


def _bandit_hint_scores(actions: List[str], feats: Dict[str, float]) -> Dict[str, float]:
    """
    Return bandit UCB scores for all actions, clamped to [0..1].
    Uses get_scores() directly so learned weights actually influence selection —
    the old approach called choose(..., return_scores=True) which threw TypeError
    and always returned an empty dict.

    Fixed-scale clamp instead of min-max normalization (function_selection_fix_v2
    §3.3): the bandit returns an optimistic 1.0 for any cold arm in the current
    bucket (contextual_bandit.get_scores). Min-max DESTROYED that optimism —
    when every candidate is cold they all score 1.0, the span collapses to 0, and
    they all normalize to 0.0, so the bandit's exploration never reached the pick.
    Clamping preserves the cold-arm 1.0 as a real positive hint.
    """
    try:
        from brain.think.bandit.contextual_bandit import get_scores
        raw = get_scores(actions, feats)
        if not raw:
            return {}
        return {k: max(0.0, min(1.0, float(v))) for k, v in raw.items()}
    except Exception as exc:
        record_failure("select_function.bandit_scores", exc)
        return {}


def _ensure_min_candidates(actions: List[str]) -> List[str]:
    """Guarantee at least 2 options to avoid collapsing into auto-select."""
    if len(actions) >= 2:
        return list(dict.fromkeys(actions))  # de-dupe preserve order
    seeded = list(dict.fromkeys([*actions, *FALLBACK_ACTIONS]))
    return seeded[:2] if len(seeded) >= 2 else seeded


def _emo_mode_function_map() -> Dict[str, Dict[str, float]]:
    """Emotional-mode → per-fn boost map. Weighted "emo_<mode>:<w>" tags in the
    manifest are the source of truth; each mode falls back to its literal map.
    (E6: the dead pursue_committed_goal 0.20 entry under "focused" was removed.)"""
    defaults: Dict[str, Dict[str, float]] = {
        "focused":       {"assess_goal_progress": 0.15, "plan_next_step": 0.10},
        "creative":      {"generate_intrinsic_goals": 0.18, "look_outward": 0.15, "narrative_update": 0.12},
        "exploratory":   {"seek_novelty": 0.20, "search_own_files": 0.15, "look_around": 0.12},
        "philosophical": {"reflection": 0.20, "narrative_update": 0.15, "idle_consolidation_cycle": 0.10},
        "critical":      {"detect_memory_contradictions": 0.18, "self_review": 0.15, "attempt_regulation": 0.10},
        "cautious":      {"attempt_regulation": 0.20, "reflection": 0.15, "self_review": 0.10},
        "analytical":    {"search_own_files": 0.18, "grep_files": 0.15, "self_review": 0.10},
    }
    return {mode: (_tag_weights(f"emo_{mode}") or dflt) for mode, dflt in defaults.items()}
