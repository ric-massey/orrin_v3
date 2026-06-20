from datetime import datetime, timezone
import time
import random

from affect.reward_signals.reward_spike import log_reward_spike
from affect.affect_buffer import queue_affect_change
from utils.json_utils import save_json
from utils.log import log_activity
from utils.signal_utils import create_signal
from brain.paths import AFFECT_STATE_FILE, REWARD_TRACE


def release_reward_signal(
    context,
    signal_type="reward_signal",
    actual_reward=1.0,
    expected_reward=0.7,
    effort=0.5,
    mode="phasic",
    source=None
):
    """
    Update in-memory emotional state + reward trace and persist both to disk.
    Uses context['reward_trace'] (string key) for the live buffer and REWARD_TRACE (Path) for disk.
    """

    # Ensure we have the full emotion file structure, not just a sparse dict
    affect_state = context.get("affect_state")
    if not isinstance(affect_state, dict) or not affect_state.get("core_signals"):
        from utils.json_utils import load_json as _load_emo
        affect_state = _load_emo(AFFECT_STATE_FILE, default_type=dict) or {}
        context["affect_state"] = affect_state
    reward_trace = context.setdefault("reward_trace", [])
    last_tags = context.get("last_tags", [])

    # --- Reward Prediction Error (RPE) with noise ---
    rpe = actual_reward - expected_reward
    noise = random.gauss(0, 0.05)
    rpe_noisy = max(min(rpe + noise, 1.0), -1.0)

    surprise = max(0.0, rpe_noisy)
    disappointment = max(0.0, -rpe_noisy)

    # --- Effort modulation (clamped) ---
    # resource_deficit is top-level; motivation lives in core_signals (may also be top-level)
    core_emo = affect_state.get("core_signals") or {}
    resource_deficit    = float(affect_state.get("resource_deficit", 0.0) or 0.0)
    motivation = float(core_emo.get("motivation", affect_state.get("motivation", 0.5)) or 0.5)
    effort_modulated = effort * (1 - resource_deficit) * (0.5 + motivation)
    # clamp effort bonus so it doesn't explode
    effort_bonus = min(max(1.0 + effort_modulated, 0.2), 2.0)

    strength = surprise * effort_bonus

    # --- Information-gain gate on the exploration_drive (curiosity) pump ---
    # Curiosity should track LEARNING PROGRESS / information gain, not raw activity
    # (Oudeyer & Kaplan 2007; Gottlieb & Oudeyer 2018; Berlyne 1960 epistemic vs.
    # diversive curiosity). Without this, re-reading the same files keeps refuelling
    # exploration_drive off reward-prediction surprise even though nothing new was
    # learned — pinning it at the ceiling so it perpetually wins action selection
    # (the curiosity trap). last_novelty is the per-action content novelty of the
    # latest outcome (0..1): low novelty → damp the exploration_drive gain so
    # curiosity decays toward its setpoint between genuinely informative discoveries.
    # ONLY the exploration pump is gated; motivation (goal "wanting", Berridge &
    # Robinson 1998) is left intact, and exploration stays fully AVAILABLE in
    # selection — it just stops being self-reinforcing on low-information repetition.
    # Floor at 0.1, not 0.4: a 40 % refuel on zero-novelty repetition out-ran the
    # restoring force entirely (845 barren repeats of the same search kept the
    # drive pinned — FINDINGS 2026-06-12 §2.3). 10 % keeps exploration available
    # without letting pure repetition hold it at the ceiling.
    _info_gain = float(context.get("last_novelty", 1.0) or 0.0)
    _expl_gate = 0.1 + 0.9 * max(0.0, min(1.0, _info_gain))

    # === reward_signal (incentive / approach drive) ===
    # Encodes incentive salience — "wanting", the pull to move toward a goal — rather than
    # hedonic satisfaction (the wanting-vs-liking distinction; Berridge & Robinson 1998).
    # stability_signal (the hedonic baseline) gates how much of it converts to action:
    # low wellbeing blunts the approach drive. positive_valence is used as the hedonic proxy.
    if signal_type == "reward_signal":
        positive_valence     = float(core_emo.get("positive_valence",     0.3) or 0.3)   # hedonic proxy for stability_signal state
        risk_estimate = float(core_emo.get("risk_estimate", 0.0) or 0.0)

        base_motivation_gain = 0.04 * strength   # primary reward_signal target: wanting/drive
        base_exploration_drive_gain  = 0.025 * strength  # incentive salience → exploration pull

        # Low hedonic state (low positive_valence) blunts how much drive we can muster (Tops et al. 2009)
        wellbeing_mod = 0.6 + 0.4 * positive_valence
        risk_estimate_mod   = 1 - 0.6 * risk_estimate

        motivation_gain = base_motivation_gain * wellbeing_mod * risk_estimate_mod
        exploration_drive_gain  = base_exploration_drive_gain  * wellbeing_mod * risk_estimate_mod * _expl_gate

        if mode == "phasic":
            motivation_gain *= 1.7 + random.uniform(-0.2, 0.2)
            exploration_drive_gain  *= 1.7 + random.uniform(-0.2, 0.2)

        queue_affect_change(affect_state, "motivation", motivation_gain, source="reward_signal")
        queue_affect_change(affect_state, "exploration_drive",  exploration_drive_gain,  source="reward_signal")

        log_reward_spike("reward_signal", strength=strength, tags=last_tags)

    # === Novelty ===
    elif signal_type == "novelty":
        base_exploration_drive_gain = 0.03 * strength
        # stagnation_signal and exploration_drive are core_signals keys
        stagnation_signal   = float(core_emo.get("stagnation_signal",   affect_state.get("stagnation_signal",   0.3)) or 0.3)
        exploration_drive = float(core_emo.get("exploration_drive", affect_state.get("exploration_drive", 0.5)) or 0.5)

        exploration_drive_gain = base_exploration_drive_gain * (1 + 0.5 * stagnation_signal) * (1 - resource_deficit) * _expl_gate
        queue_affect_change(affect_state, "exploration_drive", exploration_drive_gain, source="novelty")

        log_reward_spike("novelty", strength=strength, tags=last_tags)

    # === stability_signal (contentment / wellbeing floor) ===
    # The baseline-wellbeing signal: raises positive_valence and damps risk_estimate
    # (models serotonergic inhibition of the threat pathway; Hariri & Holmes 2006).
    # Unlike reward_signal (approach/wanting), it reflects being okay with the current
    # state rather than seeking more.
    elif signal_type == "stability_signal":
        base_gain = 0.03 * strength
        risk_estimate = float(core_emo.get("risk_estimate", 0.0) or 0.0)
        # High risk_estimate blunts stability_signal effect (consistent with 5-HT/anxiolytic research)
        stability_signal_strength = base_gain * (1 - 0.5 * risk_estimate)
        queue_affect_change(affect_state, "positive_valence",       stability_signal_strength,        source="stability_signal")
        queue_affect_change(affect_state, "risk_estimate",   -stability_signal_strength * 0.4, source="stability_signal")

        log_reward_spike("stability_signal", strength=strength, tags=last_tags)

    # === connection (affiliation) ===
    # Social connection reduces social_deficit and raises exploration_drive (wanting to engage more).
    # Models oxytocinergic affiliation: lowers social_penalty and social_deficit, promotes openness
    # (Heinrichs 2003).
    elif signal_type == "connection":
        queue_affect_change(affect_state, "social_deficit", -0.08 * strength, source="connection")
        queue_affect_change(affect_state, "social_penalty",      -0.05 * strength, source="connection")
        queue_affect_change(affect_state, "exploration_drive",   0.05 * strength, source="connection")
        queue_affect_change(affect_state, "motivation",  0.04 * strength, source="connection")

        log_reward_spike("connection", strength=strength, tags=last_tags)

    # === completion_signal (hedonic "liking") ===
    # The consummatory pleasure of achievement — distinct from reward_signal ("wanting"):
    # reward_signal drives the pursuit, this registers on arrival (liking vs wanting;
    # Berridge 1996, 2007). Released on task completion, flow, social warmth. Wanting and
    # liking are dissociable (want-without-like = addiction; like-without-want = satiation).
    elif signal_type == "completion_signal":
        base_positive_valence_gain = 0.12 * strength
        positive_valence_gain       = base_positive_valence_gain * (1.0 - resource_deficit * 0.4)  # resource_deficit blunts hedonic response
        confidence_gain = 0.05 * strength
        motivation_settle = -0.02 * strength  # completion → slight satiation (wanting reduces)
        queue_affect_change(affect_state, "positive_valence",        positive_valence_gain,         source="completion_signal")
        queue_affect_change(affect_state, "confidence", confidence_gain,  source="completion_signal")
        queue_affect_change(affect_state, "motivation", motivation_settle, source="completion_signal")
        log_reward_spike("completion_signal", strength=strength, tags=last_tags)

    # === Large RPE impulse — direction-aware ===
    # Positive large prediction error: reward_signal burst → strong pull toward more seeking.
    # Negative large prediction error: reward_signal pause → aversion, reduced drive
    # (phasic burst/pause coding of reward-prediction error; Schultz 2007).
    if rpe_noisy > 0.8 and random.random() < 0.7:
        impulse = create_signal(
            source="reward_impulse",
            content="Strong positive surprise — sudden pull toward action. Drive spike.",
            signal_strength=0.92,
            tags=["reward_signal", "wanting", "drive_spike", "action"],
        )
        context.setdefault("raw_signals", []).append(impulse)
        log_activity(f"reward_signal drive spike — unexpected positive outcome: strength={strength:.2f}")
    elif rpe_noisy < -0.8 and random.random() < 0.7:
        impulse = create_signal(
            source="reward_impulse",
            content="Strong negative surprise — drive reduced, aversion signal.",
            signal_strength=0.85,
            tags=["reward_signal_pause", "aversion", "drive_reduction"],
        )
        context.setdefault("raw_signals", []).append(impulse)
        log_activity(f"reward_signal pause — outcome far worse than expected: strength={strength:.2f}")

    # Optionally cap raw_signals growth
    if len(context.get("raw_signals", [])) > 200:
        context["raw_signals"] = context["raw_signals"][-200:]

    # === Append to in-memory trace and persist ===
    noisy_strength = strength * random.uniform(0.85, 1.15)
    reward_trace.append({
        "type": signal_type,
        "strength": noisy_strength,
        "actual_reward": actual_reward,
        "expected_reward": expected_reward,
        "effort": effort,
        "mode": mode,
        "tags": last_tags,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": source,
    })
    if len(reward_trace) > 50:
        reward_trace.pop(0)

    # Persist reward trace only. Emotional state is NOT saved here — update_affect_state()
    # owns that save and applies ceilings, velocity, and hedonic adaptation before writing.
    # Saving mid-cycle would bypass those constraints and cause ceiling violations on disk.
    save_json(REWARD_TRACE, reward_trace)

    return context


def decay_reward_trace(context, base_decay_rate=0.015):
    """
    Decay the in-memory reward trace stored under context['reward_trace'].
    Also persists the decayed trace back to REWARD_TRACE on disk.
    """
    trace = context.get("reward_trace", [])
    affect_state = context.get("affect_state", {})

    # Most emotion values live in core_signals; resource_deficit and activation_level are top-level
    _core = affect_state.get("core_signals") or {}
    stagnation_signal = float(_core.get("stagnation_signal", affect_state.get("stagnation_signal", 0.3)) or 0.3)
    negative_valence = float(_core.get("negative_valence", affect_state.get("negative_valence", 0.1)) or 0.1)
    risk_estimate = float(_core.get("risk_estimate", affect_state.get("risk_estimate", 0.1)) or 0.1)
    resource_deficit = float(affect_state.get("resource_deficit", 0.2) or 0.2)
    activation_level = float(affect_state.get("activation_level", 0.2) or 0.2)

    current_time = time.time()
    new_trace = []

    for entry in trace:
        mod_decay = base_decay_rate

        if negative_valence > 0.6:
            mod_decay *= 0.7
        if stagnation_signal > 0.6:
            mod_decay *= 1.5
        if risk_estimate > 0.7:
            mod_decay *= 0.9

        mod_decay *= 1 + resource_deficit * 0.5

        salience = entry.get("salience", 1.0)
        mod_decay /= max(salience, 0.1)

        if random.random() < 0.05 * activation_level:
            mod_decay *= 0.5

        last_ref = entry.get("last_referenced_time", 0.0)
        time_since_ref = current_time - last_ref
        if time_since_ref < 300:
            mod_decay *= 0.3

        entry["strength"] *= (1 - mod_decay) ** 2

        if entry["strength"] > 0.03:
            new_trace.append(entry)

    context["reward_trace"] = new_trace
    # persist decayed buffer so it survives restarts
    save_json(REWARD_TRACE, new_trace)
    return context


def novelty_penalty(last_choice, current_choice, recent_choices, affect_state=None, context=None):
    """
    Soft stagnation_signal/novelty penalty or reward for action selection.
    Negative for repetition, positive for breaking ruts.
    """
    if affect_state is None:
        affect_state = {}
    if context is None:
        context = {}

    # Moodiness: occasionally ignore penalty (7%)
    if random.random() < 0.07:
        return 0.0

    # Emotion values live in core_signals; resource_deficit is top-level
    _core = affect_state.get("core_signals") or {}
    def _emo(key, default=0.0):
        return float(_core.get(key, affect_state.get(key, default)) or default)

    risk_estimate    = _emo("risk_estimate",   0.0)
    threat_level       = _emo("threat_level",      0.0)
    stagnation_signal    = _emo("stagnation_signal",   0.3)
    exploration_drive  = _emo("exploration_drive", 0.5)
    negative_valence    = _emo("negative_valence",   0.0)
    excitement = _emo("excitement",0.0)
    motivation = _emo("motivation",0.5)
    resource_deficit    = float(affect_state.get("resource_deficit", 0.0) or 0.0)

    # derivative of stagnation_signal
    context.setdefault("stagnation_signal_history", [])
    context["stagnation_signal_history"].append(stagnation_signal)
    if len(context["stagnation_signal_history"]) > 6:
        context["stagnation_signal_history"] = context["stagnation_signal_history"][-6:]

    if len(context["stagnation_signal_history"]) > 1:
        delta_stagnation_signal = context["stagnation_signal_history"][-1] - context["stagnation_signal_history"][-2]
    else:
        delta_stagnation_signal = 0.0

    context.setdefault("stagnation_signal_deltas", [])
    context["stagnation_signal_deltas"].append(delta_stagnation_signal)
    if len(context["stagnation_signal_deltas"]) > 5:
        context["stagnation_signal_deltas"] = context["stagnation_signal_deltas"][-5:]
    smoothed_deriv = sum(context["stagnation_signal_deltas"]) / len(context["stagnation_signal_deltas"])

    # hard repeat penalty
    if current_choice == last_choice:
        if risk_estimate > 0.6 or threat_level > 0.5 or motivation > 0.7:
            return -0.1
        penalty = -0.4 - resource_deficit * 0.2
        return max(penalty, -0.7)

    # soft penalty for recent repeats
    recent_n = recent_choices[-4:]
    base_penalty = -0.18 if current_choice in recent_n else 0.0

    emotion_mod = (exploration_drive + stagnation_signal) - (risk_estimate + threat_level + negative_valence)
    if negative_valence > 0.6:
        emotion_mod *= 0.6
    if excitement > 0.5 or motivation > 0.7:
        emotion_mod *= -0.8
    base_penalty *= (1 + 1.5 * emotion_mod)

    # derivative softly modulates
    if abs(smoothed_deriv) > 0.03:
        deriv_effect = min(max(smoothed_deriv, -0.12), 0.12)
        base_penalty = 0.85 * base_penalty + 0.15 * (base_penalty * (1.0 + deriv_effect * 2.5))

    # reward for breaking ruts
    if current_choice not in recent_choices:
        length = len(recent_choices)
        last_index = recent_choices[::-1].index(current_choice) if current_choice in recent_choices else length
        reward = min(0.15 + 0.15 * last_index, 0.5)
        boost = exploration_drive * 0.4 + excitement * 0.3 + motivation * 0.3
        reward *= 1 + boost
        reward = min(reward, 0.7)
        if smoothed_deriv > 0.08:
            reward += min(smoothed_deriv * 0.11, 0.07)
        return reward

    return base_penalty


def release_reward(context, *, signal, actual, expected, effort, mode, source):
    """
    Canonical keyword-only reward emitter.

    Several call sites (finalize.py, execute_cognitive_actions.py, ...) each kept
    their own byte-identical private `_reward` wrapper around release_reward_signal.
    This is the single shared implementation they now delegate to, so the
    coercion + error-swallowing behaviour lives in exactly one place. Never raises;
    a failed reward must not break the action/cognition path.
    """
    if not context:
        return
    try:
        release_reward_signal(
            context,
            signal_type=signal,
            actual_reward=float(actual),
            expected_reward=float(expected),
            effort=float(effort),
            mode=mode,
            source=source,
        )
    except Exception as e:
        from utils.log import log_model_issue
        log_model_issue(f"Reward signal failed ({source}): {e}")