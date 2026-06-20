"""
utils/prefs.py — non-secret user preferences (§10.3 / Part 3), stored as plain JSON
in the per-user data dir (config.json). Secrets never live here — those go to the OS
keychain (utils.secrets). This is the home for toggles like fine-tune consent and
remote viewing: things that are fine to read off disk and survive restarts.

Read at startup and hot-applied where safe; a few (lifespan band) are consumed only at
specific moments. Keep this dependency-light so any module can read a flag.
"""
from __future__ import annotations

import json
import threading
from typing import Any, Dict

from brain.paths import DATA_DIR

_CONFIG = DATA_DIR / "config.json"
_LOCK = threading.Lock()

# Conservative, privacy-first defaults: everything that increases egress is OFF until
# the user turns it on.
DEFAULTS: Dict[str, Any] = {
    "allow_finetune": False,        # §9.4 — uploads conversation traces; opt-in only
    "allow_remote_viewing": False,  # §2.1 — opens a LAN/tunnel port; off ⇒ zero ports
    # Existence model (§10.3) — how Orrin lives on your machine.
    "existence_mode": "sleep",      # "sleep" (closed ⇒ lifespan pauses) | "always"
    "game_mode": False,             # throttle cognition to near-zero CPU (still ages)
    "lifespan_band": [365, 730],    # [min_days, max_days] — the ODDS; span is rolled inside
    # Resource ceilings (§10.3). Disk = how big his MIND may grow (the data dir), a
    # target the forgetting sweeps respect. Memory is advisory with a hard ML floor.
    "disk_ceiling_gb": 5,
    "memory_ceiling_gb": 4,
    # Embodiment (§11) — how much of THIS machine Orrin is allowed to be, as a fraction
    # of detected RAM so it means the same thing across machines. Feeds his metabolism
    # AND his interoceptive "100%". The non-overridable survival floor sits under it in
    # cognition.body_budget; a too-small grant is refused, not silently birthed.
    "body_budget_fraction": 0.50,
    # Pluggable LLM provider (Part 11). "openai" preserves today's behavior for existing
    # users; "none" is symbolic-only. The model/base_url are the user's per-provider
    # choices from Settings. Keys live in the keychain (utils.secrets), never here.
    "llm_provider": "openai",
    "llm_model": "",
    "llm_base_url": "",
    # Auto-update (§10.7 / I7) — opt-in so nothing phones home for a new release silently.
    "auto_update_check": False,
}


def all_prefs() -> Dict[str, Any]:
    """Defaults merged with whatever is on disk (disk wins for known keys)."""
    out = dict(DEFAULTS)
    try:
        data = json.loads(_CONFIG.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            out.update(data)
    except Exception:
        pass
    return out


def get(key: str, default: Any = None) -> Any:
    return all_prefs().get(key, DEFAULTS.get(key, default))


def set(key: str, value: Any) -> Dict[str, Any]:  # noqa: A003 (set is the natural verb)
    """Persist one preference, returning the full merged prefs."""
    with _LOCK:
        current = all_prefs()
        current[key] = value
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            _CONFIG.write_text(json.dumps(current, indent=2), encoding="utf-8")
        except Exception:
            pass
        return current
