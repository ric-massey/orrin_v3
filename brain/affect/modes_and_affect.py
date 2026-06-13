# brain/affect/modes_and_affect.py
from __future__ import annotations
import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional
import json

from utils.json_utils import load_json, save_json
from utils.log import log_activity, log_error
from cog_memory.working_memory import update_working_memory

from paths import MODE_FILE, PRIVATE_THOUGHTS_FILE, AFFECT_STATE_FILE

# Mode arbiter (BEHAVIOR_FIX_PLAN Phase 4): set_current_mode is the ONE mode
# authority — modes_and_affect's automatic adjustment and update_affect_state's
# dominant-emotion shift both propose through here (two controllers were
# fighting one knob, audit §10). Two stabilizers:
#   * dwell time   — a committed mode holds for _MODE_DWELL_S before any switch;
#   * hysteresis   — a switch needs the SAME target proposed on
#                    _MODE_CONFIRMATIONS consecutive proposals, so a signal
#                    flickering across a threshold can't flip the mode.
# One logged transition per actual change (the no-op/early returns log nothing).
_MODE_DWELL_S: float = 300.0          # ≥ 5 minutes between transitions
_MODE_CONFIRMATIONS: int = 2          # consecutive identical proposals to switch
_last_mode_change_ts: float = 0.0
_pending_mode: Optional[str] = None
_pending_count: int = 0

def get_current_mode() -> str:
    try:
        data = load_json(MODE_FILE, default_type=dict)
        if not isinstance(data, dict):
            log_error(f"⚠️ {MODE_FILE} did not contain a dict. Returning 'unknown'.")
            return "unknown"
        return str(data.get("mode", "unknown"))
    except Exception as e:
        log_error(f"⚠️ Failed to load {MODE_FILE}: {e}")
        return "unknown"

def set_current_mode(mode: str, reason: Optional[str] = None) -> None:
    """
    Update Orrin's current operating mode with a reason.
    Logs transition and avoids duplicate mode setting.
    """
    global _last_mode_change_ts, _pending_mode, _pending_count
    try:
        previous = load_json(MODE_FILE, default_type=dict)
        if not isinstance(previous, dict):
            previous = {}
        old_mode = str(previous.get("mode", "unknown"))

        # No-op if unchanged — also clears any half-confirmed switch proposal.
        if old_mode == mode:
            _pending_mode, _pending_count = None, 0
            return

        now = time.time()

        # Dwell: the committed mode holds for a minimum period.
        if (now - _last_mode_change_ts) < _MODE_DWELL_S:
            return

        # Hysteresis: the same target must be proposed on consecutive calls.
        if mode != _pending_mode:
            _pending_mode, _pending_count = mode, 1
            return
        _pending_count += 1
        if _pending_count < _MODE_CONFIRMATIONS:
            return
        _pending_mode, _pending_count = None, 0
        _last_mode_change_ts = now

        if not reason:
            reason = f"Automatic adjustment detected internal condition for mode: {mode}"

        # Persist mode
        save_json(MODE_FILE, {"mode": mode})

        transition = {
            "from": old_mode,
            "to": mode,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "reason": reason,
        }

        # Append a human-readable trace
        with open(PRIVATE_THOUGHTS_FILE, "a", encoding="utf-8") as f:
            f.write(f"\n[Mode Transition]\n{json.dumps(transition, indent=2)}\n")

        # Working-memory ping
        update_working_memory({
            "content": f"🔄 Orrin changed mode: {old_mode} → {mode}\nReason: {reason}",
            "event_type": "mode_change",
            "agent": "orrin",
            "importance": 2,
            "priority": 2,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        log_activity(f"Mode change recorded: {old_mode} → {mode}")
    except Exception as e:
        log_error(f"⚠️ Failed to set mode to '{mode}': {e}")

def recommend_mode_from_affect_state(min_intensity: float = 0.55, skip_neutral: bool = True) -> str:
    state: Dict[str, Any] = load_json(AFFECT_STATE_FILE, default_type=dict)
    core: Dict[str, Any] = state.get("core_signals", {}) if isinstance(state, dict) else {}

    if not isinstance(core, dict) or not core:
        return "adaptive"

    # Ensure we have numeric values
    numeric_core = {
        str(k): float(v) for k, v in core.items()
        if isinstance(v, (int, float))
    }
    if not numeric_core:
        return "adaptive"

    # Get top emotion and intensity
    emotion, intensity = max(numeric_core.items(), key=lambda x: x[1])

    if skip_neutral and emotion == "neutral":
        return "adaptive"
    if float(intensity) < float(min_intensity):
        return "adaptive"

    # NE/activation_level override: high gain_signal forces focused mode regardless of dominant emotion.
    # NE sharpens signal-to-noise; when activation_level is high Orrin should lock onto the task
    # rather than drifting into philosophical or exploratory modes (Sara 2009).
    ne_proxy = float(state.get("_ne_proxy", 0.0) or 0.0)
    if ne_proxy > 0.65 and emotion not in ("impasse_signal", "conflict_signal", "threat_level", "risk_estimate"):
        return "focused"

    # Emotion → Mode mapping
    emotion_mode_map = {
        "positive_valence": "creative",
        "conflict_signal": "critical",
        "negative_valence": "philosophical",
        "threat_level": "cautious",
        "rejection_signal": "analytical",
        "surprise": "exploratory",
        "exploration_drive": "exploratory",
        "wonder": "philosophical",
        "impasse_signal": "critical",
        "melancholy": "philosophical",
        "stagnation_signal": "exploratory",
        "motivation": "focused",
        "expected_gain": "creative",
        "uncertainty": "cautious",
        "social_deficit": "philosophical",
    }

    return emotion_mode_map.get(emotion, "adaptive")

def affect_driven_mode_shift() -> None:
    """
    Automatically adjusts Orrin's operating mode based on emotional state.
    """
    try:
        recommended_mode = recommend_mode_from_affect_state()
        current_mode = get_current_mode()
        if recommended_mode != current_mode:
            set_current_mode(recommended_mode, reason="Emotional state shift detected.")
    except Exception as e:
        log_error(f"⚠️ Failed to shift mode from emotional state: {e}")