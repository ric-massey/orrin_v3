# utils/path_redact.py
# Replace the repo root absolute path in any string with the literal <repo>.
from __future__ import annotations

import re
from pathlib import Path

_PLACEHOLDER = "<repo>"

def _repo_root() -> str:
    # brain/utils/ → brain/ → repo root
    return str(Path(__file__).resolve().parent.parent.parent)

# Build once; also handle backslash variant on Windows
_ROOT: str = _repo_root()
_ROOT_FWD = _ROOT.replace("\\", "/")

_pattern: re.Pattern | None = None

def _get_pattern() -> re.Pattern:
    global _pattern
    if _pattern is None:
        # Escape both forward-slash and backslash variants
        fwd = re.escape(_ROOT_FWD)
        bak = re.escape(_ROOT.replace("/", "\\"))
        _pattern = re.compile(f"({fwd}|{bak})")
    return _pattern


def redact(text: str) -> str:
    """Replace the absolute repo root path with '<repo>' in text."""
    if not text or _PLACEHOLDER in text:
        return text
    return _get_pattern().sub(_PLACEHOLDER, text)
