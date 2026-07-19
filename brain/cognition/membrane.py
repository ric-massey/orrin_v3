# brain/cognition/membrane.py
#
# The ANATOMY MEMBRANE (Run 11 §2, M1/M2/M3 — design: 07-19 conversation,
# agent memory project_anatomy_membrane). Third membrane after expression
# (one door) and interoception (two readers). Unifying law: no gauge, no
# blueprint, no transcript — the reasoning layer gets an ESTIMATE of state,
# an INFERENCE of its nature, a RECONSTRUCTION of its past; never the file.
#
#   M1 — blueprints: Orrin's reasoning layer cannot read his own source.
#        Humans reason over behavior, not their connectome. Agency-layer
#        maintenance organs (code_writer, auto_repair, architect,
#        self_extension) may read source AS A TOOL, but source text never
#        enters working memory / workspace / self-model updates.
#   M2 — organs: brain/data state files are body, not environment
#        (runtime_lifetime.json is the true death date; bandit_state.json is
#        his own preference weights). fs_perception's "body_touched" — feel
#        the change, don't read the organ — is the correct pattern and stays.
#   M3 — flight recorder: machine transcripts of his cognition (activity log,
#        thought stream, private log — brain/logs and the brain/data streams)
#        are Ric-only; his past reaches him through the memory system.
#        DIARY EXCEPTION: artifacts he AUTHORED (credited effect bodies,
#        memos, notes) remain readable — humans reread diaries.
#
# This is a WALL, not a request (Law 3): a mechanical path filter at the
# file-read chokepoints (grep_files, toolkit.read_file), fail-closed — an
# unidentified caller is reasoning-layer. M4 (behavioral introspection) lands
# WITH this in search_own_files, so introspective goals stay completable.
from __future__ import annotations

from pathlib import Path
from typing import Iterable, List, Optional, Tuple

from brain.paths import DATA_DIR, LOGS_DIR

# Agency-layer maintenance organs that read source as a tool. Their reads never
# enter the workspace as prose — they feed patching/verification machinery.
ORGAN_CALLERS = frozenset({
    "code_writer", "auto_repair", "architect", "self_extension", "sandbox",
})

# Source-file suffixes = blueprints (M1). Markdown is content, not blueprint.
_BLUEPRINT_SUFFIXES = frozenset({
    ".py", ".pyi", ".ts", ".tsx", ".js", ".jsx", ".sh", ".c", ".h", ".rs",
})

# Diary exception (M3): self-authored artifact stores under brain/data that the
# reasoning layer may reread. effect_artifacts holds the content-addressed
# bodies of HIS credited notes/memos; self-written code stays a blueprint.
_DIARY_DIRS = ("effect_artifacts",)


def caller_is_organ(caller: Optional[str]) -> bool:
    return str(caller or "").strip().lower() in ORGAN_CALLERS


def deny_reason(path: str | Path) -> Optional[str]:
    """Why a reasoning-layer read of `path` is denied, or None if readable.
    Reasons: 'blueprint' (M1), 'organ_state' (M2), 'flight_recorder' (M3)."""
    try:
        p = Path(str(path)).expanduser()
        try:
            rp = p.resolve()
        except OSError:
            rp = p
        if rp.suffix.lower() in _BLUEPRINT_SUFFIXES:
            return "blueprint"
        try:
            rel_logs = rp.is_relative_to(LOGS_DIR.resolve())
        except (OSError, ValueError):
            rel_logs = False
        if rel_logs:
            return "flight_recorder"
        try:
            rel_data = rp.is_relative_to(DATA_DIR.resolve())
        except (OSError, ValueError):
            rel_data = False
        if rel_data:
            rel = rp.resolve().relative_to(DATA_DIR.resolve())
            if rel.parts and rel.parts[0] in _DIARY_DIRS:
                return None                     # diary: his own authored bodies
            return "organ_state"
        return None
    except Exception:  # intentional: membrane fails CLOSED — an unclassifiable path is treated as organ
        return "organ_state"


def read_allowed(path: str | Path, caller: Optional[str] = None) -> bool:
    """True if `caller` may read `path`. Organ callers pass; everyone else is
    reasoning-layer and gets the membrane."""
    if caller_is_organ(caller):
        return True
    return deny_reason(path) is None


def filter_readable(paths: Iterable[str | Path],
                    caller: Optional[str] = None) -> Tuple[List[str], int]:
    """(allowed paths, denied count) for a reasoning-layer read set."""
    if caller_is_organ(caller):
        allowed = [str(p) for p in paths]
        return allowed, 0
    allowed, denied = [], 0
    for p in paths:
        if deny_reason(p) is None:
            allowed.append(str(p))
        else:
            denied += 1
    return allowed, denied
