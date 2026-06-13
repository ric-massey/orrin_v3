# threat_detector.py — rule-based threat classification (no LLM)
from utils.emotion_utils import dominant_emotion
from utils.log import log_activity

# Thresholds for threat detection
_THREAT_LEVEL_THRESHOLD        = 0.70
_FIGHT_THRESHOLD       = 0.75  # impasse_signal or conflict_signal
_FREEZE_THRESHOLD      = 0.80  # uncertainty
_FREEZE_RESOURCE_DEFICIT        = 0.65  # resource_deficit required for freeze
_STABILITY_FIGHT       = 0.55
_STABILITY_FLIGHT      = 0.50
_SPIKE_EXTREME         = 0.90  # any emotion this high + very low stability
_SPIKE_STABILITY_FLOOR = 0.35


def process_affective_signals(context):
    affect_state = context.get("affect_state", {}) or {}

    # === Extract core emotions (only numeric values) ===
    if isinstance(affect_state.get("core_signals"), dict):
        core = {k: float(v) for k, v in affect_state["core_signals"].items()
                if isinstance(v, (int, float))}
    else:
        # Flat state — exclude non-emotion scalars only
        core = {k: float(v) for k, v in affect_state.items()
                if isinstance(v, (int, float)) and k not in {
                    "affect_stability", "confidence_by_domain",
                    "resource_deficit", "valence", "activation_level", "mood",
                }}

    # Dominant emotion (fallback to 'neutral')
    try:
        dom = dominant_emotion(affect_state)
    except Exception:
        dom = "neutral"
    context["dominant_affect"] = dom or "neutral"

    # Scalar snapshots — resource_deficit and stability are top-level; motivation may be in core_signals
    resource_deficit    = float(affect_state.get("resource_deficit",             0.0) or 0.0)
    stability  = float(affect_state.get("affect_stability", 1.0) or 1.0)
    motivation = float(core.get("motivation", affect_state.get("motivation", 0.5)) or 0.5)

    # Recent reward summary (for context dict — kept for downstream readers)
    recent_rewards = context.get("reward_trace", []) or []
    summary_bits = []
    for r in recent_rewards[-5:]:
        if isinstance(r, dict):
            rtype = str(r.get("type", "unknown"))
            try:
                rstr = float(r.get("strength", 0.0) or 0.0)
            except Exception:
                rstr = 0.0
            summary_bits.append(f"{rtype}({rstr:.2f})")
    reward_summary = ", ".join(summary_bits) if summary_bits else "none"

    # Novelty/impulse signals
    raw_signals = context.get("raw_signals", []) or []
    recent_impulses = [
        s for s in raw_signals
        if isinstance(s, dict)
        and s.get("source") == "reward_impulse"
        and (s.get("signal_strength", 0) or 0) > 0.8
    ]

    # Top emotions for spike detection
    top_emotions = sorted(core.items(), key=lambda x: x[1], reverse=True)[:5]
    spike_intensity = max((v for _, v in top_emotions), default=0.0)

    # Named emotion values
    threat_level        = float(core.get("threat_level",        0.0) or 0.0)
    impasse_signal = float(core.get("impasse_signal", 0.0) or 0.0)
    conflict_signal       = float(core.get("conflict_signal",       0.0) or 0.0)
    uncertainty = float(core.get("uncertainty", 0.0) or 0.0)

    # === Rule-based threat classification ===
    threat_detected = False
    response_type   = "none"
    why             = ""

    if threat_level > _THREAT_LEVEL_THRESHOLD and stability < _STABILITY_FLIGHT:
        threat_detected = True
        response_type   = "flight"
        why = f"threat_level={threat_level:.2f} stability={stability:.2f}"

    elif (impasse_signal > _FIGHT_THRESHOLD or conflict_signal > _FIGHT_THRESHOLD - 0.05) and stability < _STABILITY_FIGHT:
        threat_detected = True
        response_type   = "fight"
        why = f"impasse_signal={impasse_signal:.2f} conflict_signal={conflict_signal:.2f} stability={stability:.2f}"

    elif uncertainty > _FREEZE_THRESHOLD and resource_deficit > _FREEZE_RESOURCE_DEFICIT:
        threat_detected = True
        response_type   = "freeze"
        why = f"uncertainty={uncertainty:.2f} resource_deficit={resource_deficit:.2f}"

    elif spike_intensity > _SPIKE_EXTREME and stability < _SPIKE_STABILITY_FLOOR:
        threat_detected = True
        if dom in ("threat_level", "loss_signal", "social_penalty"):
            response_type = "flight"
        elif dom in ("impasse_signal", "conflict_signal"):
            response_type = "fight"
        else:
            response_type = "freeze"
        why = f"extreme_spike={spike_intensity:.2f} dom={dom} stability={stability:.2f}"

    shortcut_map = {
        "fight": "speak",
        "flight": "dream",
        "freeze": "introspective_planning",
        "none":   "none",
    }
    shortcut_function = shortcut_map[response_type] if threat_detected else "none"

    if threat_detected:
        log_activity(f"[threat_detector] {response_type} threat: {why}")

    context["threat_detector_response"] = {
        "threat_detected":       threat_detected,
        "threat_tags":           [response_type] if threat_detected else [],
        "spike_intensity":       round(float(spike_intensity or 0.0), 2),
        "shortcut_function":     shortcut_function,
        "llm_reasoning":         why,
        "resource_deficit":               resource_deficit,
        "motivation":            motivation,
        "recent_reward_summary": reward_summary,
        "recent_impulses_count": len(recent_impulses),
    }

    return context, context["threat_detector_response"]
