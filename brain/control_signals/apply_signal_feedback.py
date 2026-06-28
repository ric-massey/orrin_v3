# brain/control_signals/apply_affective_feedback.py
from datetime import datetime, timezone
from brain.utils.affect_signal_utils import log_penalty_signal, log_uncertainty_spike 
from brain.control_signals.update_signal_state import update_affect_state
from brain.control_signals.modes_and_signals import set_current_mode
from brain.control_signals.signal_drift import check_affect_drift
from brain.control_signals.reward_signals.reward_signals import release_reward_signal

# Canonical set of core_signals fields that are NOT nameable felt emotions — they
# are control/appraisal/resource gauges that happen to live in the same dict.
# Promoted to a module constant so any consumer that needs "the dominant emotion"
# (dominant-emotion blending here, pre-workspace binding in cognition/binding.py)
# filters by ONE shared definition instead of each inventing its own taxonomy.
NON_EMOTION_SIGNALS = frozenset({
    "confidence", "affect_stability", "resource_deficit", "stability_signal",
    "connection", "social_deficit", "stagnation_signal", "activation_level",
})


def _parse_iso_ts(ts: str) -> datetime:
    """Robust ISO8601 parser that tolerates 'Z' and returns aware UTC datetimes."""
    if not isinstance(ts, str):
        return datetime.now(timezone.utc)
    ts = ts.strip()
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (ValueError, TypeError):  # intentional: unparseable timestamp → now
        return datetime.now(timezone.utc)

def apply_affective_feedback(context):
    """
    Simulates realistic affective dynamics including domain-specific confidence,
    emotional memory decay, narrative feedback, suppression, and dominant emotion blending.
    Now logs emotional narratives and feedback into working memory for traceability.
    """
    from brain.cog_memory.working_memory import update_working_memory

    affect_state = context.get("affect_state", {}) or {}
    cognition_log = context.get("cognition_log", [])[-7:] or []
    feedback_weight = float(context.get("feedback_weight", 1.0) or 1.0)

    # === A. Domain-Specific Confidence Adjustment ===
    confidence_by_domain = dict(affect_state.get("confidence_by_domain", {}) or {})
    success_tags = {"success", "clarity", "coherence"}
    failure_tags = {"failure", "error", "conflict", "confusion"}
    inertia = 0.85

    for thought in cognition_log:
        if not isinstance(thought, dict):
            continue
        domain = thought.get("domain", "general")
        importance = float(thought.get("importance", 0.5) or 0.5)
        tags = thought.get("tags", []) or []

        valence = 0
        if any(t in success_tags for t in tags):
            valence = 1
        elif any(t in failure_tags for t in tags):
            valence = -1

        intensity = importance * feedback_weight

        if domain not in confidence_by_domain:
            confidence_by_domain[domain] = 0.5

        current_conf = float(confidence_by_domain.get(domain, 0.5))
        delta = 0.1 * (max(0.0, intensity) ** 1.5)

        if valence > 0:
            confidence_by_domain[domain] = min(1.0, (current_conf * inertia) + (delta * (1 - inertia)))
            # Reward for a success event with effort modulated by resource_deficit and motivation
            release_reward_signal(
                context,
                signal_type="reward_signal",
                actual_reward=0.9,
                expected_reward=0.6,
                effort=intensity * (1 - float(affect_state.get("resource_deficit", 0.0) or 0.0)) * (0.5 + float(affect_state.get("motivation", 0.5) or 0.5)),
                mode="phasic",
                source="success event"
            )
            update_working_memory({
                "content": f"Success event in {domain}: tags={tags}, importance={importance}",
                "event_type": "affect_feedback",
                "tags": tags,
                "importance": importance,
                "domain": domain,
                "valence": valence,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
        elif valence < 0:
            log_penalty_signal(context, "confusion", increment=delta)
            confidence_by_domain[domain] = max(0.0, (current_conf * inertia) - (delta * 1.2 * (1 - inertia)))
            update_working_memory({
                "content": f"Negative event in {domain}: tags={tags}, importance={importance}",
                "event_type": "affect_feedback",
                "tags": tags,
                "importance": importance,
                "domain": domain,
                "valence": valence,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })

    affect_state["confidence_by_domain"] = confidence_by_domain

    # === B. Emotion Memory Buffer with Decay ===
    emotional_events = context.get("emotional_events", []) or []
    decay_rate = 0.05
    now = datetime.now(timezone.utc)

    # Keep only last hour and only well-formed entries
    filtered_events = []
    for e in emotional_events:
        if not isinstance(e, dict):
            continue
        ts = _parse_iso_ts(e.get("timestamp"))
        if (now - ts).total_seconds() < 3600:
            # ensure valid shape
            emo = e.get("emotion")
            try:
                intensity = float(e.get("intensity", 0.0) or 0.0)
            except Exception:
                intensity = 0.0
            if isinstance(emo, str):
                filtered_events.append({"emotion": emo, "intensity": intensity, "timestamp": ts.isoformat()})
    emotional_events = filtered_events

    mood_influence = {}
    for e in emotional_events:
        ts = _parse_iso_ts(e["timestamp"])
        age_seconds = (now - ts).total_seconds()
        decay = max(0.0, 1 - (decay_rate * age_seconds / 60.0))
        mood_influence[e["emotion"]] = mood_influence.get(e["emotion"], 0.0) + e["intensity"] * decay

    # Apply mood influence to core_signals (not top-level affect_state)
    core_emo = affect_state.get("core_signals")
    _target = core_emo if isinstance(core_emo, dict) else affect_state
    for k, v in mood_influence.items():
        try:
            base = float(_target.get(k, 0.0) or 0.0)
        except Exception:
            base = 0.0
        _target[k] = round(min(1.0, base + v * 0.2), 3)

    context["emotional_events"] = emotional_events

    # === C. Narrative Generation (for self-explanation or logging) ===
    if cognition_log:
        most_impactful = max(
            cognition_log,
            key=lambda x: float(x.get("importance", 0.5) or 0.5) if isinstance(x, dict) else 0.0,
        )
        tags = (most_impactful.get('tags') or []) if isinstance(most_impactful, dict) else []
        description = (most_impactful.get('description') or 'a recent event') if isinstance(most_impactful, dict) else 'a recent event'
        narrative = f"I felt {' and '.join(tags) if tags else 'something'} during {description}."
        context["affect_narrative"] = narrative
        update_working_memory({
            "content": narrative,
            "event_type": "affect_narrative",
            "importance": float(most_impactful.get("importance", 1) or 1) if isinstance(most_impactful, dict) else 1,
            "priority": 2,
            "emotion": tags[0] if tags else None,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

    # === D. Sudden Mood Collapse — Trigger Secondary Effects ===
    stability = float(affect_state.get("affect_stability", 1.0) or 1.0)
    if stability < 0.35:
        log_uncertainty_spike(context, increment=0.2)
    elif stability > 0.75:
        # Only reward genuinely high stability, not just "not collapsed" (was firing every cycle)
        release_reward_signal(
            context,
            signal_type="stability_signal",
            actual_reward=0.7,
            expected_reward=0.5,
            effort=0.5 * (1 - float(affect_state.get("resource_deficit", 0.0) or 0.0)) * (0.5 + float(affect_state.get("motivation", 0.5) or 0.5)),
            mode="tonic",
            source="stability reward"
        )

    # === E. Suppressed Emotions (based on context) ===
    masked = context.get("mask_emotions", []) or []
    _core_e = affect_state.get("core_signals") if isinstance(affect_state.get("core_signals"), dict) else None
    for emotion in masked:
        if not isinstance(emotion, str):
            continue
        # Emotions live in core_signals; check there first, then top-level
        if _core_e is not None and isinstance(_core_e.get(emotion), (int, float)):
            _core_e[emotion] = float(_core_e[emotion]) * 0.5
        elif isinstance(affect_state.get(emotion), (int, float)):
            affect_state[emotion] = float(affect_state[emotion]) * 0.5

    # === F. Dominant Emotion Blending ===
    # Read from core_signals only — top-level state includes resource_deficit, stability_signal, etc.
    _NON_EMOTIONS = NON_EMOTION_SIGNALS
    core_signals_f = affect_state.get("core_signals") or {}
    numeric_emotions = {
        k: float(v)
        for k, v in core_signals_f.items()
        if isinstance(v, (int, float)) and k not in _NON_EMOTIONS
    }
    top_two = sorted(numeric_emotions.items(), key=lambda x: x[1], reverse=True)[:2]
    context["dominant_signals"] = [e[0] for e in top_two]

    if top_two:
        # Use the mode map rather than raw emotion name — sets a meaningful mode string
        from brain.control_signals.modes_and_signals import recommend_mode_from_affect_state as _rmfe
        set_current_mode(_rmfe())
        # Only reward clarity when emotion is genuinely elevated but not stuck at ceiling
        if 0.7 < top_two[0][1] < 0.96:
            release_reward_signal(
                context,
                signal_type="novelty",
                actual_reward=float(top_two[0][1]),
                expected_reward=0.5,
                effort=0.6 * (1 - float(affect_state.get("resource_deficit", 0.0) or 0.0)) * (0.5 + float(affect_state.get("motivation", 0.5) or 0.5)),
                mode="tonic",
                source="emotional clarity"
            )
            update_working_memory({
                "content": f"Strongly defined dominant emotion: {top_two[0][0]} ({top_two[0][1]:.2f})",
                "event_type": "dominant_affect",
                "emotion": top_two[0][0],
                "intensity": float(top_two[0][1]),
                "timestamp": datetime.now(timezone.utc).isoformat()
            })

    # === G. Update final state, then check drift against fresh values ===
    update_affect_state(context=context, trigger=None)
    check_affect_drift(context, max_cycles=10)
    return context