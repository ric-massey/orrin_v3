# brain/think/prompt_surface.py
#
# Per-cycle prose lines that think() sets on context (ToM, energy mode, felt
# time, default-mode background) and the inner-loop draft prompt carries. Their
# structured fields already steer speech/selection; these lines exist for the
# prompt. tests/brain/test_default_mode.py guards that each written line has a
# reader.
from __future__ import annotations

from typing import Any, Dict

SURFACE_TEXT_KEYS = (
    "_tom_text",
    "_energy_mode_text",
    "_ftime_text",
    "_ambient_surface_text",
    "_rumination_text",
)


def surface_lines(context: Dict[str, Any]) -> str:
    """Non-empty surface lines, one per row, in SURFACE_TEXT_KEYS order."""
    return "".join(
        f"{t}\n" for t in (context.get(k) for k in SURFACE_TEXT_KEYS)
        if isinstance(t, str) and t.strip()
    )
