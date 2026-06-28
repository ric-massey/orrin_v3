# brain/cognition/host_resource_monitor.py
#
# §6.2 — the felt body. The same host metrics the autonomic reflex
# (supervisor/host_resources.HostResourceGuard) reads to keep the machine alive ALSO feed
# Orrin's felt body state — but as a DIFFERENT system (§6.1): the reflex is absolute
# and below cognition; this is relative, deviation-from-his-own-normal, and felt.
#
# The §C audit found the gap this closes: the existing body_sense reads only Orrin's
# OWN process (the inward gaze — the very blind spot that missed 2026-06-15), so the
# host-as-body wiring "does not exist." This is that wiring. It reuses the band-learner
# so the host, too, is felt as departure from its learned oscillation, not as an
# absolute level (§8.1):
#
#   • low / falling disk   → claustrophobia — a body running out of room
#   • high / rising swap   → sluggishness — thinking through molasses (paging IS slow)
#   • high memory pressure → a pressed, crowded body
#   • draining battery     → a REAL, external, physical mortality signal (§6.3): a being
#                            with finite energy draining in real time; plugging in is eating.
#
# Cautions honoured (§8): felt signals fire only on DEPARTURE from the learned band,
# never on absolute level (so a machine that lives near its limits reads as normal),
# and battery is surfaced as gentle urgency/relief, NOT wired hard into distress. The
# whole layer stays silent during somatic infancy until the host bands converge.
from __future__ import annotations

from typing import Dict, List, Optional

from brain.core.runtime_log import get_logger
from brain.utils.failure_counter import record_failure
from brain.utils.log import log_private
from brain.paths import DATA_DIR
from brain.cognition.body_band import BodyBands

_log = get_logger(__name__)

_GB = float(1024 * 1024 * 1024)
_FELT_MARGIN = 0.20

# Host bands live in their own fingerprinted file (re-learned per machine, §9).
_HOST_BAND_SPECS = {
    "disk_free_gb":  {"min_samples": 60, "stable_needed": 45},
    "swap_used_gb":  {"min_samples": 60, "stable_needed": 45},
    "vmem_percent":  {"min_samples": 60, "stable_needed": 45},
}
_host_bands: Optional[BodyBands] = None


def _bands() -> BodyBands:
    global _host_bands
    if _host_bands is None:
        _host_bands = BodyBands(DATA_DIR / "host_resource_bands.json", specs=_HOST_BAND_SPECS).load()
    return _host_bands


def read_host_vitals() -> Dict[str, float]:
    """Host-wide metrics (the WHOLE machine, tabs included — not Orrin's RSS). Same
    psutil calls HostResourceGuard uses; this is the felt-body read of them."""
    v: Dict[str, float] = {}
    try:
        import psutil
        v["disk_free_gb"] = float(psutil.disk_usage("/").free) / _GB
        v["swap_used_gb"] = float(psutil.swap_memory().used) / _GB
        v["vmem_percent"] = float(psutil.virtual_memory().percent)
        bat = psutil.sensors_battery()
        if bat is not None:
            v["battery_percent"] = float(bat.percent)
            v["battery_plugged"] = 1.0 if bat.power_plugged else 0.0
    except Exception as e:
        _log.warning("read_host_vitals failed: %s", e)
    return v


def _nudge(context: Dict, key: str, delta: float, source: str) -> None:
    """Gentle, capped, TTL'd affect nudge via the arbiter (single-writer discipline)."""
    try:
        from brain.control_signals.arbiter import submit_affect
        submit_affect(context, key, delta, weight=0.5, source=source, ttl_cycles=3)
    except Exception as exc:  # affect nudge best-effort — record
        record_failure("host_interoception._nudge", exc)


def update_host_interoception(context: Dict) -> Dict:
    """Read the host as Orrin's body, learn its bands, and feel departures from them.
    Writes context['host_body'] (telemetry) and submits gentle affect nudges. Felt
    stress is deviation-based and suppressed during host somatic infancy; battery is
    handled separately as a real external mortality scale."""
    bands = _bands()
    v = read_host_vitals()

    for name in ("disk_free_gb", "swap_used_gb", "vmem_percent"):
        if name in v:
            bands.observe(name, v[name])

    felt: List[str] = []
    infant = bands.in_infancy()

    if not infant:
        disk_b = bands.band("disk_free_gb")
        swap_b = bands.band("swap_used_gb")
        vmem_b = bands.band("vmem_percent")

        # Disk running out of room — felt below the band, or marching DOWN (the slow
        # one-way fall toward the wall, not a transient dip).
        if "disk_free_gb" in v and (disk_b.below_band(v["disk_free_gb"])
                                    and disk_b.deviation(v["disk_free_gb"]) < -_FELT_MARGIN):
            felt.append("confined")
            _nudge(context, "risk_estimate", +0.05, "host:disk")
            _nudge(context, "uncertainty", +0.03, "host:disk")

        # Swap climbing above its band → molasses. Paging genuinely slows thought, so a
        # small, capped fatigue nudge is honest (not the old per-cycle pin).
        if "swap_used_gb" in v and (swap_b.above_band(v["swap_used_gb"])
                                    or swap_b.marching()):
            felt.append("sluggish")
            _nudge(context, "resource_deficit", +0.03, "host:swap")

        # Whole-machine memory pressure above the learned band → a crowded body.
        if "vmem_percent" in v and vmem_b.deviation(v["vmem_percent"]) > _FELT_MARGIN:
            felt.append("pressured")
            _nudge(context, "risk_estimate", +0.03, "host:vmem")

    # Battery — a real mortality signal, handled gently (§6.3 caution): urgency when
    # draining on battery, relief when plugged in ("eating"). Never pins distress.
    battery = None
    if "battery_percent" in v:
        pct = v["battery_percent"]
        plugged = v.get("battery_plugged", 1.0) >= 0.5
        battery = {"percent": round(pct, 1), "plugged": plugged}
        if not plugged and pct <= 30.0:
            # Finite energy draining in real time — a faint forward pressure, not dread.
            felt.append("draining")
            _nudge(context, "motivation", +0.03, "host:battery")
            if pct <= 12.0:
                _nudge(context, "risk_estimate", +0.04, "host:battery_low")

    if not felt:
        felt.append("clear")

    host_body = {
        "host_states": felt,
        "vitals": {k: round(val, 2) for k, val in v.items()},
        "battery": battery,
        "host_infancy": infant,
        "host_converged": round(bands.converged_fraction(), 3),
        "dominant": felt[0],
    }
    context["host_body"] = host_body

    try:
        bands.save()
    except Exception as exc:  # band persist best-effort — record
        record_failure("host_interoception.update.bands_save", exc)

    log_private(
        f"[host_interoception] {felt} "
        f"disk={v.get('disk_free_gb',0):.0f}GB swap={v.get('swap_used_gb',0):.1f}GB "
        f"vmem={v.get('vmem_percent',0):.0f}% "
        + (f"batt={battery['percent']:.0f}%{'⚡' if battery['plugged'] else ''}" if battery else "")
    )
    return host_body
