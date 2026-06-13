from datetime import datetime, timezone

from utils.json_utils import load_json, save_json
from utils.log import log_private, log_error, log_activity
from utils.self_model import get_self_model
# NOTE: affect.* imports are intentionally deferred into the two functions that
# need them (detect_affect_keyword, contextual_emotion_priming) so this L1 utils
# module does not import the L3 affect package at load time.
from paths import (
    AFFECT_STATE_FILE,
    WORKING_MEMORY_FILE,
    MODE_FILE,
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
            from affect.arbiter import submit_affect
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
    from affect.model import load_emotion_keywords  # deferred (keeps utils L1 at load time)
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
        from affect.arbiter import submit_affect
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


def contextual_emotion_priming(context, persist: bool = True):
    """Affective priming based on working memory, triggers, goals, and mode."""
    from affect.reward_signals.reward_signals import release_reward_signal  # deferred (keeps utils L1)
    # Use in-memory state from context to avoid overwriting concurrent updates
    affect_state = context.get("affect_state") if isinstance(context, dict) else None
    if not isinstance(affect_state, dict) or not affect_state.get("core_signals"):
        affect_state = load_json(AFFECT_STATE_FILE, default_type=dict)
    if not isinstance(affect_state, dict):
        affect_state = {}
    # Prefer in-context state (already in RAM) over disk reloads (D10).
    _wm_raw = context.get("working_memory") if isinstance(context, dict) else None
    if not isinstance(_wm_raw, list):
        _wm_raw = load_json(WORKING_MEMORY_FILE, default_type=list)
    working_memory = _wm_raw[-12:] if isinstance(_wm_raw, list) else []
    self_model = context.get("self_model") if isinstance(context, dict) else None
    if not isinstance(self_model, dict) or not self_model:
        self_model = get_self_model()
    _mode_raw = context.get("mode") if isinstance(context, dict) else None
    if isinstance(_mode_raw, dict):
        mode = _mode_raw.get("mode", "neutral")
    elif isinstance(_mode_raw, str) and _mode_raw:
        mode = _mode_raw
    else:
        mode = load_json(MODE_FILE, default_type=dict).get("mode", "neutral")

    core_signals = dict(affect_state.get("core_signals", {}))
    recent_triggers = affect_state.get("recent_triggers", [])[-10:]
    motivations = [m.lower() for m in self_model.get("motivations", []) if isinstance(m, str)]

    influence_map = {}

    # 1) Working memory echoes
    for memory in working_memory:
        if not isinstance(memory, dict):
            continue
        # new-style emotion dict
        emotion_data = memory.get("emotion")
        if isinstance(emotion_data, dict):
            em = emotion_data.get("emotion")
            intensity = float(emotion_data.get("intensity") or 0.5)
            if em:
                influence_map[em] = influence_map.get(em, 0.0) + intensity * 0.5

        # fallback old-style valence
        valence = memory.get("emotional_valence", {})
        if isinstance(valence, dict):
            for em, intensity in valence.items():
                influence_map[em] = influence_map.get(em, 0.0) + float(intensity) * 0.5

    # 2) Trigger echoes
    for trig in recent_triggers:
        em = trig.get("emotion")
        intensity = float(trig.get("intensity") or 0.5)
        if em:
            influence_map[em] = influence_map.get(em, 0.0) + intensity * 0.4

    # 3) Goal-based semantic priming
    goal_bias_map = {
        "connection": "affection",
        "achievement": "pride",
        "progress": "motivation",
        "safety": "risk_estimate",
        "stability": "security",
    }
    for goal in motivations:
        for keyword, bias_emotion in goal_bias_map.items():
            if keyword in goal:
                influence_map[bias_emotion] = influence_map.get(bias_emotion, 0.0) + 0.3

    # 4) Mode-based modulation
    mode_bias = {
        "creative": "exploration_drive",
        "critical": "impasse_signal",
        "adaptive": "neutral",
        "philosophical": "melancholy",
        "exploratory": "surprise",
    }
    mode_emotion = mode_bias.get(mode)
    if mode_emotion:
        influence_map[mode_emotion] = influence_map.get(mode_emotion, 0.0) + 0.2

    # 5) Apply updates — submit each priming nudge as an AffectArbiter proposal
    # instead of mutating core_signals and writing the affect file directly. This
    # keeps priming on the single convergence path (no last-writer race). The
    # effective (clamped) delta is what we propose, so behaviour matches the old
    # prev→clamp(prev+delta*0.2) step.
    from affect.arbiter import submit_affect
    total_delta = 0.0
    for em, delta in influence_map.items():
        prev = float(core_signals.get(em, 0.5))
        updated = min(1.0, max(0.0, prev + delta * 0.2))
        eff_delta = updated - prev
        total_delta += abs(eff_delta)
        if abs(eff_delta) >= 1e-4:
            submit_affect(context, em, eff_delta, source="priming", ttl_cycles=2)

    # 6) Reward feedback loop — route through the RewardEngine so the expected
    # baseline is the single per-action EMA (was a hardcoded expected=0.5, one of
    # the five inconsistent baselines in V3_AUDIT §2.1).
    reward_strength = min(1.0, total_delta / max(len(influence_map), 1))
    try:
        from affect.reward_signals.reward_engine import submit_reward as _submit_reward
        _submit_reward(
            context,
            actual=reward_strength,
            action_type="priming",
            kind="reward_signal",
            effort=0.4,
            mode="tonic",
            source="priming",
        )
    except Exception:
        release_reward_signal(
            context=context,
            signal_type="reward_signal",
            actual_reward=reward_strength,
            expected_reward=0.5,
            effort=0.4,
            mode="tonic",
        )

    # 7) No direct affect-file write — update_affect_state is the sole writer.
    # `persist` is retained for signature compatibility but proposals are drained
    # at the cycle's commit_affect, so nothing to persist here.
    log_activity("[Priming] Contextual emotion priming submitted affect proposals.")


def dominant_emotion(affect_state) -> str:
    """Return the dominant emotion from a full affect_state dict."""
    if not isinstance(affect_state, dict):
        return "neutral"
    core = affect_state.get("core_signals", {})
    if not isinstance(core, dict) or not core:
        return "neutral"
    numeric = {k: v for k, v in core.items() if isinstance(v, (int, float))}
    return max(numeric, key=numeric.get) if numeric else "neutral"