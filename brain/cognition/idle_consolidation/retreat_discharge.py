# brain/cognition/idle_consolidation/retreat_discharge.py
# Extracted from consolidation_cycle.py (kept under the module-size soft limit).
# The "release valve actually releases" fix (SIGNAL_TO_ACTION_AUDIT §2.3 / R3).
from __future__ import annotations

from typing import Dict

from brain.utils.log import log_activity
from brain.utils.failure_counter import record_failure


def submit_retreat_discharge() -> Dict[str, float]:
    """Discharge the threat/impasse that ELECTED this retreat — the "release valve
    actually releases" fix (SIGNAL_TO_ACTION_AUDIT §2.3 / R3).

    The action arbiter elects the dream/consolidation cycle as a low-cost retreat
    under a threat/impasse spike. Until now the retreat only discharged
    resource_deficit, never the signal that elected it — so the originating signal
    never fell, the audit's "relief test" never passed, and the retreat was
    re-elected every cycle (a valve that releases nothing is indistinguishable from
    freezing). Withdrawing/resting legitimately lowers arousal, so we discharge a
    small, clamped, TTL'd amount of any *elevated* threat_level / impasse_signal.

    Bounded and proportional: a genuinely sustained external threat re-spikes next
    cycle, so this relieves a stuck retreat-loop without masking real danger. No-op
    on a normal idle dream (signals not elevated → nothing submitted). Daemon-safe
    (context=None → thread-safe arbiter inbox), like the resource_deficit rest
    proposal. Returns the per-signal deltas submitted (for tests/telemetry)."""
    submitted: Dict[str, float] = {}
    try:
        from brain.control_signals.arbiter import submit_signal as _submit_affect
        from brain.utils.json_utils import load_json as _lj
        from brain.paths import SIGNAL_STATE_FILE as _ASF
        _core = (_lj(_ASF, default_type=dict) or {}).get("core_signals", {}) or {}
        for _sig in ("threat_level", "impasse_signal"):
            _val = float(_core.get(_sig, 0.0) or 0.0)
            if _val > 0.45:   # elevated enough to have driven the threat-retreat vote
                _discharge = round(-min(0.18, 0.30 * _val), 3)   # proportional, bounded
                _submit_affect(None, _sig, _discharge, source="dream_retreat_discharge", ttl_cycles=2)
                submitted[_sig] = _discharge
                log_activity(f"[dream] retreat discharge {_sig} {_discharge} (was {_val:.2f}) → arbiter")
    except Exception as _e:
        record_failure("idle_consolidation_cycle._submit_retreat_discharge", _e)
    return submitted
