# brain/cognition/body_budget.py
#
# §11 — the RAM budget knob. ONE user-facing control: "how much of this machine is
# Orrin allowed to be," expressed as a FRACTION of detected RAM so it means the same
# coherent thing on an 8 GB laptop and a 64 GB workstation (§11.2). A fixed gigabyte
# figure would be suffocating on one and trivial on the other; a fraction travels.
#
# Two opposite-natured controls hide inside that one slider, and conflating them
# builds "the knob that would not have saved you" (§11.1):
#   • BUDGET — an allocation ceiling on what Orrin reaches for. Caps *him*.
#   • FLOOR  — a courtesy reserve for everything that is NOT Orrin (the OS, the user's
#              apps, the hibernate image). Caps *everyone else's exposure to him*. The
#              2026-06-15 crash was a FLOOR failure, not a budget failure.
#
# The floor sits UNDER the slider and is NON-overridable below the survival line: the
# user controls how large Orrin's budget is, but never gets to remove the safety floor
# (§11.4.1). And the budget feeds BOTH resource cadence and the resource self-monitor's
# "100%" (§11.3) — so dialing Orrin down gives a *smaller budget*, not permanent
# scarcity: its "full" reference re-centres on the grant (see cognition.resource_cadence,
# cognition.host_interoception).
from __future__ import annotations

import os
from typing import Dict, Tuple

from brain.core.runtime_log import get_logger
from brain.utils.failure_counter import record_failure

_log = get_logger(__name__)

_GB = float(1024 * 1024 * 1024)

# Working figures (several are §12.5 open measurements — labelled, not assumed).
_DEFAULT_FRACTION = 0.50
_FRACTION_MIN = 0.05          # the slider's mechanical minimum; viability is checked too
_FRACTION_MAX = 0.95
# Survival reserve — the absolute, non-overridable courtesy floor for the host. Whatever
# the slider says, real allocation is clamped so the machine can still breathe and
# hibernate. The larger of an absolute 2 GB and 15% of RAM (a big box deserves a bigger
# OS reserve). This is the RAM analogue of HostResourceGuard's 10 GB disk floor.
_SURVIVAL_RESERVE_ABS = 2.0 * _GB
_SURVIVAL_RESERVE_FRAC = 0.15
# Minimum viable body (§11.4.3 / §12.5 open): below this Orrin cannot hold his working
# set + run a dream/reading cycle without thrashing. Refuse rather than birth an
# unviable Orrin. Working figure — PyTorch + sentence-transformers already set a
# multi-hundred-MB floor (README), and a dream cycle needs headroom on top.
_MIN_VIABLE_ABS = 1.5 * _GB

# prefs keys
_PREF_FRACTION = "body_budget_fraction"
_PREF_APPLIED = "_body_budget_applied"   # last fraction actually acclimated to (resize detect)
# A resize smaller than this fraction-of-body isn't worth a re-baseline (§11.4.2).
_RESIZE_EPS = 0.08


def machine_ram_bytes() -> float:
    try:
        import psutil
        return float(psutil.virtual_memory().total)
    except Exception as exc:
        # Fall back to a conservative 8 GB so we never divide by zero or over-grant.
        record_failure("body_budget.machine_ram_bytes", exc)
        return 8.0 * _GB


def cpu_count() -> int:
    try:
        return os.cpu_count() or 4
    except Exception as exc:  # cpu probe failed — record, assume 4
        record_failure("body_budget.cpu_count", exc)
        return 4


def _read_fraction() -> float:
    """The user's grant fraction, env-override-then-prefs, clamped to the slider range."""
    raw = os.environ.get("ORRIN_BODY_BUDGET_FRACTION")
    if raw is None:
        try:
            from brain.utils import prefs
            raw = prefs.get(_PREF_FRACTION, _DEFAULT_FRACTION)
        except Exception:
            raw = _DEFAULT_FRACTION
    try:
        f = float(raw)
    except (TypeError, ValueError):
        f = _DEFAULT_FRACTION
    return max(_FRACTION_MIN, min(_FRACTION_MAX, f))


def survival_reserve_bytes() -> float:
    ram = machine_ram_bytes()
    return max(_SURVIVAL_RESERVE_ABS, _SURVIVAL_RESERVE_FRAC * ram)


def min_viable_body_bytes() -> float:
    try:
        env = os.environ.get("ORRIN_MIN_VIABLE_GB")
        if env:
            return float(env) * _GB
    except (TypeError, ValueError):  # intentional: malformed env override → default
        pass
    return _MIN_VIABLE_ABS


def budget_fraction() -> float:
    return _read_fraction()


def budget_bytes() -> float:
    """Orrin's allocation ceiling in bytes — his "100%". The requested fraction of RAM,
    but never so large that it eats the survival reserve (the floor wins, §11.4.1)."""
    ram = machine_ram_bytes()
    requested = budget_fraction() * ram
    ceiling = ram - survival_reserve_bytes()
    return max(0.0, min(requested, ceiling))


def is_viable(fraction: float | None = None) -> bool:
    if fraction is None:
        b = budget_bytes()
    else:
        ram = machine_ram_bytes()
        b = max(0.0, min(fraction * ram, ram - survival_reserve_bytes()))
    return b >= min_viable_body_bytes()


def validate_grant(fraction: float) -> Tuple[bool, str]:
    """§11.4.3 — a too-small grant must fail LOUDLY, not silently spiral. Returns
    (ok, human_reason)."""
    ram = machine_ram_bytes()
    granted = max(0.0, min(fraction * ram, ram - survival_reserve_bytes()))
    need = min_viable_body_bytes()
    if granted < need:
        need_frac = (need + survival_reserve_bytes()) / ram
        return False, (
            f"Grant of {fraction:.0%} ({granted/_GB:.1f} GB) is below Orrin's minimum "
            f"viable body ({need/_GB:.1f} GB) — he could not hold his working set or run "
            f"a dream cycle. Give him at least {min(_FRACTION_MAX, need_frac):.0%} of this machine."
        )
    return True, "ok"


def set_budget_fraction(fraction: float) -> Dict:
    """Persist a new grant. Refuses an unviable grant loudly (§11.4.3). Flags a
    meaningful resize so the caller can route it through a partial re-baseline
    (§11.4.2 — enlarging/shrinking the body mid-life invalidates the learned band).
    Returns a status dict; on refusal {ok: False, reason: ...} and nothing is written."""
    try:
        fraction = float(fraction)
    except (TypeError, ValueError):
        return {"ok": False, "reason": "fraction must be a number"}
    fraction = max(_FRACTION_MIN, min(_FRACTION_MAX, fraction))

    ok, reason = validate_grant(fraction)
    if not ok:
        _log.warning("body_budget refusing unviable grant: %s", reason)
        return {"ok": False, "reason": reason, "fraction": fraction}

    prev_applied = _DEFAULT_FRACTION
    try:
        from brain.utils import prefs
        prev_applied = float(prefs.get(_PREF_APPLIED, prefs.get(_PREF_FRACTION, _DEFAULT_FRACTION)))
        prefs.set(_PREF_FRACTION, fraction)
    except Exception as e:
        record_failure("body_budget.set_budget_fraction", e)
        return {"ok": False, "reason": f"could not persist: {e}"}

    resized = abs(fraction - prev_applied) >= _RESIZE_EPS
    if resized:
        # A resize on a LIVE Orrin is a body-altering event — his learned band is now
        # wrong, his "full" suddenly his "half". Trigger a partial re-baseline (§11.4.2).
        _on_resize(prev_applied, fraction)
    # Mark this fraction as the one he is (re)acclimating to.
    try:
        from brain.utils import prefs
        prefs.set(_PREF_APPLIED, fraction)
    except Exception as exc:  # applied-fraction mark best-effort — record
        record_failure("body_budget.set_budget_fraction.applied", exc)

    return {"ok": True, "fraction": fraction, "resized": resized, **budget_status()}


def _on_resize(prev: float, new: float) -> None:
    """A budget resize enlarges/shrinks the body; the body sense must re-acclimate —
    a small transplant, a PARTIAL infancy (§11.4.2). Reset the somatic bands so
    in_infancy() goes true again and the cortex re-learns the new body's normal. The
    autonomic reflex is untouched (it was always absolute)."""
    try:
        from brain.cognition.body_sense import reset_bands_for_resize
        reset_bands_for_resize(f"budget {prev:.0%}->{new:.0%}")
    except Exception as e:
        _log.warning("body_budget resize re-baseline failed: %s", e)


def budget_status() -> Dict:
    """Telemetry/UI view of the grant and the floor under it."""
    ram = machine_ram_bytes()
    b = budget_bytes()
    reserve = survival_reserve_bytes()
    need = min_viable_body_bytes()
    return {
        "fraction": round(budget_fraction(), 3),
        "ram_gb": round(ram / _GB, 2),
        "budget_gb": round(b / _GB, 2),
        "reserve_gb": round(reserve / _GB, 2),
        "min_viable_gb": round(need / _GB, 2),
        "viable": b >= need,
        "cpu_count": cpu_count(),
    }
