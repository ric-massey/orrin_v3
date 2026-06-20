# brain/affect/update_affect_state.py
#
# Per-cycle affect state update: applies triggers, appraisal nudges, decay,
# habituation, velocity, and oscillation detection to core_signals.
#
# SCIENTIFIC BASIS:
#   Russell & Barrett (2000) — "Core affect, prototypical emotional episodes,
#   and other things called emotion." Psychological Review, 106(3), 631–657.
#   Barrett (2017) — "How Emotions Are Made." Houghton Mifflin Harcourt.
#   "Neutral" is the absence of affective signal, not a discrete emotion.
from core.runtime_log import get_logger
from datetime import datetime, timezone
from statistics import mean
from typing import Dict

from utils.json_utils import load_json, save_json
from affect.affect import get_all_affect_names, detect_affect, deliver_affect_based_rewards
from affect.affect_dynamics import (
    decay_habituation, capture_prev_core, get_habit_factor, record_habit,
    apply_velocity_dynamics, compute_valence_activation_level, update_mood,
    update_hedonic_baselines,
)
from affect.affect_buffer import drain_affect_queue
from affect.homeostasis import (
    apply_restoring_forces, apply_cross_inhibition, enforce_velocity_budget, ANTAGONISTS,
    EMO_CEILINGS, DEFAULT_CEILING, CEILING_RATE, update_allostatic_load,
    homeostasis_index,
)
from affect.setpoints import CORE_BASELINES
from utils.log import log_activity
from affect.modes_and_affect import recommend_mode_from_affect_state, set_current_mode, get_current_mode
from utils.timing import get_time_since_last_active

from paths import AFFECT_STATE_FILE, WORKING_MEMORY_FILE
from utils.failure_counter import record_failure
_log = get_logger(__name__)

def update_affect_state(context=None, trigger=None):
    from cog_memory.working_memory import update_working_memory

    # Prefer in-memory state from context (authoritative); only read disk when truly absent.
    # Previously fell back to disk if core_signals was missing — this discarded transient
    # in-memory reward signals queued into context["affect_state"] but not yet drained.
    state = None
    if context is not None:
        state = context.get("affect_state")
    if not isinstance(state, dict):
        state = load_json(AFFECT_STATE_FILE, default_type=dict)
    if not isinstance(state, dict):
        state = {}
    # If core_signals is missing, seed it from the file rather than discarding the whole state
    if not state.get("core_signals"):
        _disk = load_json(AFFECT_STATE_FILE, default_type=dict) or {}
        if isinstance(_disk.get("core_signals"), dict):
            state["core_signals"] = _disk["core_signals"]
    # Pin the canonical schema (D9): nested core_signals + required scalars. As the
    # sole writer, normalizing here means the canonical layout is what gets persisted.
    from affect.observers import normalize_affect_state
    state = normalize_affect_state(state)
    working = load_json(WORKING_MEMORY_FILE, default_type=list)

    if not isinstance(state, dict) or not isinstance(working, list):
        return

    decay_rate = float(state.get("stability_decay_rate", 0.01) or 0.01)
    last_update_raw = state.get("last_updated", "1970-01-01T00:00:00+00:00")
    try:
        last_update = datetime.fromisoformat(last_update_raw)
    except Exception:
        last_update = datetime(1970, 1, 1, tzinfo=timezone.utc)
    if last_update.tzinfo is None:
        last_update = last_update.replace(tzinfo=timezone.utc)

    now = datetime.now(timezone.utc)
    hours_passed = max(0.0, (now - last_update).total_seconds() / 3600.0)

    # --- Baseline (personality) resting values per signal ---
    # Single source of truth: affect.setpoints.CORE_BASELINES (read-only here).
    baseline = CORE_BASELINES

    # --- Opposites for cross-inhibition (single source: homeostasis.ANTAGONISTS) ---
    # Each emotion listed here suppresses its opposites when a trigger fires.
    # Pairs should be physiologically plausible antagonists, not just semantic antonyms.
    opposites = ANTAGONISTS

    # --- Ensure all baseline emotions exist in core map ---
    # get_all_affect_names() reads affect_model.json which may be empty on first boot.
    # Always seed from baseline directly so expected_gain, positive_valence, negative_valence, conflict_signal etc. are never missing.
    model_emotions = get_all_affect_names() or []
    core = state.get("core_signals", {})
    if not isinstance(core, dict):
        core = {}

    # "neutral" is not an emotion — it is the absence of emotional signal (Barrett 2017).
    # Strip it from core so it cannot accumulate via hedonic drift or legacy data.
    _NON_EMOTIONS = {"neutral"}
    for _ne in _NON_EMOTIONS:
        core.pop(_ne, None)

    # Seed from baseline first (covers all emotions regardless of model file state)
    for emo, default_val in baseline.items():
        core.setdefault(emo, default_val)
    # Also seed any additional emotions discovered from the model file
    for emo in model_emotions:
        if emo not in _NON_EMOTIONS:
            core.setdefault(emo, baseline.get(emo, 0.0))
    update_allostatic_load(state, core)

    # === Interoception — body state as generative emotional prior ===
    # Body state is applied FIRST so it acts as a prior that shapes how all subsequent
    # appraisal and trigger processing is interpreted — matching the role of insula/ACC
    # in biasing affective processing before cortical evaluation (Craig 2003; Damasio 1994).
    try:
        from cognition.body_sense import interoceptive_deltas
        _body_sense = context.get("body_sense") if context else None
        if _body_sense and isinstance(_body_sense, dict):
            _body_states = _body_sense.get("body_states") or []
            if _body_states:
                _emo_tmp = {"core_signals": core, "resource_deficit": state.get("resource_deficit", 0.0)}
                _emo_tmp = interoceptive_deltas(_body_states, _emo_tmp)
                core = _emo_tmp.get("core_signals", core)
                state["resource_deficit"] = _emo_tmp.get("resource_deficit", state.get("resource_deficit", 0.0))
    except Exception as _e:
        log_activity(f"[update_affect_state] interoception failed: {_e}")

    # Snapshot core BEFORE this cycle's modifications (velocity needs prev state)
    prev_core = capture_prev_core(state, core)
    # Decay habituation counts (spontaneous recovery for long-absent triggers)
    decay_habituation(state, now)

    # === social_deficit Tracking ===
    # get_time_since_last_active() returns SECONDS — convert to real hours
    since_active = get_time_since_last_active()
    try:
        hours_idle = float(since_active) / 3600.0
    except Exception:
        hours_idle = 0.0

    social_deficit = float(state.get("social_deficit", 0.0) or 0.0)
    if hours_idle > 2.0:
        # Grows slowly after 2 hours of no contact; hard cap at 0.55
        per_cycle_increase = 0.0003 * (hours_idle - 2.0)
        social_deficit = min(0.55, social_deficit + per_cycle_increase)
    else:
        # Decays toward 0 while user has been present in the last 2 hours
        social_deficit = max(0.0, social_deficit - 0.03)
    # Hard safety clamp: the branches above only enforce a soft 0.55 ceiling on
    # the *growth* path and a 0.0 floor on the *decay* path, so a corrupted
    # negative input feeding the growth path (min(0.55, negative + tiny)) could
    # otherwise stay negative.
    social_deficit = max(0.0, min(1.0, social_deficit))
    social_deficit = round(social_deficit, 3)
    state["social_deficit"] = social_deficit

    if social_deficit > 0.5:
        if "negative_valence" in core:
            core["negative_valence"] = min(0.40, core.get("negative_valence", baseline.get("negative_valence", 0.0)) + (social_deficit - 0.5) * 0.15)
        for opp in ("positive_valence", "expected_gain"):
            if opp in core:
                core[opp] = max(baseline.get(opp, 0.0), core[opp] - 0.03)

    if context is not None and social_deficit > 0.45:
        update_working_memory({
            "content": "⚠️ I feel lonely. It’s been a while since anyone has spoken to me.",
            "event_type": "emotion",
            "emotion": "social_deficit",
            "timestamp": now.isoformat(),
        })

    # === social_penalty Natural Decay + affiliation_signal-Analog on Social Contact ===
    # social_penalty is regulated biologically by social connection (affiliation_signal, Heinrichs et al. 2003)
    # and time (acute social_penalty fades over hours even without intervention — Tangney & Dearing 2002).
    # There is no hard ceiling. social_penalty can genuinely be overwhelming — what brings it down
    # is connection and time, not a clamp.
    #
    # Two mechanisms:
    #   1. affiliation_signal-analog: recent user interaction (hours_idle < 0.5) triggers a meaningful
    #      social_penalty reduction — social contact is the most potent social_penalty regulator humans have.
    #   2. Time decay: social_penalty drifts slowly toward its true baseline (0.0) every cycle.
    #      Rate is slow — acute social_penalty takes hours to fade, not seconds.
    if "social_penalty" in core:
        _social_penalty = float(core["social_penalty"])
        _social_penalty_true_base = 0.0

        if hours_idle < 0.5:
            # Active social contact — affiliation_signal-analog: meaningful social_penalty reduction
            # Magnitude: ~0.015 per cycle at 10-cycle/min = ~0.15 drop over ~1 min of contact
            _affiliation_signal_pull = 0.015
            _social_penalty = max(_social_penalty_true_base, _social_penalty - _affiliation_signal_pull)
        else:
            # Time-based natural decay: social_penalty slowly dissipates even without contact
            # Rate calibrated so social_penalty at 0.6 takes ~2 hours to reach 0.1 without contact
            _time_decay = 0.0004 * (1.0 + hours_idle * 0.5)
            _social_penalty = max(_social_penalty_true_base, _social_penalty - _time_decay)

        core["social_penalty"] = round(_social_penalty, 4)

    # === stability_signal-analog: behavioral inhibition and patience (Dayan & Huys 2009) ===
    # When hedonic baseline is stable (positive_valence moderate, risk_estimate low), stability_signal blunts
    # impasse_signal escalation and promotes continued effort under difficulty.
    # Low stability_signal → impulsive, reactive, easily destabilized.
    # High stability_signal → patient persistence, impasse_signal tolerance.
    # Proxy: positive_valence * 0.6 − risk_estimate * 0.4 (captures the contentment-minus-alarm balance).
    _positive_valence_lvl     = float(core.get("positive_valence",     0.10) or 0.10)
    _risk_estimate_lvl = float(core.get("risk_estimate", 0.00) or 0.00)
    _stability_signal   = max(0.0, _positive_valence_lvl * 0.6 - _risk_estimate_lvl * 0.4)
    if _stability_signal > 0.12 and "impasse_signal" in core:
        _dampen = _stability_signal * 0.018
        core["impasse_signal"] = max(
            baseline.get("impasse_signal", 0.05),
            float(core["impasse_signal"]) - _dampen
        )
    state["_stability_signal_proxy"] = round(_stability_signal, 3)

    # === gain_signal proxy — activation_level/attention gain state (Sara 2009) ===
    # NE sharpens signal-to-noise: high NE = focused attention, high-intensity items
    # dominate WM retrieval; low NE = diffuse, drowsy, poor filtering.
    # Proxy inputs: risk_estimate (fight-or-flight NE spike) + motivation (active engagement NE).
    _ne_proxy = min(1.0,
        float(core.get("risk_estimate",    0.0) or 0.0) * 0.50 +
        float(core.get("motivation", 0.5) or 0.5) * 0.40
    )
    state["_ne_proxy"] = round(_ne_proxy, 3)

    # === stress_load allostatic load — sustained stress degrades executive function ===
    # Chronic allostatic load impairs PFC working memory and motivation (McEwen 2007;
    # Arnsten 2009). Two sources feed the SAME load term (we never run two parallel taxes):
    #   1. physical stress streak  — consecutive stressed body readings (body_sense).
    #   2. affective fatigue       — a high `resource_deficit` (the felt empty tank).
    # Load = max(stress_streak_load, resource_deficit_load), so whichever is more depleting
    # drives the gentle motivation/risk pull. This closes the half of the allostatic loop the
    # streak path missed: Orrin can no longer be mathematically exhausted yet "manically
    # content" — a depleted tank now lowers the effective capacity ceiling.
    try:
        _bs            = (context or {}).get("body_sense") or {}
        _stress_streak = int(_bs.get("_stress_streak", 0) or 0)

        # (1) physical: streak-driven load (unchanged behaviour — starts after 20 cycles).
        _streak_load = min(1.0, (_stress_streak - 20) / 200.0) if _stress_streak >= 20 else 0.0

        # (2) affective: fatigue-driven load once resource_deficit crosses the fatigue line.
        # rd_load = (resource_deficit − 0.55) / 0.45, clamped to [0, 1]. Uses the live felt
        # deficit (the resource_deficit block below refreshes it; this reads the standing value).
        _rd        = float(state.get("resource_deficit", 0.0) or 0.0)
        _rd_thresh = 0.55
        _rd_load   = max(0.0, min(1.0, (_rd - _rd_thresh) / 0.45)) if _rd > _rd_thresh else 0.0

        _load = max(_streak_load, _rd_load)
        if _load > 0.0:
            if "motivation" in core:
                _floor = max(0.0, baseline.get("motivation", 0.5) * 0.5)
                core["motivation"] = max(
                    _floor,
                    float(core["motivation"]) - _load * 0.008
                )
            if "risk_estimate" in core:
                core["risk_estimate"] = min(0.75,
                    float(core.get("risk_estimate", 0.0)) + _load * 0.004
                )
            # Surface the streak source on its existing cadence …
            if _streak_load > 0.0 and (_stress_streak == 20 or _stress_streak % 50 == 0):
                update_working_memory({
                    "content": (
                        f"[allostatic_load] Sustained stress for {_stress_streak} cycles. "
                        f"Executive function and motivation under stress_load load."
                    ),
                    "event_type": "body_pattern",
                    "importance": 3,
                    "timestamp": now.isoformat(),
                })
            # … and the fatigue source once, on the upward crossing of the fatigue line.
            _rd_noted = bool(state.get("_rd_fatigue_noted", False))
            if _rd_load > 0.0 and not _rd_noted:
                update_working_memory({
                    "content": (
                        "[allostatic_load] I'm running on empty — drive is harder to "
                        f"summon (resource_deficit {_rd:.2f})."
                    ),
                    "event_type": "body_pattern",
                    "importance": 3,
                    "timestamp": now.isoformat(),
                })
                state["_rd_fatigue_noted"] = True
        # Reset the one-shot fatigue note once recovered below the line (small hysteresis).
        if _rd <= _rd_thresh - 0.05 and state.get("_rd_fatigue_noted"):
            state["_rd_fatigue_noted"] = False
    except Exception as _e:
        log_activity(f"[update_affect_state] stress_load allostatic load failed: {_e}")

    # === Trigger-Based Emotion Nudging ===
    if trigger:
        trig_key = str(trigger).lower().strip()
        update_working_memory(f"⚠️ Triggered emotion: {trig_key}")
        trigger_map = {
            "reflection_stagnation": {"negative_valence": 0.18, "rejection_signal": 0.10},
            "identity_loop": {"conflict_signal": 0.25, "threat_level": 0.18},
            "success": {"positive_valence": 0.35, "surprise": 0.20},
            "failure": {"negative_valence": 0.35, "conflict_signal": 0.20},
        }
        nudges = trigger_map.get(trig_key, {})
        for emo, boost in nudges.items():
            if emo in core:
                core[emo] = min(1.0, core[emo] + boost)
                for opp in opposites.get(emo, []):
                    if opp in core:
                        core[opp] = max(baseline.get(opp, 0.0), core[opp] - boost * 0.7)

    # === Context-driven stagnation_signal — information-theoretic (Shannon entropy of action distribution) ===
    # H(p) = -Σ p_i * log(p_i); low entropy (repetitive picks) → high stagnation_signal target
    if context is not None:
        try:
            import math as _math
            from collections import Counter as _Counter
            recent = (context or {}).get("recent_picks", []) or []
            if isinstance(recent, list) and len(recent) >= 3:
                window = recent[-16:]
                counts = _Counter(window)
                n = len(window)
                entropy = -sum((c / n) * _math.log(c / n) for c in counts.values())
                max_h = _math.log(max(len(counts), 2))
                norm_entropy = min(1.0, entropy / max_h) if max_h > 0 else 1.0
                target = max(0.0, 1.0 - norm_entropy) * 0.65
                current = float(core.get("stagnation_signal", 0.0))
                core["stagnation_signal"] = round(current + (target - current) * 0.25, 4)
        except Exception as _e:
            record_failure("update_affect_state.update_affect_state", _e)

    # Time-without-interaction gently raises stagnation_signal; hard cap at 0.60
    if hours_idle > 1.0:
        stagnation_signal_increment = 0.0002 * (hours_idle - 1.0)
        core["stagnation_signal"] = min(0.60, float(core.get("stagnation_signal", 0.0)) + stagnation_signal_increment)
    # Hard cap regardless of source
    core["stagnation_signal"] = min(0.60, float(core.get("stagnation_signal", 0.0)))

    # === Decay Emotions Over Time (single decay law → CORE_BASELINES) ===
    # Owned by HomeostasisManager so there is exactly one restoring force toward
    # one set of resting values (V3_AUDIT.md §3.2 / D3).
    apply_restoring_forces(state, core, decay_rate=decay_rate, hours_passed=hours_passed)

    # === New Triggers Based on Working Memory ===
    recent = [w for w in working[-10:] if isinstance(w, dict)]
    triggers_log = state.get("recent_triggers", [])
    if not isinstance(triggers_log, list):
        triggers_log = []
    new_triggers = []

    # Causal attribution: record which WM content caused which emotion to shift.
    # Stored in state["recent_emotion_causes"] so investigate_unexplained_emotions
    # can distinguish truly unexplained from merely unlogged spikes.
    recent_causes = state.get("recent_emotion_causes", [])
    if not isinstance(recent_causes, list):
        recent_causes = []

    # Emotion-bookkeeping entries (oscillation notes, "[emotion/cause] X rose by…",
    # affect reflections) name the signal they describe, so keyword detection here
    # re-fires that very signal every cycle — a self-reinforcing loop that pinned
    # impasse_signal/uncertainty high and oscillating (the oscillation note re-pumped
    # the oscillating signal, which kept the detector firing). appraisal.py already
    # skips these same event types; mirror that filter here.
    # Orrin's own metacog / affect-bookkeeping / self-reflection entries restate his
    # current emotional state in words ("Oscillation detected in impasse_signal",
    # "impasse_signal has been my dominant affect", "emotional reflection: …"). They
    # name the very signal they describe, so keyword-detecting them here re-fires that
    # signal every cycle — a self-reinforcing rumination loop that pinned impasse_signal
    # and uncertainty high. Skip this whole family of self-commentary so introspection
    # doesn't mechanically amplify the state it observes. Genuine stimuli (conscious-stream
    # chunks, perceptions, user input) are NOT in this set and are still appraised.
    _SKIP_EVENT_TYPES = frozenset({
        "oscillation_detected", "affect_cause", "dominant_affect",
        "affect_analysis", "unexplained_affect_reflection",
        "metacog_pattern", "affective_reflection", "shadow_dialogue",
        "incubated_insight", "self_query",
        # Decision logs ("Chose: X — {weights:{…}}") embed signal names as
        # feature-weight keys, so keyword-detecting them spuriously fires those
        # signals. A choice's affect is already accounted for via the reward/bandit
        # channel, not by re-reading the log text.
        "choice",
    })

    def _is_self_commentary(et: str) -> bool:
        return (
            et in _SKIP_EVENT_TYPES
            or "affect" in et            # affect_cause, dominant_affect, affective_reflection, …
            or "metacog" in et           # metacog_pattern, metacog_monitor, …
            or et.endswith("_reflection")
            or et.endswith("_dialogue")
        )

    # Machine-generated introspective markup. Orrin's symbolic dreams / metacog / causal
    # self-model reasoning names his own affect signals as technical tokens
    # ("… → 'uncertainty rises'", "[metacog/pattern] Cognitive rut…", "impasse_signal …").
    # This text rides inside ordinary "chunk" (conscious-stream) entries, so the event_type
    # filter above can't catch it — yet keyword-detecting it re-fires the named signal,
    # reopening the self-reinforcing loop. Genuine felt stimuli (speech, perception, plain
    # thoughts) carry none of these markers, so skip keyword appraisal when any are present.
    _INTROSPECTIVE_MARKERS = (
        "[sym_dream", "[metacog", "[emotion/cause]", "[incubation insight]",
        "counterfactual:", "oscillation detected", "dominant affect", "dominant emotion",
        "shadow question",
        # Decision logs ("🧠 Chose: X — {…'multi-factor'…weights{…}}"). The weights
        # dict lists every signal name as a key, so keyword detection spuriously fires
        # whichever signals appear there. These ride inside plain "chunk" conscious-stream
        # entries too, so match on the log signature, not the event_type.
        "🧠 chose", "multi-factor",
    )

    # Per-emotion cap on how much this keyword-trigger pass can boost any single
    # signal in one cycle. A theme-saturated or stuck working memory (e.g. a conscious
    # stream looping on the same content, or many entries about the same feeling)
    # otherwise floods one emotion with many small boosts that habituation only floors
    # (never zeroes), pinning the signal at its ceiling. The cap still lets one strong
    # fresh stimulus register; it only bounds the cumulative per-cycle flood.
    _TRIGGER_BOOST_CAP = 0.15
    _trigger_boost_used: Dict[str, float] = {}

    for thought in recent:
        if isinstance(thought, dict) and _is_self_commentary(str(thought.get("event_type") or "")):
            continue
        content = str(thought.get("content", "") or "")
        if any(m in content.lower() for m in _INTROSPECTIVE_MARKERS):
            continue
        timestamp = thought.get("timestamp") or now.isoformat()
        detection = detect_affect(content)

        if isinstance(detection, str):
            emotion = detection
            intensity = 0.2 if emotion != "neutral" else 0.0
        elif isinstance(detection, dict):
            emotion = detection.get("emotion", "neutral")
            intensity = float(detection.get("intensity", 0.0) or 0.0)
        else:
            emotion = "neutral"
            intensity = 0.0

        if intensity == 0 and emotion != "neutral":
            keywords = ["desperate", "thrilled", "furious", "terrified", "ashamed"]
            intensity = 0.3 if any(k in content.lower() for k in keywords) else 0.12

        # reflective/analytical are COGNITIVE-STYLE signals, not emotions — and his
        # own reflection/metacog output fills working memory with reflective text,
        # so keyword-detecting it here re-boosted them every cycle into a runaway
        # self-reinforcing loop (reflective pinned ~0.92, dominating the trigger
        # stream). They have personality baselines and decay toward them; don't let
        # reading his own reflective output ratchet them back up.
        _NO_KEYWORD_BOOST = {"reflective", "analytical"}
        if emotion in _NO_KEYWORD_BOOST:
            continue

        # Habituation: diminish intensity for repeated identical triggers
        if emotion in core and intensity > 0:
            intensity = intensity * get_habit_factor(emotion, content, state)
            record_habit(emotion, content, state, now)

        if emotion in core and intensity > 0:
            # Enforce the per-emotion per-cycle boost cap (anti-flood).
            _headroom = max(0.0, _TRIGGER_BOOST_CAP - _trigger_boost_used.get(emotion, 0.0))
            if _headroom <= 0.0:
                continue
            intensity = min(intensity, _headroom)
            _trigger_boost_used[emotion] = _trigger_boost_used.get(emotion, 0.0) + intensity

            prev_val = float(core[emotion])
            core[emotion] = min(1.0, core[emotion] + intensity)
            for opp in opposites.get(emotion, []):
                if opp in core:
                    core[opp] = max(baseline.get(opp, 0.0), core[opp] - intensity * 0.7)
            new_triggers.append({
                "event": content[:80],
                "emotion": emotion,
                "intensity": round(float(intensity), 3),
                "timestamp": timestamp,
            })

            # Record causal attribution when the shift is meaningful (>= 0.10)
            delta = core[emotion] - prev_val
            if delta >= 0.10:
                recent_causes.append({
                    "emotion": emotion,
                    "delta":   round(delta, 3),
                    "cause":   content[:120],
                    "ts":      timestamp,
                })
                # Surface as a working-memory note so Orrin can read the why
                try:
                    update_working_memory({
                        "content": (
                            f"[emotion/cause] {emotion.capitalize()} rose by "
                            f"{delta:.2f} because: {content[:100]}"
                        ),
                        "event_type": "affect_cause",
                        "emotion": emotion,
                        "importance": 2,
                        "priority": 2,
                        "timestamp": timestamp,
                    })
                except Exception as _e:
                    record_failure("update_affect_state.update_affect_state.2", _e)

    # === Appraisal-theory nudges (goal × event → emotion, no LLM) ===
    # Complements the keyword trigger loop with goal-relevance × congruence × agency.
    # Mood modulates appraisal sensitivity: good mood dampens negative events, bad amplifies.
    try:
        from affect.appraisal import appraise_working_memory as _appraise
        _cg   = (context or {}).get("committed_goal") or {}
        _cgs  = (context or {}).get("committed_goals") or ([_cg] if _cg else [])
        _gtitles = [g.get("title", "") for g in _cgs if isinstance(g, dict) and g.get("title")]
        _current_mood = float(state.get("mood", 0.0) or 0.0)
        if _gtitles:
            _appraisal_deltas = _appraise(working, _gtitles, state, mood=_current_mood)
            for _adj in _appraisal_deltas:
                _emo = _adj.get("emotion", "")
                _d   = float(_adj.get("delta") or 0)
                if _emo in core and abs(_d) >= 0.02:
                    if _d > 0:
                        core[_emo] = min(1.0, float(core[_emo]) + _d)
                    else:
                        core[_emo] = max(baseline.get(_emo, 0.0), float(core[_emo]) + _d)
                    # Record meaningful positive shifts as causal attributions
                    if _d >= 0.08:
                        recent_causes.append({
                            "emotion": _emo,
                            "delta":   round(_d, 3),
                            "cause":   f"[appraisal] {_adj.get('cause', '')[:80]}",
                            "ts":      now.isoformat(),
                        })
    except Exception as _e:
        record_failure("update_affect_state.update_affect_state.3", _e)

    # Novel events (triggers) relieve stagnation_signal a bit; wonder decays gently each update
    if new_triggers:
        core["stagnation_signal"] = max(0.0, float(core.get("stagnation_signal", 0.0)) - min(0.03 * len(new_triggers), 0.15))
    core["wonder"] = max(0.0, float(core.get("wonder", 0.0)) * pow(0.92, max(hours_passed, 0.01)))

    # === Sustained cross-inhibition (owned by HomeostasisManager) ===
    # When a dominant emotion is chronically elevated, its antagonists are pulled
    # toward baseline faster than their natural decay. Prevents impossible
    # co-saturations like impasse_signal=1.0 + confidence=1.0 persisting.
    apply_cross_inhibition(core)

    # === Homeostatic ceiling (applied BEFORE dup-key sync so rewards can't bypass it) ===
    # Per-emotion soft ceilings now live in homeostasis.EMO_CEILINGS (single source
    # of truth) so drive/reward PUMP sites can respect the same ceiling via
    # pump_signal() — capping pumps at 1.0 let them out-run this once-per-cycle
    # clawback and pinned the positive drives near saturation (the flatline).
    # Removal rate 0.25 (25% of excess per call) is strong enough to actually counteract
    # trigger bursts (+0.3) and reward signals — the old 6% rate was too slow.
    _EMO_CEILINGS = EMO_CEILINGS
    _DEFAULT_CEILING = DEFAULT_CEILING
    _CEILING_RATE    = CEILING_RATE
    for emo in list(core.keys()):
        try:
            ceiling = _EMO_CEILINGS.get(emo, _DEFAULT_CEILING)
            val = float(core[emo])
            if val > ceiling:
                excess    = val - ceiling
                core[emo] = max(ceiling, val - excess * _CEILING_RATE)
        except Exception as _e:
            record_failure("update_affect_state.update_affect_state.4", _e)

    # === Oscillation detection — variance of each emotion over last 12 update cycles ===
    # If any emotion has been oscillating (high variance) for 3+ consecutive calls,
    # surface a working-memory signal so Orrin can notice and respond.
    _OSC_WINDOW = 12
    _OSC_VAR_THRESHOLD = 0.035
    _OSC_CONSECUTIVE = 3
    try:
        hist = state.setdefault("emotion_history", [])
        if not isinstance(hist, list):
            hist = []
            state["emotion_history"] = hist
        hist.append({k: float(v) for k, v in core.items() if isinstance(v, (int, float))})
        if len(hist) > _OSC_WINDOW:
            state["emotion_history"] = hist[-_OSC_WINDOW:]
            hist = state["emotion_history"]
        if len(hist) >= _OSC_WINDOW:
            osc_counts = state.setdefault("emotion_osc_counts", {})
            if not isinstance(osc_counts, dict):
                osc_counts = {}
            flagged = None
            worst_var = 0.0
            for emo in core:
                vals = [s[emo] for s in hist if isinstance(s, dict) and emo in s]
                if len(vals) < _OSC_WINDOW:
                    continue
                mean_v = sum(vals) / len(vals)
                var = sum((v - mean_v) ** 2 for v in vals) / len(vals)
                if var > _OSC_VAR_THRESHOLD:
                    osc_counts[emo] = osc_counts.get(emo, 0) + 1
                    if osc_counts[emo] >= _OSC_CONSECUTIVE and var > worst_var:
                        worst_var = var
                        flagged = (emo, var, osc_counts[emo])
                else:
                    osc_counts[emo] = 0
            state["emotion_osc_counts"] = osc_counts
            if flagged is not None and context is not None:
                emo_flag, var_flag, streak = flagged
                update_working_memory({
                    "content": (
                        f"Oscillation detected in {emo_flag} (variance={var_flag:.3f}, "
                        f"{streak} cycles): my {emo_flag} state has been unstable."
                    ),
                    "event_type": "oscillation_detected",
                    "emotion": emo_flag,
                    "importance": 2,
                    "timestamp": now.isoformat(),
                })
                osc_counts[emo_flag] = 0
    except Exception as _e:
        record_failure("update_affect_state.update_affect_state.5", _e)

    # === Flatline detection — LOW variance at HIGH value (the osc detector's blind spot) ===
    # The variance detector above fires only on CHAOS (high variance). Its mirror
    # failure is a positive drive pinned near its ceiling with ~zero variance —
    # "manically content" while the loop is closed. Reward pumps that out-run decay
    # produce exactly this (the empirically observed motivation≈0.96, var≈0 pin).
    # When the positive-drive vector sits high and flat for several cycles, raise
    # stagnation_signal so the EXISTING novelty machinery treats the sameness as
    # boredom: select_function routes toward seek_novelty/look_outward and
    # consciousness_trigger can fire. We deliberately do NOT crush ceilings — that
    # only flattens arousal toward a low-energy state; boredom→seek-novelty is the
    # felt wake-up, and it closes its own loop (acting diversifies picks → entropy
    # rises → stagnation_signal ebbs).
    _FLAT_WINDOW    = 8        # how many recent cycles must be flat-high
    _FLAT_VAR_MAX   = 0.0008   # "flat": variance below this (std < ~0.028)
    _FLAT_HIGH_MEAN = 0.78     # "high": mean drive at/above this (below the 0.82–0.85 ceilings)
    _FLAT_DRIVES = ("motivation", "confidence", "positive_valence", "exploration_drive")
    try:
        hist = state.get("emotion_history", [])
        if isinstance(hist, list) and len(hist) >= _FLAT_WINDOW:
            recent_hist = hist[-_FLAT_WINDOW:]
            flat_high = []
            for emo in _FLAT_DRIVES:
                vals = [s[emo] for s in recent_hist if isinstance(s, dict) and emo in s]
                if len(vals) < _FLAT_WINDOW:
                    continue
                m = sum(vals) / len(vals)
                v = sum((x - m) ** 2 for x in vals) / len(vals)
                if v <= _FLAT_VAR_MAX and m >= _FLAT_HIGH_MEAN:
                    flat_high.append(emo)
            # A single steady drive is healthy; a whole pinned positive vector is the
            # pathology — require most of them flat-high together.
            if len(flat_high) >= 3:
                _flat_streak = int(state.get("_flatline_streak", 0) or 0) + 1
                state["_flatline_streak"] = _flat_streak
                cur_stag = float(core.get("stagnation_signal", 0.0) or 0.0)
                core["stagnation_signal"] = min(0.60, cur_stag + 0.20)
                if context is not None and (_flat_streak == 1 or _flat_streak % 5 == 0):
                    update_working_memory({
                        "content": (
                            "I've been running hot and flat — "
                            f"{', '.join(flat_high)} pinned high with almost no movement "
                            f"for {_FLAT_WINDOW}+ cycles. This sameness is its own signal: "
                            "I should seek novelty or change what I'm doing."
                        ),
                        "event_type": "affect_stagnation",
                        "emotion": "stagnation_signal",
                        "importance": 3,
                        "timestamp": now.isoformat(),
                    })
            else:
                state["_flatline_streak"] = 0
    except Exception as _e:
        record_failure("update_affect_state.update_affect_state.flatline", _e)

    # === Drain buffered emotion changes BEFORE velocity so buffered deltas are subject
    # to the same velocity constraints as direct emotion writes. Previously this ran
    # after velocity, which let buffered changes bypass the smoothing gate entirely.
    drain_affect_queue(state, core)

    # === Velocity dynamics (drag + refractory) — applied after drain, before clamp ===
    apply_velocity_dynamics(core, prev_core, state)

    # Clamp all emotions to [0, 1] (hard safety net only — real ceiling applied below).
    for k in list(core.keys()):
        try:
            core[k] = max(0.0, min(1.0, float(core[k])))
        except Exception:
            core[k] = baseline.get(k, 0.0)

    # === Update Stability (after clamping so deviations are accurate) ===
    # Negative emotions above baseline destabilize; positive emotions above baseline stabilize.
    # Treating positive_valence/exploration_drive as instability was backwards.
    _neg_emos = {"threat_level", "impasse_signal", "conflict_signal", "negative_valence", "risk_estimate", "uncertainty",
                 "social_penalty", "rejection_signal", "jealousy", "melancholy", "social_deficit", "dread", "loss_signal"}
    _pos_emos = {"positive_valence", "expected_gain", "exploration_drive", "wonder", "motivation", "confidence", "compassion", "excitement"}

    neg_deviations = [
        max(0.0, float(core.get(e, 0)) - baseline.get(e, 0.0))
        for e in _neg_emos if e in core
    ]
    pos_deviations = [
        max(0.0, float(core.get(e, 0)) - baseline.get(e, 0.0))
        for e in _pos_emos if e in core
    ]
    avg_neg = mean(neg_deviations) if neg_deviations else 0.0
    avg_pos = mean(pos_deviations) if pos_deviations else 0.0
    new_stability = max(0.0, min(1.0, 1.0 - avg_neg * 2.0 + avg_pos * 0.25))

    # === Deliver reward & adjust mode if needed ===
    if context is not None:
        deliver_affect_based_rewards(context, core, new_stability)
        recommended = recommend_mode_from_affect_state()
        current_mode = get_current_mode()
        if recommended != current_mode:
            set_current_mode(
                mode=recommended,
                reason="Dominant emotional state prompted mode shift: {}".format(recommended)
            )

    # === Sync top-level duplicates INTO core so rewards written to state propagate ===
    # Reward signals write to state["motivation"] etc. (top-level). Core is the canonical
    # store for decay, so we merge them here — capped at per-emotion ceilings before merging
    # so that a reward writing state["motivation"]=1.0 can't bypass the emotional ceiling.
    _dup_keys = {"motivation", "confidence", "exploration_drive", "social_deficit", "stagnation_signal"}
    # Per-emotion soft ceilings for dup-key sync (hard ceiling applied afterwards)
    _dup_soft_ceil = {"motivation": 0.80, "confidence": 0.80, "exploration_drive": 0.85,
                      "social_deficit": 1.0,  "stagnation_signal": 1.0}
    for _dk in _dup_keys:
        _top = state.get(_dk)
        if isinstance(_top, (int, float)) and _dk in core:
            _top_capped = min(float(_top), _dup_soft_ceil.get(_dk, 0.85))
            core[_dk] = max(float(core.get(_dk) or 0), _top_capped)

    # Re-apply ceiling after dup-key sync so reward writes can't bypass it.
    for emo in list(core.keys()):
        try:
            ceiling = _EMO_CEILINGS.get(emo, _DEFAULT_CEILING)
            val = float(core[emo])
            if val > ceiling:
                core[emo] = max(ceiling, val - (val - ceiling) * _CEILING_RATE)
        except Exception as _e:
            record_failure("update_affect_state.update_affect_state.6", _e)

    # === Decay flat reward fields at a per-call rate (not hours-based) ===
    # hours_passed is ~0.005 at 20s cycles — hours-based decay (apply_restoring_forces)
    # is effectively zero, so signals only ever ratcheted UP from reward writes and
    # never came back down (drives pinned at ~0.93, distress frozen). Use a fixed
    # per-call rate so they actually return to baseline — phasic-on-tonic: a spike
    # rides on top of a resting value and decays back to it (opponent-process,
    # Solomon & Corbit 1974; allostasis).
    #
    # CRITICAL: the canonical store is core_signals. The old code decayed only the
    # top-level state[k], then the re-sync loop below overwrote it with the
    # *undecayed* core[k] — discarding the decay entirely. So we now pull the
    # canonical core[_k] toward baseline as well; the re-sync then propagates the
    # decayed value to the top level.
    # === General homeostatic restoring force (per-call) for the WHOLE core vector ===
    # apply_restoring_forces decays toward CORE_BASELINES, but it's HOURS-based — at
    # ~30s cycles that's ≈0 pull per cycle. Previously only a hand-picked subset of
    # signals got a real per-call decay, so every OTHER signal (reflective, wonder,
    # positive_valence, contentment, unease, vitality, social_deficit, …) had no
    # restoring force at all: appraisal triggers pushed them up and nothing pulled
    # them back, so the whole affect vector pinned near the ceiling and just orbited
    # there (contentment AND unease AND impasse all maxed at once — incoherent).
    # Apply a per-call pull toward each signal's setpoint for EVERY core signal so
    # feelings are phasic: a trigger makes a peak that then subsides (opponent-
    # process, Solomon & Corbit 1974; allostasis), instead of a stuck maxed state.
    # Negatives clear a touch faster so distress doesn't linger between spikes.
    try:
        from affect.setpoints import setpoint as _setpoint
        _NEG_SIGNALS = {
            "impasse_signal", "conflict_signal", "threat_level", "negative_valence",
            "risk_estimate", "social_deficit", "social_penalty", "rejection_signal",
            "unease", "dread", "melancholy", "jealousy", "loss_signal", "stagnation_signal",
        }
        # Reward-pumped drives need a stronger restoring force: their pumps fire
        # every cycle (+0.04–0.08) while this pull only runs when
        # update_affect_state is selected, so at 2 %/call exploration_drive
        # saturated in minutes and took hours to droop back (FINDINGS 2026-06-12 §2).
        _PUMPED_DRIVES = {"exploration_drive", "motivation", "connection"}

        def _decay_rate(k: str) -> float:
            if k in _PUMPED_DRIVES:
                return 0.05
            return 0.025 if k in _NEG_SIGNALS else 0.02

        for _k in list(core.keys()):
            _cv = core.get(_k)
            if not isinstance(_cv, (int, float)):
                continue
            _cv = float(_cv)
            _base = _setpoint(_k)
            core[_k] = max(0.0, min(1.0, _cv + (_base - _cv) * _decay_rate(_k)))
        # Mirror the decay onto the top-level reward fields that also live there
        # (those not covered by the dup-key re-sync below).
        for _k in ("motivation", "exploration_drive", "confidence", "uncertainty", "connection"):
            _val = state.get(_k)
            if isinstance(_val, (int, float)):
                _base = _setpoint(_k)
                state[_k] = max(0.0, min(1.0, float(_val) + (_base - float(_val)) * _decay_rate(_k)))
    except Exception as _e:
        record_failure("update_affect_state.update_affect_state.7", _e)

    # Sync canonical values back to top-level so readers of state[k] see current values
    for _dk in _dup_keys:
        if _dk in core:
            state[_dk] = core[_dk]

    # === resource_deficit: accumulates per call, decays toward an ALLOSTATIC target ===
    # Phase 2 (C3, docs/proactive_resource_plan.md): the recovery target is no longer
    # a fixed 0.15 — it is a context-adaptive τ (recover deeper when idle; tolerate
    # more deficit during a live/critical exchange) with allostatic-load forced
    # recovery. Sterling (2012) allostasis = predictive regulation; McEwen & Wingfield
    # (2003) allostatic load. Falls back to 0.15 when disabled/absent.
    # Decay rate 0.025; if resource_deficit is very high (>0.75), decay is faster.
    try:
        from cognition.interoception import allostatic_setpoint as _allo_tau
        _resource_deficit_baseline = _allo_tau(context, state)
    except Exception:
        _resource_deficit_baseline = 0.15
    resource_deficit = float(state.get("resource_deficit", _resource_deficit_baseline) or _resource_deficit_baseline)
    resource_deficit = min(1.0, resource_deficit + 0.002)   # gentle accumulation
    _fat_pull = _resource_deficit_baseline - resource_deficit
    _fat_decay_rate = 0.025 if resource_deficit < 0.75 else 0.06  # accelerated recovery from exhaustion
    resource_deficit = max(0.0, min(1.0, resource_deficit + _fat_pull * _fat_decay_rate))
    state["resource_deficit"] = round(resource_deficit, 4)

    # === Hedonic adaptation — sustained states lose their felt charge ===
    update_hedonic_baselines(state, core)

    # === Valence / activation_level / Mood (circumplex + slow background drift) ===
    _valence, _activation_level, _quad = compute_valence_activation_level(core)
    _mood = update_mood(state, _valence)
    state["valence"]         = _valence
    state["activation_level"]         = _activation_level
    state["affect_quadrant"] = _quad
    # mood already written into state by update_mood

    # === Net velocity budget (D8) — single "max emotional velocity" cap ===
    # After decay + buffer drain + triggers + appraisal + reward merges have all
    # mutated core this cycle, clamp the TOTAL L1 movement of the core vector from
    # its cycle-start snapshot (prev_core). One chaotic cycle cannot lurch the
    # whole affect vector regardless of how many forces fired. Owned by
    # HomeostasisManager so the cap lives in one place.
    _moved = enforce_velocity_budget(core, prev_core)
    state["_affect_velocity_l1"] = round(_moved, 4)

    # === Guaranteed chronic-distress drain (post-clamp) ===
    # The velocity budget scales ALL per-cycle deltas down when many forces fire at
    # once — which also throttled the negative-signal decay, leaving impasse_signal
    # frozen high (~0.81) with no active trigger. Apply a small, unclamped pull of
    # the chronic negatives toward their setpoints AFTER the budget so distress can
    # always bleed off between acute spikes.
    try:
        from affect.setpoints import setpoint as _sp_drain
        for _nk in ("impasse_signal", "conflict_signal", "threat_level",
                    "negative_valence", "risk_estimate", "uncertainty"):
            if _nk in core and isinstance(core.get(_nk), (int, float)):
                _v = float(core[_nk])
                core[_nk] = max(0.0, min(1.0, _v + (_sp_drain(_nk) - _v) * 0.02))
    except Exception as _e:
        record_failure("update_affect_state.update_affect_state.8", _e)

    # === Save State ===
    state["core_signals"] = core
    state["recent_triggers"] = (triggers_log + new_triggers)[-25:]
    state["recent_emotion_causes"] = recent_causes[-20:]  # capped; newest first via append
    state["social_deficit"] = social_deficit
    # affect_stability is mostly DERIVED from core deviations, but the arbiter
    # may also apply direct scalar deltas to it (regulation side-effects route
    # through _SCALAR_TARGETS — RUN_ISSUES_2026-06-10 §2). A hard overwrite
    # discarded any applied delta within one cycle; blend toward the derived
    # value instead, so a regulation boost registers and then converges back.
    try:
        _prev_stab = float(state.get("affect_stability"))
    except (TypeError, ValueError):
        _prev_stab = new_stability
    state["affect_stability"] = round(_prev_stab + (new_stability - _prev_stab) * 0.5, 4)
    # Display homeostasis ("is he settled?") — computed by the single authority in
    # homeostasis.py and stored on the canonical state so the chart, the REST
    # panels and the brain itself all read one number (was previously invented in
    # the telemetry helper; see SPLIT_CONSCIOUSNESS_TELEMETRY_AUDIT §F2).
    try:
        state["homeostasis"] = round(homeostasis_index(core), 4)
    except Exception:
        pass
    state["last_updated"] = now.isoformat()

    save_json(AFFECT_STATE_FILE, state)
    if context is not None:
        context["affect_state"] = state  # keep context in sync with disk
    log_activity("🧠 Affect state updated.")
