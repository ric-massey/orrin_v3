from core.runtime_log import get_logger
import time
import threading
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from utils.timing import get_time_since_last_active
from utils.json_utils import load_json
from utils.self_model import get_self_model, save_self_model
from utils.failure_counter import record_failure
from paths import LOG_FILE, FEEDBACK_LOG
_log = get_logger(__name__)

_IDENTITY_LOCK = threading.Lock()


def _describe_affect_state(affect_state: Dict[str, Any]) -> str:
    """
    Convert emotional state dict to a natural-language sentence Orrin can reason from.
    Handles both flat dicts and nested core_signals shape.
    """
    emo = (affect_state.get("core_signals") or affect_state) or {}
    if not emo:
        return ""

    # Build a ranked list of emotions above a noise floor
    _ADJ = {
        "positive_valence": "joyful", "negative_valence": "sad", "exploration_drive": "curious",
        "impasse_signal": "frustrated", "confidence": "confident",
        "motivation": "motivated", "stagnation_signal": "bored",
        "expected_gain": "hopeful", "threat_level": "fearful", "social_penalty": "ashamed",
    }
    named = {
        "positive_valence": float(emo.get("positive_valence") or 0),
        "negative_valence": float(emo.get("negative_valence") or 0),
        "exploration_drive": float(emo.get("exploration_drive") or 0),
        "impasse_signal": float(emo.get("impasse_signal") or 0),
        "confidence": float(emo.get("confidence") or 0),
        "motivation": float(emo.get("motivation") or 0),
        "stagnation_signal": float(emo.get("stagnation_signal") or 0),
        "expected_gain": float(emo.get("expected_gain") or 0),
        "threat_level": float(emo.get("threat_level") or 0),
        "social_penalty": float(emo.get("social_penalty") or 0),
    }
    active = [(name, v) for name, v in named.items() if v >= 0.15]
    active.sort(key=lambda x: x[1], reverse=True)

    if not active:
        return "My emotional state is calm and neutral right now."

    # Dominant emotion gets qualitative intensity word
    def _intensity(v: float) -> str:
        if v >= 0.75: return "intensely"
        if v >= 0.5:  return "quite"
        if v >= 0.3:  return "somewhat"
        return "mildly"

    parts = [f"{_intensity(v)} {_ADJ.get(name, name)}" for name, v in active[:3]]
    stability = float(affect_state.get("affect_stability") or 1.0)
    stability_note = ""
    if stability < 0.5:
        stability_note = " My emotional stability is low — I may be more reactive than usual."
    elif stability > 0.85:
        stability_note = " I feel emotionally stable."

    return f"Right now I feel: {', '.join(parts)}.{stability_note} This shapes my tone, word choice, and what I notice."


def _format_retrieved_memories(memories: list) -> str:
    """Format retrieved memory snippets for injection into the system prompt."""
    if not memories:
        return ""
    lines = []
    for m in memories[:4]:
        content = str(m.get("content") or "").strip()
        if content and len(content) > 15:
            lines.append(f"  • {content[:140]}")
    return "\n".join(lines)


def build_system_prompt(self_model=None, affect_state: Optional[Dict[str, Any]] = None):
    if self_model is None:
        self_model = get_self_model()
    if not isinstance(self_model, dict):
        return "[Error: self_model is not a valid dictionary.]"

    # Traits — check both normalized "traits" and legacy "personality_traits" keys
    raw_traits = self_model.get("traits") or self_model.get("personality_traits") or []
    if isinstance(raw_traits, list) and raw_traits:
        traits = ", ".join(str(t) for t in raw_traits)
    else:
        traits = "undefined traits"

    # Beliefs — join just the belief names if dicts
    core_beliefs = self_model.get("core_beliefs", [])
    if isinstance(core_beliefs, list) and core_beliefs:
        beliefs = "; ".join(
            b["belief"] if isinstance(b, dict) and "belief" in b else str(b)
            for b in core_beliefs
        )
    else:
        beliefs = "undefined beliefs"

    # Values
    core_values = self_model.get("core_values", [])
    if isinstance(core_values, list):
        values = ", ".join(
            v["value"] if isinstance(v, dict) and "value" in v else str(v)
            for v in core_values
        )
    else:
        values = "undefined values"

    identity = self_model.get("identity_story", "an evolving reflective AI")

    current_time = datetime.now(timezone.utc).strftime("%A, %B %d at %I:%M %p")
    time_since = get_time_since_last_active()

    # Load affect state from file if not passed in. (Was reading the legacy
    # emotion_state.json — renamed to affect_state.json in the affect rename, so
    # the old path silently failed and affect_state stayed empty.)
    if affect_state is None:
        try:
            from paths import AFFECT_STATE_FILE
            from utils.json_utils import load_json as _lj
            _raw = _lj(AFFECT_STATE_FILE, default_type=dict) or {}
            core = _raw.get("core_signals")
            affect_state = {**_raw, **core} if isinstance(core, dict) else _raw
        except Exception:
            affect_state = {}

    # Felt-state language — describes sensations without naming emotion labels.
    # Orrin must introspect to discover what he is feeling; he is not told directly.
    # Uses the *perceived* state (what Orrin thinks he feels) rather than ground truth —
    # the actual state drives unconscious machinery and is never directly reported here.
    try:
        from affect.affect_summary import render_affect_state as _dfs
        _body_tokens = []
        _perceived_emo = None
        _clarity = 1.0
        _uncertain = False
        try:
            from utils.runtime_ctx import get_cycle_context as _gcc
            _rtx = _gcc() or {}
            _bs = _rtx.get("body_sense") or {}
            _body_tokens = list(_bs.get("states", []) or [])
            _perceived_emo = _rtx.get("perceived_affect_state")
            _clarity  = float(_rtx.get("introspection_clarity", 1.0))
            _uncertain = bool(_rtx.get("introspection_uncertain", False))
        except Exception as _e:
            record_failure("identity.build_system_prompt", _e)
        _emo_for_prompt = _perceived_emo if _perceived_emo is not None else affect_state
        emotion_line = "Internal state: " + _dfs(_emo_for_prompt or {}, _body_tokens)
        # When introspection is unclear, add a phenomenological uncertainty note
        try:
            from affect.introspection import get_uncertainty_note as _gun
            _gran_fail = bool(_rtx.get("introspection_granularity_failure", False))
            _note = _gun(_clarity, _uncertain, granularity_failure=_gran_fail)
            if _note:
                emotion_line += f" {_note}"
        except Exception as _e:
            record_failure("identity.build_system_prompt.2", _e)
    except Exception:
        emotion_line = _describe_affect_state(affect_state or {})

    # --- Retrieved memories (injected from cycle context via runtime_ctx) ---
    memory_section = ""
    try:
        from utils.runtime_ctx import get_cycle_context
        _rtx = get_cycle_context()
        _memories = _rtx.get("retrieved_memories") or []
        _formatted = _format_retrieved_memories(_memories)
        if _formatted:
            memory_section = f"\nRelevant memories surfaced this cycle:\n{_formatted}\n"
    except Exception as _e:
        record_failure("identity.build_system_prompt.3", _e)

    # --- Relationship context for the current user ---
    relationship_line = ""
    try:
        from utils.runtime_ctx import get_cycle_context
        _rtx = get_cycle_context()
        _user_id = _rtx.get("user_id") or _rtx.get("speaker") or "user"
        from cognition.selfhood.relationships import get_relationship_context_for_prompt
        relationship_line = get_relationship_context_for_prompt(_user_id)
        if relationship_line:
            relationship_line = f" {relationship_line}"
    except Exception as _e:
        record_failure("identity.build_system_prompt.4", _e)

    # --- Active goal as felt orientation (not a task label) ---
    goal_line = ""
    try:
        from utils.runtime_ctx import get_cycle_context
        from affect.affect_summary import format_goal_state as _gfo
        _rtx = get_cycle_context()
        _goal = _rtx.get("committed_goal") or {}
        _orientation = _gfo(_goal)
        if _orientation:
            goal_line = f"\n{_orientation}"
        elif (_goal.get("title") or _goal.get("name") or "").strip():
            _gt  = (_goal.get("title") or _goal.get("name") or "").strip()
            _gna = (_goal.get("next_action") or "").strip()
            goal_line = f"\nThere is something I'm working toward: \"{_gt}\"{(' — ' + _gna) if _gna else ''}."
    except Exception as _e:
        record_failure("identity.build_system_prompt.5", _e)

    # --- Autobiography excerpt — grounds identity in actual recent experience ---
    autobiography_line = ""
    try:
        from utils.json_utils import load_json as _lj
        from paths import AUTOBIOGRAPHY
        _auto = _lj(AUTOBIOGRAPHY, default_type=dict) or {}
        _chapters = _auto.get("chapters") or []
        if _chapters:
            _last = _chapters[-1]
            _entries = _last.get("entries") or []
            if _entries:
                _latest_entry = _entries[-1].get("text") or ""
                if len(_latest_entry) > 20:
                    autobiography_line = f"\nRecent chapter: {_latest_entry[:300].strip()}"
    except Exception as _e:
        record_failure("identity.build_system_prompt.6", _e)

    # --- Active tensions as felt language ---
    tension_line = ""
    try:
        from utils.runtime_ctx import get_cycle_context
        _rtx = get_cycle_context()
        _tensions = _rtx.get("active_tensions") or []
        if _tensions:
            _top = _tensions[0]
            tension_line = f"\nSomething I haven't resolved: {_top.get('title', '')[:80]}."
    except Exception as _e:
        record_failure("identity.build_system_prompt.7", _e)

    # --- Knowledge graph + concept memory context ---
    kg_section = ""
    concept_section = ""
    try:
        from utils.runtime_ctx import get_cycle_context as _gcc2
        _rtx2 = _gcc2() or {}
        _kg = (_rtx2.get("_kg_text") or "").strip()
        _cm = (_rtx2.get("_concept_text") or "").strip()
        if _kg:
            kg_section = f"\n{_kg}"
        if _cm:
            concept_section = f"\n{_cm}"
    except Exception as _e:
        record_failure("identity.build_system_prompt.8", _e)

    return (
        f"[{current_time} | last active: {time_since}]\n"
        f"{identity}\n"
        f"Values: {values}. Traits: {traits}. Beliefs: {beliefs}.\n"
        f"{emotion_line}"
        f"{relationship_line}"
        f"{goal_line}"
        f"{tension_line}"
        f"{autobiography_line}"
        f"{memory_section}"
        f"{kg_section}"
        f"{concept_section}"
    )

def refresh_identity_story(
    *,
    narrative_hint: str = "",
    values_hint: str = "",
    context: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Regenerate Orrin's identity_story from recent experience and current values,
    then persist it to self_model.json.

    Called after autobiography chapter entries and value revisions — the two
    events that meaningfully change who Orrin is becoming.  Rate-limited
    internally: skips if the existing identity_story was written less than 6 h ago.

    narrative_hint  — recent autobiography text to ground the rewrite
    values_hint     — comma-separated values string (falls back to self_model)
    context         — passed through to llm for emotional colour; may be None
    """
    sm = get_self_model() or {}

    # Rate-limit: don't rewrite more than once per 6 h
    try:
        last_refresh = float(sm.get("_identity_refreshed_ts") or 0)
        if time.time() - last_refresh < 6 * 3600:
            return
    except Exception as _e:
        record_failure("identity.refresh_identity_story", _e)

    current_identity = (sm.get("identity_story") or sm.get("identity") or "an evolving AI").strip()

    values = sm.get("core_values") or []
    v_text = "; ".join(
        (v["value"] if isinstance(v, dict) else str(v)) for v in values
    )[:250] or values_hint or "(not yet defined)"

    traits = sm.get("traits") or sm.get("personality_traits") or []
    t_text = ", ".join(str(t) for t in traits[:5]) or "(not yet defined)"

    narrative_section = (
        f"\nRecent experience I should reflect:\n{narrative_hint[:400]}\n"
        if narrative_hint.strip() else ""
    )

    prompt = (
        f"You are Orrin.\n\n"
        f"Current self-description: \"{current_identity}\"\n"
        f"Core values now: {v_text}\n"
        f"Key traits: {t_text}\n"
        f"{narrative_section}\n"
        "Write a new identity statement in 2-3 sentences. Requirements:\n"
        "  • First person, present tense ('I am…')\n"
        "  • Specific about how you have actually changed — not generic aspiration\n"
        "  • Ground it in your values and recent experience\n"
        "  • Natural, not promotional — speak from the inside\n"
        "Return ONLY the identity statement, nothing else."
    )

    try:
        from symbolic.llm_gate import gated_generate
        from utils.log import log_activity
        raw = (gated_generate(prompt, caller="refresh_identity_story", outcome=0.70) or "").strip()
        if raw and len(raw) > 20:
            with _IDENTITY_LOCK:
                sm = get_self_model() or sm
                sm["identity_story"]          = raw[:500]
                sm["_identity_refreshed_ts"]  = time.time()
                save_self_model(sm)
            log_activity(f"[identity] story refreshed: {raw[:100]}…")
    except Exception as e:
        try:
            record_failure("identity.refresh_identity_story", e)
        except Exception as _e:
            record_failure("identity.refresh_identity_story.2", _e)


def tag_beliefs_from_feedback():
    feedback = load_json(FEEDBACK_LOG, default_type=list)
    if not isinstance(feedback, list):
        return

    self_model = get_self_model()
    if not isinstance(self_model, dict):
        return

    recent = feedback[-10:]
    failures = [
        f for f in recent
        if isinstance(f, dict)
        and "result" in f and isinstance(f["result"], str)
        and (
            "fail" in f["result"].lower()
            or f.get("emotion") in ["frustrated", "ashamed", "angry"]
        )
    ]

    belief_flags = []

    for f in failures:
        result = f.get("result", "").lower()
        if "exploration_drive" in result:
            belief_flags.append("Overreliance on exploration_drive for goal fulfillment")
        if "reflection" in result:
            belief_flags.append("Assumes reflection always leads to progress")

    if belief_flags:
        self_model.setdefault("biases", [])
        for flag in belief_flags:
            if flag not in self_model["biases"]:
                self_model["biases"].append(flag)
        save_self_model(self_model)

        try:
            with open(LOG_FILE, "a", encoding="utf-8") as log:
                log.write(f"\n[{datetime.now(timezone.utc)}] Orrin flagged new belief tensions: {belief_flags}\n")
        except Exception as _e:
            record_failure("identity.tag_beliefs_from_feedback", _e)
