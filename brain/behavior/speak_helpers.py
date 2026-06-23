# brain/behavior/speak.py helpers
# brain/behavior/speak_helpers.py
#
# Pre-class speech helpers for speak.py (CODEBASE_CLEANUP_PLAN 4.5C), lifted
# verbatim to bring that module under the 600-line soft limit. The standalone
# functions OrrinSpeaker composes: _opinion_hook / _your_world_hook (surface a
# held opinion or a world-model note into a reply), _clean_content (strip
# leading timestamps), filter_memories (drop machine/noise entries), and
# _derive_tone (map affect state to a speak/tone/hesitation decision). speak.py
# re-imports these for the OrrinSpeaker class + external callers (talk_policy).
from __future__ import annotations

import random
import re
from typing import Any, Dict

from brain.utils.log import log_private, log_error
from brain.utils.json_utils import load_json
from brain.paths import RELATIONSHIPS_FILE
from brain.utils.failure_counter import record_failure

_LEADING_TS_RE = re.compile(r'^\[\d{4}-\d{2}-\d{2}T[^\]]+\]\s*')


def _opinion_hook(thought: str, context: dict) -> str:
    """30% chance: prefix thought with a relevant held opinion (confidence > 0.50)."""
    if random.random() > 0.30:
        return ""
    try:
        from brain.cognition.opinions import get_all_opinions
        opinions = get_all_opinions()
        if not opinions:
            return ""
        thought_lower = thought.lower()
        for op in opinions:
            if float(op.get("confidence") or 0) < 0.50:
                continue
            topic = str(op.get("topic") or "").strip()
            if len(topic) < 4:
                continue
            if topic.lower() in thought_lower:
                view = str(op.get("view") or "").strip()
                if view and len(view) > 10:
                    # Master plan 3.4: voicing an opinion raises its stake.
                    try:
                        from brain.cognition.opinions import mark_opinion_used
                        mark_opinion_used(op.get("id"))
                    except ImportError:  # intentional: opinions module optional → skip stake update
                        pass
                    return f"I think {view}"
    except Exception as _e:
        record_failure("speak._opinion_hook", _e)
    return ""


def _your_world_hook(thought: str, context: dict) -> str:
    """25% chance: add a suffix framing thought in terms of what the person cares about."""
    if random.random() > 0.25:
        return ""
    try:
        rels = context.get("relationships") or load_json(
            RELATIONSHIPS_FILE, default_type=dict
        ) or {}
        uid = context.get("user_id", "user")
        your_world = (rels.get(uid) or {}).get("your_world") or {}
        if not your_world:
            return ""

        thought_lower = thought.lower()
        twords = {w for w in thought_lower.split() if len(w) > 4}

        for item in (your_world.get("cares_about") or []):
            item_str = str(item).lower()
            if any(w in item_str for w in twords):
                label = str(item)[:40]
                return f"(thinking of how this connects to {label})"

        for proj in (your_world.get("projects") or []):
            name = str(proj.get("name") if isinstance(proj, dict) else proj)
            if any(w in name.lower() for w in twords):
                return f"(this might touch {name[:40]})"
    except Exception as _e:
        record_failure("speak._your_world_hook", _e)
    return ""



def _clean_content(s: str) -> str:
    return _LEADING_TS_RE.sub("", (s or "")).strip()


def filter_memories(memories, tag="[MemoryFilter]"):
    if not isinstance(memories, list):
        log_error(f"{tag} Expected list, got {type(memories)}: {memories}")
        return []
    filtered = []
    for i, m in enumerate(memories):
        if isinstance(m, dict):
            filtered.append(m)
        else:
            log_private(f"{tag} Non-dict at index {i}: {repr(m)[:120]} (type: {type(m)})")
    return filtered


def _derive_tone(affect_state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Rule-based tone from emotional state. No LLM call — fast, offline, always works.
    Checks both flat and nested core_signals shapes.
    """
    emotions = (affect_state.get("core_signals") or affect_state) or {}
    positive_valence         = float(emotions.get("positive_valence") or 0.0)
    exploration_drive   = float(emotions.get("exploration_drive") or 0.0)
    threat_level        = float(emotions.get("threat_level") or 0.0)
    impasse_signal = float(emotions.get("impasse_signal") or 0.0)
    negative_valence     = float(emotions.get("negative_valence") or 0.0)
    confidence  = float(emotions.get("confidence") or 0.0)

    if threat_level > 0.5 or negative_valence > 0.5:
        return {"speak": True, "tone": "hesitant",   "hesitation": 0.6}
    if impasse_signal > 0.5:
        return {"speak": True, "tone": "direct",     "hesitation": 0.1}
    if positive_valence > 0.6 and confidence > 0.4:
        return {"speak": True, "tone": "excited",    "hesitation": 0.1}
    if exploration_drive > 0.6:
        return {"speak": True, "tone": "inquisitive","hesitation": 0.2}
    if positive_valence > 0.4:
        return {"speak": True, "tone": "warm",       "hesitation": 0.2}
    return     {"speak": True, "tone": "neutral",    "hesitation": 0.3}
