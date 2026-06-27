from datetime import datetime, timezone

from brain.utils.json_utils import load_json, save_json
from brain.utils.log import log_private, log_error
# NOTE: affect.* imports are intentionally deferred into the function that needs
# them (detect_affect_keyword) so this L1 utils module does not import the L3
# affect package at load time.
from brain.paths import (
    AFFECT_STATE_FILE,
    EMOTIONAL_SENSITIVITY_FILE, 
)

# NOTE: decay_affect_state() was deleted in the V3 convergence refactor (D3).
# It pulled every signal toward 0.5, contradicting update_affect_state's decay
# toward per-signal baselines — two setpoints for one signal. It had no callers.
# The single restoring-force authority is now affect.homeostasis.apply_restoring_forces,
# decaying toward affect.setpoints.CORE_BASELINES.


def adjust_affect_state(emotion: str, amount: float, reason: str = "", context=None):
    """Adjust a single core emotion with sensitivity, clamped to [0,1].

    When a live context is supplied, the change is routed through the
    AffectArbiter (affect.arbiter.submit_affect) as a proposal rather than being
    written straight to the affect_state file. This keeps the in-loop callers on
    the single convergence path (no last-writer-wins file races, gradual drain).
    The legacy direct-file path is preserved only for context-less callers.
    """
    if reason == "user_command":
        log_private(f"Refused to change emotion '{emotion}' due to direct user command.")
        return

    state_path = AFFECT_STATE_FILE
    sensitivity_path = EMOTIONAL_SENSITIVITY_FILE

    sensitivity = load_json(sensitivity_path, default_type=dict)
    sens = float(sensitivity.get(emotion) or 1.0)
    scaled_amount = float(amount) * sens

    # Live-context path: submit a proposal to the convergence layer and return.
    if isinstance(context, dict) and isinstance(context.get("affect_state"), dict):
        try:
            from brain.affect.arbiter import submit_affect
            submit_affect(context, emotion, scaled_amount, source=(reason or "adjust")[:40])
            context.setdefault("raw_signals", []).append({
                "source": "emotion",
                "content": f"Emotion adjusted: {emotion} by {round(scaled_amount, 4)} due to {reason or 'unspecified'}",
                "signal_strength": min(max(abs(scaled_amount), 0.3), 1.0),
                "tags": ["emotion", "internal", str(emotion), str(reason or "adjustment")],
            })
            log_private(f"Emotion proposal: {emotion} by {round(scaled_amount, 4)} ({reason or 'unspecified'})")
            return
        except Exception as _e:
            log_error(f"adjust_affect_state arbiter submit failed, falling back to file: {_e}")

    # Legacy direct-file path (context-less callers only).
    state = load_json(state_path, default_type=dict)
    core = dict(state.get("core_signals", {}))

    if emotion not in core:
        core[emotion] = 0.5

    # If it's already very strong, tiny nudges are skipped
    if abs(scaled_amount) < 0.1 and abs(core[emotion] - 0.5) > 0.4:
        log_private(f"Emotion '{emotion}' too strong to shift by {scaled_amount}. Skipped.")
        return

    new_value = round(core[emotion] + scaled_amount, 4)
    core[emotion] = max(0.0, min(1.0, new_value))

    stability = float(state.get("affect_stability") or 1.0)
    if scaled_amount > 0:
        stability = min(1.0, stability + (scaled_amount * 0.1))
    elif scaled_amount < 0:
        stability = max(0.0, stability - (abs(scaled_amount) * 0.1))

    state["core_signals"] = core
    state["affect_stability"] = round(stability, 4)
    state["last_updated"] = datetime.now(timezone.utc).isoformat()
    state.setdefault("recent_triggers", []).append({
        "event": reason or f"adjusted_{emotion}",
        "emotion": emotion,
        "intensity": round(scaled_amount, 4),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    save_json(state_path, state)
    log_private(f"Emotion adjusted: {emotion} by {round(scaled_amount, 4)} due to {reason or 'unspecified'}")

    # Add a signal_router signal if a context is provided
    if context is not None:
        context.setdefault("raw_signals", []).append({
            "source": "emotion",
            "content": f"Emotion adjusted: {emotion} by {round(scaled_amount, 4)} due to {reason or 'unspecified'}",
            "signal_strength": min(max(abs(scaled_amount), 0.3), 1.0),
            "tags": ["emotion", "internal", str(emotion), str(reason or "adjustment")],
        })


_warned_no_emotion_keywords = False


def detect_affect_keyword(text: str) -> str:
    from brain.affect.model import load_emotion_keywords  # deferred (keeps utils L1 at load time)
    global _warned_no_emotion_keywords
    text = (text or "").lower()
    emotion_keywords = load_emotion_keywords()
    if not emotion_keywords:
        # Once per session — an empty model is a boot-time fact, not a
        # per-utterance event (boot reseeds it; see affect.model).
        if not _warned_no_emotion_keywords:
            _warned_no_emotion_keywords = True
            log_error("⚠️ No emotion keywords loaded — affect detection will return 'neutral' this session.")
        return "neutral"

    emotion_scores = {emotion: 0 for emotion in emotion_keywords}
    for emotion, keywords in emotion_keywords.items():
        for word in keywords:
            if word in text:
                emotion_scores[emotion] += 1

    return max(emotion_scores, key=emotion_scores.get) if any(emotion_scores.values()) else "neutral"


def log_penalty_signal(context, emotion: str = "impasse_signal", increment: float = 0.3):
    """Raise a penalty/negative signal. Routes through the AffectArbiter when a
    live context is present (no direct affect-file write, no last-writer race);
    falls back to a direct file write only for genuinely context-less callers."""
    # Live-context path: propose the increment to the convergence layer.
    if isinstance(context, dict) and isinstance(context.get("affect_state"), dict):
        from brain.affect.arbiter import submit_affect
        submit_affect(context, emotion, float(increment), source="penalty_signal", ttl_cycles=2)
        log_private(f"⚠️ penalty_signal proposal: {emotion} += {round(float(increment), 4)}")
        context.setdefault("raw_signals", []).append({
            "source": "emotion",
            "content": f"penalty_signal signal: {emotion} += {round(float(increment), 4)}",
            "signal_strength": min(max(float(increment), 0.3), 1.0),
            "tags": ["emotion", "penalty_signal", "internal", str(emotion)],
        })
        return

    # Legacy direct-file path (context-less callers only).
    full_state = load_json(AFFECT_STATE_FILE, default_type=dict)
    if not isinstance(full_state, dict):
        full_state = {}
    core_signals = dict(full_state.get("core_signals", {}))
    core_signals[emotion] = min(core_signals.get(emotion, 0.0) + float(increment), 1.0)
    full_state["core_signals"] = core_signals
    save_json(AFFECT_STATE_FILE, full_state)
    log_private(f"⚠️ penalty_signal signal: {emotion} increased to {core_signals[emotion]}")


def log_uncertainty_spike(context, increment: float = 0.2):
    log_private("😵 Disorientation: No function selected by think()")
    log_penalty_signal(context, emotion="uncertainty", increment=increment)


def dominant_emotion(affect_state) -> str:
    """Return the dominant emotion from a full affect_state dict."""
    if not isinstance(affect_state, dict):
        return "neutral"
    core = affect_state.get("core_signals", {})
    if not isinstance(core, dict) or not core:
        return "neutral"
    numeric = {k: v for k, v in core.items() if isinstance(v, (int, float))}
    return max(numeric, key=numeric.get) if numeric else "neutral"