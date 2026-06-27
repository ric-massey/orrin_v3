from brain.core.runtime_log import get_logger
from datetime import datetime, timezone, timedelta
from typing import Any, Tuple
from brain.utils.load_utils import load_json
from brain.utils.log import log_activity
from brain.utils.knowledge_utils import recall_relevant_knowledge
from brain.think.think_utils.user_input import handle_user_input
from brain.control_signals.reward_signals.reward_signals import release_reward_signal
from brain.paths import AFFECT_MODEL_FILE, ATTENTION_HISTORY
from brain.utils.json_utils import save_json
from brain.utils.signal_utils import gather_signals
from brain.utils.failure_counter import record_failure
_log = get_logger(__name__)


def _as_strings(items):
    """Coerce recall results into a list of lowercase strings for containment checks."""
    out = []
    for it in items or []:
        if isinstance(it, str):
            out.append(it.lower())
        elif isinstance(it, dict):
            # prefer 'content' if present, else stringify
            s = str(it.get("content", it))
            if s:
                out.append(s.lower())
        else:
            out.append(str(it).lower())
    return out


def process_inputs(context: Any, raw_signals: Any = None) -> Tuple[Any, Any]:
    """
    Orrin's signal_router: biologically inspired signal prioritization based on emotion,
    novelty, memory relevance, and dynamic goal context.
    Always pulls user input and injects as signals, so user input is never missed.
    """
    cycle_count = context.get("cycle_count", {})
    if not isinstance(cycle_count, dict) or "count" not in cycle_count:
        cycle_count = {"count": 0}

    # Pull user input → signals
    signals, context = handle_user_input(
        context,
        cycle_count,
        context.get("long_memory", []),
        context.get("working_memory", []),
        context.get("relationships", {}),
        context.get("speaker", None),
    )

    # Also gather subsystem signals
    try:
        signals.extend(gather_signals(context) or [])
    except Exception as _e:
        # don't let a subsystem failure break input processing
        record_failure("signal_router.process_inputs", _e)

    # Merge new signals into any already-loaded embodiment/peer signals — do NOT overwrite.
    # ORRIN_loop populates context["raw_signals"] with embodiment, drive, and peer signals
    # before calling process_inputs(); overwriting here silently discards all of them.
    context.setdefault("raw_signals", []).extend(signals)

    if raw_signals is None:
        raw_signals = context.get("raw_signals", [])

    affect_state = context.get("affect_state", {}) or {}
    self_model = context.get("self_model", {}) or {}
    mode = (context.get("mode", {}) or {}).get("mode", "neutral")

    core_signals = affect_state.get("core_signals", {}) or {}
    _numeric_emo = {k: v for k, v in core_signals.items() if isinstance(v, (int, float))}
    dominant_signal = max(_numeric_emo, key=_numeric_emo.get) if _numeric_emo else "neutral"

    # === Load all known affect tags dynamically ===
    emotion_model = load_json(AFFECT_MODEL_FILE, default_type=dict)
    known_emotions = set(emotion_model.keys()) if isinstance(emotion_model, dict) else set()

    def emo_boost(tag: str) -> float:
        return round(float(core_signals.get(tag) or 0.0) * 0.3, 3)

    # === Memory and Directive Priming ===
    directive = self_model.get("core_directive", {}) or {}
    directive_stmt = directive.get("statement", "") or ""
    try:
        focus_related = recall_relevant_knowledge(
            directive_stmt,
            long_memory=context.get("long_memory", []),
            working_memory=context.get("working_memory", []),
            max_items=8,
        )
    except Exception:
        focus_related = []
    focus_texts = _as_strings(focus_related)

    goal_words = [w.lower() for w in directive.get("motivations", []) if isinstance(w, str)]

    # === Attention history: novelty context + source reliability scores ===
    recent_signals = load_json(ATTENTION_HISTORY, default_type=list)
    if not isinstance(recent_signals, list):
        recent_signals = []
    recent_contents = [
        (r.get("content") or "").lower()
        for r in recent_signals[-20:]
        if isinstance(r, dict)
    ]

    # Build per-source average priority from last 100 records — sources that
    # historically route high-value signals get a small credibility bonus.
    _src_scores: dict = {}
    _src_counts: dict = {}
    for _r in recent_signals[-100:]:
        if not isinstance(_r, dict):
            continue
        _src = str(_r.get("signal_source") or "unknown")
        _sc = float(_r.get("priority_score") or 0.0)
        _src_scores[_src] = _src_scores.get(_src, 0.0) + _sc
        _src_counts[_src] = _src_counts.get(_src, 0) + 1
    _src_avg: dict = {
        s: _src_scores[s] / _src_counts[s]
        for s in _src_scores
        if _src_counts[s] >= 3  # need at least 3 samples to trust the average
    }

    # Dominant affect from the last 20 attention records — if a particular
    # affect signal has been steering attention, mildly amplify signals tagged with it.
    _emo_freq: dict = {}
    for _r in recent_signals[-20:]:
        if not isinstance(_r, dict):
            continue
        _de = str(_r.get("dominant_affect") or "")
        if _de:
            _emo_freq[_de] = _emo_freq.get(_de, 0) + 1
    _sustained_emotion = max(_emo_freq, key=_emo_freq.get) if _emo_freq else ""

    # === Attentional momentum: signals that held attention last cycle get a persistence bonus ===
    _prev_top_content: set = context.get("_prev_top_signal_contents") or set()

    prioritized = []

    # --- Emergency interrupt support ---
    emergency_action = None
    MAX_EMERGENCY_AGE = timedelta(minutes=5)  # Only treat emergencies newer than this

    for signal in raw_signals or []:
        if not isinstance(signal, dict):
            continue

        try:
            base = float(signal.get("signal_strength", 0.5) or 0.5)
        except (TypeError, ValueError):
            base = 0.5
        tags = signal.get("tags", []) or []
        if not isinstance(tags, list):
            tags = [str(tags)]
        content = str(signal.get("content") or "").lower()
        source = str(signal.get("source") or "unknown")

        # === Emergency/fire-alarm logic (never triggers on user input) ===
        if (
            any(t in {"error", "crash"} for t in tags)
            and "user_input" not in tags
            and any(k in content for k in ("critical", "crash", "failure", "emergency"))
        ):
            # Only if the signal is recent
            sig_time_str = signal.get("timestamp")
            is_recent = False
            if sig_time_str:
                try:
                    sig_time = datetime.fromisoformat(sig_time_str.replace("Z", "+00:00"))
                    is_recent = (datetime.now(timezone.utc) - sig_time) < MAX_EMERGENCY_AGE
                except Exception as _e:
                    record_failure("signal_router.process_inputs.2", _e)
            if is_recent:
                emergency_action = {
                    "action": "emergency_shutdown",
                    "reason": f"Fire alarm from signal_router: {content[:100]}",
                    "source_signal": signal,
                }
                # Reward for emergency detection
                try:
                    release_reward_signal(
                        context,
                        signal_type="reward_signal",
                        actual_reward=0.7,
                        expected_reward=0.4,
                        effort=0.3,
                        mode="phasic",
                        source="emergency_signal_detected",
                    )
                except Exception as _e:
                    record_failure("signal_router.process_inputs.3", _e)

        # === Source credibility boost (from attention history) ===
        _src_mean = _src_avg.get(source, 0.0)
        if _src_mean > 0.6:
            base += 0.08  # this source historically routes high-value signals
        elif _src_mean < 0.3 and source not in ("user_input", "thread_of_attention"):
            base -= 0.05  # this source has been consistently low-value

        # === Sustained-affect amplifier ===
        if _sustained_emotion and _sustained_emotion in tags:
            base += 0.05  # attention has been sustained on this affect — keep momentum

        # === Affect-Weighted Tag Adjustments (dynamic) ===
        for tag in tags:
            if tag in known_emotions:
                base += emo_boost(tag)

        # === Memory relevance (use strings distilled from recall results) ===
        if any(ft and ft in content for ft in focus_texts):
            base += 0.15

        # === Goal and mode relevance ===
        if any(gw and gw in content for gw in goal_words):
            base += 0.15
        try:
            from brain.cognition.goal_lens import relevance as _goal_relevance
            _lens_rel = _goal_relevance(context.get("goal_lens"), f"{content} {' '.join(tags)}")
            # Bounded: enough to reorder close candidates, never enough to beat
            # a high-salience user or emergency signal by itself.
            base += 0.22 * _lens_rel
            signal["goal_lens_relevance"] = round(_lens_rel, 3)
        except (ImportError, TypeError, ValueError, AttributeError):  # best-effort goal-lens reweight
            pass
        if mode and mode in content:
            base += 0.1

        # === Content-based Novelty Decay (approximate) ===
        # A signal is non-novel if the current content is a substring of something seen recently
        # (i.e., this signal is contained in a past signal — same topic, shorter form).
        similar_contents = [c for c in recent_contents if c and content in c]
        novelty_score = max(0.0, 1.0 - (len(similar_contents) / max(1, len(recent_contents))))
        base += novelty_score * 0.2
        if novelty_score < 0.3:
            base -= 0.15

        # === Attentional momentum: held-attention signals stay easier to re-attend ===
        if content[:80] in _prev_top_content:
            base += 0.08

        # === Mild boost for stagnation_signal/errors ===
        if any(t in {"stagnation_signal", "error"} for t in tags):
            base += 0.05

        # === Final adjustments and clamping ===
        base = round(min(max(base, 0.0), 1.0), 3)
        signal["priority_score"] = base

        # routing target
        signal_tags = set(tags)
        if "user_input" in signal_tags:
            rt = "prefrontal_cortex"
        elif "sound" in signal_tags:
            rt = "auditory_cortex"
        elif "image" in signal_tags:
            rt = "visual_cortex"
        elif "emotion" in signal_tags:
            rt = "emotion_cortex"
        else:
            rt = "general"
        signal["routing_target"] = rt

        prioritized.append(signal)

    # === If fire alarm triggered, set in context and persist to long_memory ===
    if emergency_action:
        context["emergency_action"] = emergency_action
        try:
            from brain.cog_memory.long_memory import update_long_memory as _ulm_emerg
            _ulm_emerg(
                f"[emergency] Shutdown triggered by: {emergency_action.get('reason', 'unknown')[:200]}",
                emotion="threat_level",
                event_type="emergency_shutdown",
                importance=5,
                context=context,
            )
        except Exception as _e:
            record_failure("signal_router.process_inputs.4", _e)

    # === Sort and slice ===
    prioritized.sort(key=lambda s: s.get("priority_score", 0.0), reverse=True)

    # Deduplicate by content so two subsystems emitting identical content in the same
    # cycle don't both pass through (which would double their effective strength).
    _seen_content: set = set()
    _deduped = []
    for _s in prioritized:
        _key = str(_s.get("content", ""))[:120]
        if _key not in _seen_content:
            _seen_content.add(_key)
            _deduped.append(_s)
    prioritized = _deduped

    # === Apply 3-slot attention cap with affective hijacking ===
    try:
        from brain.cognition.attention import apply_attention_filter as _aaf
        top_signals = _aaf(prioritized, context)
    except Exception:
        top_signals = prioritized[:5]

    # === Attention mode logic ===
    if not raw_signals:
        attention_state = "drowsy"
    elif any("user_input" in (s.get("tags") or []) for s in top_signals):
        attention_state = "alert"
    elif any(s.get("priority_score", 0.0) > 0.6 for s in top_signals):
        attention_state = "engaged"
    elif any("internal" in (s.get("tags") or []) for s in top_signals):
        attention_state = "wandering"
    else:
        attention_state = "neutral"

    if not top_signals:
        log_activity("[signal_router] No high-priority signals selected.")
        for s in prioritized[:5]:
            log_activity(f"  - Rejected: {(s.get('content') or '')[:80]} | Score: {s.get('priority_score', 0)}")

    _attn_note = ""
    if context.get("attention_constrained"):
        _hb = context.get("_hijacked_by", {})
        _attn_note = f" | hijacked by {_hb.get('emotion','?')} ({_hb.get('intensity',0):.2f}), {context.get('attention_remaining',3)} slot(s) free"
    log_activity(f"[signal_router] Routed {len(top_signals)}/3 signals | Attention mode: {attention_state}{_attn_note}")

    # === Persist attention history (cap to last 500) ===
    history = load_json(ATTENTION_HISTORY, default_type=list)
    if not isinstance(history, list):
        history = []

    _hijacked_by = context.get("_hijacked_by")
    # Persist only the strongest few core signals, rounded — the full
    # core_signals snapshot was ~800 B per record × 3 records per cycle, making
    # attention_history.json ~750 KB of mostly near-zero floats rewritten every
    # cycle (part of the pulse_too_slow I/O load).
    _emo_top = {}
    if isinstance(core_signals, dict):
        _emo_top = {
            k: round(float(v), 3)
            for k, v in sorted(core_signals.items(),
                               key=lambda kv: -abs(float(kv[1]) if isinstance(kv[1], (int, float)) else 0.0))[:5]
            if isinstance(v, (int, float))
        }
    new_records = []
    for s in top_signals:
        new_records.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "signal_source": s.get("source", "unknown"),
            "content": s.get("content", ""),
            "tags": s.get("tags", []),
            "priority_score": s.get("priority_score", 0.0),
            "attention_mode": attention_state,
            "dominant_affect": dominant_signal,
            "emotional_context": _emo_top,
            "routing_target": s.get("routing_target", "general"),
            "attention_slots": context.get("attention_slots", 3),
            "attention_remaining": context.get("attention_remaining", 3),
            "hijacked_by": _hijacked_by,
        })

    history.extend(new_records)
    if len(history) > 500:
        history = history[-500:]
    # Migrate-in-place: shrink pre-existing records that carry the full
    # core_signals snapshot, so the file slims now rather than 500 cycles on.
    for _rec in history:
        _ec = _rec.get("emotional_context") if isinstance(_rec, dict) else None
        if isinstance(_ec, dict) and len(_ec) > 6:
            _rec["emotional_context"] = {
                k: round(float(v), 3)
                for k, v in sorted(_ec.items(),
                                   key=lambda kv: -abs(float(kv[1]) if isinstance(kv[1], (int, float)) else 0.0))[:5]
                if isinstance(v, (int, float))
            }
    save_json(ATTENTION_HISTORY, history)

    # === Inject back into context ===
    context["top_signals"] = top_signals
    context["attention_mode"] = attention_state
    # Carry top-signal content keys into next cycle for attentional momentum
    context["_prev_top_signal_contents"] = {str(s.get("content", ""))[:80] for s in top_signals}

    # Record active signal sources so finalize_cycle can credit them via
    # attention value learning (reward-driven routing-weight plasticity).
    context["_active_signal_sources"] = list({
        str(s.get("source") or "unknown") for s in top_signals
    })
    if context.get("goal_lens"):
        telemetry = context.setdefault("_goal_lens_telemetry", {})
        rels = [float(s.get("goal_lens_relevance", 0.0) or 0.0) for s in top_signals]
        telemetry["top_signal_relevance"] = round(max(rels, default=0.0), 3)
        telemetry["goal_relevant_top_signals"] = sum(1 for rel in rels if rel >= 0.15)

    # Apply learned attention value weights: sources that historically
    # preceded high reward get a credibility bonus here.
    try:
        from brain.think.attention_weights import get_source_weight as _gsw
        for _s in top_signals:
            _src = str(_s.get("source") or "unknown")
            _learned_w = _gsw(_src)
            # Blend learned weight with current priority: 20% learned, 80% live score
            _s["priority_score"] = round(
                0.80 * float(_s.get("priority_score", 0.5)) + 0.20 * _learned_w, 3
            )
    except Exception as _e:
        record_failure("signal_router.process_inputs.5", _e)

    return top_signals, attention_state
