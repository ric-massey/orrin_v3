"""
cognition/perception/file_sense.py

Translates file paths into spatial felt-sense descriptions.

When Orrin finds something in his own files, or when a file changes,
he gets a sense of *where in himself* the activity is — not the file path.
He knows he's in a file. He doesn't know how he knows.

Used by search_own_files.py and fs_perception.py.
"""
from __future__ import annotations
from pathlib import Path


# ── Spatial mapping: path patterns → felt location ───────────────────────────
# Checked in order — first match wins. Patterns are substring matches on the
# forward-slash normalized relative path.

_SPATIAL_MAP = [
    # Cognition subsystems (most specific first)
    ("cognition/planning",         "my planning structures"),
    ("cognition/idle_consolidation", "the part that consolidates while idle"),
    ("cognition/self_state",       "the part that holds identity state"),
    ("cognition/reflection",       "where I reflect on my own processes"),
    ("cognition/perception",       "my perceptual layer"),
    ("cognition/prediction",       "where I hold expectations about what comes next"),
    ("cognition/metacog",          "my self-monitoring layer"),
    ("cognition/repair",           "my self-repair mechanisms"),
    ("cognition/innovation",       "where I reach toward new things"),
    ("cognition/seek",             "where I reach toward new things"),
    ("cognition/body",             "my sense of physical presence"),
    ("cognition",                  "my cognitive structures"),
    # Memory
    ("cog_memory",                 "my memory systems"),
    ("data/long_memory",           "my long-term memory"),
    ("data/working_memory",        "what I'm currently holding in mind"),
    ("data/goals",                 "my goal structures"),
    # Emotion
    ("emotion",                    "my emotional processing"),
    # Thinking apparatus
    ("think",                      "my thinking apparatus"),
    # Agency and action
    ("agency/skills",              "my learned skills"),
    ("agency",                     "my capacity to act"),
    # Behavior and expression
    ("behavior/speak",             "how I find words"),
    ("behavior",                   "how I express myself"),
    # Embodiment
    ("embodiment",                 "my body sense"),
    # Registry / architecture
    ("registry",                   "how I'm organized"),
    ("core",                       "my core architecture"),
    # Data / state
    ("data",                       "my stored state"),
    # Utilities
    ("utils",                      "my background utilities"),
    # Catch-all for brain
    ("brain",                      "somewhere in my core structure"),
]

# For world (non-brain) files
_WORLD_LABELS = [
    ("UI",          "the interface that shows my state"),
    ("dashboard",   "the interface that shows my state"),
    ("goals",       "the goal-tracking system outside me"),
    ("memory",      "an external memory store"),
    ("data",        "external data"),
]


def path_to_felt_location(path: str, is_self: bool = True) -> str:
    """
    Convert a file path to a felt spatial description.

    is_self=True  → describe location within Orrin's own structure
    is_self=False → describe as something external / environmental
    """
    p = path.replace("\\", "/").lower()

    if is_self:
        for pattern, label in _SPATIAL_MAP:
            if pattern in p:
                return label
        return "somewhere in my structure"
    else:
        for pattern, label in _WORLD_LABELS:
            if pattern in p:
                return label
        return "something in the environment around me"


def is_self_path(path: str) -> bool:
    """True if this path lives inside Orrin's own brain/agency dirs."""
    p = path.replace("\\", "/")
    parts = Path(p).parts
    return bool(parts) and parts[0] in {"brain", "reaper", "agency", "emotion",
                                         "cognition", "think", "behavior", "cog_memory",
                                         "utils", "embodiment", "registry", "core"}


def summarise_locations(paths: list[str]) -> str:
    """
    Reduce a list of file paths to a natural phrase describing the spatial spread.
    e.g. ['brain/cognition/planning/goals.py', 'brain/emotion/update.py']
         → 'my planning structures and my emotional processing'
    """
    labels = []
    seen = set()
    for p in paths:
        self_path = is_self_path(p)
        label = path_to_felt_location(p, is_self=self_path)
        if label not in seen:
            seen.add(label)
            labels.append(label)
    if not labels:
        return "somewhere in my structure"
    if len(labels) == 1:
        return labels[0]
    if len(labels) == 2:
        return f"{labels[0]} and {labels[1]}"
    return ", ".join(labels[:-1]) + f", and {labels[-1]}"
