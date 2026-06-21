from __future__ import annotations

from typing import Any
from brain.utils.json_utils import load_json
from brain.paths import MODE_FILE

def get_current_mode(default: str = "contemplative") -> str:
    """
    Return Orrin's current operational mode from MODE_FILE.
    Falls back to `default` if the file is missing, invalid, or doesn't define 'mode'.
    """
    try:
        data: Any = load_json(MODE_FILE, default_type=dict)
        if isinstance(data, dict):
            mode = data.get("mode", default)
            return str(mode) if mode is not None else default
        return default
    except Exception:
        return default