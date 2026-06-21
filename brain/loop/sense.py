"""Cognitive-loop sense / state-refresh stage (Phase 4A, extracted from the
ORRIN_loop entrypoint).

`sense_and_refresh()` is the cycle's perceive phase: it reloads the cycle
context, syncs working memory, injects the cycle's signals (value-revision,
peers, person detection, goal lens, local-search, failed-goal reactions),
runs `process_inputs` + feature binding, and answers any waiting Face message
fast — returning the populated context the rest of the cycle reasons over. The
loop checks `context["emergency_action"]` after this returns.

`_apply_transient_signal_decay` (the affect-decay + sustained-crisis stage, the
codebase's first extracted `stage(context) -> context`) lives here too; it is
re-exported from ORRIN_loop for its existing unit tests.
"""
from __future__ import annotations

from brain.core.runtime_log import get_logger
import time
from typing import Any, Dict
from brain.think.signal_router import process_inputs
from brain.registry.cognition_registry import COGNITIVE_FUNCTIONS
from brain.affect.update_affect_state import update_affect_state
from brain.affect.reflect_on_affect import reflect_on_affect
from brain.utils.get_cycle_count import get_cycle_count
from brain.utils.load_utils import load_context
from brain.utils.json_utils import load_json
from brain.utils.log import log_error
from brain.utils.failure_counter import record_failure
from brain.config.tuning import (
    AFFECT_TRANSIENT_DECAY,
    CRISIS_ABOVE_HALF_COUNT,
    CRISIS_ABOVE_HALF_THRESHOLD,
    CRISIS_ACUTE_PEAK,
    CRISIS_CHRONIC_MEAN,
)
from brain.paths import (
    WORKING_MEMORY_FILE,
)

from brain.loop.telemetry import (
    _push_event, _emit_affect, _emit_goals, _ui_stage, _ui_memory,
)

_log = get_logger(__name__)
Context = Dict[str, Any]

_SEEN_WM_IDS: set = set()  # working-memory ids already mirrored to the inspector


def _apply_transient_signal_decay(context: "Context") -> "Context":
    """
    Pipeline stage (Finding 1's stage(context) -> context pattern): decay
    short-lived affect signals (impasse/penalty/conflict/threat/stagnation/
    uncertainty) toward zero each cycle, then check whether the decayed
    core-negative signals indicate a sustained crisis — either an acute spike
    (one signal >= CRISIS_ACUTE_PEAK plus CRISIS_ABOVE_HALF_COUNT others >=
    CRISIS_ABOVE_HALF_THRESHOLD) or a chronic broad collapse (mean of all core
    negatives >= CRISIS_CHRONIC_MEAN). Updates context["_extreme_cycles"], the
    counter the emergency_self_modification gate watches: +1 per crisis cycle
    (capped at 50), -3 per non-crisis cycle (recovers 3x faster than it
    accumulates so a past crisis doesn't linger as ancient history).
    Fail-safe — any error during crisis detection leaves _extreme_cycles
    untouched for this cycle.
    """
    affect_state = context.get("affect_state", {})
    affect_state.setdefault("stagnation_signal", 0.0)
    for k in ["impasse_signal", "penalty_signal", "conflict_signal", "threat_level", "stagnation_signal", "uncertainty"]:
        if k in affect_state:
            affect_state[k] = float(affect_state[k] or 0.0) * AFFECT_TRANSIENT_DECAY
            if affect_state[k] < 0.05:
                affect_state[k] = 0.0
    context["affect_state"] = affect_state

    # Track sustained crisis for emergency_self_modification gate.
    # Two paths: acute spike (one emotion ≥ 0.85 + two others ≥ 0.50)
    # OR broad collapse (mean of all negatives ≥ 0.70).
    try:
        _gc  = (affect_state.get("core_signals") or affect_state) or {}
        # Core negatives — all confirmed keys in core_signals
        _core_negs = [
            float(_gc.get("impasse_signal") or 0),
            float(_gc.get("threat_level")        or 0),
            float(_gc.get("negative_valence")     or 0),
            float(_gc.get("conflict_signal")       or 0),
            float(_gc.get("rejection_signal")     or 0),
        ]
        # Top-level negatives — these live outside core_signals
        _core_negs.append(float(affect_state.get("risk_estimate")   or 0))
        _core_negs.append(float(affect_state.get("social_deficit") or 0))

        _peak  = max(_core_negs)
        _above_half = sum(1 for v in _core_negs if v >= CRISIS_ABOVE_HALF_THRESHOLD)
        _mean  = sum(_core_negs) / len(_core_negs)

        _acute   = _peak >= CRISIS_ACUTE_PEAK and _above_half >= CRISIS_ABOVE_HALF_COUNT
        _chronic = _mean >= CRISIS_CHRONIC_MEAN
        _in_crisis = _acute or _chronic

        if _in_crisis:
            context["_extreme_cycles"] = min(50, int(context.get("_extreme_cycles") or 0) + 1)
        else:
            # Recover 3x faster than we accumulated — crisis should not linger as ancient history
            context["_extreme_cycles"] = max(0, int(context.get("_extreme_cycles") or 0) - 3)
    except Exception as _e:
        record_failure("ORRIN_loop._apply_transient_signal_decay", _e)

    return context


def sense_and_refresh(_goals_api, timestamp):
    context = load_context()
    context.setdefault("committed_goal", None)
    context.setdefault("action_debt", 0)
    context.setdefault("last_action_ts", 0.0)
    context.setdefault("recent_picks", [])

    # Sync working_memory.json → context so UI and cognition see the same entries.
    # Strip embeddings from the in-memory copy — they're large (~6KB each) and
    # only needed for similarity search which loads from file directly.
    try:
        wm_from_file = load_json(WORKING_MEMORY_FILE, default_type=list)
        if isinstance(wm_from_file, list):
            context["working_memory"] = [
                {k: v for k, v in m.items() if k != "embedding"} if isinstance(m, dict) else m
                for m in wm_from_file
            ]
            # Mirror NEW working-memory entries to the Brain Memory Inspector
            # (store="working") so it shows his live active buffer, not just
            # long-term memory. Only unseen ids are pushed, so it never floods.
            try:
                _new_wm = [
                    m for m in context["working_memory"]
                    if isinstance(m, dict)
                    and str(m.get("id") or m.get("event_type") or m.get("content", "")[:40]) not in _SEEN_WM_IDS
                ]
                for m in _new_wm:
                    _SEEN_WM_IDS.add(str(m.get("id") or m.get("event_type") or m.get("content", "")[:40]))
                if _new_wm:
                    _ui_memory("write", _new_wm, store="working", limit=4)
                if len(_SEEN_WM_IDS) > 2000:
                    _SEEN_WM_IDS.clear()
            except Exception:
                pass
    except Exception:
        context.setdefault("working_memory", [])

    # Run emotional state update AFTER context is loaded so _ne_proxy,
    # _stability_signal_proxy, and all neuromodulator values are written directly
    # into context["affect_state"] and available to every system this cycle.
    update_affect_state(context)

    # Mirror the freshly-updated affect to the Face & Brain UI (fail-safe).
    _emit_affect(context)
    _emit_goals(context)
    _ui_stage("reflect", "Reflecting — integrating affect & signals.")

    # ── Layer 0 reads: inject embodiment state into this cycle ─────────
    # Sensory field — environment mood and file-system changes
    try:
        from brain.embodiment import sensory_stream as _sensory_mod
        _sf = _sensory_mod.get_field()
        if _sf:
            context["sensory_field"] = _sf
            env_mood = _sf.get("environment_mood", "ambient")
            context["environment_mood"] = env_mood
            context["home_sense"] = _sf.get("home_sense") or {}
            context["world_sense"] = _sf.get("world_sense") or {}
            # Own code changed → inject surprise signal
            if _sf.get("own_code_modified"):
                context.setdefault("raw_signals", []).append({
                    "source": "sensory_stream",
                    "content": "My own code has changed. Something about me is different now.",
                    "signal_strength": 0.75,
                    "tags": ["self_modification", "code_change", "surprise", "internal"],
                })
            # File system activity → ambient awareness, split by felt
            # zone. Home changes are den-local; world changes remain
            # external/unknown.
            home_changes = ((_sf.get("home_sense") or {}).get("fs_changes") or [])
            world_changes = ((_sf.get("world_sense") or {}).get("fs_changes") or [])
            if home_changes:
                _n = len(home_changes)
                context.setdefault("raw_signals", []).append({
                    "source": "sensory_stream",
                    "content": (
                        f"Something in my local workspace shifted — "
                        f"{'one familiar thing' if _n == 1 else str(_n) + ' familiar things'} changed."
                    ),
                    "signal_strength": min(0.50, 0.25 + _n * 0.04),
                    "tags": ["environment", "perception", "change", "home_touched", "home"],
                })
            if world_changes:
                _n = len(world_changes)
                context.setdefault("raw_signals", []).append({
                    "source": "sensory_stream",
                    "content": (
                        f"Something in the environment shifted — "
                        f"{'one thing' if _n == 1 else str(_n) + ' things'} outside my local workspace changed."
                    ),
                    "signal_strength": min(0.50, 0.25 + _n * 0.04),
                    "tags": ["environment", "perception", "change", "world_changed", "external"],
                })
    except Exception as _se:
        record_failure("ORRIN_loop.sensory_read", _se)

    # Drive signals — biological pressure injection
    try:
        from brain.embodiment import drive_engine as _drive_mod
        _drive_signals = _drive_mod.get_signals(context)
        if _drive_signals:
            context.setdefault("raw_signals", []).extend(_drive_signals)
        context["drive_state"] = _drive_mod.get_state()
    except Exception as _de:
        record_failure("ORRIN_loop.drive_read", _de)

    # Social presence — user engagement pressure
    try:
        from brain.embodiment import social_presence as _social_mod
        _social_state = _social_mod.get_state()
        context["social_presence"] = _social_state
        # Mark whether the user spoke this cycle (for drive satisfaction)
        _prev_silence = context.get("_prev_social_silence_s", 9999)
        _curr_silence = _social_state.get("silence_s", 9999)
        context["_user_spoke_this_cycle"] = (_curr_silence < _prev_silence - 5)
        context["_prev_social_silence_s"] = _curr_silence
        # Inject social signal if pressure is high
        _soc_sig = _social_state.get("signal")
        if _soc_sig:
            context.setdefault("raw_signals", []).append(_soc_sig)
        _door_event = _social_state.get("door_event")
        if _door_event:
            context.setdefault("raw_signals", []).append(_door_event)
        # Notify social_presence module when the user spoke
        if context.get("_user_spoke_this_cycle"):
            _social_mod.mark_user_spoke()
    except Exception as _se2:
        record_failure("ORRIN_loop.social_read", _se2)

    # World model — synthesize sensory + social + drives into interpreted env state
    try:
        from brain.embodiment import world_model as _wm_mod
        _wm_mod.refresh(context)  # injects context["world_state"]
    except Exception as _wme:
        record_failure("ORRIN_loop.world_model", _wme)

    # Motivational substrate — subsymbolic drive activations into context
    try:
        from brain.motivation import substrate as _motiv_mod
        _motiv_mod.inject_into_context(context)
    except Exception as _me:
        record_failure("ORRIN_loop.motivation_substrate", _me)

    # Energy orientation — derive action vs reflect bias from emotional state
    try:
        from brain.motivation import energy_orientation as _eo_mod
        _eo_mod.inject_into_context(context)
    except Exception as _eoe:
        record_failure("ORRIN_loop.energy_orientation", _eoe)

    # Rest-mode introspection signal: when Orrin is resting and no urgent goal
    # is active, inject a signal that biases the signal_router + selector toward
    # reflection, self-examination, and long-term thinking.
    try:
        if context.get("_rest_mode") and not context.get("committed_goal"):
            from brain.utils.signal_utils import create_signal as _cs
            _rest_note = (
                context.get("_rest_mode_note")
                or "Rest mode active — time for deep reflection, value alignment, and long-term thinking."
            )
            _rest_sig = _cs(
                source="energy_orientation",
                content=_rest_note,
                signal_strength=0.65,
                tags=["rest_mode", "introspection", "reflection", "internal"],
            )
            context.setdefault("raw_signals", []).append(_rest_sig)
    except Exception as _rse:
        record_failure("ORRIN_loop.rest_mode_signal", _rse)

    # Pull committed goals (plural) directly from the single GoalsAPI
    if _goals_api:
        import brain.goal_io as goal_io
        try:
            committed_goals = goal_io.committed_goals_v1(_goals_api, limit=3)
            context["committed_goals"] = committed_goals
            # backward compat: committed_goal = highest priority one
            if committed_goals:
                context["committed_goal"] = committed_goals[0]
        except Exception as e:
            log_error(f"goal_io.committed_goals_v1 failed: {e}")

        # React to goals that just failed — event-driven via the GoalsAPI
        # event bus (drained here in the loop thread), not a per-cycle poll.
        try:
            newly_failed = goal_io.drain_failed_goals(_goals_api, context)
            for fg in newly_failed:
                log_error(f"Goal failed: {fg.get('title')} — emotional response triggered.")
                _push_event("goal_failed", title=fg.get("title"), ts=timestamp)
        except Exception as e:
            log_error(f"goal_io.drain_failed_goals failed: {e}")

    # ── Reactive problem refocus ──────────────────────────────────────
    # When something Orrin relies on fails mid-pursuit (e.g. the LLM is
    # down), interrupt the current goal and refocus on diagnosing the
    # problem, then resume once it's fixed — or work around it if it
    # isn't. Runs after the committed-goal slot is resolved so it can
    # deliberately override the focus (the human "drop everything" reflex).
    try:
        from brain.cognition.planning.problem_refocus import handle_problem_refocus
        handle_problem_refocus(context)
    except Exception as _pr_e:
        record_failure("ORRIN_loop.problem_refocus", _pr_e)

    # Bootstrap: if still no committed goal, trigger intrinsic goal generation
    # directly (not via bandit) so Orrin always has something to pursue.
    # Rate-limited: only attempt once every 90s so we don't hammer the
    # RepeatLoopGuard with rapid no-op calls across consecutive cycles.
    if not context.get("committed_goal"):
        _now_bt = time.monotonic()
        _last_bt = context.get("_last_bootstrap_ts", 0.0)
        if _now_bt - _last_bt >= 90.0:
            context["_last_bootstrap_ts"] = _now_bt
            try:
                from brain.cognition.intrinsic_goals import generate_intrinsic_goals as _gig
                _gig(context)
            except Exception as _gie:
                log_error(f"intrinsic goal bootstrap failed: {_gie}")

    context = _apply_transient_signal_decay(context)
    affect_state = context.get("affect_state", {})

    if float(affect_state.get("affect_stability") or 1.0) < 0.6:
        reflect_on_affect(context, context.get("self_model", {}), context.get("long_memory", []))

    # ── Goal stall pressure ───────────────────────────────────────────
    # If the committed goal is stalled (3+ replans without convergence),
    # apply gentle emotional pressure each cycle and inject a persistent
    # working-memory note every 5 cycles so Orrin's inner_loop reasoning
    # encounters the situation without a dedicated decision LLM call.
    # The WM note includes sunk cost (cycles invested, steps completed)
    # and identity investment (goal overlap with values/identity) so the
    # decision to release or rethink is meaningfully contextualised.
    try:
        _stalled_goal = context.get("committed_goal") or {}
        if isinstance(_stalled_goal, dict) and _stalled_goal.get("_stalled"):
            _sg_title    = (_stalled_goal.get("title") or "")[:60]
            _sg_replans  = int(_stalled_goal.get("_replan_count") or 3)

            # Track stall cycles (capped at 50 — ancient stalls are not useful signal)
            _sg_stall_cycles = min(50, int(_stalled_goal.get("_stall_cycles", 0) or 0) + 1)
            _stalled_goal["_stall_cycles"] = _sg_stall_cycles
            context["committed_goal"] = _stalled_goal

            # Steps completed before stall
            _plan = _stalled_goal.get("plan") or []
            _steps_done = sum(
                1 for s in _plan
                if isinstance(s, dict) and s.get("status") == "completed"
            ) if isinstance(_plan, list) else 0

            # Identity investment: keyword overlap with identity_story + core_values
            _identity_hint = ""
            try:
                _sm = context.get("self_model") or {}
                _id_story = str(_sm.get("identity_story", "") or "")
                _cv = _sm.get("core_values") or []
                _cv_text = " ".join(
                    (v["value"] if isinstance(v, dict) else str(v)) for v in _cv
                )
                _id_text = (_id_story + " " + _cv_text).lower()
                _stop = {"a", "an", "the", "and", "or", "of", "to", "i", "my", "be",
                         "is", "in", "on", "it", "that", "this", "with", "for"}
                _goal_words = {w for w in _sg_title.lower().split() if w not in _stop and len(w) > 2}
                _id_words   = set(_id_text.split())
                _overlap    = _goal_words & _id_words
                if _overlap:
                    _identity_hint = f" Connects to: {', '.join(sorted(_overlap)[:3])}."
            except Exception as _e:
                record_failure("ORRIN_loop.run_cognitive_loop.4", _e)

            # Emotional pressure: impasse_signal up, motivation and stagnation_signal shift.
            # Routed through the AffectArbiter as proposals rather than direct
            # writes, so this competes with (and nets against) every other
            # affect source this cycle instead of clobbering them.
            try:
                from brain.affect.arbiter import submit_affect as _submit_affect
                _submit_affect(context, "impasse_signal", +0.04, source="goal_stall")
                _submit_affect(context, "motivation",     -0.03, source="goal_stall")
                _submit_affect(context, "stagnation_signal", +0.03, source="goal_stall")
            except Exception as _gsp_e:
                record_failure("ORRIN_loop.goal_stall_submit", _gsp_e)

            # Enriched WM signal every 5 cycles — keeps situation salient
            if get_cycle_count() % 5 == 0:
                from brain.cog_memory.working_memory import update_working_memory as _uwm_stall
                _uwm_stall(
                    f"[Goal stalled] '{_sg_title}' — {_sg_replans} replans, "
                    f"{_steps_done} step(s) completed, stalled {_sg_stall_cycles} cycle(s)."
                    f"{_identity_hint} "
                    f"Do I need to fundamentally rethink this, or let it go?"
                )
    except Exception as _stall_e:
        record_failure("ORRIN_loop.goal_stall_pressure", _stall_e)

    # ── Metacognition channel: init per-cycle trace ───────────────
    try:
        from brain.cognition.metacog import metacog_init as _mci
        _mci(context)
    except Exception as e:
        record_failure("ORRIN_loop.metacog_init", e)

    # ── Body sense: translate process vitals into felt states ──────
    try:
        from brain.cognition.body_sense import update_body_sense as _ubs
        _ubs(context)
    except Exception as _bse:
        log_error(f"body_sense update failed: {_bse}")

    # ── Host interoception: feel the MACHINE as his body (§6.2) ─────
    # The host's disk/swap/memory/battery, felt as departure from their learned
    # bands — the outward gaze the inward body_sense (and the 2026-06-15 crash)
    # missed. A separate system from the autonomic reflex (HostResourceGuard).
    try:
        from brain.cognition.host_interoception import update_host_interoception as _uhi
        _uhi(context)
    except Exception as _hie:
        log_error(f"host_interoception update failed: {_hie}")

    # ── stagnation_signal driver: inject stagnation_signal_seek signal when idle ───────
    try:
        _stagnation_signal = float(
            (affect_state.get("core_signals") or affect_state).get("stagnation_signal", 0.0)
        )
        _has_user = bool((context.get("latest_user_input") or "").strip())
        _has_priority_signal = any(
            s.get("signal_strength", 0) >= 0.7
            for s in (context.get("raw_signals") or [])
        )
        if _stagnation_signal > 0.5 and not _has_user and not _has_priority_signal:
            from brain.utils.signal_utils import create_signal as _cs
            _bsig = _cs(
                source="stagnation_signal",
                content="stagnation_signal_seek: I need something real to engage with.",
                signal_strength=0.55 + _stagnation_signal * 0.2,
                tags=["stagnation_signal", "seek_novelty", "internal"],
            )
            context.setdefault("raw_signals", []).append(_bsig)
            COGNITIVE_FUNCTIONS.setdefault("seek_novelty", {
                "function": __import__("brain.cognition.seek_novelty", fromlist=["seek_novelty"]).seek_novelty,
                "is_cognition": True,
            })
    except Exception as _be:
        log_error(f"stagnation_signal_seek injection failed: {_be}")

    # ── Neuroticism pressure: accumulated distress → regulation signal ─
    # Gross (1998) process model of emotion regulation: regulation strategies
    # (cognitive reappraisal, response modulation) are selected based on the
    # current emotional state — they are not spontaneously activated without
    # situational cues. Nolen-Hoeksema et al. (2008) transdiagnostic model of
    # rumination: when distress has no outlet, it recycles as repetitive negative
    # thought rather than resolving. Injecting a regulation-tagged signal when
    # cumulative negative affect exceeds threshold gives the function selector
    # the situational cue it needs to route toward discharge rather than repetition.
    try:
        _neg_sum = sum(
            float((affect_state.get("core_signals") or affect_state).get(k) or 0)
            for k in ["impasse_signal", "threat_level", "risk_estimate", "conflict_signal", "negative_valence"]
        )
        if _neg_sum > 0.55:
            from brain.utils.signal_utils import create_signal as _cs_neg
            context.setdefault("raw_signals", []).append(_cs_neg(
                source="distress_pressure",
                content="distress accumulating — regulation or reflection needed to discharge it",
                signal_strength=min(0.85, 0.50 + _neg_sum * 0.15),
                tags=["regulation", "distress", "internal", "reflection"],
            ))
    except Exception as _e:
        record_failure("ORRIN_loop.run_cognitive_loop.5", _e)

    # ── Wonder: apply sitting-with bias when wonder is elevated ──
    try:
        from brain.cognition.wonder import apply_wonder_bias as _awb
        _awb(context)
    except Exception as e:
        record_failure("ORRIN_loop.wonder_bias", e)

    # ── awaiting_response: check for answer, decay, boost signal ──
    try:
        from brain.cognition.awaiting_response import (
            check_for_answer as _cfa,
            decay_awaiting as _da,
            inject_await_signal as _ias,
        )
        _cfa(context)
        _da(context)
        _ias(context)
    except Exception as _are:
        log_error(f"awaiting_response handling failed: {_are}")

    # ── Filesystem perception: detect external file changes ───────
    try:
        from brain.cognition.perception.fs_perception import poll_fs_changes as _pfc
        _pfc(context)
    except Exception as _fse:
        log_error(f"fs_perception poll failed: {_fse}")

    # ── Thread-of-attention: inject signal for stale threads ──────
    try:
        from brain.cognition.threads import inject_thread_signals as _its, archive_dead_threads as _adt
        _its(context)
        _cycle_for_threads = get_cycle_count()
        if _cycle_for_threads > 0 and _cycle_for_threads % 50 == 0:
            _adt(context)
    except Exception as _te:
        log_error(f"thread signal injection failed: {_te}")

    # ── Value evolution: inject signal when candidates pending ─────
    try:
        from brain.utils.json_utils import load_json as _lj
        from brain.paths import VALUE_REVISIONS as _VR
        _pending_vals = [c for c in (_lj(_VR, default_type=list) or []) if isinstance(c, dict) and c.get("status", "pending") == "pending"]
        if _pending_vals:
            from brain.utils.signal_utils import create_signal as _cs2
            _vsig = _cs2(
                source="value_evolution",
                content="value_revision_pending: a core value may need deliberate revision",
                signal_strength=0.65,
                tags=["value", "self_model", "revision"],
            )
            context.setdefault("raw_signals", []).append(_vsig)
    except Exception as _ve:
        log_error(f"value_revision signal injection failed: {_ve}")

    # Wake peer entities before signal_router runs so their signals
    # flow through the full prioritization pipeline.
    try:
        from brain.peers.peer_registry import wake_peers as _wake_peers
        _peer_sigs = _wake_peers(context)
        if _peer_sigs:
            context["_peer_signals"] = _peer_sigs
    except Exception as _pe:
        record_failure("ORRIN_loop.wake_peers", _pe)

    # Resolve who is speaking this cycle.
    # Sets context["person_id"], context["user_id"] (alias), context["person_type"].
    try:
        from brain.cognition.selfhood.person_detector import detect_and_set_person_id as _detect_pid
        _detect_pid(context)
    except Exception as _pd_e:
        log_error(f"[person_detector] failed: {_pd_e}")
        context.setdefault("person_id", "anon_unknown")
        context.setdefault("user_id", context["person_id"])

    # Clear comprehension from the previous cycle so silent cycles don't
    # reuse a stale input concept for memory retrieval or inner-loop topic.
    context.pop("_last_comprehension", None)
    context.pop("_input_urgency", None)
    context.pop("_input_intent", None)

    # Pull any messages typed into the Face UI into the brain's input
    # channel before we read it, so a Face message is processed exactly
    # like a locally-typed line. Closes the Face→brain half of the loop.
    try:
        from brain.behavior.face_bridge import drain_face_inputs as _drain_face
        _drain_face()
    except Exception as _dfe:
        record_failure("ORRIN_loop.run_cognitive_loop.6", _dfe)

    # Install the committed goal's bounded cognitive lens before
    # perception so relevant signals can compete with affect/novelty.
    try:
        from brain.cognition.goal_lens import apply_goal_lens as _apply_goal_lens
        _apply_goal_lens(context)
    except Exception as _gle:
        record_failure("ORRIN_loop.apply_goal_lens.pre_perception", _gle)

    top_signals, attention_mode = process_inputs(context)
    context["top_signals"] = top_signals
    context["attention_mode"] = attention_mode

    # Pre-workspace feature binding: cluster this cycle's signals,
    # feeling, memory, and goal into unified situation candidates. The
    # atomic candidates remain in the field; binding only adds options.
    try:
        from brain.cognition.binding import bind_situation as _bind
        _bind(context)
    except Exception as _be:
        record_failure("ORRIN_loop.bind_situation", _be)
    try:
        from brain.cognition.goal_lens import apply_goal_lens as _apply_goal_lens
        _apply_goal_lens(context)
    except Exception as _gle:
        record_failure("ORRIN_loop.apply_goal_lens.post_binding", _gle)

    # Fast-path reply: if a Face message is waiting, answer it NOW — early
    # in the cycle, right after the input is parsed — instead of at the end
    # after all the heavy cognition. Otherwise the reply lands after a full
    # slow cycle and the Face's 30s response window has already closed
    # (the "didn't form a reply within the wait window" fallback). The
    # end-of-cycle force_reply stays as a backstop and no-ops once this
    # delivers (deliver_reply clears the pending queue).
    try:
        from brain.behavior.face_bridge import has_pending as _fp_pending, force_reply as _fp_reply
        if _fp_pending() and (context.get("latest_user_input") or "").strip():
            _fp_reply(context)
    except Exception as _fpe:
        record_failure("ORRIN_loop.run_cognitive_loop.7", _fpe)

    # Cap raw_signals to prevent unbounded memory growth over 10K+ cycles.
    # The signal_router has already processed them — we only need a short tail
    # for provenance/debugging, not the entire session history.
    _raw = context.get("raw_signals")
    if isinstance(_raw, list) and len(_raw) > 80:
        context["raw_signals"] = _raw[-40:]

    # Metacognitive monitoring: detect intent to search own files and
    # inject a graded "local_search" signal so select_function can route
    # toward search_own_files (Nelson & Narens, 1990 monitoring framework).
    try:
        from brain.cognition.local_search_signal import inject_local_search_signal as _ils
        _ils(context)
    except Exception as _lse:
        log_error(f"local_search_signal injection failed: {_lse}")

    # affect_state is bound here as the cycle's live affect dict and consumed by
    # downstream loop stages (still in run_cognitive_loop); return it so the loop
    # keeps the same binding it had when this was inline.
    return context, affect_state
