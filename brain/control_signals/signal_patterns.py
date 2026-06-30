# brain/control_signals/affect_patterns.py
#
# Per-cycle affect pattern phases extracted from update_signal_state
# (CODEBASE_CLEANUP_PLAN 4.5C) to bring that module under the 600-line soft
# limit. Two cohesive phases that operate on the same per-cycle (state, core)
# scope as the parent, lifted verbatim:
#
#   apply_wm_triggers_and_appraisal — keyword/affect triggers from working memory
#       plus appraisal-theory nudges (goal × event), with self-commentary filtering,
#       per-emotion boost caps, habituation, and causal attribution.
#   detect_oscillation_and_flatline — variance-based oscillation detection and its
#       mirror, flat-high "running hot and flat" stagnation detection.
#
# update_working_memory is passed in (the parent imports it lazily to dodge a
# circular import) so the call binding is unchanged.
from __future__ import annotations
from brain.cognition.global_workspace import bound_goal

from typing import Dict

from brain.control_signals.signals import detect_signal
from brain.control_signals.signal_dynamics import get_habit_factor, record_habit
from brain.control_signals.homeostasis import pump_signal
from brain.utils.failure_counter import record_failure


def apply_wm_triggers_and_appraisal(
    state, core, working, context, opposites, baseline, now, hours_passed,
    update_working_memory,
):
    """Apply WM keyword triggers + appraisal nudges to core.

    Returns (new_triggers, recent_causes, triggers_log) for the caller to persist.
    """
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
        detection = detect_signal(content)

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
            # (T0.2) Respect the homeostatic ceiling on the boost so appraisal
            # triggers can't pump a drive above its EMO_CEILINGS value and pin it
            # there (the over-cap leak). pump_signal caps positive boosts at the
            # per-signal ceiling; the once-per-cycle clawback owns legacy overshoot.
            pump_signal(core, emotion, intensity)
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
                # Surface as a working-memory note so Orrin can read the why — in
                # felt language ("a sense of being stuck grew because…"), not the raw
                # signal key + precise delta (felt_lexicon membrane). Raw key kept in
                # the structured `emotion` field for internal routing only.
                try:
                    from brain.utils.felt_lexicon import felt_label as _felt
                    update_working_memory({
                        "content": (
                            f"[emotion/cause] A sense of {_felt(str(emotion))} grew "
                            f"because: {content[:100]}"
                        ),
                        "event_type": "affect_cause",
                        "emotion": emotion,
                        "importance": 2,
                        "priority": 2,
                        "timestamp": timestamp,
                    })
                except Exception as _e:
                    record_failure("update_signal_state.update_signal_state.2", _e)

    # === Appraisal-theory nudges (goal × event → emotion, no LLM) ===
    # Complements the keyword trigger loop with goal-relevance × congruence × agency.
    # Mood modulates appraisal sensitivity: good mood dampens negative events, bad amplifies.
    try:
        from brain.control_signals.appraisal import appraise_working_memory as _appraise
        _cg   = bound_goal((context or {})) or {}
        _cgs  = (context or {}).get("committed_goals") or ([_cg] if _cg else [])
        _gtitles = [g.get("title", "") for g in _cgs if isinstance(g, dict) and g.get("title")]
        _current_mood = float(state.get("smoothed_state", 0.0) or 0.0)  # was "mood" key
        if _gtitles:
            # Persist the habituation recency map on affect_state so a recurring
            # thought stops pumping its emotion every cycle (RUN diag 2026-06-29).
            _hab_map = state.get("_appraisal_habituation")
            if not isinstance(_hab_map, dict):
                _hab_map = {}
                state["_appraisal_habituation"] = _hab_map
            _appraisal_deltas = _appraise(working, _gtitles, state, mood=_current_mood,
                                          habituation=_hab_map)
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
        record_failure("update_signal_state.update_signal_state.3", _e)

    # Novel events (triggers) relieve stagnation_signal a bit; wonder decays gently each update
    if new_triggers:
        core["stagnation_signal"] = max(0.0, float(core.get("stagnation_signal", 0.0)) - min(0.03 * len(new_triggers), 0.15))
    core["novelty_signal"] = max(0.0, float(core.get("novelty_signal", 0.0)) * pow(0.92, max(hours_passed, 0.01)))
    return new_triggers, recent_causes, triggers_log


def detect_oscillation_and_flatline(state, core, context, now, update_working_memory):
    """Detect emotion oscillation (high variance) and flat-high stagnation.

    Mutates state/core in place and surfaces working-memory notes; returns None.
    """
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
        record_failure("update_signal_state.update_signal_state.5", _e)

    # === Flatline detection — LOW variance at HIGH value (the osc detector's blind spot) ===
    # The variance detector above fires only on CHAOS (high variance). Its mirror
    # failure is a positive drive pinned near its ceiling with ~zero variance —
    # "manically content" while the loop is closed. Reward pumps that out-run decay
    # produce exactly this (the empirically observed motivation≈0.96, var≈0 pin).
    # When the positive-drive vector sits high and flat for several cycles, raise
    # stagnation_signal so the EXISTING novelty machinery treats the sameness as
    # boredom: select_function routes toward seek_novelty/look_outward and
    # deliberation_gate can fire. We deliberately do NOT crush ceilings — that
    # only flattens arousal toward a low-energy state; boredom→seek-novelty is the
    # felt wake-up, and it closes its own loop (acting diversifies picks → entropy
    # rises → stagnation_signal ebbs).
    _FLAT_WINDOW    = 8        # how many recent cycles must be flat-high
    _FLAT_VAR_MAX   = 0.0008   # "flat": variance below this (std < ~0.028)
    _FLAT_HIGH_MEAN = 0.78     # "high": mean drive at/above this (below the 0.82–0.85 ceilings)
    _FLAT_DRIVES = ("motivation", "confidence", "reward_positive", "exploration_drive")
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
                    from brain.utils.felt_lexicon import felt_label as _felt
                    _flat_felt = ", ".join(dict.fromkeys(_felt(e) for e in flat_high))
                    update_working_memory({
                        "content": (
                            "I've been running hot and flat — "
                            f"{_flat_felt} all pinned high with almost no movement "
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
        record_failure("update_signal_state.update_signal_state.flatline", _e)
