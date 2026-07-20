# brain/cognition/entropy_monitor.py
#
# C8 (Run 11 §6.1b) — the distribution-entropy monitor, the GENERAL instrument.
#
# Every historical pathology — commitment monopoly (Runs 5–8), the fetch loop
# (Run 6), ignition saturation (Run 10), the memo pump — is the same event on a
# different surface: ENTROPY COLLAPSE of a distribution feeding a gate. The
# stagnation signal already implements the pattern in miniature for action
# picks (update_signal_state.py — Shannon entropy → felt stagnation). This
# module generalizes it: a rolling symbol window per load-bearing distribution,
# normalized Shannon entropy over it, and collapse routed into the felt layer
# as pressure — surface-agnostic, so the NEXT relocation of the monopoly
# pathology is caught without knowing in advance where it lands.
#
# Channels wired at birth (observers at the real chokepoints):
#   commitment_driver — which goal holds the driver slot   (commitment_value)
#   ignition_source   — which trigger wins deliberation    (deliberation_gate)
#   credited_kind     — what kinds of effect earn credit   (effect_ledger)
#   action_pick       — which cognitive function runs      (finalize)
#
# The §10 gate reads snapshot()'s per-channel entropy series at capture.
from __future__ import annotations

import math
import threading
import time
from collections import Counter, deque
from typing import Any, Deque, Dict, List, Optional

from brain.paths import DATA_DIR
from brain.utils.failure_counter import record_failure
from brain.utils.json_utils import load_json, save_json

_FILE = DATA_DIR / "entropy_monitor.json"

_WINDOW = 200          # symbols per channel window
_MIN_SAMPLES = 30      # below this, entropy is undefined (no verdict)
_COLLAPSE_FLOOR = 0.35 # normalized entropy below this = collapse
_PRESSURE_COOLDOWN_S = 600.0   # felt pressure at most once per channel per 10 min
_SNAPSHOT_EVERY = 25   # persist every N observations (cheap, bounded)
_HISTORY_KEEP = 400    # per-channel entropy readings kept for the gate

_lock = threading.Lock()
_windows: Dict[str, Deque[str]] = {}
_last_pressure_ts: Dict[str, float] = {}
_obs_since_save = 0


def observe(channel: str, symbol: Any) -> None:
    """Append one symbol to a channel's rolling window. Cheap; never raises."""
    try:
        ch, sym = str(channel or ""), str(symbol or "")
        if not ch or not sym:
            return
        global _obs_since_save
        with _lock:
            win = _windows.setdefault(ch, deque(maxlen=_WINDOW))
            win.append(sym)
            _obs_since_save += 1
            if _obs_since_save >= _SNAPSHOT_EVERY:
                _obs_since_save = 0
                _persist_locked()
    except Exception as exc:
        record_failure("entropy_monitor.observe", exc)


def entropy(channel: str) -> Optional[float]:
    """Normalized Shannon entropy of the channel's window in [0,1] — 1.0 is
    maximally diverse, 0.0 is a single repeated symbol. None until warm."""
    try:
        with _lock:
            win = _windows.get(str(channel))
            if not win or len(win) < _MIN_SAMPLES:
                return None
            counts = Counter(win)
            n = len(win)
            h = -sum((c / n) * math.log(c / n) for c in counts.values())
            max_h = math.log(max(len(counts), 2))
            return round(min(1.0, h / max_h) if max_h > 0 else 1.0, 4)
    except Exception as exc:
        record_failure("entropy_monitor.entropy", exc)
        return None


def collapsed_channels() -> List[str]:
    """Channels whose distribution has collapsed (warm + entropy < floor)."""
    out: List[str] = []
    for ch in list(_windows.keys()):
        e = entropy(ch)
        if e is not None and e < _COLLAPSE_FLOOR:
            out.append(ch)
    return out


def route_collapse_pressure(context: Dict[str, Any]) -> List[str]:
    """Once per cycle (finalize): route any collapsed channel into the FELT
    layer as stagnation pressure — the same monotony feeling, whatever surface
    collapsed — plus a loud log + telemetry event. Edge-limited per channel by
    a cooldown so the pressure is a push, not a siren. Returns the channels
    that fired this call."""
    fired: List[str] = []
    try:
        now = time.time()
        for ch in collapsed_channels():
            if now - _last_pressure_ts.get(ch, 0.0) < _PRESSURE_COOLDOWN_S:
                continue
            _last_pressure_ts[ch] = now
            fired.append(ch)
            e = entropy(ch)
            try:
                from brain.control_signals.arbiter import submit_signal
                submit_signal(context, "stagnation_signal", +0.15,
                              source=f"entropy_collapse:{ch}", ttl_cycles=6)
            except Exception as _se:
                record_failure("entropy_monitor.pressure", _se)
            try:
                from brain.utils.log import log_activity
                log_activity(f"[entropy] {ch} distribution collapsed "
                             f"(H={e}) — routing felt stagnation pressure")
            except Exception:  # intentional: logging is best-effort
                pass
            try:
                from brain.events import record_event as _rec
                _rec({"type": "entropy_collapse", "channel": ch, "entropy": e})
            except Exception as _re:
                record_failure("entropy_monitor.event", _re)
        if fired:
            with _lock:
                _persist_locked()
    except Exception as exc:
        record_failure("entropy_monitor.route_collapse_pressure", exc)
    return fired


def _persist_locked() -> None:
    """Append current entropies to the on-disk history (gate telemetry)."""
    try:
        d = load_json(_FILE, default_type=dict) or {}
        if not isinstance(d, dict):
            d = {}
        hist = d.setdefault("history", {})
        now = round(time.time(), 1)
        for ch, win in _windows.items():
            if len(win) < _MIN_SAMPLES:
                continue
            counts = Counter(win)
            n = len(win)
            h = -sum((c / n) * math.log(c / n) for c in counts.values())
            max_h = math.log(max(len(counts), 2))
            e = round(min(1.0, h / max_h) if max_h > 0 else 1.0, 4)
            rows = hist.setdefault(ch, [])
            rows.append({"ts": now, "entropy": e, "distinct": len(counts)})
            if len(rows) > _HISTORY_KEEP:
                hist[ch] = rows[-_HISTORY_KEEP:]
        d["updated"] = now
        save_json(_FILE, d)
    except Exception as exc:
        record_failure("entropy_monitor._persist", exc)


def snapshot() -> Dict[str, Any]:
    """Current per-channel entropy + the persisted history (run analysis)."""
    cur = {ch: entropy(ch) for ch in list(_windows.keys())}
    d = load_json(_FILE, default_type=dict) or {}
    return {"current": cur, "history": d.get("history", {})}
