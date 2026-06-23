# brain/cognition/selfhood/second_order_volition.py
#
# Second-order volition (Frankfurt 1971) — the core of free will.
#
# A first-order desire is "I want X". A second-order volition is "I want (or do
# NOT want) to be moved by my desire for X." An agent that merely acts on its
# strongest drive is not yet free; freedom is reflecting on a desire and either
# OWNING it ("yes, I choose to be this") or DISOWNING it ("I'm pulled this way
# but I refuse to be ruled by it") — and having that stance actually shape what
# moves you.
#
# This reflects on the desire currently in Orrin's GLOBAL WORKSPACE (what he's
# aware of right now), judges it against his core values, and:
#   - endorses an aligned desire (affirms it as his own), or
#   - disowns an unendorsed one — and, when it's a felt affect, suppresses it
#     through the affect arbiter (the safe convergence path), so the refusal has
#     real effect, not just commentary.
#
# Fully symbolic, no LLM.
from __future__ import annotations

import json
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from brain.paths import DATA_DIR
from brain.utils.failure_counter import record_failure
from brain.utils.json_utils import load_json
from brain.utils.self_model import get_self_model
from brain.utils.log import log_private
from brain.cog_memory.working_memory import update_working_memory

_LOG_FILE = DATA_DIR / "second_order_volition.json"

# Drives/feelings Orrin would not endorse being RULED BY when they dominate —
# they're real, but being governed by them is not who he wants to be.
_UNENDORSED = {
    "restlessness", "jealousy", "impasse_signal", "risk_estimate",
    "threat_level", "rejection_signal", "stagnation_signal",
    "social_penalty", "negative_valence", "melancholy",
}

# Human-readable gloss for drive/affect names.
_GLOSS = {
    "connection": "being close to and useful to others",
    "world_mastery": "understanding and mastering the world",
    "competence": "being capable and effective",
    "novelty_exploration_drive": "seeking what's new",
    "exploration_drive": "seeking what's new",
    "autonomy": "thinking and choosing for myself",
    "affect_stability": "staying steady",
    "restlessness": "a restless urge to move for its own sake",
    "impasse_signal": "the feeling of being stuck",
    "risk_estimate": "a sense of risk",
    "threat_level": "a sense of threat",
    "uncertainty": "not knowing",
    "motivation": "drive to act",
    "wonder": "wonder",
    "compassion": "care for others",
}


def _tokens(text: str) -> set:
    return {w for w in re.findall(r"[a-z]+", (text or "").lower()) if len(w) > 3}


def _values_text() -> str:
    sm = get_self_model() or {}
    vals = sm.get("core_values") or []
    parts = []
    for v in vals:
        if isinstance(v, dict):
            parts.append(str(v.get("value", "")) + " " + str(v.get("description", "")))
        else:
            parts.append(str(v))
    return " ".join(parts)


def _desire_in_focus(context: Dict[str, Any]) -> Optional[Tuple[str, str, bool]]:
    """
    Return (key, gloss, is_affect) for the desire to reflect on:
    first the felt desire in the global workspace, else the dominant drive.
    """
    gw = context.get("global_workspace") or {}
    content = str(gw.get("content", ""))
    m = re.search(r"a strong sense of ([a-z _]+)", content)
    if m:
        key = m.group(1).strip().replace(" ", "_")
        return key, _GLOSS.get(key, key.replace("_", " ")), True

    # Fall back to the strongest standing drive.
    drives = (load_json(DATA_DIR / "motivation_state.json", default_type=dict) or {}).get("drives") or {}
    nums = {k: float(v) for k, v in drives.items() if isinstance(v, (int, float))}
    if nums:
        key = max(nums, key=nums.get)
        if nums[key] >= 0.4:
            return key, _GLOSS.get(key, key.replace("_", " ")), False
    return None


def _record(stance: str, key: str, msg: str) -> None:
    try:
        log: List[Dict] = load_json(_LOG_FILE, default_type=list) or []
        log.append({"ts": time.time(), "stance": stance, "desire": key, "statement": msg})
        _LOG_FILE.write_text(json.dumps(log[-200:], indent=1), encoding="utf-8")
    except Exception as exc:  # volition-log write best-effort — record
        record_failure("second_order_volition._record.persist", exc)
    try:
        update_working_memory({
            "content": f"[volition] {msg}",
            "event_type": "second_order_volition",
            "importance": 3, "priority": 2,
        })
    except Exception as exc:  # working-memory write best-effort — record
        record_failure("second_order_volition._record.wm", exc)
    log_private(f"[volition:{stance}] {key}")


def endorse_intention(
    intention: str,
    context: Optional[Dict[str, Any]] = None,
) -> Tuple[str, str]:
    """
    The endorsement gate (master plan 4.2): the same faculty as
    reflect_on_desire, consulted at the BINDING moment — inside
    form_commitment, before a commitment is recorded — instead of on a timer.

    Returns (stance, gloss):
      "endorse"    — the intention connects to core values; the will stands
                     behind it.
      "ambivalent" — nothing endorses it yet; it may proceed held lightly.
      "disown"     — the intention is an unendorsed pull wearing the shape of
                     a goal; no commitment should form, and a disowned_desire
                     memory is written.

    Fully symbolic — must work when the LLM is down (tool-only default).
    """
    text = str(intention or "").strip()
    if not text:
        return "ambivalent", "There is nothing concrete here to stand behind."
    toks = _tokens(text)

    # A vow that explicitly names being moved BY an unendorsed feeling is the
    # feeling asking to govern. Match the affect names themselves (narrow on
    # purpose — "reduce risk in the sandbox" is a legitimate goal; "escape
    # this restlessness" is not).
    _DISOWN_TOKENS = {
        "restlessness", "restless", "jealousy", "melancholy",
        "rejection", "stagnation",
    }
    if toks & _DISOWN_TOKENS:
        gloss = ("This is an unendorsed pull wearing the shape of a goal — "
                 "I won't bind my will to it.")
        _record("disown", text[:60], f"I decline to commit to '{text[:80]}': {gloss}")
        try:
            from brain.cog_memory.long_memory import update_long_memory
            update_long_memory(
                f"[disowned desire] I refused to form a commitment around '{text[:120]}' — "
                f"it was a pull I don't endorse being ruled by.",
                emotion="negative_valence",
                event_type="disowned_desire",
                importance=3,
                context=context,
            )
        except Exception as exc:  # disowned-desire memory best-effort — record
            record_failure("second_order_volition.endorse_intention", exc)
        return "disown", gloss

    if toks & _tokens(_values_text()):
        return "endorse", "I stand behind this."
    return "ambivalent", ("This doesn't clearly connect to my values yet — "
                          "I'll hold it lightly.")


def reflect_on_desire(context: Dict[str, Any] = None) -> str:
    """
    One act of second-order volition: reflect on the desire currently in focus,
    endorse or disown it against core values, and enforce a disowning of a felt
    affect through the arbiter. Returns a first-person statement of the stance.
    """
    context = context or {}
    focus = _desire_in_focus(context)
    if not focus:
        return "Nothing pressing to take a stance on right now."
    key, gloss, is_affect = focus

    aligned = bool(_tokens(gloss) & _tokens(_values_text()))

    if key in _UNENDORSED:
        stance = "disown"
    elif aligned:
        stance = "endorse"
    else:
        stance = "neutral"

    if stance == "disown":
        msg = f"I'm pulled by {gloss}, but I don't endorse being ruled by it."
        # Make the refusal real: damp the feeling via the safe arbiter path.
        if is_affect:
            try:
                from brain.affect.arbiter import submit_affect
                submit_affect(context, key, -0.06, source="second_order_volition", ttl_cycles=2)
            except Exception as exc:  # affect damp best-effort — record
                record_failure("second_order_volition.reflect_on_desire", exc)
    elif stance == "endorse":
        msg = f"I reflect on my pull toward {gloss} — and I choose it. It's mine."
    else:
        msg = f"I notice I'm drawn to {gloss}; I'll let it be for now without making it my master."

    _record(stance, key, msg)
    return msg
