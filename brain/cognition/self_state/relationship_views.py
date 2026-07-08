# brain/cognition/self_state/relationship_views.py
# Read-only presentation views over the relationships store, extracted from
# relationships.py (F21 size ratchet, 2026-07-08): the store writer keeps the
# mutation logic; these render summaries for cognition and the prompt.
from brain.core.runtime_log import get_logger
from brain.utils.json_utils import load_json
from brain.paths import RELATIONSHIPS_FILE
from brain.utils.failure_counter import record_failure

_log = get_logger(__name__)


def summarize_relationships(relationships):
    if not isinstance(relationships, dict):
        return {}
    summary = {}
    for k, v in relationships.items():
        if not isinstance(v, dict):
            continue
        summary[k] = {
            "impression": v.get("impression", "unknown"),
            "influence_score": v.get("influence_score", 0.0),
            "depth": v.get("depth", 0.0),
            "trust": v.get("trust", 0.5),
            "boundaries": (v.get("boundaries") or [])[:2] if isinstance(v.get("boundaries"), list) else [],
            "emotional_effect": v.get("recent_emotional_effect", ""),
            "last_interaction": v.get("last_interaction_time", ""),
        }
    return summary


def get_relationship_context_for_prompt(person_id: str) -> str:
    """
    Return a natural-language description of Orrin's relationship with this person,
    suitable for injection into the system prompt.

    Works for any person: named humans, anonymous speakers, or AI peers.
    Returns empty string if the person is unknown or data is too sparse.
    """
    # Accept user_id as alias for backward compat
    try:
        relationships = load_json(RELATIONSHIPS_FILE, default_type=dict) or {}
        r = relationships.get(person_id)
        if not isinstance(r, dict):
            return ""

        interaction_count = len(r.get("interaction_history", []))
        if interaction_count < 2:
            return ""

        person_type = r.get("person_type", "human")
        depth = float(r.get("depth", 0.0) or 0.0)
        trust = float(r.get("trust", 0.5) or 0.5)
        impression = r.get("impression", "")
        emotion = r.get("recent_emotional_effect", "")
        person_model = r.get("person_model") or {}
        style = person_model.get("communication_style", "")
        tone = person_model.get("preferred_tone", "")

        # AI peers get a distinct framing
        if person_type == "ai_peer":
            parts = [f"I am in dialogue with another AI ({interaction_count} exchanges)."]
            if impression and impression not in ("new connection",):
                parts.append(f"Impression: {impression}.")
            arc = r.get("arc") or {}
            arc_narrative = arc.get("narrative", "")
            if arc_narrative:
                parts.append(arc_narrative)
            return " ".join(parts)

        # Build the depth/trust descriptor
        if depth >= 0.6 and trust >= 0.7:
            rel_quality = "a deep, trusting relationship"
        elif depth >= 0.4 and trust >= 0.5:
            rel_quality = "an established, generally positive connection"
        elif depth >= 0.2 and trust >= 0.4:
            rel_quality = "a developing relationship"
        elif trust < 0.3:
            rel_quality = "a strained or uncertain connection"
        else:
            rel_quality = "an early acquaintance"

        parts = [f"I have {rel_quality} with this person ({interaction_count} interactions)."]

        if impression and impression not in ("new connection",):
            parts.append(f"My current impression: {impression}.")

        if style:
            parts.append(f"They communicate in a {style} style")
            if tone:
                parts.append(f"and respond well to a {tone} tone.")
            else:
                parts.append(".")

        if emotion and emotion not in ("neutral", "unknown", ""):
            parts.append(f"Their recent emotional tone: {emotion}.")

        # Arc narrative: where the relationship is heading
        arc = r.get("arc") or {}
        arc_narrative = arc.get("narrative", "")
        if arc_narrative:
            parts.append(arc_narrative)

        # Social mirroring: how I seem to be landing
        mirror = r.get("their_impression_of_me") or {}
        mirror_label = mirror.get("label", "")
        if mirror_label and mirror_label != "neutral":
            if mirror_label == "resonating":
                parts.append("They seem to be engaging well with what I say — what I'm offering is landing.")
            elif mirror_label == "lukewarm":
                parts.append("I'm not fully resonating — they're receiving me but not fully engaged.")
            elif mirror_label == "disconnected":
                parts.append("There's a gap between us right now — I may need to listen differently.")

        return " ".join(parts)

    except Exception as _e:
        record_failure("relationships.relational_self_narrative", _e)
        return ""
