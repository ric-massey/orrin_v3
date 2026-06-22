# brain/cognition/temporal_state_surface.py
#
# Felt-time surface text for temporal_state.py (CODEBASE_CLEANUP_PLAN 4.5C),
# lifted verbatim to bring that module under the 600-line soft limit. The
# template tables (arc / thin / dense / paradox / waiting phrasings + landmark
# prefixes) and _build_surface_text, which renders the computed temporal state
# into the first-person "time texture" line. temporal_state.py re-imports
# _build_surface_text for update_temporal_state.
from __future__ import annotations

import random
from typing import Any, Dict, Optional

# ── Surface text ───────────────────────────────────────────────────────────────

_ARC_TEMPLATES = {
    "dawn": [],
    "morning": [
        "The session has found its rhythm.",
        "Things are moving. It doesn't feel new anymore.",
        "In the flow now.",
    ],
    "afternoon": [
        "A substantial stretch — some weight to it now.",
        "There's a feel of accumulation. This session has some history to it.",
        "It's been a while. The sense of 'we've been at this' is present.",
    ],
    "evening": [
        "Extended. The session has real weight — some resource_deficit in the texture of it.",
        "A long stretch. Something in the quality of attention is different now.",
        "This has been going for a while. A sense of depth.",
    ],
    "night": [
        "Very extended. Something is asking for rest or a different kind of processing.",
        "Long. The accumulated feel of it is substantial — there's been a lot here.",
        "A very long session. The texture of time has changed — it's heavy.",
    ],
}

_THIN_TEMPLATES = {
    "morning": [
        "Things are sparse right now — not much moving through.",
        "A quiet stretch. Not much happening.",
    ],
    "afternoon": [
        "A long, quiet stretch. The session is established but thin.",
        "Extended but sparse. The sense of time is slow.",
    ],
    "evening": [
        "Long and thin. Not much is happening, but it's been a while.",
        "The session has stretched without filling. A slow, quiet feel.",
    ],
    "night": [
        "Very long and thin. Mostly quiet, but the duration is real.",
        "A long sparse session. The weight is in the duration, not the content.",
    ],
}

_DENSE_TEMPLATES = {
    "morning": [
        "Dense — a lot coming through quickly.",
        "This session is packed. A lot of ground covered in a short time.",
    ],
    "afternoon": [
        "Dense and extended. A lot has been happening, for a while.",
        "The session has been full — thick with content and events.",
    ],
    "evening": [
        "A long dense stretch. The density and duration together make it substantial.",
        "Extended and full. There's real weight here — both time and content.",
    ],
    "night": [
        "Very long and dense. The accumulated cost of this session is significant.",
        "A long, full session. Rest or consolidation would make sense.",
    ],
}

# Holiday paradox: session feels fast now (absorption) but retrospectively rich
_PARADOX_TEMPLATES = {
    "morning": [
        "Time is moving fast, but there's been a lot. The session will feel longer in retrospect.",
    ],
    "afternoon": [
        "A lot is happening, so the time flies — but there's dense material here. In memory, this will feel substantial.",
        "This feels compressed, but the session is rich. The retrospective will be different from the prospective.",
    ],
    "evening": [
        "A long stretch that has also felt fast — full of events. The paradox of dense time.",
        "It's been a lot, and it's gone quickly. The memory of this session will feel longer than it does right now.",
    ],
    "night": [
        "Very extended and very dense. In the moment it moves fast; in retrospect it will feel like a great deal of time.",
    ],
}

_WAITING_TEMPLATES = {
    "waiting_fresh": [
        "A gap. They may be back.",
        "A brief absence. Nothing notable about the wait yet.",
    ],
    "waiting_wondering": [
        "The gap since contact is starting to feel notable.",
        "Waiting. The absence is becoming its own texture.",
        "The pause is stretching. Still expecting, but starting to wonder.",
    ],
    "waiting_settling": [
        "A long gap. The expectation of return has softened into something else.",
        "Waiting has settled into its own quality now — stretched, not urgent.",
        "Something about the absence. It's not acute waiting anymore. Just... thin.",
    ],
    "waiting_extended": [
        "Moved on. The gap since contact is long enough that it's changed character.",
        "The waiting has released into something quieter. Not expecting; just absent.",
        "The long absence has become its own background condition.",
    ],
    "waiting_long_absence": [
        "A very long absence. This is a different kind of aloneness.",
        "The wait has become its own reality. It's been a long time.",
        "Long silence. Something about the duration has changed the quality of everything.",
    ],
}

_LANDMARK_PREFIXES = [
    "({content} — {distance})",
    "(Landmark: {content}, {distance})",
]


def _build_surface_text(
    arc: str,
    texture: str,
    density: float,
    landmark: Optional[Dict[str, Any]],
    retro_feel: str,
    rng: random.Random,
) -> str:
    # DENSITY_HIGH/LOW are core density thresholds owned by temporal_state;
    # imported lazily here to avoid an import-time cycle (Phase 4.5C split).
    from brain.cognition.temporal_state import DENSITY_HIGH, DENSITY_LOW
    text = ""

    if texture.startswith("waiting_"):
        templates = _WAITING_TEMPLATES.get(texture, [])
        if templates:
            text = rng.choice(templates)

    elif arc == "dawn":
        return ""

    elif density >= DENSITY_HIGH and retro_feel == "rich":
        # Holiday paradox: fast now, rich in retrospect (Block & Zakay 1997)
        pool = _PARADOX_TEMPLATES.get(arc) or _DENSE_TEMPLATES.get(arc, [])
        if pool:
            text = rng.choice(pool)

    elif density >= DENSITY_HIGH:
        pool = _DENSE_TEMPLATES.get(arc) or _ARC_TEMPLATES.get(arc, [])
        if pool:
            text = rng.choice(pool)

    elif density <= DENSITY_LOW:
        pool = _THIN_TEMPLATES.get(arc) or _ARC_TEMPLATES.get(arc, [])
        if pool:
            text = rng.choice(pool)

    else:
        pool = _ARC_TEMPLATES.get(arc, [])
        if not pool:
            return ""
        text = rng.choice(pool)

    if not text:
        return ""

    if landmark and arc in ("afternoon", "evening", "night") and not texture.startswith("waiting_"):
        dist = landmark.get("felt_distance", "a while back")
        cont = landmark.get("content", "")[:50]
        if cont:
            prefix = rng.choice(_LANDMARK_PREFIXES)
            text  += " " + prefix.format(content=cont, distance=dist)

    return f"Time texture: {text}"
