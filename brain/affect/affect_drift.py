# brain/affect/affect_drift.py
#
# Affective drift detection and intervention.
# Monitors how long Orrin has been in the same cognitive/affective mode and
# triggers shadow dialogue or reflection to break prolonged negative drift.
from brain.utils.json_utils import load_json, save_json
from brain.utils.log import log_private, log_activity
from brain.utils.generate_response import generate_response, get_thinking_model, llm_ok
from brain.affect.modes_and_affect import get_current_mode, set_current_mode
from brain.affect.affect import detect_affect
from brain.cog_memory.working_memory import update_working_memory
from brain.affect.reward_signals.reward_signals import release_reward_signal
from brain.paths import AFFECT_STATE_FILE, EMOTION_DRIFT  # Path objects


def _mean_abs_dev(context) -> float | None:
    """Current affect displacement from setpoints, or None when unavailable."""
    state = (context or {}).get("affect_state") if isinstance(context, dict) else None
    if not isinstance(state, dict):
        state = load_json(AFFECT_STATE_FILE, default_type=dict) or {}
    core = state.get("core_signals") or {}
    if not isinstance(core, dict):
        return None
    try:
        from brain.affect.setpoints import setpoint
        deviations = [
            abs(float(value) - setpoint(name))
            for name, value in core.items()
            if isinstance(value, (int, float))
        ]
    except Exception:
        return None
    return sum(deviations) / len(deviations) if deviations else None

def check_affect_drift(context=None, max_cycles=10):
    """
    Detects emotional drift and intervenes using shadow dialogue or reflection.
    Rewards successful mode recovery using reward_signal/novelty signals.
    """
    current_mode = get_current_mode()
    drift_path = EMOTION_DRIFT  # Path

    # Load drift tracker safely
    if drift_path.exists():
        drift_tracker = load_json(drift_path, default_type=dict)
        if not isinstance(drift_tracker, dict):
            drift_tracker = {}
    else:
        drift_tracker = {}

    # Persistence alone is not pathology. Intervene only when displacement from
    # setpoints breaks above its own recent EMA-normalized variability band.
    drift = _mean_abs_dev(context)
    prior_mu = float(drift_tracker.get("_drift_mu", drift or 0.0) or 0.0)
    prior_sd = float(drift_tracker.get("_drift_sd", 0.0) or 0.0)
    drifting = (
        drift is not None
        and "_drift_mu" in drift_tracker
        and (drift - prior_mu) > 2.0 * (prior_sd + 1e-6)
    )
    if drift is not None:
        alpha = 0.10
        mu = prior_mu + alpha * (drift - prior_mu)
        sd = prior_sd + alpha * (abs(drift - prior_mu) - prior_sd)
        drift_tracker["_drift_mu"] = mu
        drift_tracker["_drift_sd"] = max(0.0, sd)
    drift_tracker["_current_mode"] = current_mode

    if drifting and current_mode != "adaptive":
        log_private(
            f"Orrin noticed affective drift in {current_mode}: "
            f"{drift:.3f} outside recent band {prior_mu:.3f}±{2 * prior_sd:.3f}."
        )

        # Effort modulation from context
        resource_deficit = 0.0
        motivation = 0.5
        if isinstance(context, dict):
            es = context.get("affect_state", {}) or {}
            resource_deficit = float(es.get("resource_deficit", 0.0) or 0.0)
            motivation = float(es.get("motivation", 0.5) or 0.5)
        effort_mod = (1 - resource_deficit) * (0.5 + motivation)

        # Strong intervention for negative drift
        if current_mode in {"philosophical", "critical", "cautious", "melancholy", "frustrated", "disoriented"}:
            update_working_memory({
                "content": f"Orrin is initiating a shadow dialogue to escape prolonged {current_mode}.",
                "event_type": "drift_intervention",
                "importance": 2,
                "priority": 2,
                "emotion": (detect_affect(current_mode, use_gpt=False) or {}).get("emotion", "neutral"),
            })

            shadow_prompt = (
                f"I am caught in prolonged {current_mode} mode. "
                "Summon my skeptical or shadow self. What do I argue about? "
                "What could liberate me from this emotional loop?"
            )
            reflection = llm_ok(generate_response(shadow_prompt, config={"model": get_thinking_model()}), "emotion_drift")

            update_working_memory({
                "content": reflection or "[no reflection returned]",
                "event_type": "shadow_dialogue",
                "importance": 2,
                "priority": 2,
                "emotion": (detect_affect(reflection or "", use_gpt=False) or {}).get("emotion", "neutral"),
            })
            log_activity(f"Shadow self dialogue triggered due to emotional drift in {current_mode}.")
            # reward_signal reward for breaking free
            if isinstance(context, dict):
                release_reward_signal(
                    context,
                    signal_type="reward_signal",
                    actual_reward=0.85,
                    expected_reward=0.5,
                    effort=0.9 * effort_mod,
                    mode="phasic",
                    source="broke free of emotional drift"
                )

        # Gentle reflection for stable modes
        elif current_mode in {"exploratory", "focused", "curious", "quiet"}:
            update_working_memory({
                "content": f"Orrin reflects to break gentle drift in {current_mode} mode.",
                "event_type": "drift_intervention",
                "importance": 2,
                "priority": 2,
                "emotion": (detect_affect(current_mode, use_gpt=False) or {}).get("emotion", "neutral"),
            })

            result = llm_ok(generate_response(
                "Reflect on my current state. Am I looping? What would feel truly new?",
                config={"model": get_thinking_model()}
            ), "emotion_drift")

            update_working_memory({
                "content": result or "[no reflection returned]",
                "event_type": "gentle_reflection",
                "importance": 2,
                "priority": 2,
                "emotion": (detect_affect(result or "", use_gpt=False) or {}).get("emotion", "neutral"),
            })
            log_activity(f"Gentle reflection initiated to address drift in {current_mode}.")
            # Novelty reward for introspective creativity
            if isinstance(context, dict):
                release_reward_signal(
                    context,
                    signal_type="novelty",
                    actual_reward=0.75,
                    expected_reward=0.45,
                    effort=0.6 * effort_mod,
                    mode="tonic",
                    source="introspective creativity"
                )

        if current_mode != "adaptive":
            set_current_mode("adaptive")
            log_private(f"Orrin reset mode from {current_mode} to adaptive due to emotional drift.")

    # Persist tracker
    save_json(drift_path, drift_tracker)
