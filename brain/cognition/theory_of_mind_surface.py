# brain/cognition/theory_of_mind_surface.py
#
# Surface-text framing for theory_of_mind.py (CODEBASE_CLEANUP_PLAN 4.5C), lifted
# verbatim to bring that module under the 600-line soft limit. Pure rendering:
# map the inferred affective/cognitive/intention states (+ predicted next move
# and confidence) to the natural-language "mentalizing" summary simulate()
# surfaces. No I/O, no brain deps.
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

_AFFECTIVE_FRAMING = {
    "frustrated":                  "seem frustrated",
    "anxious":                     "seem concerned",
    "emotionally open":            "are being personally open",
    "positive":                    "seem to be in a good place",
    "engaged and aligned":         "seem engaged and tracking",
    "reserved":                    "are giving little away",
    "disagreeing or redirecting":  "are disagreeing — not hostile, but not with this",
    "attentive":                   "seem focused and present",
    "task-focused":                "are in execution mode",
    "curious and seeking":         "seem genuinely curious about something specific",
    "carrying something difficult": "seem to be carrying something",
    "possibly carrying some friction": "may be carrying some friction",
}

_COGNITIVE_FRAMING = {
    "goal-blocked":  "Something is blocking their goal.",
    "goal-directed": "They want execution.",
    "exploring":     "The question is open — building understanding.",
    "seeking":       "They want a specific answer.",
    "revising":      "They're updating their model.",
    "confirming":    "They're checking their model matches.",
    "processing":    "They're working through something.",
    "minimal":       "Minimal cognitive engagement — keep the response light.",
    "attending":     "",
}

_INTENTION_FRAMING = {
    "instructing":          "They want execution — not discussion.",
    "seeking_information":  "They want a clear answer.",
    "seeking_connection":   "They want to be understood, not advised.",
    "redirecting":          "They're pushing back. The direction needs to change.",
    "seeking_validation":   "They want their concern acknowledged.",
    "exploring":            "The question is open. They're thinking alongside Orrin.",
    "validating":           "They're affirming — following the thread.",
    "minimal":              "Hard to read. Keep the response light.",
}

_NEXT_FRAMING = {
    "seeking_validation":   "check whether it was done right",
    "seeking_information":  "follow up with a question",
    "exploring":            "explore further",
    "redirecting":          "push back again if not addressed",
    "minimal":              "stay brief",
    "validating":           "affirm or continue",
}


def _build_surface_text(
    affective_state: str,
    cognitive_state: str,
    intention: str,
    shift: Optional[Tuple[str, str]],
    misaligned: bool,
    belief: Dict[str, Any],
    prediction_miss: bool,
    next_predicted: str,
    conf: float,
    consec_misalign: int,
    resolving_misalignment: bool = False,
    synchrony: float = 0.50,
) -> str:
    parts = []
    affective_text = _AFFECTIVE_FRAMING.get(affective_state, f"seem {affective_state}")
    cognitive_text = _COGNITIVE_FRAMING.get(cognitive_state, "")
    intent_text    = _INTENTION_FRAMING.get(intention, "")

    # Priority 0: misalignment resolved — affirmation after corrections
    if resolving_misalignment:
        parts.append(
            f"They {affective_text} — the misalignment cleared. "
            f"They affirmed after the corrections. {intent_text}"
        )
    # Priority 1: misalignment (most actionable signal in conversation)
    elif misaligned:
        if consec_misalign >= 3:
            parts.append(
                f"Misalignment (persistent): they still don't feel understood — "
                f"this is the {consec_misalign}rd consecutive time. What Orrin is doing isn't landing."
            )
        elif consec_misalign == 2:
            parts.append(
                "Misalignment (repeated): they corrected again. They don't feel "
                "understood. Orrin needs to change approach, not just try again."
            )
        else:
            parts.append(
                f"Misalignment: they {affective_text} — they don't feel understood. "
                f"The last response didn't meet their model. {intent_text}"
            )
    # Priority 2: meaningful shift in mental state
    elif shift:
        direction, desc = shift
        if direction == "improved":
            shifted = desc.split(":")[1].strip() if ":" in desc else desc
            parts.append(f"Shift (positive): they {affective_text} now. {shifted}. {intent_text}")
        elif direction == "worsened":
            parts.append(f"Shift (negative): they {affective_text}. Something worsened. {intent_text}")
        elif direction == "withdrawn":
            parts.append("They've gone quiet. Possible disengagement or processing.")
    # Priority 3: stable state — combine cognitive + affective for richer read
    else:
        cog_line = cognitive_text if cognitive_text and cognitive_text != intent_text else ""
        body = f"They {affective_text}. " + " ".join(filter(None, [cog_line, intent_text]))
        parts.append(body.strip())

    # Synchrony annotation (Feldman): only surface when meaningfully divergent or aligned
    if synchrony >= 0.75 and not misaligned:
        parts.append("(High synchrony — shared register.)")
    elif synchrony <= 0.25:
        parts.append("(Low synchrony — some distance in how we're relating.)")

    # Prediction miss: model was wrong — worth flagging for recalibration
    if prediction_miss and not misaligned:
        parts.append("(Different from what I expected — recalibrating.)")

    # Next prediction
    next_desc = _NEXT_FRAMING.get(next_predicted)
    if next_desc and not misaligned:
        parts.append(f"Likely next: they will {next_desc}.")

    prefix = "Mentalizing (tentative): " if conf < 0.50 else "Mentalizing: "
    return prefix + " ".join(parts)
