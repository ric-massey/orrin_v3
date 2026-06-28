from brain.cognition.idle_consolidation import compose_consolidation  # ✅ use compose_consolidation(self_model, recent)
from brain.control_signals.signal_drift import check_affect_drift
from brain.behavior.behavior_generation import generate_behavior_from_integration
from brain.control_signals.update_signal_state import update_affect_state
from brain.control_signals.reflect_on_signals import reflect_on_affect
from brain.control_signals.apply_signal_feedback import apply_affective_feedback
from brain.control_signals.threat_detector import process_affective_signals
from brain.cog_memory.working_memory import update_working_memory
from brain.control_signals.reward_signals.reward_signals import release_reward_signal
from brain.control_signals.reward_signals.resource_deficit import update_function_usage_fatigue
from brain.utils.json_utils import load_json
from brain.paths import AFFECT_STATE_FILE
import json  # NEW


def idle_consolidation_logic(context):
    """
    Handles dreaming, drift checks, behavior generation (side effects),
    emotion reflection, feedback application, threat_detector pass, and state update.
    Returns: (context, affect_state, threat_detector_response)
    """
    # Robust cycle extraction: supports int or {"count": int}
    raw_cycles = context.get("cycle_count", 0)
    cycles = raw_cycles.get("count", 0) if isinstance(raw_cycles, dict) else int(raw_cycles or 0)

    self_model = context.get("self_model", {}) or {}
    affect_state = context.get("affect_state", {}) or {}
    long_memory = context.get("long_memory", []) or []
    working_memory = context.get("working_memory", []) or []

    # --- Dream every 5 cycles (but not at cycle 0) ---
    if cycles > 0 and (cycles % 5 == 0):
        # Build a small "recent" list (strings) from working memory first, then long memory
        # Prefer recency and keep it short to avoid huge prompts
        wm_recent = [str(m.get("content", "")).strip() for m in working_memory[-10:] if isinstance(m, dict)]
        lm_recent = [str(m.get("content", "")).strip() for m in long_memory[-10:] if isinstance(m, dict)]
        recent = [s for s in (wm_recent + lm_recent) if s][:8]

        dream_text = compose_consolidation(self_model, recent)
        if dream_text:
            update_working_memory({
                "content": "Dream: " + dream_text.strip(),
                "event_type": "dream",
                "importance": 2,
                "priority": 2,
                "referenced": 0,
                "pin": False
            })
            update_function_usage_fatigue(context, "dream")
            release_reward_signal(
                context,
                signal_type="novelty",
                actual_reward=0.4,
                expected_reward=0.3,
                effort=0.3,
                source="dreaming"
            )

    # --- Drift check + behavior integration (now queues proposals instead of ignoring) ---
    try:
        check_affect_drift(context)  # if your impl accepts context
    except TypeError:
        check_affect_drift()         # fallback to no-arg variant

    proposals = generate_behavior_from_integration(context)  # now captured
    if isinstance(proposals, list) and proposals:
        # Clean + de-dup against any existing queued proposals
        existing = context.get("behavior_proposals", [])
        def _key(a: dict):
            if not isinstance(a, dict):
                return None
            return (
                a.get("type"),
                a.get("description"),
                json.dumps(a.get("content", None), sort_keys=True, default=str)
            )
        seen = { _key(a) for a in existing if isinstance(a, dict) }
        new = []
        for a in proposals:
            if not isinstance(a, dict) or not a.get("type"):
                continue
            k = _key(a)
            if k not in seen:
                new.append(a)
                seen.add(k)

        if new:
            # Prepend new ones for recency; keep queue small
            context["behavior_proposals"] = (new + existing)[:12]
            update_working_memory({
                "content": f"🧩 Queued {len(new)} behavior proposal(s) for scoring.",
                "event_type": "behavior_proposals",
                "importance": 1,
                "priority": 1,
            })

    # --- Reflect on emotions (every 10 cycles or low stability) ---
    if (cycles % 10 == 0) or (affect_state.get("affect_stability", 1.0) < 0.6):
        reflect_on_affect(context, self_model, long_memory)

    # --- Apply feedback and process threat_detector ---
    maybe_ctx = apply_affective_feedback(context)
    if isinstance(maybe_ctx, dict):
        context = maybe_ctx

    context, threat_detector_response = process_affective_signals(context)

    # --- Update emotional state and refresh from disk ---
    try:
        update_affect_state(context)  # preferred signature
    except TypeError:
        update_affect_state()         # fallback to no-arg variant

    affect_state = load_json(AFFECT_STATE_FILE, default_type=dict) or {}
    context["affect_state"] = affect_state  # mirror fresh state

    return context, affect_state, threat_detector_response
